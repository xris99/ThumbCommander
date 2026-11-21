# 7. The radio

State today: `flight.comm` offers four orders and a landing request;
`Brain.message` shows one of four made-up lines for the wingman.
`comm.wc` (a byte copy of COMMUNIC.DAT) is on the device and unused.

The original system is small and worth porting whole: a message
table, a queue with one slot per ship, about fifteen places that post
messages, a two-step menu, and a portrait in the right display.

Source: wc1-re `src/comm.c` (menus, portraits, `real_vid_transmit`),
`src/cockpt.c` (`send_message`, `npc_communication`, `vid_transmit`,
`vid_equiv`), `src/screen.c` (`request`, `reply`, `can_land`).

```bash
python3 tool/wc1_inspect.py WING comm            # every line of every personality
python3 tool/wc1_inspect.py WING comm --sm2
python3 tool/wc1_inspect.py WING shape WINGMEN.VGA 1 --png /tmp/comm
```

## 7.1 The message table

`COMMUNIC.DAT`: 14 personalities x 11 lines x 80 bytes, NUL-padded
[data]. `text = raw[(personality * 11 + line) * 80 : ... + 80]`.

| Personality | Who | | Personality | Who |
|-------------|-----|-|-------------|-----|
| 0 | Spirit | | 7 | Knight |
| 1 | Hunter | | 8-11 | the four Kilrathi aces: Bhurak, Dakhath, Khajja, Bakhtosh |
| 2 | Bossman | | 12 | any other Confederation ship (also the Tiger's Claw) |
| 3 | Iceman | | 13 | any other Kilrathi |
| 4 | Angel | | | |
| 5 | Paladin | | | |
| 6 | Maniac | | | |

Which personality speaks (`get_face(rating, side)`) [src]: rating -1
(unnamed pilot) -> 12 for a Confederation ship, 13 for a Kilrathi;
a named Kilrathi (rating 9-12) -> rating - 1; a named wingman
(rating 0-7) -> the rating itself.

The eleven lines, by number (`send_message(obj, n)`):

| n | Wingmen and Confederation ships | Kilrathi |
|---|--------------------------------|----------|
| 0 | order accepted | ace greeting |
| 1 | order refused | ace greeting when an ace status flag is set (the text reads as "again") |
| 2 | enemies sighted | taunt |
| 3 | asks permission to attack | taunt |
| 4 | needs help | taunt (reply to yours) |
| 5 | reports a kill | gloats over a kill |
| 6 | praises the player's kill; the carrier's greeting | remark about luck (after an instant kill; an ace breaking off) |
| 7 | dying | dying |
| 8 | "we should leave"; carrier: cleared to land | text exists, no call site found |
| 9 | wingman leaves; carrier: landing denied | text exists, no call site found |
| 10 | "watch your fire" (the player hit them) | |

Lines contain the tokens `$C` (callsign), `$N` / `$P` (name), `$R`
(rank); `ExpandCommMessageTokens` replaces them. The displayed text is
`"<speaker>: <line>"`, the speaker being the wingman's callsign, the
ace's name, or the ship type's name.

## 7.2 Posting and delivering

`send_message(obj, n)` does not display anything. It stores `n` in the
ship's slot `acWingmanMessageStatesArray[obj]` - if [src]:

- not in the training simulator or a canned sequence;
- the ship is a living ship in slots 0-9;
- the ship is a named pilot, **or** the Tiger's Claw, **or** the
  mission's main ship, **or** any Kilrathi;
- the wingman is not under radio silence (then the slot is cleared).

A newer message overwrites an older undelivered one.

`npc_communication()` runs every flight frame [src]:

```
for obj in 1..9, while no message is showing:
    if the ship is alive and has a pending message:
        vid_equiv(obj, message); clear the slot
with probability 1/2500 per frame:
    the first Kilrathi fighter that is attacking, and is an ace or
    passes a 20 % roll, queues taunt 2, 3 or 4
```

`vid_equiv` refuses while the right display is busy with damage or
the camera is outside; otherwise `real_vid_transmit` shows the
message. It stays for `(min(5, len / 2) + 5) * (message speed + 1)`
flight frames (`MeasureMessageWidth`; the option "message speed" is
0-2). A flight frame is a game turn: count turns, not pictures
(4.4.1). The port shows its messages for 25 turns.

## 7.3 Who says what, when

Every automatic call site [src]:

| Line | Speaker | Trigger | Where |
|------|---------|---------|-------|
| 2 | wingman | enemies within 16,000 that this wave has not been announced for, no message showing | `src/brains.c:256` |
| 3 | wingman | has a target but engaging is not allowed (you ordered formation) | `src/brains.c:248` |
| 4 | wingman | stress rises past 15; or, rarely, the player is badly damaged and worse off than the wingman | `src/smart.c:726` |
| 8 | wingman | same roll, but the wingman is in better shape than the player | `src/smart.c:737` |
| 4 | any posting ship | hit while badly damaged, 3.5 % per hit, not by the player | `src/ship.c:724` |
| 5 | attacker | destroyed an enemy | `src/ship.c:1306` (`explode`) |
| 5 | wingman | his shot killed a Kilrathi (50 %) | `src/ship.c:514` |
| 5 | a Kilrathi | his shot killed your wingman | `src/ship.c:514` |
| 5 | a named Kilrathi | your wingman has just died | `src/ship.c:1372` |
| 6 | wingman | you killed a Kilrathi (10 %) | `src/spc.c:958` |
| 6 | a Kilrathi | scored the 1-in-100 instant kill | `src/ship.c:612` |
| 6 | a Kilrathi ace | breaks off badly damaged | `src/ship.c:1524` |
| 6 | carrier / mission ship | you arrive at the ship you were sent to | `src/cockpt.c:1440` |
| 7 | the dying ship | named pilot or the mission's main ship always; others 3 % | `src/ship.c:1372` |
| 9 | wingman | cannot continue and heads home | `src/logic.c:486` |
| 10 | wingman | you shot him | `src/ship.c:578` |
| 0 / 1 | a Kilrathi ace | greeting when he appears; 1 if you met before | `ace_greeting`, `src/logic.c:146` |

## 7.4 Orders

The menu has two steps [src `BuildCommunicationRecipientMenu`,
`BuildCommunicationCommandMenu`]. It opens only if you have a wingman
or a target.

**Recipient**: your wingman; or, if you have something targeted,
"ENEMY TARGET" for a Kilrathi fighter, or the ship's name for a
Confederation ship (only while enemies are within 14,000, or always
for the Tiger's Claw). With no wingman the target is chosen directly.

**Command**, shown only when it makes sense:

| # | Text | Offered when | Effect (`request`, `src/screen.c`) |
|---|------|--------------|--------------------------------|
| 7 | Break and attack. | wingman in formation, enemies near | leaves formation; reply 0 |
| 8 | Keep formation! | wingman has been released | holds; Hunter and Maniac may refuse (reply 1) |
| 9 | Form on my wing. | wingman not in formation | returns; same refusal rule |
| 10 / 11 | Keep radio silence / Broadcast freely | wingman | toggles `bRadioSilence` |
| 12 | Request Landing | recipient is the Tiger's Claw, not yet cleared | `can_land()` -> line 8 and clearance, else line 9 |
| 1 | Attack my target! | friendly recipient, you target a Kilrathi | engages it, reply 0; reply 1 if the target is unsuitable or he is retreating |
| 2 | Help me out here | friendly recipient, you are below 50 % and enemies near | attacks whoever targets you |
| 3 | Return to base. | wingman | goes home if his character agrees (`i_wanna_rout`), reply 0 / 1 |
| 4, 5, 6 | three taunts | recipient is Kilrathi | 70 % (aces always) answer with line 2, 3 or 4, and he turns on you |
| 0 | Never mind... | always | closes the menu |

`can_land()`: no enemy within 20,000, and either you are damaged, have
kills, are low on fuel, or have achieved or visited an objective.
The port's landing request already implements a simplified version of
this.

The refusal rules are character: `disobey_formation` lets pilot level
10 refuse while an enemy is on your tail and level 11 while Kilrathi
remain; `i_wanna_rout` is a per-pilot rule for "return to base".
`ai.py` has `pilot level` as `ob.level`.

## 7.5 Portraits

`WINGMEN.VGA`, every frame 73 x 66 with hot spot (0, 0), drawn at the
top-left corner of the right display [src, data]:

| Section | Frames | Content |
|---------|--------|---------|
| 0 | 2 | Confederation background: a helmet on a green scan-line screen |
| 1-8 | 5 each | one named wingman: the parts that differ (helmet badge, eyes, collar), transparent elsewhere |
| 9 | 2 | Kilrathi background |
| 10 | 5 | Kilrathi face parts, used for all Kilrathi (faces 8-11 and 13) |
| 11 | 2 | static (interference) |

A transmission draws the background's frame 0, then the speaker's
section on top. `real_vid_transmit` uses frame 0; while the message is
up, `vid_transmit` redraws every second frame with a random frame 0-2
(a random number 0-3; 3 keeps the previous frame), which makes the
face flicker between three expressions. A dying Confederation speaker
shows the static shape instead. Generic Confederation ships
(personality 12) have no overlay section: only the helmet background
appears.

Secret Missions 2 takes two portraits from `WINGMEN1.VGA` [src].

## 7.6 Porting plan

**Converter**

- `comm.wc` exists. Nothing to add for text.
- `convert_portraits`: compose background + overlay on the PC for
  frames 0-2 of each of the 9 speakers (8 wingmen + Kilrathi), plus
  the two bare backgrounds and static; scale to the size of the
  port's right display rectangle (stored per cockpit in `ck<N>.wc`;
  73 x 66 original is 29 x 32 at screen scale). About 30 small
  frames, under 30 KB as one `.wcs`. The art is monochrome green on
  dark - it survives the reduction well.
- Copy the four ace names and the 13 menu texts into
  `tool/wc1/tables.py`.

**Runtime**

1. `World`: add `msg` slots per ship (the field `Obj.msg` exists,
   initialised to -1) and `send_message(ob, n)` with the filter of
   7.2. Replace `Brain.message` calls by it, then add the call sites
   of 7.3 in the functions that already exist under the same names
   (`explode`, `inflict_damage`, `intelligence_events`, `wingman`).
2. `Flight`: per frame run the delivery loop; look the line up in
   `comm.wc` (`f.seek((p * 11 + n) * 80)`; keep the file handle open
   during a flight or read all 12 KB once), expand tokens, prefix the
   speaker, show it through the existing message line with the
   original duration formula, and show the portrait in the right
   display while it is up.
3. `Flight.comm`: rebuild as the two-step menu with the conditions of
   7.4 and route choices through a `request(ship, command)` port.
   The four existing orders map to commands 7, 9, 1, 12.
4. Taunts need Kilrathi `acShipRating` to be honoured for aces (the
   mission data has it; the port reads it as `ob.rating`).

The port's message line holds two lines of 126 pixels; the longest
original line is 79 characters plus the speaker prefix - check that
`font.wrap(...)[:2]` does not cut lines, or scroll them.

**Check**: a headless test that forces each `send_message` number for
each personality and asserts a non-empty line is displayed; and one
that walks every menu state.

## 7.7 Open points

- Radio speech does not exist in the DOS game. wc1-re can play
  user-supplied recordings (`src/sdl/speech.c`); out of scope here.
- `pCommStaticShape` is drawn with frame index 2 for a dying Kilrathi
  although the section has two frames [src, data]; what the original
  shows then was not checked.
- The portrait frames 3 and 4 of each speaker are not referenced by
  the code paths read here.
