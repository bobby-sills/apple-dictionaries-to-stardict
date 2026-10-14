#!/usr/bin/env python3
"""Reshape the Apple Dictionary's source XML into apple-peeler's format for to_stardict.py.

apple-peeler skips the Apple Dictionary because its data lives in per-language .lproj folders,
but each folder ships the dictionary's source as plain AppleDictionary.xml. That source has no
d:title; the title is the <h1>, and extra lookup terms are <d:index> values. This writes entries
with d:title set, and the extra terms as <span class="alias"> (which to_stardict.py indexes in
the .syn file and removes from the displayed entry).

Usage: prep_apple_dictionary.py [LANG] [OUTPUT.xml]   (default: en, output/Apple Dictionary.xml)
"""
import html
import re
import sys
from pathlib import Path

BASE = Path('/System/Library/AssetsV2/com_apple_MobileAsset_DictionaryServices_dictionaryOSX')
ENTRY_RE = re.compile(r'<d:entry\s+id="([^"]*)"[^>]*>(.*?)</d:entry>', re.S)
INDEX_RE = re.compile(r'<d:index\b[^>]*>.*?</d:index>', re.S)
VALUE_RE = re.compile(r'<d:index_value>(.*?)</d:index_value>', re.S)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else 'en'
    out = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / 'output' / 'Apple Dictionary.xml')
    src = next(BASE.glob(f'*/AssetData/Apple Dictionary.dictionary/Contents/Resources/{lang}.lproj/AppleDictionary.xml'))
    text = src.read_text(encoding='utf-8')

    entries = []
    for entry_id, body in ENTRY_RE.findall(text):
        h1 = H1_RE.search(body)
        title = re.sub(r'<[^>]+>', '', h1.group(1)).strip() if h1 else entry_id
        aliases = []
        for block in INDEX_RE.findall(body):
            aliases += [html.unescape(v).strip() for v in VALUE_RE.findall(block)]
        body = INDEX_RE.sub('', body).strip()
        body += ''.join(f'<span class="alias">{html.escape(a)}</span>' for a in dict.fromkeys(aliases) if a != title)
        entries.append(f'<d:entry id="{entry_id}" d:title="{html.escape(title, quote=True)}">{body}</d:entry>')

    out.write_text('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" '
                   'xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n'
                   + '\n'.join(entries) + '\n</d:dictionary>\n', encoding='utf-8')
    print(f'Wrote {out}: {len(entries)} entries from {src.parent.name}')


if __name__ == '__main__':
    main()
