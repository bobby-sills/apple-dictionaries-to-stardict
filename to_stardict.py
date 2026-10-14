#!/usr/bin/env python3
"""Convert apple-peeler XML output into a StarDict dictionary (.ifo/.idx/.dict/.syn/.css).

Usage: to_stardict.py INPUT.xml OUTPUT_DIR BASENAME [--bookname NAME] [--ids REGEX]

--ids keeps only entries whose id matches REGEX, e.g. to split a bilingual dictionary
by direction ('^f_' for French->English, '^e_' for English->French in Apple's French - English).

Writes OUTPUT_DIR/BASENAME/BASENAME.{ifo,idx,dict.dz,syn,css}. For a plain .dict, run
`gzip -dk -S .dz BASENAME.dict.dz`. The HTML uses real <b>/<i>/<div>
tags so it reads well on renderers that ignore CSS (e.g. CrossPoint); the .css file adds
spacing and finer styling for readers that load it (e.g. KOReader).
"""
import argparse
import html
import re
import struct
import unicodedata
import zlib
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import lxml.html

ENTRY_RE = re.compile(r'<d:entry\b[^>]*?id="([^"]*)"[^>]*?d:title="([^"]*)"[^>]*>(.*?)</d:entry>', re.S)
# x-dictionary:r:<id>[:<bundle-id>[:<headword>]]  ->  bword://<headword>
LINK_RE = re.compile(r'href="x-dictionary:r:([^:"]*)(?::[^:"]*)?(?::([^"]*))?"')
# x-dictionary:d:<url-encoded word>[:<bundle-id>] looks the word up directly
DLINK_RE = re.compile(r'href="x-dictionary:d:([^:"]*)(?::[^"]*)?"')
BWORD_RE = re.compile(r'href="bword://([^"]*)"')
# Hebrew points/cantillation and Arabic harakat (incl. dagger alif); letters themselves are untouched
KANA_RE = re.compile('[぀-ヿー]+')
READING = 'reading'  # marks a kana-reading form (vs None = plain form, str = French ending base)
POINTS_RE = re.compile('[֑-ׇֽֿׁׂًׅׄ-ٰٟ]')
# Empty Apple marker tags such as <d:def></d:def>, and any leftover d: attributes/namespaces
DTAG_RE = re.compile(r'</?d:[a-z]+[^>]*>')
DATTR_RE = re.compile(r'\s(?:d:[a-z]+|xmlns(?::d)?)="[^"]*"')
# Attributes nothing downstream uses
JUNK_ATTRS = ('id', 'role', 'dialect', 'media', 'soundfile', 'prlexid', 'lexid', 'manifest', 'hm')

# Element classes -> tag. Matched against the element's class list, first hit wins.
# Monolingual (NOAD, French) and bilingual (Oxford-Hachette) dictionaries use different class names.
DROP = {'syl_txt', 't_respell'}  # duplicate headword with dots; US respelling (IPA is kept)
BLOCK = {'hg', 'sg', 'se1', 'se2', 'subEntryBlock', 'subEntry', 'etym',
         'hwg', 'gramb', 'semb', 'exg', 'csec',
         'thesBlock', 'synBlock', 'note', 'pronBlock', 'synList', 'antList'}
# ty_label/t_label mark section labels (sense numbers, PHRASES, ANTONYMS, SYNONYME); the same tg_*
# class without them is just punctuation
BOLD = {'hw', 'sn', 'l', 'f', 'v', 'x_xoLblBlk', 'hv', 'cw', 'bold', 'ty_label', 't_label'}
ITALIC = {'pos', 'ex', 'reg', 'ge', 'sj', 'ps', 'tgr', 'gr', 'ind', 'lev', 'fld', 'italic'}

# Alternate forms that get .syn entries pointing at their headword:
# inflections/feminines (inf), variants (v, hv), derivatives and phrases (l, frm)
SYN_CLASSES = ('inf', 'v', 'l', 'hv', 'frm')
# The French dictionary often gives these as endings only ("généreux, euse")
ENDING_CLASSES = {'t_feminineForm', 't_pluralForm'}

