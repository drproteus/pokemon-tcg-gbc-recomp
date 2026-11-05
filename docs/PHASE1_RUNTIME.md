# Phase 1 — Native runtime (status)

Status: **working** on macOS (arm64). The vanilla game boots, renders the title
screen correctly, and runs as a native SDL2 executable via static
recompilation. The native-patch SDK is verified end-to-end with a spike hook.

## What works

The full pipeline is reproducible from the disassembly with no copyrighted ROM
input:

```
vendor/poketcg (RGBDS)  ->  poketcg.gbc        (SHA1 0f8670a5..., byte-identical)
vendor/gb-recompiled    ->  gbrecomp binary
poketcg.gbc + poketcg.sym --gbrecomp-->  build/recomp/  (portable C + SDL2 runtime)
build/recomp            --cmake+ninja-->  build/recomp/build/poketcg  (native exe)
```

One command:

```bash
tools/recompile.sh --run
```

The native executable boots headless, runs guest frames, allocates cartridge
RAM, and loads/saves battery saves (`.sav`).

## How it was verified

- `poketcg.gbc` SHA1 matches `vendor/poketcg/rom.sha1`
  (`0f8670a583255cff3e5b7ca71b5d7454d928fc48`).
- `gbrecomp` discovered ~77k functions / ~594k IR blocks and emitted ~125 C
  translation units.
- `build/recomp/build/poketcg --headless --no-audio --limit-frames 120`
  exits 0 and dumps a sane machine state (PC `0x0271`, SP in WRAM, frames
  completed, battery RAM loaded/saved).

### Rendering (title screen)

Captured guest frames (`--dump-frames`) and decoded the pixels directly. By
~frame 1200 the game is on the title screen; the dominant colors are exactly
the game's title screen:

| Color | Share | What it is |
| --- | --- | --- |
| `(230,230,197)` cream | 58% | title background |
| `(0,0,0)` black | 11% | text / outlines |
| `(255,180,0)` orange | 10% | title character body |
| `(0,82,222)` blue | 8% | title character wings / logo blue |
| `(255,0,0)` red | 4% | accents |
| `(255,255,0)` yellow | 0.3% | logo yellow |

A `--trace-entries` run confirms the boot path reaches the title screen: it
executes `SCENE_TITLE_SCREEN` → `LoadScene`, starts `MUSIC_TITLESCREEN`, and
runs the title-screen sprite animation (`DrawSpriteAnimationFrame`,
`_HandleAllSpriteAnimations`, `HandleAnimationFrame`) before waiting for
"Press Start". A PNG of the title screen is saved at
`build/recomp/title_screen.png` for eyeballing.

### Native patch (spike)

`native-patches/spike/` binds `WaitForVBlank` (`gbfn:v1:0000:0264`, the game
calls it once per frame) with pre/replace/post callbacks that count and log to
stderr. The patch:

- validates against the exact ROM SHA-256 at generation time, and
- fires **114 pre / 113 post** invocations across a 120-frame headless run
  (~once per frame; the final frame's post is pending when the frame limit
  hits).

This proves the full native-patch dispatch path: manifest → exact-ROM binding →
C callback → `gb_native_call_original` preserving guest timing. Regenerate with:

```bash
tools/recompile.sh --patch native-patches/spike/manifest.json
```

> Note: the runtime's `ctx->hram[i]` maps to HRAM `0xFF80+i`, which in this game
> is `hBankROM`/`hBankSRAM`/`hBankVRAM`/`hDMAFunction` — do **not** use it as
> scratch (the synthetic example in `gb-recompiled` can, this game cannot).

## Caveats (experimental recompiler)

`gb-recompiled` is explicit that it is not a whole-catalogue compatibility
claim. For this ROM it reported:

- `[ERROR] Undefined instruction at <bank>:<addr>` for several addresses, and
- `[ANALYSIS] Unresolved JP HL at ...` in a few places.

Per its design, code it cannot statically compile falls back to the bundled
interpreter at runtime, so execution continues. The counts and addresses should
be tracked as we validate specific screens; the presence of fallbacks means
performance and accuracy are not yet final.

## Next steps (Phase 1 remainder)

1. **Symbol mapping quality** — the disassembly `.sym` was passed, so generated
   functions carry semantic names; catalog which high-value functions (duel
   engine, card effect commands, menu code) resolve cleanly.
2. **Real QoL native patch** — replace the spike logger with an actual change
   (e.g. text speed) via the bounded gameplay-mutation API.
3. **CI** — reproduce build + headless boot in GitHub Actions (macOS/Linux/Win).
4. **Widescreen design pass** — defer full implementation, but document the
   presentation surface (see `docs/ARCHITECTURE.md`, Phase 4).

## Output notes

- `build/` is git-ignored: the recompiled executable embeds the ROM, so
  generated artifacts stay local and are never committed.
- `poketcg_metadata.json` is large (~1.4 GB) — it is a generated analysis
  artifact, also under `build/`.
