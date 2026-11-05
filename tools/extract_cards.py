#!/usr/bin/env python3
"""
extract_cards.py — extract Pokémon TCG card data from the pret/poketcg
disassembly into a structured JSON document (CastleDB-ready).

Usage:
    python3 tools/extract_cards.py [CARDS_ASM] [-o OUT.json]

Defaults:
    CARDS_ASM  vendor/poketcg/src/data/cards.asm
    OUT        data/castledb/cards.json

The output is a plain, documented JSON object that can be imported into
CastleDB as a sheet, or re-compiled back to assembly by the (future) card
compiler. Field values keep the original RGBDS symbols where the meaning is a
named constant (rarity, type, effect commands, ...) and decode to integers where
the source is a literal number (HP, damage, level, ...).
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Directive / label tokenization
# ---------------------------------------------------------------------------

LABEL_RE = re.compile(r"^([A-Za-z_]\w*):$")          # card labels
GLOBAL_LABEL_RE = re.compile(r"^([A-Za-z_]\w*)::$")  # CardPointers::
DIRECTIVE_RE = re.compile(r"^(db|dw|dx|dd|dt|dbw|dwb|dn|bigdw|sgb|rgb|tx|gfx|energy|textpointer|textitem)\s+(.+)$")

# cell kinds used when decoding a card body
POINTER_OPS = {"tx", "gfx", "textpointer"}
WORD_OPS = {"dw"}
BYTE_OPS = {"db"}


def split_args(args: str) -> list[str]:
    """Split a directive argument list on commas (no string literals in cards.asm)."""
    return [p.strip() for p in args.split(",") if p.strip()]


def clean_line(raw: str) -> str:
    """Strip comments and surrounding whitespace."""
    return raw.split(";", 1)[0].strip()


def parse_energy(args: str) -> list[dict]:
    """Decode an `energy` macro argument list into typed energy amounts.

    `energy GRASS, 2`            -> [{"type": "GRASS", "amount": 2}]
    `energy GRASS, 1, COLORLESS, 2` -> [{"type": "GRASS", "amount": 1}, ...]
    `energy 0`                   -> []
    """
    parts = [p.strip() for p in args.split(",") if p.strip()]
    if len(parts) == 1 and parts[0] in ("0", "$0"):
        return []
    out = []
    for i in range(0, len(parts), 2):
        out.append({"type": parts[i], "amount": int(parts[i + 1])})
    return out


def coerce(raw: str):
    """Return an int when the raw text is a plain/hex number or a simple
    arithmetic expression; otherwise return the raw symbol string."""
    raw = raw.strip()
    if raw == "":
        return None
    if re.fullmatch(r"\$[0-9a-fA-F]+", raw):
        return int(raw[1:], 16)
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    # allow simple expressions such as "463 * 10" or "15 * 10"
    if re.fullmatch(r"[0-9\s+\-*/]+", raw):
        try:
            return int(eval(raw))  # noqa: S307 — constrained by the regex above
        except Exception:
            return raw
    return raw


# ---------------------------------------------------------------------------
# Card record schemas (byte offsets documented in
# vendor/poketcg/src/constants/card_data_constants.asm)
# ---------------------------------------------------------------------------

# kind: how to turn the consumed cells into a friendly value
#   symbol   -> first cell raw text
#   pointer  -> first cell raw text (a 2-byte reference)
#   int      -> coerce first cell raw text
#   intlist  -> coerce every 1-byte cell (e.g. "2, 4")
#   energy   -> parse_energy
#   set      -> split a bitmask expression into its symbols

COMMON = [
    ("type", 1, "symbol"),
    ("gfx", 2, "pointer"),
    ("name", 2, "pointer"),
    ("rarity", 1, "symbol"),
    ("set", 1, "set"),
    ("id", 1, "symbol"),
]

NONPKMN_TAIL = [
    ("effect_commands", 2, "pointer"),
    ("description", 2, "pointer"),
    ("description_cont", 2, "pointer"),
]


def attack(prefix: str) -> list[tuple]:
    return [
        (f"{prefix}_energy", 4, "energy"),
        (f"{prefix}_name", 2, "pointer"),
        (f"{prefix}_description", 2, "pointer"),
        (f"{prefix}_description_cont", 2, "pointer"),
        (f"{prefix}_damage", 1, "int"),
        (f"{prefix}_category", 1, "symbol"),
        (f"{prefix}_effect_commands", 2, "pointer"),
        (f"{prefix}_flag1", 1, "symbol"),
        (f"{prefix}_flag2", 1, "symbol"),
        (f"{prefix}_flag3", 1, "symbol"),
        (f"{prefix}_effect_param", 1, "symbol"),
        (f"{prefix}_animation", 1, "symbol"),
    ]


PKMN_TAIL = [
    ("hp", 1, "int"),
    ("stage", 1, "symbol"),
    ("pre_evo_name", 2, "pointer"),
    *attack("attack1"),
    *attack("attack2"),
    ("retreat_cost", 1, "int"),
    ("weakness", 1, "symbol"),
    ("resistance", 1, "symbol"),
    ("category", 2, "pointer"),
    ("pokedex_number", 1, "int"),
    ("unused", 1, "int"),
    ("level", 1, "int"),
    ("length", 2, "intlist"),
    ("weight", 2, "int"),
    ("description", 2, "pointer"),
    ("ai_info", 1, "symbol"),
]


def classify_type(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("TYPE_ENERGY"):
        return "energy"
    if raw.startswith("TYPE_TRAINER"):
        return "trainer"
    if raw.startswith("TYPE_PKMN"):
        return "pokemon"
    return "unknown"


def schema_for(type_raw: str):
    kind = classify_type(type_raw)
    if kind == "pokemon":
        return COMMON + PKMN_TAIL
    # trainer and energy cards share the non-pokemon tail
    return COMMON + NONPKMN_TAIL


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def tokenize(path: Path):
    """Return (pointer_symbols, records) where records is an ordered list of
    (label, [directive tuples])."""
    pointer_symbols = []
    records = []
    current_label = None
    current_dirs = []
    in_pointers = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = clean_line(raw)
        if not line:
            continue

        gl = GLOBAL_LABEL_RE.match(line)
        if gl:
            if gl.group(1) == "CardPointers":
                in_pointers = True
            continue

        lab = LABEL_RE.match(line)
        if lab:
            # a new card record begins
            if current_label is not None:
                records.append((current_label, current_dirs))
            current_label = lab.group(1)
            current_dirs = []
            in_pointers = False
            continue

        dm = DIRECTIVE_RE.match(line)
        if dm:
            op, args = dm.group(1), dm.group(2)
            if in_pointers and op in WORD_OPS:
                pointer_symbols.append(args.strip())
            elif current_label is not None:
                current_dirs.append((op, args))
            continue

        # anything else inside a record (blank was already skipped) is ignored
        # so stray comments/whitespace never desync the cursor.

    if current_label is not None:
        records.append((current_label, current_dirs))

    return pointer_symbols, records


def cells_from(dirs: list[tuple]) -> list[dict]:
    """Expand directive lines into a flat list of cells {size, kind, raw}."""
    cells = []
    for op, args in dirs:
        if op in BYTE_OPS:
            for part in split_args(args):
                cells.append({"size": 1, "kind": "byte", "raw": part})
        elif op in WORD_OPS:
            for part in split_args(args):
                cells.append({"size": 2, "kind": "word", "raw": part})
        elif op in POINTER_OPS:
            cells.append({"size": 2, "kind": "pointer", "raw": args.strip()})
        elif op == "energy":
            cells.append({"size": 4, "kind": "energy", "raw": args.strip()})
        # other directives are not expected in cards.asm; ignored defensively
    return cells


def consume(cells: list[dict], schema: list[tuple]) -> dict:
    """Consume cells positionally according to the schema."""
    result = {}
    i = 0
    for name, size, kind in schema:
        collected = []
        remaining = size
        while remaining > 0:
            cell = cells[i]
            i += 1
            collected.append(cell)
            remaining -= cell["size"]
        result[name] = (kind, collected)
    return result


def finalize(fields: dict) -> dict:
    out = {}
    for name, (kind, cells) in fields.items():
        raws = [c["raw"] for c in cells]
        if kind == "energy":
            out[name] = parse_energy(cells[0]["raw"])
        elif kind == "set":
            out[name] = [p.strip() for p in raws[0].split("|") if p.strip()]
        elif kind == "intlist":
            out[name] = [coerce(r) for r in raws]
        elif kind == "int":
            out[name] = coerce(raws[0])
        else:  # symbol / pointer
            out[name] = raws[0]
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cards_asm", nargs="?", default="vendor/poketcg/src/data/cards.asm")
    parser.add_argument("-o", "--out", default="data/castledb/cards.json")
    parser.add_argument(
        "--gfx-asm",
        default=None,
        help="path to src/gfx.asm; resolved card art is added as gfx_file "
        "(default: auto-detect next to cards.asm)",
    )
    parser.add_argument(
        "--no-gfx", action="store_true", help="do not resolve card art"
    )
    args = parser.parse_args(argv)

    cards_path = Path(args.cards_asm)
    if not cards_path.exists():
        print(f"error: {cards_path} not found", file=sys.stderr)
        return 1

    pointer_symbols, records = tokenize(cards_path)

    # Build id -> symbol from CardPointers (index 1-based, NULL at index 0)
    id_by_symbol = {}
    for idx, sym in enumerate(pointer_symbols):
        if sym != "NULL":
            id_by_symbol[sym] = idx  # 0-based: first real card == 0

    cards = []
    warnings = []
    for label, dirs in records:
        cells = cells_from(dirs)
        type_raw = cells[0]["raw"] if cells else ""
        schema = schema_for(type_raw)
        fields = consume(cells, schema)
        card = finalize(fields)

        card["symbol"] = label
        card["card_type"] = classify_type(type_raw)

        if label in id_by_symbol:
            # preserve the original assembly constant (e.g. "CARD_ID") that the
            # source wrote in the CARD_DATA_ID byte, in addition to the numeric
            # card ID derived from the CardPointers index.
            card["id_symbol"] = card.get("id")
            card["id"] = id_by_symbol[label]  # numeric card ID (1-based)
        else:
            warnings.append(f"card label {label!r} not found in CardPointers")

        cards.append(card)

    for sym in id_by_symbol:
        if sym not in {c["symbol"] for c in cards}:
            warnings.append(f"CardPointers symbol {sym!r} has no card record")

    # Optionally resolve each card's art file (gfx symbol -> gfx/cards/<name>.png)
    if not args.no_gfx:
        gfx_asm = args.gfx_asm or (cards_path.parent.parent / "gfx.asm")
        if Path(gfx_asm).exists():
            from gfx import parse_gfx_asm

            art = parse_gfx_asm(gfx_asm)
            for c in cards:
                base = art.get(c.get("gfx"))
                c["gfx_file"] = f"{base}.png" if base else None

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = {
        "schema": "poketcg.cards",
        "version": 1,
        "source": str(cards_path),
        "count": len(cards),
        "pointer_count": len([s for s in pointer_symbols if s != "NULL"]),
        "cards": cards,
    }
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {len(cards)} cards -> {out_path}")
    if warnings:
        print("\nwarnings:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