CSS = """\
.hg { margin-bottom: 0.3em; }
.hw { font-size: 1.15em; }
.prx, .pr { font-size: 0.9em; }
.se1 { margin-top: 0.5em; }
.se2 { margin-top: 0.25em; }
.msDict { margin-left: 1.2em; }
.se2 > .msDict.t_first { margin-left: 0; }
.ex { font-size: 0.95em; }
.subEntryBlock, .etym { margin-top: 0.6em; }
.subEntry { margin-left: 1.2em; margin-top: 0.2em; }
.x_xoLblBlk { font-size: 0.85em; letter-spacing: 0.05em; }
.reg, .ge, .sj { font-size: 0.9em; }
.hwg { margin-bottom: 0.3em; }
.gramb { margin-top: 0.5em; }
.semb { margin-top: 0.25em; margin-left: 1.2em; }
.exg { margin-left: 1.2em; }
.csec { margin-top: 0.4em; }
.tgr, .gr, .lev, .fld, .ind { font-size: 0.9em; }
.note, .synBlock { margin-top: 0.4em; font-size: 0.9em; }
.pronBlock { font-size: 0.9em; }
.synList, .antList { margin-left: 1.2em; margin-top: 0.15em; }
"""


def matter_name(entry_id):
    # Front/back matter (e.g. ref_CountriesOfTheWorld) has no headword; name it from the id
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', entry_id.split('_', 1)[-1])


def has_sibling_class(el, cls):
    parent = el.getparent()
    return parent is not None and any(cls in s.get('class', '').split() for s in parent if s is not el)


def text_of(el):
    return re.sub(r'\s+', ' ', el.text_content()).strip()


def link_target(m, titles):
    entry_id, word = m.groups()
    # Links may point at a sub-sense id like m_en_gbus0000850.004; fall back to the entry id
    word = word or titles.get(entry_id) or titles.get(entry_id.split('.')[0]) or matter_name(entry_id)
    return 'href="bword://%s"' % word


def convert(body, titles):
    """Return (html, alternate_forms) for one entry body. titles maps entry id -> headword."""
    body = LINK_RE.sub(lambda m: link_target(m, titles), body)
    body = DLINK_RE.sub(lambda m: 'href="bword://%s"' % html.escape(unquote(m.group(1)), quote=True), body)
    body = DATTR_RE.sub('', DTAG_RE.sub('', body))

    root = lxml.html.fragment_fromstring(body, create_parent='div')
    forms = []
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        for a in JUNK_ATTRS:
            el.attrib.pop(a, None)
        classes = set(el.get('class', '').split())
        # The respelling is only redundant when an IPA pronunciation sits beside it (NOAD);
        # in Italian it is the only pronunciation guide (pe·sa·tù·ra)
        # Traditional Chinese puts a linked Zhuyin reading over each headword character (ruby).
        # The links search by pronunciation, which StarDict can't do, and flattened inline they
        # jumble the headword (女ㄋㄩˇ壻ㄒㄩˋ); the full reading is shown separately anyway.
        if el.tag == 'rt' and el.find('a[@type="bopomofo"]') is not None:
            el.drop_tree()
            continue
        if el.tag == 'a' and el.get('type') == 'bopomofo':
            el.drop_tag()
            continue
        # Extra lookup terms added by prep_apple_dictionary.py: index them, don't display them
        if 'alias' in classes:
            forms.append((text_of(el), None))
            el.drop_tree()
            continue
        if classes & DROP and ('t_respell' not in classes or has_sibling_class(el, 't_IPA')):
            el.drop_tree()
            continue
        # "-en, er": once one form in a group is a hyphenated ending, the rest are endings too
        ending_group = 'inf' in classes and any(
            text_of(s).startswith('-') for s in el.getparent() if 'inf' in s.get('class', '').split())
        # Japanese headwords are kanji (麻疹) with the kana reading (はしか) only in the hw element;
        # books often write the word in kana, so index the reading too
        if 'hw' in classes and KANA_RE.fullmatch(text_of(el).replace(' ', '')):
            forms.append((text_of(el).replace(' ', ''), READING))
        if classes & set(SYN_CLASSES) and not ending_group:
            # Endings attach to the displayed headword, which can differ from the title
            # ("adjectif ou adjectival, ale, aux" is titled "adjectif")
            base = None
            if classes & ENDING_CLASSES:
                header = root.find_class('hg')
                heads = [e for e in header[0].iter() if {'hw', 'v'} & set(e.get('class', '').split())] if header else []
                base = re.sub(r'\s*\d+$', '', text_of(heads[-1])) if heads else ''
            forms.append((text_of(el), base))
        # Only the unnumbered-first sense of a numbered group stays inline, after its number.
        # A bilingual translation group that follows example lines starts its own line too.
        prev = el.getprevious()
        after_block = prev is not None and prev.tag == 'div'
        if (classes & BLOCK or ('msDict' in classes and 't_first' not in classes)
                or (classes & {'trgg', 'trg'} and after_block)):
            el.tag = 'div'
        elif classes & BOLD or {'syn', 't_core'} <= classes:  # thesaurus: the sense's core synonym
            el.tag = 'b'
        elif classes & ITALIC:
            el.tag = 'i'
        # Adjacent labels with no separator ("finances" "informatique") rely on Apple's CSS for
        # spacing; give them a real space so they don't run together
        nxt = el.getnext()
        if (el.tag in ('i', 'b') and not (el.tail or '').strip() and nxt is not None
                and nxt.get('class') == el.get('class') and not el.tail):
            el.tail = ' '

    out = ''.join(lxml.html.tostring(c, encoding='unicode') for c in root)
    # lxml percent-encodes href values (accélérer -> acc%C3%A9l%C3%A9rer); readers look up bword
    # targets literally, so decode them back
    out = BWORD_RE.sub(lambda m: 'href="bword://%s"' % unquote(m.group(1)).replace('"', '&quot;'), out)
    return (root.text or '') + out, forms


