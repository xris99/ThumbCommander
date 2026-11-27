# 12. Memory on the device

RAM is the tightest resource of this port. The first run on a real
ThumbyColor ended in `MemoryError` at launch; this chapter records
what was learned, how the game budgets its heap since, and what to do
when a new feature needs room.

## 12.1 The numbers from a real device

**The first build** died at launch. Its log (figures taken without
collecting first, so they include garbage):

| Moment | Free heap (bytes) |
|--------|-------------------|
| engine audio and cutscene helpers loaded | 187,376 |
| game modules for the menus loaded, tables read | 88,672 |
| crash while allocating the third pool of the frame cache | 43,600 |

It failed asking for 8,000 contiguous bytes while 43 KB were free in
total: the heap was **fragmented**, and the margin was small as well.

**The clean build** - the shape this chapter's plan defends - flies.
Its `WC mem` lines, each taken after a collection, on the same
device:

| Line | Free heap | Cost of the step | What the step is |
|------|-----------|------------------|------------------|
| start | 230,768 | | the engine is up; `MainGame` and `wcdata` are loaded |
| buffers | 188,512 | 42,256 | frame cache and cockpit buffer |
| code | 126,096 | 62,416 | `ui`, `wcgfx`, `flight`, `world`, `ai`, `wcmath` (53,929 bytes as `.mpy` files: loaded code takes about 1.16 times its file size) |
| ready | 96,896 | 29,200 | ship and AI tables, two fonts, palette, sound handles |
| launch | 87,776 | 9,120 | `campaign` module, saved game, campaign and mission records; the briefing is already released |
| flight | 63,360 | 24,416 | the world (44 objects), the pilot AI, sprite set tables |
| landed | 64,896 | | the `Flight` object is gone; the world is still held for scoring |
| launch (second sortie) | 87,744 | | 32 bytes below the first: nothing leaks between flights |
| flight (second sortie) | 63,456 | | |

So: **about 231 KB of heap when the game starts, 63 KB free while
flying, 88 KB free in the menus.** Two `launch` lines 32 bytes apart:
nothing leaks between flights.

The same build then died at the title on a second ThumbyColor. That
device runs its engine some 11 KB heavier, so its lines read `start`
222,864, `buffers` 180,608, `code` 114,752, `ready` 85,408, and when
the title built its own world only 17,136 bytes were left. The
allocation that failed was a fresh `wcdata.Ai()` reading `ai.wc`:
2,560 rounded bytes asked for inside `titleseq._title_world`
(titleseq.py:2175). The file is 2,319 bytes in the current assets -
that log ran a stale conversion - but the shape stands: the cinematic
needs some 70 KB, its module and tables, its own AI tables, a
44-object world, and 47 KB of the missing room was held by the flight
window, which a title does not use: the loaded `flight` and `ai`
modules (some 30 KB of code) and the pilot tables `Game` had read at
start-up. The fix, in 12.2 step 2: the flight and AI code leaves
before the cinematic's tables arrive and returns lazily at launch -
and it is still the plan. What the release was counted on never
showed when the modules stayed boot-claimed: the pop gave back the
modules' objects only, some 2 KB - not the 30 KB of code (fact 1).

The build that let the flight code go cleared the title and died at
the first briefing: 39,552 left uncollected when it failed. The
request was this mission's briefing packet, 9,883 bytes read whole by
`wcdata.briefing_packet`: re-importing the flight code right after
the cinematic had landed it inside the heap the title had cut up, so
the menus stayed too fragmented for the packet to find one piece wide
enough. The release now spans the whole flight-free stretch -
menus, briefings, cut scenes - and the code comes back at launch,
where `launch` is high again by the room it was owed (12.2 step 4).

The build that carried the briefing fix cleared the title on that
device and died at the talking head of the first briefing: about 51
KB left uncollected when it failed. The ask was 7,936 bytes inside
`wcdata.Head` reading a face's file: head files run 13.4 to 18 KB and
`load` hands back one block of their size (wcdata.py:28) - the same
class of ask as the packet's: a file-sized block the heap, chopped by
the title's landing and the flight's leftovers, had in no one piece.
This is the failure the phase-owned plan exists to answer: before the
conversation imports, everything a flight or cutscene held is popped
and collected (MainGame.py:407-409), so the head's ask lands in room
that is all its own.

