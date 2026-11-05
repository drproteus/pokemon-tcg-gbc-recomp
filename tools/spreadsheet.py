#!/usr/bin/env python3
"""
spreadsheet.py — convert between the compiler's flat card JSON and a CSV
spreadsheet, so cards can be edited in any spreadsheet program (LibreOffice
Calc, Apple Numbers, Excel, Google Sheets, ...).

Subcommands:
    json2csv   data/castledb/cards.json  -> data/castledb/cards.csv
    csv2json   data/castledb/cards.csv   -> data/castledb/cards.json

List-valued fields are serialized as delimited strings (deliberately avoiding
the CSV comma delimiter so cells stay unquoted and spreadsheet-friendly):

    set            ["EVOLUTION","FOSSIL"]            <->  "EVOLUTION|FOSSIL"
    attack*_energy [{type:"GRASS",amount:2}, ...]    <->  "GRASS:2;COLORLESS:1"
    length         [2,4]                             <->  "2:4"

The round-trip is lossless at the byte level: csv2json(json2csv(x)) recompiles
to a byte-identical ROM (see tools/test_roundtrip.sh).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from castledb import COLUMNS  # reuse the shared column spec (name -> (kind, opt))


def _to_cell(kind, value):
    if value is None:
        return ""
    if kind == "set":
        return "|".join(s for s in value if s != "NONE")
    if kind == "energy":
        if not value:
            return ""
        return ";".join(f"{e['type']}:{e['amount']}" for e in value)
    if kind == "intlist":
        return ":".join(str(x) for x in value)
    return value


def _from_cell(kind, value):
    if value is None:
        return None
    # empty energy cost / set bitmask are meaningful: they mean "empty list",
    # not "absent" (e.g. a Pokémon with no energy cost for its second attack).
    if kind == "energy" and value == "":
        return []
    if kind == "set" and value == "":
        return []
    if value == "":
        return None
    if kind == "set":
        return [s for s in value.split("|") if s]
    if kind == "energy":
        out = []
        for part in value.split(";"):
            t, a = part.split(":")
            out.append({"type": t, "amount": int(a)})
        return out
    if kind == "intlist":
        return [int(x) for x in value.split(":")]
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _column_names():
    return list(COLUMNS.keys())


def json2csv(doc):
    cards = doc["cards"]
    names = _column_names()
    rows = []
    for c in cards:
        row = {}
        for name, (kind, _opt) in COLUMNS.items():
            row[name] = _to_cell(kind, c.get(name))
        rows.append(row)
    return names, rows


def csv2json(rows):
    cards = []
    for row in rows:
        card = {}
        for name, (kind, _opt) in COLUMNS.items():
            if name not in row:
                continue
            v = _from_cell(kind, row[name])
            if v is not None:
                card[name] = v
        cards.append(card)
    return {
        "schema": "poketcg.cards",
        "version": 1,
        "count": len(cards),
        "cards": cards,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("json2csv", help="flat JSON -> CSV")
    p1.add_argument("json", nargs="?", default="data/castledb/cards.json")
    p1.add_argument("-o", "--out", default="data/castledb/cards.csv")

    p2 = sub.add_parser("csv2json", help="CSV -> flat JSON")
    p2.add_argument("csv", nargs="?", default="data/castledb/cards.csv")
    p2.add_argument("-o", "--out", default="data/castledb/cards.json")

    args = ap.parse_args(argv)

    if args.cmd == "json2csv":
        src = Path(args.json)
        doc = json.loads(src.read_text(encoding="utf-8"))
        names, rows = json2csv(doc)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=names, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote CSV ({len(rows)} cards) -> {out}")
        return 0

    src = Path(args.csv)
    with src.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    doc = csv2json(rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote flat JSON ({len(doc['cards'])} cards) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
