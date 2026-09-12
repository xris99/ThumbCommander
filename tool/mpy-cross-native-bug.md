# mpy-cross native codegen bug — MicroPython v1.19.1 (ARMv6-M)

Status: **fixed in this repo's `tool/mpy-cross`** (see [Fix](#fix-applied-to-this-repo)).
Verified 2026-09-12: the full ThumbCommander game (natives included) now runs on the
original Thumby.

## Symptoms

On the original Thumby (firmware `MicroPython v1.19.1-5-gef54c1377`, RP2040
Cortex-M0+) the compiled `MainGame.mpy` crashed deterministically:

- reboots with "no valid commands"
- `NameError: name '' isn't defined` / `NameError: name '[🗐(C) 2020 Raspberry P...' isn't defined`
  (garbage qstr names)
- `TypeError: unsupported types for __lshift__: 'IndexError', 'int'`
- menu stalling / garbled text

Pattern that isolated the bug:

| Variant | Result |
|---|---|
| `MainGame.py` as **source** (.py) | runs perfectly |
| same code as **`.mpy` on Thumby** (1.19.1, `-march=armv6m`) | **crashes** |
| same `.mpy` on **ThumbyColor** (1.27, `-march=armv7emsp`) | runs perfectly |
| `ship.mpy`, `grayscale.mpy` (both 1.19.1 ARMv6M) | run fine |

## Root cause

A **one-line code-generation bug in upstream MicroPython v1.19.1**, in
`py/asmthumb.c`, function `asm_thumb_add_reg_reg_offset()` — the 3rd branch,
i.e. the ARMv6-M fallback used for 16-bit constants ≥ 256:

```c
} else if (reg_dest != reg_base) {
    asm_thumb_mov_rlo_i16(as, reg_dest, offset << offset_shift);
    asm_thumb_add_rlo_rlo_rlo(as, reg_dest, reg_dest, reg_dest);   // BUG: 3rd arg must be reg_base
}
```

It is reached from `asm_thumb_ldrh_reg_reg_i12_optimised()` (qstr loads,
`shift = 1`) and `asm_thumb_ldr_reg_reg_i12_optimised()` (object-table loads,
`shift = 2`) when the scaled offset doesn't fit the two smaller branches:

- qstr load: `2·(v−31) ≥ 512` → **qstr index `v ≥ 287`**
- obj load: word offset ≥ 287

The emitted `adds rD,rD,rD` (self-add) **drops the base register r6** (the
qstr-table pointer, `REG_QSTR_TABLE = REG_LOCAL_3`). The following
`ldrh rD,[rD,#0x3e]` then reads

```
address = 4·(v−31) + 0x3e      →  0x466, 0x536, 0x556, ...
```

— i.e. a small **absolute** address. On the RP2040 that range is unmapped
(SRAM starts at 0x20000000, flash at 0x10000000) → **HardFault mid-native,
deterministic and data-independent**. The fault mid-function corrupts the NLR
stack / heap / qstr state, which explains the reboots and the garbage
`NameError` names.

Broken 5-instruction sequence (from the shipped `MainGame.mpy`, qstr 297):

```
movs r0, #2          ; 0x200
lsls r0, r0, #8
adds r0, #0x14       ; r0 = 0x214 = 2·(297−31)
adds r0, r0, r0      ; BUG: r0 = 0x428 (base r6 missing)
ldrh r0, [r0, #0x3e] ; reads absolute 0x466 → HardFault
```

The same qstr in the 1.27 build (correct, single 32-bit instruction):

```
ldrh.w r0, [r6, #0x252]      ; r6 + 2·297 = qstr slot 297
```

### Provenance

The repo's `tool/mpy-cross` is built from the fork
`TinyCircuits/micropython @ ef54c1377` = **vanilla v1.19.1 + 5 commits**
(`git diff HEAD~5 --stat` shows only `README.md`, `mpy-cross/main.c` and
`ports/rp2/boards/THUMBY/` touched — `py/` is pristine). So this is an
**unmodified upstream v1.19.1 bug**; later upstream versions (verified in
1.27) pass `reg_base` correctly.

