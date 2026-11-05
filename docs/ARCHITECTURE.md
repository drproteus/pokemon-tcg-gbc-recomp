# Architecture & Strategy

This document lays out the technical strategy for the Pokémon TCG (GBC) recomp
project, the alternatives considered, and the phased plan.

## Goals

1. **Cross-platform native build** — macOS / Linux / Windows today, extensible
   to more (the runtime is SDL2-based, which also opens the door to Android and
   web via Emscripten).
2. **Widescreen + QoL** — render more of the scene than the GBC's 160×144, plus
   conveniences like faster text, run toggle, and improved input.
3. **Data-driven content** — cards, decks, boosters, maps, scripts, and text
   editable in external tools, not hand-edited assembly.
4. **Expandable** — new card sets and new levels without touching engine code.

## The two upstream pillars

The project deliberately builds on two existing open-source projects rather than
re-deriving anything:

| Pillar | What it is | Role here |
| --- | --- | --- |
| [`pret/poketcg`](https://github.com/pret/poketcg) | Clean-room **disassembly** of the game (GB assembly), assembles byte-identical to the retail ROM with RGBDS. | **Source of truth** for every data format and the reference build. |
| [`arcanite24/gb-recompiled`](https://github.com/arcanite24/gb-recompiled) | **Static recompiler**: decodes GB/LR35902 code and emits portable C + an SDL2 runtime. Includes a native-patch SDK, deterministic data-mod packages, and host presentation. | **Cross-platform runtime**, widescreen, and QoL hooks. Its "Crystal Recompiled" port is the working template. |

There is a third relevant resource, [`pret/poketcg2`](https://github.com/pret/poketcg2)
(the Japan-only sequel), which is useful for future card/feature backports and for
understanding format evolution.

### Why recompilation, not a from-scratch C decomp

"Recomp" projects in the N64/GB community mean **static binary translation**:
analyze the original machine code and emit native code, keeping the original
game logic intact. This is what `gb-recompiled` does. The alternative — a full
**source decompilation** in the style of `pokecrystal` (hand-written C that
compiles to matching assembly) — would require reconstructing the entire engine
in C, an order-of-magnitude larger effort. `pret/poketcg` is a *disassembly*
(assembly source), not a C decomp, so there is no C source to port.

**Decision: build on `gb-recompiled` for the runtime.** This gets us a working,
cross-platform, widescreen-capable native build quickly, and it already has a
native-patch + data-mod SDK that maps directly to the QoL and content-expansion
goals. The disassembly remains the authority for understanding and re-encoding
the game's data.

## The three layers

### 1. Ground truth (disassembly)

`vendor/poketcg` assembled with RGBDS produces `poketcg.gbc`. We pin the exact
ROM and treat it as the compatibility oracle. Every data change we make must be
expressible as a diff against this ROM or against its assembly source.

Key data files (confirmed against the upstream tree):

| Content | File(s) | Notes |
| --- | --- | --- |
| Card definitions | `src/data/cards.asm` | `CardPointers` table + per-card records (labels like `ExampleCard:`). |
| Card struct layout | `src/constants/card_data_constants.asm` | Documented byte offsets (`CARD_DATA_*`, attack slots, etc.). |
| Card IDs | `src/constants/card_constants.asm` | one `const` per card id, in `CardPointers` order |
| Decks | `src/data/decks.asm`, `src/data/auto_deck_card_lists.asm`, `src/data/auto_deck_machines.asm` | |
| Booster packs | `src/data/booster_packs.asm` | |
| Maps / tilemaps | `src/data/maps/tilemaps.asm`, `src/data/map_headers.asm`, `src/data/map_objects.asm` | |
| Map scripts | `src/data/map_scripts.asm`, `src/scripts/*.asm` | NPC events / dialogs per room |
| Dialog text | `src/text/*.asm`, `src/data/duel/practice_text.asm` | `tx` macros + charmap |

### 2. Recompiled runtime

`gb-recompiled` provides three mechanisms we intend to use:

- **Native patches** (`NATIVE_PATCHES.md`) — replace/hook discovered generated
  functions with C. This is where **QoL** (fast text, etc.) and **widescreen**
  viewport logic live. Patch code is compiled into the generated project.
- **Data mods** (`DATA_MODS.md`) — deterministic, ROM-free overlays keyed by
  semantic identities, validated against the exact ROM hash. This is the ideal
  vehicle for **content injection** once we extend the target policy to cover
  cards/maps. (v1 currently covers a bounded set for Crystal; we will add a
  Pokémon-TCG target policy.)
- **Port modules / host presentation** (`PORT_MODULES.md`,
  `NATIVE_PRESENTATION.md`) — semantic access to game state and host-native
  rendering. This is the mechanism for **widescreen** rendering and any
  higher-level UI.

### 3. Data pipeline (the translation layer)

This is the piece that makes content editable in external tools. The core idea:

```
CastleDB (.cdb/JSON)  ──compile──▶  cards.asm / card binary  ──▶  ROM / overlay
Tiled (.tmx/.tsx)     ──compile──▶  tilemaps.asm + headers   ──▶  ROM / overlay
```

- **Cards → CastleDB**: each card is a record with typed fields (id, name, type,
  rarity, set, hp, stage, attacks with energy cost/damage/effect, weakness,
  resistance, retreat cost, category, pokédex number, level, description). This
  maps cleanly onto the documented `CARD_DATA_*` struct.
- **Maps → Tiled**: each room's tilemap becomes a Tiled layer; NPC objects and
  warps become object layers; scripts become a structured form (Tiled custom
  properties + a script DSL).
- **Compiler**: Python scripts (`tools/`) read the exported JSON/TMX and emit the
  exact assembly/binary the game expects. This is the inverse of the extractor.

The extractor ships first (read-only, proves we understand the format), then the
compiler (write), then round-trip tests (compile(extract(x)) == x).

## Phased plan

| Phase | Deliverable | Notes |
| --- | --- | --- |
| **0. Foundation** ✅ | Repo scaffold, submodules, pinned ROM, RGBDS build of vanilla game. | Deterministic ground truth; ROM SHA1 verified. |
| **1. Recomp runtime** ✅ | `gbrecomp` the vanilla ROM → native SDL2 executable. | Boots headless; title screen renders; native-patch SDK proven. See `docs/PHASE1_RUNTIME.md`. |
| **2. Card pipeline** ✅ | Extractor (`cards.asm` → JSON), CastleDB schema, compiler (JSON → ASM), round-trip test. | Byte-exact round-trip + CastleDB edit path verified. |
| **3. Map pipeline** ⏳ | Extractor (tilemaps/headers/objects → Tiled), compiler (TMX → ASM), round-trip test. | Enables "levels editable in Tiled". |
| **4. QoL + widescreen** ⏳ | Native patches for QoL; host presentation for widescreen. | Runtime + patch SDK are ready. |
| **5. Expansion content** ⏳ | Ship an example new card set + a new map, authored entirely externally. | Proves the whole loop; note `NUM_CARDS`/`card_constants` must grow for *new* cards. |

## Open questions (to resolve in Phase 0/1)

1. **ROM base** — US `poketcg.gbc` (pret's target) vs. other revisions. We start
   with pret's documented SHA-1 (`0f8670a583255cff3e5b7ca71b5d7454d928fc48`).
2. **Content injection path** — extend `gb-recompiled`'s data-mod target policy
   for TCG (preferred), vs. patching the disassembly and re-recompiling. The
   former keeps a single runtime and fails closed; the latter is simpler for
   large binary additions (new tilesets, card gfx). Likely a mix: data mods for
   records, ROM expansion for graphics.
3. **Widescreen definition** — TCG is menu/duel-screen heavy, not a scrolling
   overworld. Widescreen likely means extending the fixed screens' layout to
   16:9 rather than enlarging a scroll window; needs a design pass in Phase 4.

## Alternatives considered (and rejected, for now)

- **Full C decomp from scratch** — too large; no C source exists.
- **Emulator wrapping (libretro/SameBoy)** — "runs" cross-platform but doesn't
  give native widescreen or a clean data pipeline; recomp gives us a real C
  codebase to patch.
- **Hand-write a new engine** — loses the exact game logic; the disassembly is
  the game, and recompiling it preserves behavior.
