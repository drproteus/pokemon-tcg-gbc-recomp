# Tools

Python scripts that implement the translation layer between the game's native
data and external-editable formats (CastleDB, Tiled).

## Card pipeline (working, byte-exact)

```
cards.asm  ──extract_cards.py──▶  cards.json  ──castledb.py json2cdb──▶  cards.cdb
                                        ▲                                        │
                                        └────────── castledb.py cdb2json ────────┘
cards.asm  ◀──compile_cards.py──  cards.json
```

| Tool | Direction | Notes |
| --- | --- | --- |
| `extract_cards.py` | `cards.asm` → `cards.json` | 228 cards; documented by `data/castledb/cards.schema.json` |
| `compile_cards.py` | `cards.json` → `cards.asm` | lossless; emits `CardPointers` + records |
| `spreadsheet.py` | `cards.json` ↔ `cards.csv` | **recommended** editing surface (see below) |
| `castledb.py` | `cards.json` ↔ `cards.cdb` | legacy CastleDB database (kept for compatibility) |
| `test_roundtrip.sh` | — | proves all three paths recompile to a byte-identical ROM |

### Recommended editor: a spreadsheet

Cards are a flat table, so the simplest modern editor is a spreadsheet.
`spreadsheet.py` round-trips `cards.json` ↔ `cards.csv`; edit the CSV in
**LibreOffice Calc** (free, cross-platform, best CSV handling), Apple Numbers,
Excel, or Google Sheets.

```bash
python3 tools/spreadsheet.py json2csv data/castledb/cards.json -o data/castledb/cards.csv
# ...edit cards.csv in your spreadsheet...
python3 tools/spreadsheet.py csv2json data/castledb/cards.csv -o data/castledb/cards.json
python3 tools/compile_cards.py data/castledb/cards.json -o vendor/poketcg/src/data/cards.asm
```

> CastleDB (v1.5, 2015) is unmaintained and does not run on modern macOS
> without Rosetta + re-signing; it is retained only as a compatibility target.
> The canonical format is `cards.json`, and CSV is the recommended editing
> surface.

Examples:

```bash
# Extract
python3 tools/extract_cards.py vendor/poketcg/src/data/cards.asm -o data/castledb/cards.json

# Edit in CastleDB, then bring the result back into the compile flow
python3 tools/castledb.py cdb2json data/castledb/cards.cdb -o data/castledb/cards.json

# Compile
python3 tools/compile_cards.py data/castledb/cards.json -o vendor/poketcg/src/data/cards.asm

# Prove the whole translation layer is lossless (byte-identical ROM)
tools/test_roundtrip.sh
```

Editing a card (e.g. a card's `hp` 40→50) changes exactly the intended ROM
bytes — the HP byte, the damage byte, and the header checksum — and nothing
else.

## Map / level pipeline

Planned (Phase 3): extract `src/data/maps/tilemaps.asm` + map headers/objects
into Tiled (`.tmx` / `.tsx`), and compile edited maps back. Not yet implemented.

## Graphics & new cards

Card art lives in `src/gfx/cards/<name>.{png,2bpp,pal}` (64×48, indexed 4-color
PNG converted by `rgbgfx`). The pipeline documents and scaffolds it:

| Tool | Purpose |
| --- | --- |
| `gfx.py` | map/validate/annotate the card → art relationship |
| `new_card.py` | add a new card end-to-end (art + gfx entry + constant + record) |

```bash
# map every card to its art file (or write a CSV)
python3 tools/gfx.py map
python3 tools/gfx.py map -o cards_by_art.csv

# integrity-check the whole card<->art chain
python3 tools/gfx.py validate

# add a new card (one command: art, gfx.asm, constants, JSON, cards.asm)
python3 tools/new_card.py card.json --base vendor/poketcg --apply --recompile
make -C vendor/poketcg
```

`extract_cards.py` now also emits a `gfx_file` field per card (resolved from
`src/gfx.asm`), which flows through to the CSV/CastleDB columns.

> **Layout note:** the stock ROM packs the "Cards" section into bank `$0c`
> with almost no headroom. `new_card.py` automatically relocates "Cards" to the
> unused bank `$09` (safe: card data is referenced via `BANK(CardPointers)`), so
> the card table has a full 16 KB to grow into.

## Recomp runtime

`recompile.sh` wraps the `rom -> gbrecomp -> native build` flow and accepts an
optional native patch (`--patch <manifest>`). See `docs/PHASE1_RUNTIME.md`.

## Conventions

- All tools are standalone Python 3 (stdlib only, no dependencies).
- Extractors are read-only and verifiable against the disassembly.
- Compilers must round-trip: `compile(extract(x)) == x` (asserted at the ROM
  byte level by `test_roundtrip.sh`).
- Every emitted JSON document carries `schema` + `version`.
