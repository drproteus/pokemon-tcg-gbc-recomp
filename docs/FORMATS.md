# Data formats

Reference documentation for the game's native data formats, sourced from the
`pret/poketcg` disassembly. These are the formats the translation layer targets.

## Cards

Defined in `src/data/cards.asm`. A `CardPointers` table (word-indexed) points to
each card record; the record's own index is the card ID (matching the constants
in `src/constants/card_constants.asm`, which start at `$01`).

Each card record is a sequence of `db`/`dw`/`tx`/`gfx` directives keyed by the
offsets in `src/constants/card_data_constants.asm`.

### Common fields (all card types)

| Offset | Size | Field | Meaning |
| --- | --- | --- | --- |
| `$00` | 1 | `TYPE` | Card type (energy / trainer / pokémon) |
| `$01` | 2 | `GFX` | Pointer to card graphic |
| `$03` | 2 | `NAME` | Text pointer |
| `$05` | 1 | `RARITY` | Circle / diamond / star / promo |
| `$06` | 1 | `SET` | Set bitmask (expansion-set flags) |
| `$07` | 1 | `ID` | Card ID constant |
| `$08` | — | (varies) | Effect commands (non-pokémon) or HP (pokémon) |

### Pokémon-specific fields

| Offset | Size | Field |
| --- | --- | --- |
| `$08` | 1 | HP |
| `$09` | 1 | Stage |
| `$0a` | 2 | Pre-evolution name (text ptr) |
| `$0c`..`$1e` | — | Attack 1 (energy cost[4], name[2], description[2], damage[2], category[1], effect cmd[2], flags[3], effect param[1], animation[1]) |
| `$1f`..`$31` | — | Attack 2 (same layout) |
| `$32` | 1 | Retreat cost |
| `$33` | 1 | Weakness |
| `$34` | 1 | Resistance |
| `$35` | 2 | Category (text ptr) |
| `$37` | 1 | Pokédex number |
| `$39` | 1 | Level |
| `$3a` | 2 | Length |
| `$3c` | 2 | Weight |
| `$3e` | 2 | Pokédex description (text ptr) |
| `$40` | 1 | AI info |

`PKMN_CARD_DATA_LENGTH` is `$41` bytes. Trainer cards use `TRN_CARD_DATA_LENGTH`
(`$0e`) and energy cards `ENERGY_CARD_DATA_LENGTH` (`$0e`).

### Example (from the disassembly)

```asm
ExampleCard:
	db TYPE_ENERGY_* ; type
	gfx ExampleCardGfx ; gfx
	tx ExampleName ; name
	db CIRCLE ; rarity
	db ENERGY | NONE ; sets
	db EXAMPLE_CARD
	dw ExampleEffectCommands ; effect commands
	tx ExampleDescription ; description
	dw NONE ; description (cont)
```

The `tx` macro emits a 2-byte text pointer (bank + offset), so "text pointer"
fields are always 2 bytes even though they are rendered inline.

## Maps / levels

- `src/data/maps/tilemaps.asm` — raw tilemap data for each room.
- `src/data/map_headers.asm` — per-map header (tileset, dimensions, connections).
- `src/data/map_objects.asm` — NPC/object definitions and their scripts.
- `src/data/map_scripts.asm` + `src/scripts/*.asm` — per-room event scripts.
- `src/constants/map_constants.asm` — map IDs.

## Text

- `src/text.asm` + `src/text/text1..text13.asm` — dialog text, via `tx` macros.
- `src/constants/charmaps.asm` — character set mapping.

---

## Card JSON (translation layer)

The translation layer stores cards as versioned JSON, documented by
`data/castledb/cards.schema.json` and produced by `tools/extract_cards.py`.

```json
{
  "schema": "poketcg.cards",
  "version": 1,
  "count": 228,
  "cards": [
    {
      "id": 8,
      "id_symbol": "EXAMPLE_CARD",
      "symbol": "ExampleCard",
      "card_type": "pokemon",
      "type": "TYPE_PKMN_*",
      "gfx": "ExampleCardGfx",
      "name": "ExampleName",
      "rarity": "CIRCLE",
      "set": ["SET_A", "NONE"],
      "hp": 40,
      "stage": "BASIC",
      "pre_evo_name": "NONE",
      "attack1_energy": [{ "type": "COLORLESS", "amount": 2 }],
      "attack1_name": "ExampleAttackName",
      "attack1_damage": 20,
      "attack1_category": "DAMAGE_NORMAL",
      "attack1_effect_commands": "ExampleEffectCommands",
      "...": "..."
    }
  ]
}
```

Conventions:

- **Named constants stay as symbols** (`rarity: "CIRCLE"`, `type:
  "TYPE_PKMN_*"`, `weakness: "WR_*"`), so the compiler emits the exact
  reference and the output stays byte-identical.
- **Literal numbers become integers** (`hp: 40`, `damage: 20`, `weight: 150`).
- **`set`** is a list of set symbols (e.g. `["SET_A","NONE"]`); `NONE` is the
  literal zero, so it is byte-neutral.
- **Energy cost** is a list of `{type, amount}` pairs; `[]` means no cost.

The round-trip is lossless: `compile(extract(x))` assembles to a byte-identical
ROM (verified by `tools/test_roundtrip.sh`).

## CastleDB view

`tools/castledb.py` converts the flat JSON to a CastleDB `.cdb` database
(`data/castledb/cards.cdb`) and back. List-valued fields become delimited
strings so they are editable in CastleDB's table UI:

| JSON | CastleDB |
| --- | --- |
| `set: ["SET_A","SET_B"]` | `"SET_A,SET_B"` (TFlags) |
| `attack1_energy: [{type:"COLORLESS",amount:2}]` | `"COLORLESS,2"` (TString) |
| `length: [2,4]` | `"2,4"` (TString) |

The `.cdb → JSON → cards.asm → ROM` path is also byte-identical.

## CSV / spreadsheet view (recommended)

`tools/spreadsheet.py` converts the flat JSON to a CSV spreadsheet and back —
the recommended editing surface. List-valued fields use comma-free separators
so cells stay clean:

| JSON | CSV cell |
| --- | --- |
| `set: ["SET_A","SET_B"]` | `SET_A\|SET_B` |
| `attack1_energy: [{type:"COLORLESS",amount:2}, ...]` | `COLORLESS:2;COLORLESS:1` |
| `length: [2,4]` | `2:4` |

The `CSV → JSON → cards.asm → ROM` path is byte-identical (verified by
`tools/test_roundtrip.sh`, which now checks JSON, CSV, and `.cdb`).
