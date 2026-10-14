# Apple Dictionaries → StarDict

Convert the dictionaries that ship with macOS (Dictionary.app) into
[StarDict](https://stardict-4.sourceforge.net/StarDictFileFormat) format for e-readers such as
[KOReader](https://koreader.rocks/) and [CrossPoint](https://github.com/crosspoint-reader/crosspoint-reader).

This repo contains only the conversion scripts. **No dictionary content is included.** The
dictionaries are licensed to you through macOS by their publishers (Oxford University Press,
Duden, PONS, Larousse and others), so convert your own copies for personal use and don't
redistribute the output.

## What you get

Each dictionary becomes a folder of standard StarDict files:

| File | Contents |
|---|---|
| `NAME.ifo` | Metadata (display name, counts) |
| `NAME.idx` | Sorted headword index |
| `NAME.dict.dz` | Definitions as HTML, dictzip-compressed |
| `NAME.syn` | Alternate forms that lead to a headword (see below) |
| `NAME.css` | Styling for readers that load it (KOReader) |

Tested with 76 of the 78 dictionaries Apple offers for macOS 15. The two untested are TTY
Abbreviations and Cantonese - English. Bilingual dictionaries are split into one dictionary per
direction (e.g. `ES-EN` Spanish → English and `EN-ES` English → Spanish), giving 117 StarDict
dictionaries in total.

What the converter does beyond a straight dump:

- **Readable without CSS.** Senses, examples and sections get real `<div>`, `<b>` and `<i>`
  tags, so entries are laid out properly on readers that ignore CSS (CrossPoint). The `.css`
  file adds spacing for readers that use it.
- **Word forms in `.syn`.** Looking up an inflected or variant form finds the entry:
  *mice → mouse*, *went → go*, *chevaux → cheval*, *généreuse → généreux* (French endings like
  "généreux, *euse*" are expanded to full words).
- **Lookups match how words are printed in books:**
  - Hebrew and Arabic: headwords are written with vowel points that ordinary text omits, so
    unpointed spellings are indexed too. Ambiguous ones point at every match.
  - Japanese: kana readings lead to kanji headwords (はし → 橋, 箸, 端 …).
  - Russian: stress marks are stripped from word forms.
  - PONS German and English→Korean: stress hints on headwords (*Ạnschluss*, *abstráctor*) are
    indexed without them.
- **Working cross-references.** Apple's `x-dictionary:` links become StarDict `bword://` links.

## Requirements

- macOS with the dictionaries you want installed: open **Dictionary**, go to
  **Dictionary → Settings**, and tick them.
- Python 3.11. apple-peeler needs `lxml` 4.x, which has no prebuilt package for newer Pythons
  and is unlikely to compile on them. With Homebrew: `brew install python@3.11`.

## Setup

```sh
git clone https://github.com/bobby-sills/apple-dictionaries-to-stardict.git
cd apple-dictionaries-to-stardict
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Usage

### 1. Extract the dictionaries to XML

[apple-peeler](https://pypi.org/project/apple-peeler/) decompresses each dictionary's
`Body.data` into XML in `output/`:

```sh
# See which dictionaries are available
./venv/bin/apple-peeler --help

# Extract specific ones (repeat -d), or omit -d to extract everything
./venv/bin/apple-peeler -d "New Oxford American Dictionary" -d "French - English" --out output
```

Extracting everything takes about a minute and uses about 9 GB.

The **Apple Dictionary** (Apple product terms) isn't readable by apple-peeler. Prepare it
separately:

```sh
./venv/bin/python prep_apple_dictionary.py
```

### 2. Convert to StarDict

Build every dictionary listed in `build_all.py` (about 40 minutes for all 117):

```sh
./venv/bin/python build_all.py
```

Or only the ones you want, by the folder names listed in `build_all.py`:

```sh
./venv/bin/python build_all.py NOAD FR-EN EN-FR
```

Results go to `stardict/<NAME>/`. `build_all.py` reports an error for any dictionary whose
XML hasn't been extracted.

To convert a single file by hand:

```sh
./venv/bin/python to_stardict.py "output/French - English.xml" stardict FR-EN \
    --bookname "French → English" --ids '^f_'
```

| Option | Purpose |
|---|---|
| `--bookname` | Name shown in the reader |
| `--ids REGEX` | Keep only entries whose id matches, used to split bilingual dictionaries by direction. In Apple's files the letter before `_` is the source language (`e_` = English). |
| `--unmark CHARS` | Combining marks that are only pronunciation hints in headwords; headwords are also indexed without them |

### 3. Check the output (optional)

```sh
./venv/bin/python check_stardict.py              # every dictionary
./venv/bin/python check_stardict.py stardict FR  # just one
```

This verifies file integrity and link resolution, reports layout coverage and suspicious word
forms, and prints a sample entry.

## Installing on a reader

Copy the dictionary folders you want:

- **KOReader:** into `koreader/data/dict/` (on Kobo: `.adds/koreader/data/dict/`). KOReader
  picks up `NAME.css` automatically.
- **CrossPoint (1.6 or later):** into `/dictionaries/` on the SD card, then choose one under
  **Settings → Reader → Dictionary**. Version 1.5 doesn't support HTML definitions or `.syn` files.

## Known limitations

- **Very long entries on CrossPoint.** CrossPoint shows entries it can't lay out in memory as
  plain text. That's about 5% of Duden entries and a few hundred in the large English↔X
  dictionaries. If you get "Not enough memory" errors, decompress the definitions:
  `gzip -dk -S .dz NAME.dict.dz`.
- **Few inflected forms for some languages.** The Finnish, Hungarian, Swedish, Norwegian and
  Slovak → English dictionaries list few inflections, so inflected words from those languages
  often won't be found. Look up the base form instead.
- **Chinese, Japanese and Thai** need a reader that can find word boundaries in text without
  spaces. KOReader can for some of these languages.
- **Right-to-left scripts** (Arabic, Hebrew, Urdu) may not display correctly on every reader.
- **A few stray word forms.** A handful per dictionary, e.g. grammar labels like "irr", are
  indexed as words. Stricter filtering would also drop real short words.

## How it works

- `build_all.py`: the list of dictionaries, with display names, direction splits and unmark
  settings. It runs `to_stardict.py` for each.
- `to_stardict.py`: parses entries, maps Apple's CSS classes to block, bold and italic tags,
  rewrites links, collects word forms, and writes the `.ifo`, `.idx`, `.syn` and `.css` files
  plus a dictzip `.dict.dz` (written directly, so `dictzip` isn't required).
- `prep_apple_dictionary.py`: reshapes the Apple Dictionary's bundled source XML into
  apple-peeler's format.
- `check_stardict.py`: validates the output.

## License

The scripts are under the [MIT License](LICENSE). The license covers this code only, not the
dictionaries it converts, which remain their publishers' copyrighted works.

Credit to [apple-peeler](https://pypi.org/project/apple-peeler/) for the extraction, and to
Joseph Gentle's
[write-up on the Apple dictionary format](https://josephg.com/blog/reverse-engineering-apple-dictionaries).