### Why exactly this pattern

- **Only ARMv6M**: the buggy 16-bit fallback exists only in the ARMv6-M
  encoder. ThumbyColor compiles with `-march=armv7emsp`, which uses the
  32-bit `ldrh.w` path — unaffected.
- **Only large qstr tables**: a module must load a qstr with index ≥ 287.
  `MainGame` has 421 qstrs → affected; `ship.mpy` and `grayscale.mpy` have
  smaller tables → no site ever reaches that branch → they run fine on the
  same firmware.
- **`.py` source**: bytecode, no machine code → immune.

## Evidence

Full census of all 66 native blobs in every build artifact (capstone walk with
100 % coverage, 0 undecodable words; a site = a 16-bit `add rX,rX,rX`
immediately followed by `ldrh rX,[rX,#0x3e]` / `ldr rX,[rX,#0x7c]`):

| File | Build | Buggy sites |
|---|---|---|
| `build/thumby_old31k/.../MainGame.mpy` (the crashing one) | 1.19.1 ARMV6M | **85** (12 of 15 natives) |
| `build/thumbycolor/.../MainGame.mpy` | 1.27 ARMV7EMSP | 0 |
| `build/thumby_nonative/.../grayscale.mpy` | 1.19.1 ARMV6M | 0 |
| `build/thumby/.../ship.mpy` | 1.19.1 ARMV6M | 0 |
| full `MainGame.py.orig`, old compiler | 1.19.1 ARMV6M | **189** (23 of 24 natives) |
| full `MainGame.py.orig`, **fixed** compiler | 1.19.1 ARMV6M | **0** |

Rebuild differential (old vs fixed compiler, same source): the two `.mpy`
files differ in **exactly 189 two-byte words and nothing else** — each a
`adds rX,rX,rX` → `adds rX,rX,r6` inside the 5-instruction sequence above
(`movs rD,#hi; lsls rD,#8; adds rD,#lo; adds rD,rD,r6; ldrh rD,[rD,#0x3e]`).
Header, qstr/object tables, preludes, instruction counts and file sizes are
byte-identical. The fixed build produced byte-identical output from both the
throwaway copy and the user's fork, so the fix is fully characterized by that
one line.

## Fix applied to this repo

1. One line in the fork `/Users/christian/build/mp-thumby-mono/py/asmthumb.c:470`
   (3rd operand `reg_dest` → `reg_base` — the same fix later upstream):

   ```diff
            } else if (reg_dest != reg_base) {
                asm_thumb_mov_rlo_i16(as, reg_dest, offset << offset_shift);
   -           asm_thumb_add_rlo_rlo_rlo(as, reg_dest, reg_dest, reg_dest);
   +           asm_thumb_add_rlo_rlo_rlo(as, reg_dest, reg_dest, reg_base);
            } else {
   ```

2. `mpy-cross` rebuilt there (`make` → `MicroPython v1.19.1-5-gef54c1377-dirty`).

3. `tool/mpy-cross` in this repo replaced with that build. The original
   (buggy) binary is kept as `tool/mpy-cross.bak-orig`.

The emitted `.mpy` format is unchanged (v6); the firmware's reader needs no
modification. `tool/deploy.py` picks up the fixed compiler automatically for
the Thumby target (`-march=armv6m`).

## Notes

- `ship.mpy` / `grayscale.mpy` / the ThumbyColor build needed no change;
  recompiling them with the fixed compiler is also safe.
- If the **firmware** is ever rebuilt from this fork, the same one line in
  `py/asmthumb.c` is relevant for natives compiled into the firmware itself.
  The current flashed firmware contains no broken native (it boots and runs
  fine) — no firmware action is required now.
- Secondary hardening, unrelated to this crash: `py/nlrthumb.c`
  (`nlr_jump`, empty clobber list) is fine with the current toolchain (plain
  function call, no LTO) but should gain a `"memory"` clobber if the fork is
  ever built with GCC 14+ / LTO.
- Revert: `cp tool/mpy-cross.bak-orig tool/mpy-cross` (and undo the fork edit).
