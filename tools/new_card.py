#!/usr/bin/env python3
"""
new_card.py — scaffold a new card end-to-end: placeholder art, graphics entry,
card-constant, and the card record itself.

A new card touches four places in the disassembly plus the external JSON:

    src/gfx/cards/<file>.png              placeholder art (rgbgfx converts it)
    src/gfx.asm                           <Name>CardGfx:: + INCBIN entry
    src/constants/card_constants.asm      `const <ID>` before NUM_CARDS
    data/castledb/cards.json              the card record (then compile_cards.py
                                          regenerates src/data/cards.asm)

Usage:
    python3 tools/new_card.py card.json                 # dry-run: show snippets
    python3 tools/new_card.py card.json --apply         # write everything

`card.json` is a card spec. Text symbols (name, description, attack names, ...)
may reference existing entries (e.g. reuse another card's), since generating new
dialog text is a separate, more involved step. Example:

    {
      "symbol": "ExampleCard",
      "id_symbol": "EXAMPLE_CARD",
      "card_type": "pokemon",
      "type": "TYPE_PKMN_*",
      "rarity": "CIRCLE",
      "set": ["SET_A"],
      "name": "ExampleName",
      "description": "ExampleDescription",
      "hp": 60, "stage": "BASIC", "pre_evo_name": "NONE",
      "attacks": [
        {"energy": [{"type":"COLORLESS","amount":2}], "name":"ExampleAttackName",
         "description":"ExampleAttackDescription", "damage":20,
         "category":"DAMAGE_NORMAL", "effect_commands":"NONE",
         "animation":"ATK_ANIM_NONE"}
      ],
      "retreat_cost": 1, "weakness": "WR_*", "resistance": "NONE",
      "category": "ExampleSpeciesName", "pokedex_number": 1, "level": 10,
      "length": [3, 3], "weight": 100
    }
"""

import argparse
import json
import re
import struct
import sys
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Placeholder PNG (64x48, indexed, 4-color PLTE) so rgbgfx --colors embedded
# can produce .2bpp + .pal exactly like the existing card art.
# ---------------------------------------------------------------------------

_PALETTE = [(248, 248, 248), (232, 48, 48), (48, 112, 232), (248, 208, 48)]


def _png_chunk(typ: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + typ
        + data
        + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    )


def make_indexed_png(width: int, height: int, indices) -> bytes:
    """indices: rows of palette indices (ints 0..3)."""
    raw = b"".join(b"\x00" + bytes(row) for row in indices)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)  # 8-bit indexed
    plte = b"".join(bytes(c) for c in _PALETTE)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"PLTE", plte)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def placeholder_png(width=64, height=48) -> bytes:
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            if x < width // 2 and y < height // 2:
                idx = 0
            elif x >= width // 2 and y < height // 2:
                idx = 1
            elif x < width // 2:
                idx = 2
            else:
                idx = 3
            row.append(idx)
        rows.append(row)
    return make_indexed_png(width, height, rows)


# ---------------------------------------------------------------------------
# Card spec -> flat card record
# ---------------------------------------------------------------------------

_EMPTY_ATTACK = {
    "energy": [],
    "name": "NONE",
    "description": "NONE",
    "description_cont": "NONE",
    "damage": 0,
    "category": "DAMAGE_NORMAL",
    "effect_commands": "NONE",
    "flag1": "NONE",
    "flag2": "NONE",
    "flag3": "NONE",
    "effect_param": "0",
    "animation": "ATK_ANIM_NONE",
}


def _flatten_attacks(spec) -> dict:
    attacks = list(spec.get("attacks", []))[:2]
    while len(attacks) < 2:
        attacks.append(dict(_EMPTY_ATTACK))
    out = {}
    for i, atk in enumerate(attacks, 1):
        p = f"attack{i}_"
        for k in (
            "energy", "name", "description", "description_cont", "damage",
            "category", "effect_commands", "flag1", "flag2", "flag3",
            "effect_param", "animation",
        ):
            out[p + k] = atk.get(k, _EMPTY_ATTACK[k])
    return out


def build_card(spec: dict, card_id: int) -> dict:
    symbol = spec["symbol"]
    base = spec.get("file", spec["id_symbol"].lower())
    card = {
        "symbol": symbol,
        "card_type": spec["card_type"],
        "type": spec["type"],
        "gfx": symbol + "Gfx",
        "gfx_file": f"{base}.png",
        "name": spec["name"],
        "rarity": spec["rarity"],
        "set": spec["set"],
        "id_symbol": spec["id_symbol"],
        "id": card_id,
    }
    if spec["card_type"] == "pokemon":
        card.update(
            {
                "hp": spec["hp"],
                "stage": spec["stage"],
                "pre_evo_name": spec.get("pre_evo_name", "NONE"),
                **_flatten_attacks(spec),
                "retreat_cost": spec["retreat_cost"],
                "weakness": spec["weakness"],
                "resistance": spec.get("resistance", "NONE"),
                "category": spec["category"],
                "pokedex_number": spec["pokedex_number"],
                "unused": 0,
                "level": spec["level"],
                "length": spec["length"],
                "weight": spec["weight"],
                "description": spec["description"],
                "ai_info": spec.get("ai_info", "0"),
            }
        )
    else:
        card.update(
            {
                "effect_commands": spec.get("effect_commands", "NONE"),
                "description": spec["description"],
                "description_cont": "NONE",
            }
        )
    return card


