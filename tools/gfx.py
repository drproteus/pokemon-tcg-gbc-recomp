#!/usr/bin/env python3
"""
gfx.py — map, validate, and annotate card artwork for the Pokémon TCG pipeline.

Card art lives in src/gfx/cards/<name>.{png,2bpp,pal}. The disassembly binds
each card to its art through two indirections:

    cards.asm:   gfx <Name>CardGfx                 (a symbol, stored in the card
                                                    record's "gfx" field)
    gfx.asm:     <Name>CardGfx::                   (a label)
                 INCBIN "gfx/cards/<file>.2bpp"    (the actual tile data)

This tool resolves that chain so the pipeline can document and verify which
image each card uses.

Subcommands:
    map       print card -> gfx symbol -> image file (or write CSV)
    annotate  add a "gfx_file" field to each card in a cards.json
    validate  integrity-check the whole card<->art chain
"""

import argparse
import json
import re
import sys
from pathlib import Path

LABEL_RE = re.compile(r"^([A-Za-z_]\w*Gfx)::$")
INCBIN_RE = re.compile(r'^\s*INCBIN\s+"gfx/cards/(\w+)\.2bpp"')


def parse_gfx_asm(gfx_asm_path) -> dict:
    """Return {gfx_symbol: base_filename} parsed from src/gfx.asm."""
    mapping = {}
    current = None
    text = Path(gfx_asm_path).read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        m = LABEL_RE.match(s)
        if m:
            current = m.group(1)
            continue
        m = INCBIN_RE.match(s)
        if m and current is not None:
            mapping[current] = m.group(1)
            current = None
    return mapping


def resolve(cards, gfx_asm_path) -> dict:
    """Return {card_symbol: base_filename} (None for cards with no art)."""
    mapping = parse_gfx_asm(gfx_asm_path)
    return {c["symbol"]: mapping.get(c.get("gfx")) for c in cards}


def _art_paths(base, gfx_dir):
    base = base if base else ""
    return {
        "png": gfx_dir / f"{base}.png",
        "2bpp": gfx_dir / f"{base}.2bpp",
        "pal": gfx_dir / f"{base}.pal",
    }


def cmd_map(args):
    doc = json.loads(Path(args.cards_json).read_text(encoding="utf-8"))
    res = resolve(doc["cards"], args.gfx_asm)
    rows = []
    for c in doc["cards"]:
        base = res.get(c["symbol"])
        rows.append(
            {
                "id": c["id"],
                "card": c["symbol"],
                "gfx_symbol": c.get("gfx"),
                "gfx_file": f"{base}.png" if base else "",
            }
        )
    if args.out:
        import csv
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote mapping -> {args.out}")
    else:
        for r in rows:
            print(f"{r['id']:>3}  {r['card']:<28} {r['gfx_symbol']:<28} {r['gfx_file']}")
    return 0


def cmd_annotate(args):
    path = Path(args.cards_json)
    doc = json.loads(path.read_text(encoding="utf-8"))
    res = resolve(doc["cards"], args.gfx_asm)
    missing = 0
    for c in doc["cards"]:
        base = res.get(c["symbol"])
        if base:
            c["gfx_file"] = f"{base}.png"
        else:
            c["gfx_file"] = None
            missing += 1
    out = Path(args.out) if args.out else path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"annotated {len(doc['cards'])} cards -> {out}" + (f" ({missing} missing art)" if missing else ""))
    return 0


def cmd_validate(args):
    doc = json.loads(Path(args.cards_json).read_text(encoding="utf-8"))
    cards = doc["cards"]
    mapping = parse_gfx_asm(args.gfx_asm)
    gfx_dir = Path(args.gfx_dir)

    errors = []
    referenced = set()
    for c in cards:
        sym = c.get("gfx")
        base = mapping.get(sym)
        if base is None:
            errors.append(f"{c['symbol']}: gfx symbol {sym!r} has no gfx.asm entry")
            continue
        referenced.add(sym)
        for kind, p in _art_paths(base, gfx_dir).items():
            if not p.exists():
                errors.append(f"{c['symbol']}: missing {p.name}")

    for sym, base in mapping.items():
        if sym not in referenced:
            errors.append(f"orphan gfx.asm entry: {sym} -> {base}")

    print(f"cards: {len(cards)}, art entries: {len(mapping)}")
    if errors:
        print(f"problems: {len(errors)}", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("all card art resolves and every entry is referenced.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gfx-asm", default="vendor/poketcg/src/gfx.asm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("map", help="print/write card -> image mapping")
    p1.add_argument("cards_json", nargs="?", default="data/castledb/cards.json")
    p1.add_argument("-o", "--out", help="write CSV instead of printing")
    p1.set_defaults(func=cmd_map)

    p2 = sub.add_parser("annotate", help="add gfx_file to cards.json")
    p2.add_argument("cards_json", nargs="?", default="data/castledb/cards.json")
    p2.add_argument("-o", "--out")
    p2.set_defaults(func=cmd_annotate)

    p3 = sub.add_parser("validate", help="integrity-check card<->art")
    p3.add_argument("cards_json", nargs="?", default="data/castledb/cards.json")
    p3.add_argument("--gfx-dir", default="vendor/poketcg/src/gfx/cards")
    p3.set_defaults(func=cmd_validate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
