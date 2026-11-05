#!/usr/bin/env python3
"""
castledb.py — convert between the compiler's flat card JSON and a CastleDB
`.cdb` database, so cards can be edited in the CastleDB UI.

Subcommands:
    json2cdb   data/castledb/cards.json  -> data/castledb/cards.cdb
    cdb2json   data/castledb/cards.cdb   -> data/castledb/cards.json

The flat JSON is the compiler input (see tools/compile_cards.py); the `.cdb` is
a typed view of the same data. Type mapping (CastleDB `typeStr` codes):

    1  = TString       3  = TInt       5:<a,b>  = TEnum(values)

Fields that are list-valued in the flat JSON are represented as delimited
strings in CastleDB:

    set          ["EVOLUTION","FOSSIL"]  <->  "EVOLUTION,FOSSIL"   (NONE=0 is implicit)
    attack*_energy  [{"type":"GRASS","amount":2}]  <->  "GRASS,2"
    length       [2,4]                   <->  "2,4"

The round-trip is lossless for byte-level card data: cdb2json(json2cdb(x))
recompiles to a byte-identical ROM (see tools/test_roundtrip.sh).
"""

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

# CastleDB ColumnType indices -> typeStr
T_STRING = "1"
T_INT = "3"


def _enum(*values):
    return "5:" + ",".join(values)


def _flags(*values):
    return "10:" + ",".join(values)


# Column spec: name -> (kind, optional)
# kind: "str" | "int" | "enum:<group>" | "set" | "energy" | "intlist"
# enum values are collected from the data itself at generation time.
COLUMNS = OrderedDict(
    [
        # common
        ("id", ("int", False)),
        ("symbol", ("str", False)),
        ("card_type", ("enum:card_type", False)),
        ("type", ("enum:type", False)),
        ("gfx", ("str", False)),
        ("gfx_file", ("str", True)),
        ("name", ("str", False)),
        ("rarity", ("enum:rarity", False)),
        ("set", ("set", False)),
        # pokemon-only
        ("hp", ("int", True)),
        ("stage", ("enum:stage", True)),
        ("pre_evo_name", ("str", True)),
        ("attack1_energy", ("energy", True)),
        ("attack1_name", ("str", True)),
        ("attack1_description", ("str", True)),
        ("attack1_description_cont", ("str", True)),
        ("attack1_damage", ("int", True)),
        ("attack1_category", ("str", True)),
        ("attack1_effect_commands", ("str", True)),
        ("attack1_flag1", ("str", True)),
        ("attack1_flag2", ("str", True)),
        ("attack1_flag3", ("str", True)),
        ("attack1_effect_param", ("str", True)),
        ("attack1_animation", ("str", True)),
        ("attack2_energy", ("energy", True)),
        ("attack2_name", ("str", True)),
        ("attack2_description", ("str", True)),
        ("attack2_description_cont", ("str", True)),
        ("attack2_damage", ("int", True)),
        ("attack2_category", ("str", True)),
        ("attack2_effect_commands", ("str", True)),
        ("attack2_flag1", ("str", True)),
        ("attack2_flag2", ("str", True)),
        ("attack2_flag3", ("str", True)),
        ("attack2_effect_param", ("str", True)),
        ("attack2_animation", ("str", True)),
        ("retreat_cost", ("int", True)),
        ("weakness", ("str", True)),
        ("resistance", ("str", True)),
        ("category", ("str", True)),
        ("pokedex_number", ("int", True)),
        ("unused", ("int", True)),
        ("level", ("int", True)),
        ("length", ("intlist", True)),
        ("weight", ("int", True)),
        ("description", ("str", False)),
        ("ai_info", ("str", True)),
        # trainer/energy-only
        ("effect_commands", ("str", True)),
        ("description_cont", ("str", True)),
    ]
)

_ENUM_GROUPS = {"card_type", "type", "rarity", "stage"}


