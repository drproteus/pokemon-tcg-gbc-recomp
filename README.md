# Pokémon TCG (GBC) — Recomp Project

A cross-platform, ROM-free recompilation project for **Pokémon Trading Card Game**
(Game Boy Color), with the long-term goals of:

- running natively on macOS / Linux / Windows (and eventually more targets),
- **widescreen** and other quality-of-life improvements,
- **data-driven, externally editable content**: card sets authored as a database
  (CastleDB) and levels/maps authored in Tiled,
- a **translation layer** that round-trips the game's native data formats to and
  from those external tools.

> This repository contains **no copyrighted game data**. Card names, stats, and
> text are *derived at extract time* from your own copy of the game (the
> `pret/poketcg` disassembly, which you build and verify against a ROM you
> supply). The extracted `cards.json` / `cards.cdb` / `cards.csv` are generated,
> git-ignored artifacts — see [Legal](#legal).

---

## Status

This is an **early-stage scaffolding**. The current state:

| Piece | Status |
| --- | --- |
| Repo structure + strategy docs | ✅ |
| Reference ROM build (RGBDS, byte-identical) | ✅ |
| Native recompiled runtime (cross-platform) | ✅ boots + renders title screen — [`docs/PHASE1_RUNTIME.md`](docs/PHASE1_RUNTIME.md) |
| Native-patch SDK (QoL hook) | ✅ spike proven |
| Card data extractor (disassembly → JSON) | ✅ |
| Card compiler (JSON → `cards.asm`, byte-exact) | ✅ round-trip verified |
| CastleDB schema + converter | ✅ `tools/castledb.py` (generates `.cdb`) |
| CSV / spreadsheet editor (recommended) | ✅ `tools/spreadsheet.py` |
| Card art mapping + validation | ✅ `tools/gfx.py` |
| New-card scaffold generator | ✅ `tools/new_card.py` (adds a card end-to-end) |
| Map/Tilemap extractor (→ Tiled) | ⏳ planned |
| Widescreen / QoL patches | ⏳ planned |

---

## Architecture (short version)

The project separates three concerns, so each can be swapped independently:

1. **Ground truth** — the `pret/poketcg` disassembly, assembled with RGBDS to a
   byte-identical ROM. This is the reference implementation and the source of
   truth for all data formats.
2. **Recompiled runtime** — `gb-recompiled` turns that ROM into a portable C
   project with an SDL2 runtime. This is the cross-platform base, and where
   widescreen / QoL "native patches" and host presentation live.
3. **Data pipeline** — the game's content (cards, decks, boosters, maps, scripts,
   text) is extracted into external formats (CastleDB JSON, Tiled TMX/TSX) and
   compiled back into the game's native binary/assembly formats.

```
        ┌─────────────────────────────┐
        │  External editors          │
        │  CastleDB (.cdb / JSON)    │
        │  Tiled    (.tmx / .tsx)    │
        └──────────────┬──────────────┘
                       │  tools/ (Python compilers)
                       ▼
        ┌─────────────────────────────┐
        │  Native data / assembly     │
        │  cards.asm, maps/*.asm ...  │
        └──────────────┬──────────────┘
                       │  RGBDS
                       ▼
        ┌─────────────────────────────┐
        │  ROM (poketcg.gbc)         │
        └──────────────┬──────────────┘
                       │  gb-recompiled
                       ▼
        ┌─────────────────────────────┐
        │  Portable C + SDL2 runtime  │
        │  (widescreen, QoL patches)  │
        └─────────────────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full rationale, the
alternatives considered, and the phased plan.

---

## Quick start

> Prerequisites: Python 3.11+, Git. Optional but recommended: CMake + Ninja +
> SDL2 for the recompiled runtime, and RGBDS for building the disassembly.

```bash
# 1. Fetch the upstream sources (no ROMs are downloaded)
git submodule update --init --recursive

# 2. Build the reference ROM from the disassembly (requires RGBDS)
make -C vendor/poketcg

# 3. Recompile it to a native, cross-platform executable (requires CMake,
#    Ninja, SDL2, and a C/C++ compiler)
tools/recompile.sh --run

# 4. Extract card data as JSON (CastleDB-ready)
python3 tools/extract_cards.py
```

---

## Repository layout

```
├── docs/                # Architecture, formats, plans, runtime status
├── tools/               # Python data pipeline (extractors + compilers)
│   ├── extract_cards.py # cards.asm -> JSON
│   ├── compile_cards.py # JSON -> cards.asm (byte-exact)
│   ├── spreadsheet.py   # JSON <-> CSV (recommended editor)
│   ├── castledb.py      # JSON <-> CastleDB .cdb
│   ├── test_roundtrip.sh# prove the translation layer is lossless
│   └── recompile.sh     # ROM -> native recompiled executable
├── native-patches/      # gb-recompiled native patches (QoL hooks)
├── vendor/              # Upstream dependencies (git submodules)
│   ├── poketcg/         # pret/poketcg disassembly
│   └── gb-recompiled/   # arcanite24/gb-recompiled
├── data/                # Generated, git-ignored card data (from your copy)
│   └── castledb/        # cards.json / cards.cdb / cards.csv (extracted) + JSON Schema
└── build/               # Generated artifacts (ROMs, recompiled projects)
```

---

## Legal

- **Pokémon** is a trademark of Nintendo / The Pokémon Company / Creatures / Game
  Freak. This project is not affiliated with or endorsed by any of them.
- This repository contains **no ROM images and no extracted game data** (card
  names, stats, or text). The disassembly (`vendor/poketcg`) and the recompiler
  (`vendor/gb-recompiled`) are upstream submodules distributed by their
  respective authors under their own licenses.
- **Card data is never committed.** It is generated on demand by
  `tools/extract_cards.py` from the disassembly, which you build from (and verify
  against) a ROM you are legally entitled to use. The resulting `cards.json`,
  `cards.cdb`, and `cards.csv` live under `data/castledb/` and are git-ignored.
- You must supply a ROM you are legally entitled to use. The build tools verify
  the ROM against a known hash before producing any derived output.

---

## Credits & sources

- [`pret/poketcg`](https://github.com/pret/poketcg) — disassembly of Pokémon TCG
  (the source of truth for data formats).
- [`pret/poketcg2`](https://github.com/pret/poketcg2) — disassembly of the sequel
  (useful for future card/feature backports).
- [`arcanite24/gb-recompiled`](https://github.com/arcanite24/gb-recompiled) —
  static recompiler that emits portable C + SDL2 (the cross-platform runtime).
- [`CastleDB`](http://castledb.org/) — structured database + level editor.
- [`Tiled`](https://www.mapeditor.org/) — tile map editor.
- [`RGBDS`](https://github.com/gbdev/rgbds) — GB assembler toolchain.