def write_dictzip(path, data, chunk_len=58315):
    """Write data as a dictzip file: gzip with independently-inflatable chunks and an
    'RA' header listing their compressed sizes, so readers can seek without decompressing it all."""
    comp = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    blocks = []
    for i in range(0, len(data), chunk_len):
        blocks.append(comp.compress(data[i:i + chunk_len]) + comp.flush(zlib.Z_FULL_FLUSH))
    tail = comp.flush(zlib.Z_FINISH)
    sizes = [len(b) for b in blocks]
    extra = b'RA' + struct.pack('<HHHH', 6 + 2 * len(sizes), 1, chunk_len, len(sizes))
    extra += struct.pack('<%dH' % len(sizes), *sizes)
    with open(path, 'wb') as f:
        # magic, CM=deflate, FLG=FEXTRA, MTIME=0, XFL=2 (max compression), OS=3 (Unix)
        f.write(b'\x1f\x8b\x08\x04' + struct.pack('<I', 0) + b'\x02\x03')
        f.write(struct.pack('<H', len(extra)) + extra)
        f.writelines(blocks)
        f.write(tail)
        f.write(struct.pack('<II', zlib.crc32(data), len(data) & 0xFFFFFFFF))


def sort_key(word):
    # StarDict's ordering: g_ascii_strcasecmp, then strcmp, on UTF-8 bytes
    b = word.encode('utf-8')
    return (b.lower(), b)


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).lower()


def expand_ending(headword, form):
    """Turn a French dictionary ending into full words: généreux + "euse" -> généreuse,
    cheval + "als ou aux" -> chevals, chevaux. The ending replaces the headword from the last
    occurrence (ignoring accents) of its first letter; anything that looks like a full word is kept."""
    out = []
    for f in re.split(r'\s+ou\s+|,\s*', form):
        f = f.strip(' .;:()')
        if not f:
            continue
        i = fold(headword).rfind(fold(f[0]))
        # Full words start like the headword and are about as long (belle/beau, chevaux/cheval);
        # endings can share the start too (anglican + "ane", défendeur + "deresse") but are shorter
        full = fold(f[:2]) == fold(headword[:2]) and len(f) >= len(headword) - 1
        if i <= 0 and ' ' in headword and ' ' not in f and not full:
            # Multi-word headword whose last word changes: self-made man + "woman"
            out.append(headword.rsplit(' ', 1)[0] + ' ' + f)
        elif i <= 0 and not full and len(f) <= 3:
            continue  # an ending that can't be attached ("aux") isn't a word on its own
        elif full or ' ' in f or i <= 0:
            out.append(f)
        else:
            out.append(headword[:i] + f)
    return out