def _collect_enums(cards):
    """Distinct enum values per group, in first-seen order."""
    enums = {g: [] for g in _ENUM_GROUPS}
    for c in cards:
        for g in _ENUM_GROUPS:
            v = c.get(g)
            if v is not None and v not in enums[g]:
                enums[g].append(str(v))
    return enums


def _to_cdb_value(name, kind, value):
    if value is None:
        return None
    if kind == "set":
        # drop NONE (== 0), keep real set names
        sets = [s for s in value if s != "NONE"]
        return ",".join(sets)
    if kind == "energy":
        if not value:
            return ""
        return ",".join(f"{e['type']},{e['amount']}" for e in value)
    if kind == "intlist":
        return ",".join(str(x) for x in value)
    return value  # str / int pass through


def _from_cdb_value(name, kind, value):
    if value is None:
        return None
    if kind == "set":
        if value == "":
            return []
        return [s for s in value.split(",") if s]
    if kind == "energy":
        if value == "":
            return []
        parts = value.split(",")
        return [
            {"type": parts[i], "amount": int(parts[i + 1])}
            for i in range(0, len(parts), 2)
        ]
    if kind == "intlist":
        return [int(x) for x in value.split(",")]
    return value


def _column_defs(enums):
    defs = []
    for name, (kind, opt) in COLUMNS.items():
        if kind == "int":
            type_str = T_INT
        elif kind.startswith("enum:"):
            group = kind.split(":", 1)[1]
            type_str = _enum(*enums[group])
        elif kind == "set":
            # all set names seen in the data, minus NONE
            type_str = _flags(*[s for s in enums.get("set", [])])
        else:
            type_str = T_STRING
        col = {"name": name, "typeStr": type_str}
        if opt:
            col["opt"] = True
        defs.append(col)
    return defs


def json2cdb(doc):
    cards = doc["cards"]
    enums = _collect_enums(cards)
    # gather distinct set names for the TFlags column
    set_names = []
    for c in cards:
        for s in c.get("set", []):
            if s != "NONE" and s not in set_names:
                set_names.append(s)
    enums["set"] = set_names

    lines = []
    for c in cards:
        line = {}
        for name, (kind, _opt) in COLUMNS.items():
            line[name] = _to_cdb_value(name, kind, c.get(name))
        lines.append(line)

    return {
        "sheets": [
            {
                "name": "Cards",
                "columns": _column_defs(enums),
                "lines": lines,
                "props": {"displayColumn": "symbol"},
                "separators": [],
            }
        ],
        "customTypes": [],
        "compress": False,
    }


def cdb2json(cdb):
    sheet = next(s for s in cdb["sheets"] if s["name"] == "Cards")
    cols = {c["name"]: c for c in sheet["columns"]}
    # recover kind per column from our COLUMNS spec (order-stable)
    cards = []
    for line in sheet["lines"]:
        card = {}
        for name, (kind, _opt) in COLUMNS.items():
            if name not in line:
                continue
            card[name] = _from_cdb_value(name, kind, line[name])
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

    p1 = sub.add_parser("json2cdb", help="flat JSON -> CastleDB .cdb")
    p1.add_argument("json", nargs="?", default="data/castledb/cards.json")
    p1.add_argument("-o", "--out", default="data/castledb/cards.cdb")

    p2 = sub.add_parser("cdb2json", help="CastleDB .cdb -> flat JSON")
    p2.add_argument("cdb", nargs="?", default="data/castledb/cards.cdb")
    p2.add_argument("-o", "--out", default="data/castledb/cards.json")

    args = ap.parse_args(argv)

    if args.cmd == "json2cdb":
        src = Path(args.json)
        doc = json.loads(src.read_text(encoding="utf-8"))
        cdb = json2cdb(doc)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cdb, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote CastleDB db ({len(doc['cards'])} cards) -> {out}")
        return 0

    src = Path(args.cdb)
    cdb = json.loads(src.read_text(encoding="utf-8"))
    doc = cdb2json(cdb)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote flat JSON ({len(doc['cards'])} cards) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