# ---------------------------------------------------------------------------
# Snippets
# ---------------------------------------------------------------------------

def gfx_asm_snippet(card) -> str:
    base = card["gfx_file"][:-4]  # strip .png
    return (
        f"{card['gfx']}::\n"
        f'\tINCBIN "gfx/cards/{base}.2bpp"\n'
        f'\tINCBIN "gfx/cards/{base}.pal"'
    )


def constants_snippet(card) -> str:
    return f"\tconst {card['id_symbol']}"


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def _ensure_cards_bank(base: Path) -> None:
    """Give the "Cards" section its own ROMX bank.

    The stock layout packs "Cards" into bank $0c alongside "Decks" with almost
    no headroom, so adding even one card overflows. Bank $09 is unallocated in
    the stock linker script; moving "Cards" there (a one-time change) gives it a
    full 16 KB. Safe because card data is referenced via BANK(CardPointers),
    never a hardcoded bank number.
    """
    layout = base / "src" / "layout.link"
    text = layout.read_text(encoding="utf-8")
    if re.search(r'ROMX\s+\$[0-9a-fA-F]+\s*\n\s*"Cards"', text):
        return  # already in its own bank
    if '\t"Cards"' in text:
        text = text.replace('\t"Cards"', 'ROMX $09\n\t"Cards"', 1)
        layout.write_text(text, encoding="utf-8")
        print("  relocated 'Cards' section to its own bank $09 (layout.link)")


def apply(base: Path, spec: dict, card: dict, cards_json_path: Path) -> None:
    src = base / "src"

    # 1. placeholder art
    gfx_file = src / "gfx" / "cards" / card["gfx_file"]
    gfx_file.write_bytes(placeholder_png())
    print(f"  wrote {gfx_file}")

    # 2. gfx.asm entry (append at end)
    gfx_asm = src / "gfx.asm"
    gfx_asm.write_text(
        gfx_asm.read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + gfx_asm_snippet(card)
        + "\n",
        encoding="utf-8",
    )
    print(f"  appended gfx entry to {gfx_asm}")

    # 3. card_constants entry (before NUM_CARDS)
    constants = src / "constants" / "card_constants.asm"
    text = constants.read_text(encoding="utf-8")
    marker = "DEF NUM_CARDS EQU const_value - 1"
    assert marker in text, f"marker {marker!r} not found in {constants}"
    text = text.replace(marker, constants_snippet(card) + "\n" + marker, 1)
    constants.write_text(text, encoding="utf-8")
    print(f"  inserted constant into {constants}")

    # 4. ensure the card-data section has room to grow
    _ensure_cards_bank(base)

    # 5. append card record to the external JSON
    doc = json.loads(cards_json_path.read_text(encoding="utf-8"))
    if any(c["symbol"] == card["symbol"] for c in doc["cards"]):
        print(f"  card {card['symbol']} already present in {cards_json_path}")
    else:
        doc["cards"].append(card)
        doc["count"] = len(doc["cards"])
    cards_json_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  added card to {cards_json_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", help="path to a card spec JSON")
    ap.add_argument("--base", default="vendor/poketcg", help="disassembly root")
    ap.add_argument("--cards-json", default="data/castledb/cards.json")
    ap.add_argument("--apply", action="store_true", help="write files (default: dry-run)")
    ap.add_argument("--recompile", action="store_true",
                    help="after --apply, regenerate cards.asm with compile_cards.py")
    args = ap.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    cards_json_path = Path(args.cards_json)
    doc = json.loads(cards_json_path.read_text(encoding="utf-8"))
    next_id = max((c["id"] for c in doc["cards"]), default=0) + 1
    card = build_card(spec, next_id)

    print(f"card: {card['symbol']} (id {card['id']}, gfx {card['gfx']} -> {card['gfx_file']})")
    print("\n--- gfx.asm snippet ---")
    print(gfx_asm_snippet(card))
    print("\n--- card_constants snippet ---")
    print(constants_snippet(card))
    print("\n--- card JSON record ---")
    print(json.dumps(card, indent=2))

    if not args.apply:
        print("\n(dry-run: pass --apply to write files)")
        return 0

    apply(Path(args.base), spec, card, cards_json_path)

    if args.recompile:
        from compile_cards import main as compile_main
        out = Path(args.base) / "src" / "data" / "cards.asm"
        print("  recompiling cards.asm...")
        compile_main([str(cards_json_path), "-o", str(out)])

    print("\nDone. Next: make -C vendor/poketcg (rgbgfx converts the PNG;")
    print("the ROM sha1 will differ because the card set changed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