def clean_form(form):
    # Russian dictionaries mark stress with combining accents (обда́м); books don't, so strip them
    form = form.replace('́', '').replace('̀', '').strip(' ,;:.()')
    # Skip fragments like "going on for —", empty labels, bare symbols, and hyphenated endings
    # ("-t, -e" in Danish, "-uvši" in Croatian) whose attachment rules differ per language
    if not form or '—' in form or '/' in form or form.startswith('-') or not any(c.isalpha() for c in form):
        return None
    # Phrase fragments ("ce…") and headword placeholders ("i ~", "a ~") aren't lookup-able words
    if '…' in form or '~' in form or '―' in form:  # ― is the Japanese headword placeholder
        return None
    return form


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', type=Path)
    ap.add_argument('outdir', type=Path)
    ap.add_argument('basename')
    ap.add_argument('--bookname', help='display name (default: input file name)')
    ap.add_argument('--ids', help='only keep entries whose id matches this regex')
    ap.add_argument('--unmark', default='',
                    help='combining marks used only as pronunciation hints in headwords (e.g. stress '
                         'accents); every headword and form is also indexed without them')
    args = ap.parse_args()
    bookname = args.bookname or args.input.stem
    outdir = args.outdir / args.basename
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / args.basename
    keep = re.compile(args.ids) if args.ids else None

    text = args.input.read_text(encoding='utf-8')
    raw = [(entry_id, html.unescape(title).strip() or matter_name(entry_id), body)
           for entry_id, title, body in ENTRY_RE.findall(text)]
    # Built from every entry, so links still resolve when --ids keeps only part of the file
    titles = {entry_id: word for entry_id, word, _ in raw}
    if keep:
        raw = [r for r in raw if keep.search(r[0])]

    entries = []
    for n, (entry_id, word, body) in enumerate(raw, 1):
        body_html, forms = convert(body, titles)
        entries.append((word, body_html, forms))
        if n % 10000 == 0:
            print(f'  converted {n:,} entries...', flush=True)
    print(f'Parsed {len(entries):,} entries')

    entries.sort(key=lambda e: sort_key(e[0]))

    idx = bytearray()
    dict_data = bytearray()
    first_index = {}
    for i, (word, body, _) in enumerate(entries):
        data = body.encode('utf-8')
        idx += word.encode('utf-8') + b'\0' + struct.pack('>II', len(dict_data), len(data))
        dict_data += data
        first_index.setdefault(word, i)
    offset = len(dict_data)
    write_dictzip(f'{base}.dict.dz', bytes(dict_data))
    Path(f'{base}.idx').write_bytes(idx)

    syns = {}
    readings = set()
    for i, (word, _, forms) in enumerate(entries):
        expanded = [f for text, base in forms if base is not READING
                    for f in (expand_ending(base or word, text) if base is not None else [text])]
        for form in filter(None, map(clean_form, expanded)):
            # A form that is already a headword is found directly; first entry wins otherwise
            if form not in first_index and form not in syns:
                syns[form] = first_index[word]
        # Kana readings are shared by many words (はし: 橋, 箸, 端), so each points at every entry
        readings |= {(text, i) for text, base in forms if base is READING and text not in first_index}
    # Hebrew and Arabic dictionaries write vowel points (גְּלוּיָה); books mostly don't (גלויה),
    # so also index every headword and form without them. Unpointed spellings are ambiguous
    # (שלום: שָׁלוֹם peace, שִׁלּוּם payment), so one may point at several entries; StarDict allows
    # repeated .syn words and readers list every match.
    pairs = set(syns.items()) | readings
    for form, i in [(w, i) for i, (w, _, _) in enumerate(entries)] + list(syns.items()):
        bare = POINTS_RE.sub('', form)
        if args.unmark:
            # Stress hints like "abstráctor" (English→Korean) or "Ạnschluss" (PONS German)
            bare = unicodedata.normalize('NFC', ''.join(
                c for c in unicodedata.normalize('NFD', bare) if c not in args.unmark))
        if bare != form and bare not in first_index:
            pairs.add((bare, i))
    syn = bytearray()
    for form, i in sorted(pairs, key=lambda p: (sort_key(p[0]), p[1])):
        syn += form.encode('utf-8') + b'\0' + struct.pack('>I', i)
    Path(f'{base}.syn').write_bytes(syn)

    ifo = (
        "StarDict's dict ifo file\n"
        'version=2.4.2\n'
        f'bookname={bookname}\n'
        f'wordcount={len(entries)}\n'
        f'synwordcount={len(pairs)}\n'
        f'idxfilesize={len(idx)}\n'
        'sametypesequence=h\n'
        f'date={date.today().isoformat()}\n'
        'description=Converted from macOS Dictionary.app via apple-peeler\n'
    )
    Path(f'{base}.ifo').write_text(ifo, encoding='utf-8')
    Path(f'{base}.css').write_text(CSS, encoding='utf-8')
    print(f'Wrote {outdir}/: {len(entries):,} entries, {len(pairs):,} synonyms, '
          f'{offset / 1e6:.1f} MB of definitions')


if __name__ == '__main__':
    main()