The restored build, on the device (2026-11-27): `start` 223,104,
`buffers` 193,184 - the frame cache, 29,920, the one standing
reservation; `code` 190,512, a step of 2,672 because the boot holds
only `ui` and `wcgfx` - the flight code is not claimed until launch
(12.2 step 2), so the boot is some 60 KB lighter than the table's
clean build; `ready` 161,120 - the tables step, 29,392, the same
size as the clean build's; `pop` 156,352; `title` 52,192 - the
cinematic's landing, some 104,160: `titleseq` and the world and math
it pulls together with the 14,336-byte canvas claimed on the fresh
heap. The title's own steps print `preworld` 51,088 and `font`
28,128. The intro and the title ran through clean - the first device
run ever to clear the whole opening. The build then died at the
**third** talking head of the first briefing: `MemoryError:
allocating 15,360 bytes` in `talk.load_face` through `wcdata.load`,
`FREE 66,336` taken without collecting. The shape is facts 1 and 3
together: the dropped faces' blocks were dead but not freed -
MicroPython returns them only at a sweep - so their some 30 KB sat
inside the free total, and no piece was wide enough for the next
face. The fix, in 12.2 step 3: `load_face` collects the moment it
drops a face, so exactly one head's block is ever live and the hole
the previous face leaves is re-made before the ask.

The build with the one-face rule cleared the heads and the launch
scenes on the same device and died in the **flight's construction**:
`launch` 44,144, then `MemoryError: allocating 12,308 bytes` at
`flight.load_cockpit` inside `Game.fly`, `FREE 19,920` taken without
collecting. The arithmetic names the thief: 44,144 minus 19,920 is
24,224 - the whole flight build, the same figure the clean table pays
at its `flight` line - so at the `launch` line the flight had already
been paid for before it was asked for. The clean build read 87,776 at
`launch`; this one read 43,632 less because the flight's code was
already resident when the launch scenes ran: `launchseq` imported
`sky`, `flight` and `world` with its own module, so the launch
scenes' `import scramble, launchseq` landed the flight's some 36 KB
with them (fact 1) before `Game.fly` ever got to claim that code where
the room is, and `scramble`'s 12,288-byte frame scratch rode through
the launch held in its module's globals. The cockpit's 12,308-byte
ask then landed in a hole no wider. The fix is the same discipline one
link deeper: the launch scenes' modules leave by name and pop before
the flight is built (`MainGame.py:497-505`, `:663-666`), `launchseq`
imports the sky and the flight code only for its 3-D approach and
guards the ask (`launchseq.py:258-267`), the flight lets its own code
go again at the flight's end so every post-flight scene re-claims it
in a guarded import (`MainGame.py:726-730`), and a cockpit ask that
finds no hole gives the flight the full-screen view instead of ending
the game (`flight.py:217-220`).

The build that carried the flight fix cleared the flight on the same
device - `launch` 133,344, the launch room entire again (some 89 KB
returned by the release), a launch-to-flight step of 91,984 landing
the flight's code, its construction and the cockpit's 12,308,
`flight` 41,360 free while flying, `landed` 72,400 as the flight's
objects go back - and died at the **ejection's chase**:
`MemoryError: allocating 1,488 bytes` inside `ejectseq._dirv`
through `ejectseq.eject` and `_chase`, `FREE 6,400` taken without
collecting. The same disease one scene later, named by the same
arithmetic: 72,400 minus 6,400 is 66,000 - what `import ejectseq`
had claimed by landing its module-top imports: `ejectseq` itself
some 8.5 KB, `scramble` and its 12,288-byte scratch 22.2, `sky`
5.9, `flight` 15.2, `ai` 14.8. The room the flight had released was
spoken for before the scene drew its first picture, and the
direction bases' ask found no piece in what was left (fact 3). The
chase never needed the flight module: its projection mirrors
`flight.py:262-375`, `:194-230` and `:103-117` in its own code - it
had borrowed only the flight's two focal lengths, two colours, its
explosion sets and its truncating divide. The fix is step 2's rule
one scene deeper: those numbers and `_tdiv` stand mirrored in
`ejectseq.py:139-155`; the scene imports what it draws with inside,
for itself - `scramble` in `eject` (`ejectseq.py:933-938`) and
`stranded`, `sky` in `_chase` (`:680-685`) - every ask guarded, no
room and the scene plays its simpler path instead of ending the
game: no seat scene, a chase without stars (`:746-752`), a chase
skipped when the bases find no hole (`:756-762`), the chase's sort
tuples swept one pass wide by a `collect()` in its loop
(`:855-856`). The flight itself was already gone when the scene
started: `fly` had released the `Flight` instance with its sprite
sets, the cockpit, the star field and the code (`MainGame.py:714-
730`); what stays is the `World` the chase reads the ship from and
the campaign scores with, gone after `post_mission`
(`:614-615`). `mission` now checks `sys.modules` before popping
`scramble` after the scene - if the guarded import never fitted
there is nothing to pop (`MainGame.py:592-597`, `:605-610`). The
device's rate line printed that run: 15.1 pictures a second, 6.2
turns, worst 79 ms.

