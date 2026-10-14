#!/usr/bin/env python3
"""Sanity-check converted StarDict dictionaries.

Usage: check_stardict.py [STARDICT_DIR] [BASENAME ...]   (default: stardict/, every dictionary)

For each dictionary: verifies the .ifo counts, .idx/.syn sort order and offsets, that no Apple
links are left unconverted, and how many bword:// links resolve; reports how many entries got
line-break and bold/italic structure, oversized entries, and suspicious short .syn forms; and
prints one sample entry as plain text (⏎ = line break, ** = bold, _ = italic).
"""
import gzip
import random
import re
import struct
import sys
from pathlib import Path

import lxml.html


def plain(h):
    h = re.sub(r"<div[^>]*>", "\n", h)
    h = re.sub(r"</?b[^>]*>", "**", h)
    h = re.sub(r"</?i[^>]*>", "_", h)
    t = lxml.html.fromstring("<p>" + h + "</p>").text_content()
    return [re.sub(r"[ \t]+", " ", l).strip() for l in t.splitlines() if l.strip()]


def check(root, n):
    b = root / n / n
    ifo = dict(l.split("=", 1) for l in b.with_suffix('.ifo').read_text().splitlines()[1:])
    D = gzip.open(f"{b}.dict.dz").read()
    idx = Path(f"{b}.idx").read_bytes()
    words, pos, prev = [], 0, None
    while pos < len(idx):
        e = idx.index(b"\0", pos)
        w = idx[pos:e]
        o, s = struct.unpack(">II", idx[e + 1:e + 9])
        pos = e + 9
        k = (w.lower(), w)
        assert prev is None or prev <= k, "idx not sorted"
        prev = k
        words.append((w.decode(), o, s))
    syn = Path(f"{b}.syn").read_bytes()
    syns, pos, prev, nsyn = {}, 0, None, 0
    while pos < len(syn):
        e = syn.index(b"\0", pos)
        w = syn[pos:e]
        (i,) = struct.unpack(">I", syn[e + 1:e + 5])
        pos = e + 5
        k = (w.lower(), w)
        assert prev is None or prev <= k, "syn not sorted"
        assert i < len(words), "syn index out of range"
        syns.setdefault(w.decode(), i)
        nsyn += 1
    assert len(words) == int(ifo["wordcount"]) and nsyn == int(ifo["synwordcount"]), "ifo counts"
    assert len(idx) == int(ifo["idxfilesize"]) and words[-1][1] + words[-1][2] == len(D), "sizes"
    assert b"x-dictionary:" not in D, "unconverted links"

    hw = {w for w, _, _ in words}
    links = [lxml.html.fromstring(f"<p>{l.decode()}</p>").text_content()
             for l in re.findall(rb'href="bword://([^"]*)"', D)]
    bad = [l for l in links if l not in hw]
    sample = random.sample(words, min(2000, len(words)))
    with_div = sum(b"<div" in D[o:o + s] for _, o, s in sample) / len(sample)
    with_bi = sum((b"<b" in D[o:o + s] or b"<i" in D[o:o + s]) for _, o, s in sample) / len(sample)
    short = [(f, words[i][0]) for f, i in syns.items()
             if len(f) <= 3 and f.lower()[:1] != words[i][0].lower()[:1] and f not in hw]
    big = sum(s > 20000 for _, _, s in words)
    print(f"== {n}: {len(words):,} words, {len(syns):,} forms | links {len(links):,} ({len(bad)} unresolved) | "
          f"layout: {with_div:.0%} have line breaks, {with_bi:.0%} bold/italic | {big} entries >20KB | "
          f"short odd forms {len(short)} {short[:6]}")
    w, o, s = random.choice([x for x in sample if 300 < x[2] < 3000] or sample)
    print("   sample [" + w + "]: " + " ⏎ ".join(l[:110] for l in plain(D[o:o + s].decode())[:6]))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / 'stardict')
    names = sys.argv[2:] or sorted(p.name for p in root.iterdir() if p.is_dir())
    random.seed(7)
    for n in names:
        try:
            check(root, n)
        except Exception as ex:
            print(f"== {n}: FAILED {type(ex).__name__}: {ex}")


if __name__ == '__main__':
    main()
