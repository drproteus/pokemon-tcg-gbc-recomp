#!/usr/bin/env python3
"""
compile_cards.py — compile card JSON (from extract_cards.py) back into the
game's native `cards.asm`.

Usage:
    python3 tools/compile_cards.py [CARDS_JSON] [-o OUT.asm]

Defaults:
    CARDS_JSON  data/castledb/cards.json
    OUT         build/compiled/cards.asm   (or stdout with --stdout)

The compiler is the inverse of the extractor: it re-emits the `CardPointers`
table (cards sorted by numeric id, with the leading/trailing NULL sentinels) and
each card record in file order, using the game's directive macros (`db`, `dw`,
`tx`, `gfx`, `energy`). It is lossless: compiling the extractor's output and
assembling it produces byte-identical card data (see tools/test_roundtrip.sh).

Field emission rules:

- text-pointer fields (name, pre-evo name, descriptions, category) emit
  `tx <symbol>` for a real reference and `dw NONE` for the empty case;
- code-pointer fields (effect commands) always emit `dw <symbol>`;
- the `set` bitmask is re-joined with `|`;
- energy cost is reconstructed as `energy <type>, <amount>, ...` or `energy 0`.
"""

import argparse
import json
import sys
from pathlib import Path

# values that represent "no text pointer" in the source data
_TEXT_NONE = {"NONE", "0", "", None}


def _text_ptr(value: str) -> str:
    """Emit a text-pointer field: `tx <name>` or `dw NONE`."""
    if value in _TEXT_NONE:
        return f"\tdw {value or 'NONE'}"
    return f"\ttx {value}"


def _code_ptr(value: str) -> str:
    return f"\tdw {value}"


def _set_arg(setlist: list) -> str:
    if not setlist:
        return "NONE"
    return " | ".join(setlist)


def _energy_arg(energy: list) -> str:
    if not energy:
        return "0"
    return ", ".join(f"{e['type']}, {e['amount']}" for e in energy)


def _emit_card(card: dict) -> str:
    lines = [f"{card['symbol']}:"]
    ct = card["card_type"]

    # common header (byte offsets $00..$07)
    lines.append(f"\tdb {card['type']} ; type")
    lines.append(f"\tgfx {card['gfx']} ; gfx")
    lines.append(f"\ttx {card['name']} ; name")
    lines.append(f"\tdb {card['rarity']} ; rarity")
    lines.append(f"\tdb {_set_arg(card['set'])} ; sets")
    # id: prefer the preserved assembly constant, fall back to the numeric id
    lines.append(f"\tdb {card.get('id_symbol') or card['id']}")

    if ct == "pokemon":
        lines.append(f"\tdb {card['hp']} ; hp")
        lines.append(f"\tdb {card['stage']} ; stage")
        lines.append(f"{_text_ptr(card['pre_evo_name'])} ; pre-evo name")

        for n in ("attack1", "attack2"):
            lines.append("")
            lines.append(f"\t; {n}")
            lines.append(f"\tenergy {_energy_arg(card[n + '_energy'])} ; energies")
            lines.append(f"{_text_ptr(card[n + '_name'])} ; name")
            lines.append(f"{_text_ptr(card[n + '_description'])} ; description")
            lines.append(
                f"{_text_ptr(card[n + '_description_cont'])} ; description (cont)"
            )
            lines.append(f"\tdb {card[n + '_damage']} ; damage")
            lines.append(f"\tdb {card[n + '_category']} ; category")
            lines.append(
                f"{_code_ptr(card[n + '_effect_commands'])} ; effect commands"
            )
            lines.append(f"\tdb {card[n + '_flag1']} ; flags 1")
            lines.append(f"\tdb {card[n + '_flag2']} ; flags 2")
            lines.append(f"\tdb {card[n + '_flag3']} ; flags 3")
            lines.append(f"\tdb {card[n + '_effect_param']}")
            lines.append(f"\tdb {card[n + '_animation']} ; animation")

        lines.append("")
        lines.append(f"\tdb {card['retreat_cost']} ; retreat cost")
        lines.append(f"\tdb {card['weakness']} ; weakness")
        lines.append(f"\tdb {card['resistance']} ; resistance")
        lines.append(f"{_text_ptr(card['category'])} ; category")
        lines.append(f"\tdb {card['pokedex_number']} ; Pokedex number")
        lines.append(f"\tdb {card['unused']}")
        lines.append(f"\tdb {card['level']} ; level")
        lines.append(f"\tdb {', '.join(map(str, card['length']))} ; length")
        lines.append(f"\tdw {card['weight']} ; weight")
        lines.append(f"{_text_ptr(card['description'])} ; description")
        lines.append(f"\tdb {card['ai_info']} ; AI info")
    else:  # trainer / energy
        lines.append(f"{_code_ptr(card['effect_commands'])} ; effect commands")
        lines.append(f"{_text_ptr(card['description'])} ; description")
        lines.append(
            f"{_text_ptr(card['description_cont'])} ; description (cont)"
        )

    return "\n".join(lines)


def _emit_pointer_table(cards: list) -> str:
    """CardPointers table: NULL + cards in id order + NULL sentinel + assert."""
    ordered = sorted(cards, key=lambda c: c["id"])
    lines = ["CardPointers::", "\ttable_width 2", "\tdw NULL"]
    for card in ordered:
        lines.append(f"\tdw {card['symbol']}")
    lines.append("\tdw NULL")
    lines.append("\tassert_table_length NUM_CARDS + 2")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cards_json", nargs="?", default="data/castledb/cards.json")
    ap.add_argument("-o", "--out", default="build/compiled/cards.asm")
    ap.add_argument("--stdout", action="store_true", help="write to stdout")
    args = ap.parse_args(argv)

    src = Path(args.cards_json)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    doc = json.loads(src.read_text(encoding="utf-8"))
    cards = doc["cards"]

    header = (
        "; Compiled card data — generated by tools/compile_cards.py.\n"
        f"; Source: {src}\n"
        f"; Card count: {len(cards)}\n"
    )
    body = [_emit_pointer_table(cards)]
    body += [_emit_card(c) for c in cards]
    text = header + "\n" + "\n\n".join(body) + "\n"

    if args.stdout:
        sys.stdout.write(text)
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {len(cards)} cards -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