**The boot-arena experiment.** One round of work - reverted on
review, 2026-11-27 - held the whole heap's big buffers in one
50,040-byte reservation claimed at start-up, carved into regions
every scene borrowed from. It failed in exactly the way it was meant
to prevent, and the device logs say so:

- **intro**: the `scramble` frame scratch asked 12,288 bytes for its
  `bytearray(VIEW_N)` with 23,552 free, none of them in one piece -
  the reservation had bought the briefing's room by eating the
  intro's headroom (fact 3).
- **title import**: the module's globals dict, resizing its hash
  table to prime 167 slots (`WHITE = 0xFFFF`, `titleseq.py:1795`),
  asked 1,336 bytes with `FREE 18,416` taken without collecting. The
  module's 99 bytecode arrays, landed earlier in the same import,
  had carved every free run narrower than 1,336 bytes. And the pop
  before the import had returned nothing worth naming: boot-claimed
  modules are on no pop list (fact 1's second corner).
- **title playback**: the file system's own buffer for one `open` -
  1,148 bytes - asked during a sprite-set load (`titleseq._sset`
  into `wcdata.SpriteSet`) with about 13 KB free, nothing of it wide
  enough.

`__slots__` on `Lite` proved the device does not honour the
declaration (fact 2): the same 296-byte attribute-table ask came back
at `world.py:281`, the first store under the slotted class.

The experiment is gone; `bootmem.py` does not exist. The heap is
asked for real blocks again, and 12.2's plan is the one the clean
build's numbers came from - every large buffer owned by the phase
that uses it, freed whole when the phase ends, so each phase starts
with the heap whole and the medium asks - the 1,148-byte open
buffer, a table step, a file-sized read - find one piece wide enough
where they land. What survives from the experiment: these facts, the
stat-instead-of-open rule (12.4), and the deferral and pop discipline
of 12.2 step 2.

Three facts explain most of it:

1. **Code lives in RAM, and it comes back only when nothing holds
   it.** A `.mpy` read from the file system copies its code to the
   heap: the byte arrays, the function objects naming them, the
   module's dict holding those functions. `sys.modules.pop` plus a
   collection frees all of it - once every object of the module is
   dead. A function stays alive as long as anything holds it, and it
   holds its module's globals dict with it; so a class instantiated
   by something that outlives the pop keeps the module's dict, and
   every byte of its code, resident too. The floor build measured
   this corner: its release was owed some 30 KB and grew the room by
   some 2 KB - something still held the flight code and the release
   never came; what held it was not chased. The crash build measured
   the other corner: a device that booted straight from the intro to
   the title had never loaded `flight` or `ai` at all, so its `pop`
   released nothing and its number was only what the intro had spent.
   What the two logs teach: a boot claim never returns by pop - the
   module is not on any pop list - and it lands while the heap is
   whole, then carves the free list for everything that comes after
   (fact 3). The lever is to never claim at boot what a phase imports
   anyway: the phase's fresh import lands in one large run, and it is
   the earlier phase's release that opens the run (12.2 step 2).
2. **An instance costs RAM per attribute.** MicroPython stores
   instance attributes in a hash table of 8 bytes per slot, sized in
   steps (..., 29, 37, 47, 59, 73, 97, ...). An object with 76
   attributes takes a 97-slot table: 776 bytes, about 1 KB with its
   lists. `__slots__` does not change that in MicroPython, and the
   device was made to prove it (fact 2's log): the port declares the
   slots anyway - CPython honours them, so PC runs are exact - but
   every world object's fields are plain attributes on the device,
   and the table step is paid per instance. The lever is few
   attributes and fresh room at every phase start, not storage
   routed away (12.3).
3. **The allocator never moves a block.** Whatever is allocated late
   lands in the gaps between older blocks; a large request can fail
   although the sum of the gaps would be enough. The collector is
   mark-and-sweep: it frees dead blocks and merges them with
   neighbouring dead ones, but it never moves a live object, so
   there is no compaction to run - defragmenting by relocation is
   not a lever. What the game does get is the hole re-forming at
   every phase boundary where popped modules and phase buffers die
   whole; the lever is keeping every long-lived large block in one
   piece from the start and giving every phase buffer back whole
   (12.2 step 3).

## 12.2 The memory plan

`MainGame.py` documents and implements it at the top of the file:

1. **One standing reservation: the frame cache.** Right after
   `wcdata` is imported - and before any other game module - the game
   allocates `CACHE` (`MainGame.py:65`), the largest block it ever
   needs, once, for the whole session. Nothing else is held at
   start-up: no arena, no boot buffer, no boot-loaded flight code.
   The cache's **content** is forgotten at every phase boundary -
   `CACHE.reset()` before the title imports (`MainGame.py:255`),
   after the title (`MainGame.py:269`), when a flight is built
   (`flight.py:120`) and at flight end (`MainGame.py:715`) - so no
   stale frames ride into the phase that follows and nothing a
   conversation or a cutscene cached is still held when it is gone.
2. **Code is claimed where the room is, and let go when the scene
   is done.** `flight` and `ai` are not imported at start-up
   (`MainGame.py:70-78`): a cinematic never flies, so holding them at
   boot spends the title's room on a flight no one is flying yet -
   exactly how the floor build's title died (12.1). `Game.fly`
   claims them at launch, where the room is large again - the launch
   scenes' release has just re-formed it, and nothing has claimed the
   flight's code before that (the device's launch crash paid it early,
   12.1); `Game.options` borrows `flight` briefly for the speed names -
   `ai` comes with it (`flight.py:29`) - and lets both go again when
   the menu closes (`MainGame.py:350-352`). The flight's end lets
   `flight`, `ai` and `sky` go again (`MainGame.py:726-730`), so every
   post-flight scene re-claims the room and lands the code in guarded
   imports of its own: the fly-off's 3-D approach takes it for itself
   (`launchseq.py:258-267`, `MainGame.py:547`); the eject chase
   never lands the flight at all now - its projection is mirrored
   in its own code (`ejectseq.py:139-155`) and its room pays only
   the scene's own code, claimed guarded (`MainGame.py:571-574`).
   No room, the simpler scene, never an out-of-memory ending the
   game. A scene module must never import the flight code at its
   own top: `launchseq` did, and the launch scenes paid the flight's
   room before the flight was built (12.1); it imports lazily now
   (`launchseq.py:69-77`). `ejectseq` did the same with `scramble`,
   `sky` and `flight` at its top, and the eject chase paid their
   code in the room the flight had just freed (12.1's eject crash);
   it lands nothing at its top now and imports what it draws inside,
   guarded. The title's pop list
   drops them before its import (`MainGame.py:248-250`). A pop returns
   a module in full, code included, once nothing holds it (fact 1),
   and a re-import pays its landing again - so the flight code is paid
   at every launch and the flight-free stretch holds neither. `world`
   and `wcmath` are not at boot either: `titleseq` pulls them itself,
   so a boot copy would spend the title's room on a world the title
   has claimed for itself.
3. **Every other large buffer belongs to the phase that uses it:**
   claimed when that phase starts, after the previous phase's release
   has made the heap fresh, and given back whole when the phase ends.
   Nothing is ever borrowed from a standing reservation.
   - the title's text canvas, 128 x 112 = 14,336 bytes, claimed at
     `MainGame.py:262-265` right after the pop and collect, and given
     back at `MainGame.py:270`; if the ask fails the title runs its
     text-less path (`titleseq` falls back) instead of raising;
   - the cockpit, `D.CK_SIZE` = 12,308 bytes, claimed only when the
     cockpit option is on and its file exists (`flight.py:208-220`),
     and guarded: if no hole is wide enough the flight takes the
     full-screen view instead of raising (`flight.py:217-220` - the
     device's launch died on this very ask, 12.1) - the flight's own
     buffer, given back with the flight (`del fl`, `MainGame.py:714-716`);
   - a conversation's packet (8 KB on average, 11.3 KB at most) read
     whole into the heap per briefing (`wcdata.briefing_packet`), a
     face's picture 13.4 to 18 KB - each face change drops the
     previous head, collects it back into the heap the same breath,
     and only then claims the new block, so one face's picture is
     ever live (`talk.py:499-519`; the device's third-face failure,
     12.1's restored-build log), the backdrop's 7,936-byte view once
     per conversation (`talk.py:485-489`) - all the conversation's
     own, given back when `Game.talk` ends (`MainGame.py:417-418`);
   - the scramble scratch, 12,288 bytes (`scramble.py:94`), claimed
     with the module and given back whenever the module is popped and
     collected: the title's pop list, the launch scenes' release
     before `fly` (`MainGame.py:504` with `fly`'s pops at
     `:663-666`) and every post-flight release (`:526-528`,
     `:559-561`; after an ejection only when the guarded import
     fitted - `:592` `sys.modules` check, pop at `:595-596`). Held
     in the module's globals it rode
     through the launch in the crash build (12.1).
4. **Every phase starts with the room entire.** Before a phase's
   big claims, everything the previous phase held is popped and
   collected, so the phase's imports and buffers land in one fresh
   run instead of pieces carved out of a fragmented free list:
   - the title pops `flight` and `ai` plus the ten modules a flight
     or a cutscene may have left behind - the intro's `introfx`, the
     launch scenes, the interpreter and the end scenes
     (`MainGame.py:248-256`) - resets the cache and collects (the
     `pop` line);
   - the conversation pops `flight`, `ai`, `world`, `wcmath`, `sky`
     and `scene` (`MainGame.py:407-409`): the head asks some 18 KB in
     one block and the heap must be swept clean for it; a later
     mission re-imports what it needs and pays its landing again -
     the price of starting each phase fresh;
   - the flight pops `scene`, `launchseq` and `scramble`
     (`MainGame.py:663-666`) after `mission` has dropped those last
     two names from its own frame first (`:504`): a pop returns a
     module only when nothing holds it (fact 1), and the live frame's
     names held these - `launchseq`'s globals holding `scramble`,
     whose globals hold the 12,288-byte scratch; the pop with its
     collect is what re-forms the launch room the flight claims for
     its code and cockpit (the device's crash build skipped this step
     and died, 12.1);
   - everything else the previous scenes held - `talk`, `introfx`,
     `titleseq`, `ejectseq`, the funeral and the death scene each
     dropped themselves in the function that ran them, and the launch
     scenes' sprite sets are freed by `scramble.cleanup` and
     `launchseq.cleanup`.
   - at the end of every scene its own module goes the same way -
     `del` the local name, `sys.modules.pop`, `collect`
     (`MainGame.py:228-229`, `:271-273`, `:417-418`, `:525-528`,
     `:558-561`, `:586-597`, `:726-730`, `:764-766`): one scene is one
     class, imported for its turn, deleted completely when its turn
     ends, and a collection frees its bytes without leaving fragments -
     no scene's buffers outlive the scene, and after each step -
     cutscene, talking heads, and above all the flight - the heap
     starts fresh. The flight's `world` stays only for scoring, then
     `del world` and `collect` (`MainGame.py:614-615`).
5. **Collect early.** `gc_pace()` sets `gc.threshold` at flight start
   so a collection runs whenever half of the free heap has been used
   up, instead of when the heap is full. MicroPython has no reference
   counting, so a scene that does not fly must collect itself:
   `titleseq._pace` (titleseq.py:1128) sweeps once per drawn frame,
   keeping the cinematic's garbage one frame wide instead of letting
   it pile up until the title's tables no longer fit.

What changed against the first version, and the estimated effect:

| Change | Saves |
|--------|-------|
| frame cache 10 x 2,112 + 3 x 8,000 = 45.1 KB -> three pools, 28.4 KB (below) | 16.7 KB |
| `world.Lite` for the 34 non-ship object slots (12.3) | about 20 KB |
| briefing packet and `talk` module not held during the flight | 10 to 16 KB |
| cockpit read straight into its buffer (no second copy while loading) | 12 KB of peak |
| unused `Obj` fields removed (72 attributes: a 73-slot table) | about 2 KB |
| no boot arena: the room is not carved at start-up; every large buffer exists only while its phase needs it and goes back whole | all of the arena's 50 KB, and the fragmentation it caused |

The savings are estimates from sizes - the first build never got far
enough to be measured the same way. What is measured is the result
(12.1): the whole flight setup costs 24 KB on top of the frame
cache. The only large asks left in a session are code: `flight`, `ai`
and `sky` landing at every launch that claims them - 30,905 bytes as
`.mpy`, some 36 KB once loaded [estimate] - paid into the hole the
launch scenes' release re-forms, and landed again by the post-flight
scenes that need it, each in its own guarded import (12.2 step 2). A re-import after a
pop pays its landing again in full - a popped module gives its code
back once nothing holds it (fact 1) - so the flight code is paid at
every launch. What stays resident is what nothing pops: `world` and
`wcmath` stay loaded once the title has pulled them in, for the
mission flow, and every later scene is that much narrower; the rest
comes and goes with its scene.

### The frame cache

`wcdata.POOLS = ((10, 640), (7, 2112), (2, 3600))`:

| Pool | Slots x bytes | Holds |
|------|---------------|-------|
| tiny | 10 x 640 | bolts, missiles, sparks, debris |
| small | 7 x 2,112 | fighters, explosions |
| big | 2 x 3,600 | capital ships |

A frame goes to the smallest pool it fits; the least recently used
slot of that pool is replaced. A frame larger than the last pool
cannot be shown, so the converter guarantees the limit:
`MAX_SHIP_PIXELS = 3600` in `tool/wc1_convert.py` stores a capital
ship coarser until its largest view fits (the Tiger's Claw at `res`
56, the Exeter at 60, four others at 70-78; all fighters stay at 80).
**The two constants belong together.** At start-up `assets_stale()`
reads the header of every ship set and shows a notice if the data on
the device was converted for a larger buffer.

Measured on the PC over all 76 missions with a frame drawn every
turn: 0.25 sprite file reads per frame on average, at most 7 in one
frame, 3 or more in 1.3 % of the frames. The earlier 45 KB layout
did worse on the same run (0.33 reads per frame, at most 13, 1.9 %),
because it had 13 slots where this one has 19: small sprites no
longer occupy fighter-sized slots. A read is a file open, seek
and read on flash - if frames stutter when many objects appear at
once, give the tiny or small pool more slots before anything else.

## 12.3 Light objects

`World.o` has 44 slots: 0-9 are ships (`world.Obj`, every field),
10-43 are bolts, missiles, explosions, debris, rocks and mines
(`world.Lite`).

A `Lite` instance owns only the fields named in `world.LITE` (plus
`i` and `m`); all other `Obj` fields exist on `Lite` as **class
attributes** holding the value `Obj.clear()` would give them. Code
that reads `ob.rating` or `ob.sh[0]` on a bolt gets the default, as
before, and no instance attribute is created. `Lite` declares
`__slots__`: CPython honours it, so the PC measures the small owned
set exactly - but the device does not honour the declaration (fact
2), so on the device every `Lite` gets its attribute table and the
296-byte step is paid per instance. What makes that step survivable
is not routed storage - it is the fresh hole at every phase boundary
(12.2 step 4): `Obj` is built inside a flight, whose room was just
made, and the title's world is built after the title's own release.
The rule that keeps the defaults honest:

> Never write a field through a `Lite` object unless it is in
> `world.LITE` and reset in `Lite.clear()`.

A write to another field would land in the instance's own table,
where `clear()` does not reset it, so the value would leak into
whatever reuses the slot. On the PC the `__slots__` declaration
refuses such a write outright; `tool/wc1_check.py` guards every write
and checks that every `Lite` default equals what a fresh `Obj` starts
with (read through `getattr`), then flies every mission. Run it after
touching `world.py` or `ai.py`.

The shield, armour and weapon lists are tuples on `Lite`, so an
accidental `ob.sh[0] = ...` on a non-ship fails loudly.

## 12.4 Rules for new code

- **A buffer above about 2 KB that a feature needs is owned by the
  phase that uses it** (12.2 step 3): claimed when the phase starts,
  after the previous phase has popped and collected, and given back
  whole when the phase ends. The frame cache is the one standing
  reservation; nothing borrows from it. Two features that never run
  at the same time may reuse a buffer by claiming it at each of their
  starts - a talking head and a flight both want about 12 to 18 KB,
  and each claims its own while the other's is gone.
- **Read into buffers** (`f.readinto(buf)`), never
  `bytearray(f.read())` - the second form needs the memory twice.
- **A probe is a `stat`, never an `open`.** `open` allocates the
  file system's own buffer - 1,148 bytes on this device - and a
  fragmented heap refused that ask with about 13 KB free in no
  piece (12.1's playback log). `wcdata.exists` stats
  (`wcdata.py:16-26`). Real reads still open, and the plan is what
  keeps a wide hole ready when the ask lands.
- **Do not hold a file's contents to use a few records.** `seek` and
  read the record (`wcdata.Mission`, `SpriteSet`).
- **Drop a big object only with a collection in the same breath.**
  A dropped object gives its bytes back only at a sweep (fact 1), so
  `self.big = None` followed by `collect()` before claiming the next
  block is what makes it a hole again: `talk.load_face` does this at
  every head change (`talk.py:499-500`), and it is the rule behind
  "after each step the memory always starts fresh" - garbage kept
  without a sweep is heap held, and fact 3 refuses the next big ask
  if the sweep left no piece wide enough.
- **A name bound in a live frame holds its module.** Before a pop,
  `del` every local name the running frame binds to the module (fact
  1) - `mission` drops `scramble` and `launchseq` before `fly` pops
  them (`MainGame.py:497-505`) - and release holder and held
  together: `launchseq`'s globals hold `scramble`, so popping
  `scramble` while `launchseq` is alive returns nothing.
- **A big ask that may find no hole degrades instead of raising.**
  Guard the claim where the buffer is needed and give the scene its
  simpler path when the ask fails: no cockpit but the full-screen
  view (`flight.py:217-220`), the fly-off's deck slide without its
  3-D approach (`launchseq.py:261-267`), the eject module skipped
  and the pilot picked up unseen (`MainGame.py:571-574`), the seat
  scene skipped when `scramble` finds no room (`ejectseq.py:933-
  938`), the chase run without stars when `sky` does not land
  (`ejectseq.py:680-685`, `:746-752`) and skipped when the
  direction bases find no hole (`:756-762`) - a degraded scene is
  still a scene; an out-of-memory ends the game.
- **Classes with many instances get few attributes.** Mind the table
  steps (fact 2). Prefer one `bytearray` or `array` for N things over
  N objects.
- **Code that runs rarely goes in its own module** and is unloaded
  after use, like `talk`: import inside the function, `del` the local
  name, `sys.modules.pop(name)`, `collect()`. A module can only be
  freed if no object of its classes is still alive (fact 1).
- **No allocation per frame in the flight loop**, as before.

## 12.5 Reading the log

The game prints the free heap after a collection at fixed points:

```
WC mem start    after the engine, before the game allocated anything
WC mem buffers  frame cache allocated - the one standing reservation
WC mem code     the boot list's modules loaded
WC mem ready    tables, fonts, sound handles; the menu's baseline
WC mem pop      the title's release done, before titleseq lands
WC mem title    titleseq landed: what the cinematic costs to arrive
WC mem preworld titleseq's own step: before its world is built
WC mem font     titleseq's own step: after its ship art has arrived
                (titleseq.py:2183, :1185)
WC mem launch   at "Launch", after the launch scenes are popped and
                collected and before the flight is built
WC mem flight   flight built: what is left while flying (the flight's
                code and its cockpit buffer are claimed inside this
                step)
WC mem landed   flight objects released
```

Differences between consecutive lines are the cost of each step.
`pop` minus `ready` is what the title's release returns minus what
the intro spent: a pop returns a module in full only when nothing
holds it (fact 1), so read this line expecting the modules' code
back - it is owed only if a live object does not hold it. `title`
minus `pop` is the cinematic's full landing: `titleseq`'s some 33 KB
together with `world` and `wcmath`'s some 41 KB, which arrive on the
same import (the arena build measured this at 79,456 - the landing
does not depend on the arena). `flight` is the number that matters:
it must cover the garbage of a few frames. It was 63 KB in the clean
build, which had paid the flight code at boot; now the code lands
inside the launch-to-flight step (12.2 step 2), so this line reads
some 36 KB below the clean figure by design, and the cockpit's 12.3
KB are claimed inside it only when the hole is wide enough
(`flight.py:217-220` - the flight flies the full-screen view when it
is not). `Lite` keeps the world cheaper than full `Obj` tables
(12.3), and the release before the flight returns the launch room:
the device log 2026-11-27 measured what this line's estimate aimed
at - `launch` 133,344 with the room the release re-formed (some 89
KB returned against the crash build's 44,144), a step of 91,984
into `flight` 41,360 - the flight's code landing, its construction
and the cockpit's 12,308, paid inside the step by design - and
31,040 back at `landed` 72,400. 41 KB is above the 10 to 22 K this
line warned about; the stutter and crash guesses below it (roughly
20 KB stutter from frequent collections, 10 KB crashes in busy
scenes) stay untested [guess - neither limit has been tried].
Compare the `launch` and `landed` lines of consecutive sorties to
catch a leak: the clean build read 32 bytes between two `launch`
lines and nothing leaked.

`main.py` also prints `FREE` when the game dies. That figure is taken
without collecting, so it is a lower bound.

A `.mpy` frame of a traceback prints `line 1`: the bytecode version
the deploy emits (6) carries no line table the firmware prints, so a
crash names the chain of calls but none of its lines - `.py` frames
still show real ones. `tool/deploy.py --lines` compiles with `-b 5`
in the hope the older load path prints real lines again; whether
this firmware loads a v5 `.mpy` at all is untested, so it is a debug
build only - if the device cannot load it, `main.py` prints `ERR`
and `FREE` at the first import. v5 also costs bytes, and not evenly
(measured: `titleseq` +475, `world` +3,915 - 20 percent - while
`scramble` came out 893 smaller), so never ship it.

## 12.6 If it is still not enough

In order of effort:

1. **`-O3 -s` - already in every module of a build, and measured**
   (the deploy compiles with both, `tool/deploy.py`). `-O1` and
   `-O2` compile byte-identical to `-O0`; only `-O3` does anything:
   some 6 to 8 percent off the file (with the deploy's toolchain:
   `titleseq` 20,639 -> 18,980 bytes, `world` 21,432 -> 19,644,
   `scramble` 9,136 -> 8,541) and some 11 to 12 percent off the raw
   code that lands in RAM (measured: `titleseq` 13,488 -> 11,832
   bytes, `world` 16,701 -> 14,913, `scramble` 5,035 -> 4,441).
   What it removes is the per-scope bytecode that stores docstrings -
   nothing else can: the qstr and object tables of a `-O0` and a
   `-O3` module are byte-identical (no name, string or constant
   object is dropped), the text of a docstring never enters either
   table at any level, and this build has no asserts to drop. `-s`
   swaps the 110-character staging-path module name for the short
   file name.
2. **Cockpit off** frees again: the flight claims the cockpit's
   12,308 bytes only when the option is on and `ck%d.wc` exists
   (`flight.py:208-212`), so a flight with the option off never
   allocates them - some 12 KB of heap stays free while flying. It
   also saves flash reads and draw time: the flight never loads
   `ck%d.wc`.
3. **Fewer object slots**: `NOBJ` 44 -> 36 saves about 3 KB and caps
   the number of simultaneous bolts and debris.
4. **Split `flight.py`**: the flight computer (pause menu, nav map,
   radio menu, weapon selection) is about a seventh of the module and
   could load on demand.
5. **Split `world.py` / `ai.py` by phase**: mission setup code
   (`init_ship`, `set_up_action_sphere`, formations) versus per-turn
   code. Harder, because both are needed during a flight.
6. **Unload the flight code between flights** - already the shape:
   the title, the options menu and the end of every flight let it go
   (`MainGame.py:248-250`, `:350-352`, `:726-730`); `Game.fly` claims
   it at launch and the post-flight scenes re-claim it in guarded
   imports (12.2 step 2). What cannot go is the `World` instance the
   result is read
   from: it keeps the module alive (fact 1), so the result would have
   to be copied into a small object first if the flight's outcome
   ever needed to outlive the flight code.
7. **Freeze the modules into the firmware.** Frozen bytecode runs
   from flash and costs no heap at all - this alone would free about
   80 KB. It needs a custom firmware build, which is why it is last.

## 12.7 What the measured budget means for the plans

| Feature | Needs (estimate) | Runs when | Room there | Verdict |
|---------|------------------|-----------|------------|---------|
| radio (chapter 7) | portraits under 30 KB on flash, drawn through the frame cache; the 12 KB message table read by `seek`; some code | in flight | about 41 KB (`flight` 41,360 measured) | fits |
| talking heads (chapter 5) | about 15 KB per face, one at a time, plus code | menus | about 47 KB; the face claims fresh room because the conversation's release precedes it | fits |
| cutscenes (chapter 6) | interpreter code, sprites through the frame cache, one backdrop (7,936) | menus | about 47 KB | fits if frames stay within the cache pools |
| music player (chapter 10) | tables 9 KB, timbres 4 KB, song buffers 14 to 45 KB, state 2 KB, plus perhaps 10 KB of code | always, also in flight | about 41 KB there (measured), about 47 to 65 KB in the menus | **fits in the menus**: one 13.3 KB slot plus state plus code fits the menus' free room; the long song buffers for the title track too. **tight in flight**: with the cockpit on, about 41 KB minus the flight's garbage; cockpit-off (12.6 item 2) frees 12 KB, and levers 4 and 7 open real room. |

The room each line names stays an estimate until its own log shows
it - except the flight's, whose room is now measured. The clean
build's table (12.1) is the reference - `ready` 96,896 and
`landed` 64,896 are the menus' and the post-flight numbers that
must not drift down between sorties. Music and sound are the next
big ask - the plan keeps their room in the menus whole, and in a
flight it must come out of the cockpit claim or one of 12.6's
levers; plan from the start with the small variant (song buffers
sized for the largest in-flight song, 13.3 KB; the long title track
loaded only in the menus).

The tables step (29 KB at `ready`) is larger than its files suggest
(types 9 KB, AI 2 KB, fonts 8 KB) and has not been looked into;
it is the first place to look for a few more KB.
