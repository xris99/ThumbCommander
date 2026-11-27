# launchseq.py - the launch door and the carrier fly-off (docs/06 6.2):
# the blast doors parting past the cockpit at launch, and the fighter
# climbing off the Tiger's Claw deck after a landing.
#
# Verbatim ports of (wc1-re, GPL-3.0):
#   DrawLaunchDoorFrame       src/launch.c:55   (0x42B9A0)
#   LaunchPlayerShip          src/launch.c:103  (0x42BA90)
#   ShowCarrierLaunchSequence src/launch.c:164  (0x42BC00) - phases B, C
#   GetTransformedShapeBounds src/gr.c:1311     (0x442050)
# on the sprite sets tool/wc1_convert.py writes from SCRAMBLE.VGA
# (scr07.wcs the blast door, launch.c:118-119; scr08.wcs the Tiger's
# Claw, launch.c:192-193; scr04.wcs the deck crew, launch.c:194-195)
# and PCSHIP.V0N shape sets (sh<NN>.wcs, the player fighter,
# launch.c:196-197).
#
# Both scenes fill the whole picture, not the conversation band: the
# original draws into stSpaceBufferViewport, the 320 x 200 space buffer,
# and dumps it over the screen; on the device that is rows 16..111, so
# the clip bottom is 112. The mapping (0.4 x / 0.48 y plus the row-16
# offset) and the scaling rules are the ones verified in docs/06 6.2;
# scramble.py's _cx/_cy/_draws (scene.py / gr.c ports) place and size
# every piece, and its actor engine (cutscene.c:378-434) walks the deck
# crew. One step per displayed frame at STEP_MS; any button breaks a
# loop, as every original loop checks bEscapePressedFlag
# (launch.c:140, 363, 430). Missing files skip the scene.
#
# Not ported, documented in docs/06 6.2:
#  - the music and the sound effects (the port has no audio in
#    cutscenes yet: sfx 20/18/11/19 and track 0x1c are skipped);
#  - the animated cockpit instruments of the launch: update_cockpit
#    (cockpt.c:3151) draws the scanner, readouts and pilot as overlays
#    on the screen after dump_buffer_to_screen; the device picture is
#    the space buffer itself (header above), so the door scene redraws
#    the doors still approaching over a background the original clears
#    every pass (see the gate note below) and the instruments are
#    simply absent. Painting the static ck<N>.wc art over the doors
#    was wrong: it clipped the tunnel into the small ck glass window
#    and painted the dashboard across the parts that should pass by
#    (update_cockpit never repaints the frame art - cockpt.c:3151-3253
#    draws dynamic overlays only).
#  - phase A of the fly-off (launch.c:200-288), the 100-frame scripted
#    3D approach, is ported in _approach below and runs when flyoff is
#    handed the live flight world (MainGame.py:554; selfplay's
#    single-argument call takes the B/C-only path). The objects are
#    pinned at original-space screen positions instead of being
#    projected, so the scene needs no 3-space transform engine;
#  - the eye of that approach never pitches or yaws, so the stars stand
#    still on screen while the dust streams: the original's
#    update_star_field (spc.c:749-784) flows the field with the eye's
#    forward vector and velocity, and sky.py models field motion through
#    a turning view only - the same documented deviation as the eject
#    chase (ejectseq.py:701-705);
#  - the Update_3Space / Draw_3Space_Frame halves of the
#    RefreshCockpitStatus gates (launch.c:127, 318, 375; main.c:2136-
#    2142): these scenes keep no 3-space objects, so there is nothing
#    to advance or draw; with nFrameSkipCounter = 1 (launch.c:123,
#    314, 371) the gate's clear_view_buffer (main.c:2140, :493-498)
#    fires on every pass - that is what deletes the door sections
#    that have passed by. The port replays the clear with G.fill_rows
#    at the head of each pass and draws on every pass, as the gate
#    does.

import scramble as S
from time import ticks_ms, ticks_diff
from thumby_engine.platform import display
import ui
import wcgfx as G
import wcmath as M
# sky, flight and world are not imported with the module. The blast
# doors and the fly-off's deck halves draw with scramble's helpers
# only; the 3-D approach is the single place that needs sky.py, the
# flight's FX and FY and world's OT_TIGERS_CLAW, and it imports them
# for itself (see _approach). Landing them here held some 44 KB
# through the launch scenes: the device log 2026-11-27 died inside the
# flight's construction, allocating the cockpit's 12,308 bytes in a
# hole no wider, because its own code had landed before the launch
# did. docs/12 12.4.

# the space-buffer picture on the device: rows 16..111 (clip bottom 112)
FULL_Y1 = 112

# doorDistances[4] - launch.c:110-113 (50, 40, 30, 20)
DOOR_DISTANCES = [50, 40, 30, 20]

# pLaunchDoorShape frame 1 in ORIGINAL pixels - the frame
# GetTransformedShapeBounds is called with at launch.c:62-66. From
# SCRAMBLE.VGA section 7, verified with wc1_inspect: 104 x 128 with
# the hot spot at (53, 64), i.e. (width, height, left, top). The
# bounds are original-space positions (the draw positions 160/100 of
# launch.c:63 are original-space too), while the three pieces are
# drawn from the device scr07.wcs dims by S._draws. The device frame
# cannot be inverted to exact originals (104 x 128 scales to a 41.6 x
# 61.4 device replica; scaling the device dims back up lands on
# rounding ties), so like the tables above this is cited ground truth.
DOOR_FRAME1_ORIG = (104, 128, 53, 64)

# aCarrierLaunchFighterPath[9] - launch.c:24-28 (0x0046a598); entry 0 is
# never used by the fly-off (the path starts at frame 1, launch.c:410-414)
FLYOFF_PATH = [(-2, 1), (-1, 1), (-1, 1), (-1, 0), (-1, 1), (-1, 0),
               (-1, 1), (-1, 0), (0, 0)]
# asCarrierLaunchFighterDeltaY[14] - launch.c:29-32 (0x0046a5c0)
FLYOFF_DY = [3, 3, 3, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1]

# asCarrierLaunchApproachDeltaY[24] - launch.c:12-16 (0x0046a550): the
# fighter climbs up the picture for 24 frames, then the same values run
# backwards (launch.c:235-245) and bring it down to the deck line
APPROACH_DY = [-1, -1, -1, -2, -2, -2, -2, -3, -3, -3, -3, -3,
               -2, -2, -2, -2, -1, -1, -1, -1, -1, 0, 0, 0]
# acCarrierLaunchApproachFrames[24] - launch.c:18-22 (0x0046a580): the
# fighter's shape frames, the same mirror rule
APPROACH_FRAMES = [36, 32, 32, 32, 32, 32, 32, 32,
                   25, 25, 25, 25, 25, 25, 25, 25,
                   18, 18, 18, 18, 18, 18, 18, 18]

# the ConfigureScrambleActor calls of the fly-off, launch.c:302-309:
# (x, y, deltaX, deltaY, scale, angle, flip); index 2 is never
# configured and never drawn (launch.c:329, 334-337 draw 0, 3, 4, 1)
FLYOFF_ACTORS = {
    0: (100, 80, 1, 0, 0x100, 0, 0),
    1: (116, 130, 0, 0, 0x100, 0, 0),
    3: (300, 110, -4, 0, 0xc0, 0, 0x10),
    4: (301, 110, -4, 0, 0xc0, 0, 0x10),
}


def _bounds(w, h, hx, hy, x, y, scale):
    """GetTransformedShapeBounds (gr.c:1311-1388) reduced to the door
    call: angle 0, flip 0 (launch.c:62-66). gr.c reads the frame's hot
    spot offsets CROSSWISE at gr.c:1353-1354 - frameRight = cursor->left
    and frameLeft = cursor->right - so the extent sums (gr.c:1365-1366)
    cancel to w - 1 and h - 1 while leftEdge (gr.c:1379) scales the hot
    spot offset with frameRight, the LEFT one. frameTop and frameBottom
    are read straight (gr.c:1355-1356) and stay positive; at angle 0
    the trig is (256, 0): cosine = scale after the >> 8 (gr.c:1357-
    1359), sine = 0 which the guards raise to 1 (gr.c:1360-1364,
    1375-1378). w, h, hx, hy must be the ORIGINAL frame extents: the
    bounds are original-space positions in launch.c, mapped to device
    pixels by S._draws afterwards."""
    fr = hx                           # gr.c:1353: frameRight = cursor->left!
    fl = w - 1 - hx                   # gr.c:1354: frameLeft = cursor->right!
    ft = hy                           # gr.c:1355 (straight read)
    fb = h - 1 - hy                   # gr.c:1356 (straight read)
    cos = scale                       # gr.c:1357-1359, 256 * scale >> 8
    sin = 1                           # gr.c:1360-1364: 0, then sine++
    ex = fl + fr                      # gr.c:1365 == w - 1
    ey = fb + ft                      # gr.c:1366 == h - 1
    tw = sin * ey + cos * ex          # gr.c:1371
    if tw & 0xff:                     # (char) != 0, gr.c:1372-1373
        tw += 0x100
    tw >>= 8                          # gr.c:1374
    le = ((sin * ft) >> 8) + x - ((cos * fr) >> 8)  # gr.c:1379
    t = (sin * ey) >> 8               # gr.c:1383-1384
    t += 1                            # gr.c:1385
    left = le - t                     # gr.c:1386
    return left, left + tw            # gr.c:1387-1388


def door(ship):
    """LaunchPlayerShip (launch.c:103-161): the four blast doors part
    past the cockpit window, each one growing as it comes at you.
    RefreshCockpitStatus (:127) clears the space buffer before each
    pass - nFrameSkipCounter = 1 (:123) always meets its gate at
    main.c:2138-2140 - so a door whose distance has come down to 10
    or less stops being drawn (launch.c:60) and its last picture is
    wiped by the next pass's clear: sections that have passed by are
    deleted, not painted over. The port replays that clear with
    G.fill_rows at the head of each pass. 25 frames (launch.c:125);
    the distance step grows every 5th frame (launch.c:142-143, checked
    after the escape break at :140-141). Returns True when a button
    cut it."""
    ss = S._set('scr07.wcs')
    if ss is None:
        return False
    fb = display.buffer
    display.fill(0)
    dist = list(DOOR_DISTANCES)       # launch.c:110-113
    step = 1                          # launch.c:114
    esc = False
    for frame in range(25):           # launch.c:125
        # RefreshCockpitStatus (:127) clears the space buffer every
        # pass (main.c:2138-2140) - the doors that have passed by
        # (distance 10 or less, launch.c:60) are deleted by it
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
        for d in range(4):            # launch.c:128-134
            dd = dist[d]
            if dd > 10:               # launch.c:60
                sc = 0x1a00 // dd     # launch.c:61
                e = S._read(ss, 1)    # the bounds frame exists, :62-66
                if e is not None:
                    # the bounds come from the ORIGINAL frame extents
                    # (launch.c:63 passes the original-space position
                    # 160, 100); the device scr07.wcs dims are for the
                    # piece draws below, not for this formula
                    left, right = _bounds(*DOOR_FRAME1_ORIG, 160, 100, sc)
                    # the three door pieces at y = nScreenHeight >> 1
                    # (launch.c:73-98): frame 0 at bounds.left - 1,
                    # frame 1 dead centre, frame 2 at bounds.right
                    S._draws(fb, ss, 0, left - 1, 100, 0, sc, 0, FULL_Y1)
                    S._draws(fb, ss, 1, 160, 100, 0, sc, 0, FULL_Y1)
                    S._draws(fb, ss, 2, right, 100, 0, sc, 0, FULL_Y1)
                elif sc == 256:       # gr.c:1295 path, no bounds
                    S._draw(fb, ss, 1, 160, 100, FULL_Y1)
            dist[d] = dd - step       # launch.c:131-132
        display.update()              # dump_buffer_to_screen (:135);
        # update_cockpit (:136) paints the cockpit instruments over the
        # dumped buffer - not ported, see the header
        if S._key():                  # launch.c:140-141
            esc = True
            break
        if frame % 5 == 0:            # launch.c:142-143
            step += 1
    ui.wait_release()
    # clear_view_buffer (launch.c:157): the picture goes black; the
    # flight paints the cockpit fresh from here
    G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
    return esc


class _Eye:
    """The scripted eye of phase A: the camera held as an object, so
    sky.py - which reads the flight's player fields - can drive it as
    the eye. Same trick as ejectseq.py's _Ob for the chase
    (:136-162). Stands for aShipPositionsArray[61] and the eye slots of
    aShipVelocity / the frame (wcdata.h: EYE_OBJECT 61)."""

    def __init__(self):
        self.m = [0] * 9
        self.x = 0
        self.y = 0
        self.z = 0
        self.vx = 0
        self.vy = 0
        self.vz = 0
        self.radius = 0
        self.rp = 0
        self.ry = 0


def _approach(world, carrier, fighter, fb):
    """ShowCarrierLaunchSequence phase A (launch.c:200-288): the 100
    frames of the scripted approach. The fighter climbs up the picture
    and shrinks, then slides back down and across to the right; the
    Tiger's Claw slides in from off the right edge; stars and dust
    stream past a scripted eye that free-flies along the carrier's
    right. The two objects are pinned at original-space screen
    positions instead of being projected - launch.c:251-261 stores
    centre-relative screen coordinates and winmain.c:95-96 adds the
    centre (nCurrentViewCenterPosX/Y are the fixed 160, 100 of
    eventmgr.c:1167-1169, :1192-1194) when the objects are drawn, so
    the picture lands exactly at the plain coordinates this port draws
    at. The view script asCarrierLaunchViewData (launch.c:34-36,
    {12, 11, 1, 90, 90, 0, 9, -90, 0, 0, 20, 3, 15, -1}) holds no
    command 13 or 14, so parse_view_script (view.c:38-168) runs it to
    the -1 entry inside initialize_scripted_view (:198-206) and
    bScriptedView is already 0 before the frame loop (view.c:47-51):
    every pass of set_eye_direction_and_position (spc.c:158-168) skips
    the scripted update and takes case 15 (:458-464)."""
    import world as W                   # resident: the flight this
                                        # world came from imported it
    try:
        import sky
        import flight as FL             # fly() let the flight code go
                                        # with the flight, so this lands
                                        # it again - and the room after
                                        # the flight may not take it
    except MemoryError:
        return False        # the sky and the flight's view constants
                            # did not fit: phase A is skipped, phases B
                            # and C play as they do for the harness
                            # call. docs/12 12.4.
    claw = None                         # nScriptedViewObject = the object
    for ob in world.o[1:]:              # the player landed on: the Tiger's
        if ob.typ == W.OT_TIGERS_CLAW:  # Claw the landing code targets,
            claw = ob                   # world.py:1238-1242; gameflow.c:363
            break                       # passes nPlayerCollisionObject
    if claw is None:                    # no carrier in this flight: the
        return False                    # original could not run either
    scale = world.o[0].scale            # awObjectScales[0] =
    # typeData->scale (ship.c:248; the raw value of T.f[D.T_SCALE],
    # world.py:380) - the fighter the scene draws is the player's
    eye = _Eye()
    # initialize_scripted_view (view.c:198-206): zero_vector of the
    # velocity and init_ijk (geom.c:600-614) reset 61 to the identity
    # frame with the rotation counters at 0 - the counters stay 0 all
    # scene, so rotate_object (spc.c:462) is a no-op every pass. The
    # script then runs inside the initializer:
    M.copy(claw.m, eye.m)               # cmd 11 copy_frame(obj, 61) :617
    M.yaw(eye.m, 90)                    # cmd 1 alter_yaw(90): rotate R, F
    M.fix(eye.m)                        # about U + fix (:659-664, :628)
    M.pitch(eye.m, 90)                  # cmd 1 alter_pitch(90): rotate U,
    M.fix(eye.m)                        # F about R + fix (:651-656)
    # cmd 1 alter_roll(0): rotate_about_k(0) moves nothing (:667-672)
    eye.x = claw.x                      # cmd 12: the eye sits on the
    eye.y = claw.y                      # carrier's own position
    eye.z = claw.z
    m63 = [0] * 9
    M.copy(eye.m, m63)                  # cmd 9 copy_frame(61, 63) :617
    M.yaw(m63, -90)                     # cmd 9 alter_yaw(-90) :659-664
    M.fix(m63)                          # the frame 63's fix
    # cmd 9 ScaleFixedVector(F63, 20 << 8) added to the zeroed eye
    # velocity (:120-129): on the 16384 basis a unit component gives
    # 16384 * 5120 >> 14 = 5120 Q8 = 20 m. spc.c:459-461 adds that
    # velocity to the position every pass and launch.c:280-282 adds it
    # again in the same pass - the eye moves twice the velocity; the
    # port folds the doubling into the stored velocity (2 * 5120 =
    # 10240) and advances the eye once per pass, like the chase does
    # (ejectseq.py:752-754). F63 is the carrier's right vector: yaw +90
    # onto the carrier's up and back off again lands on the carrier's
    # side, so the camera flies along the deck line.
    eye.vx = (m63[6] * 10240) >> 14
    eye.vy = (m63[7] * 10240) >> 14
    eye.vz = (m63[8] * 10240) >> 14
    # cmd 15 (view.c:142-148) aims the eye at the carrier: the eye
    # already sits on it, the delta is the zero vector and
    # fix_objects_ijk (:628-639) normalises nothing - a no-op here too.
    # cmd 3 force_view(15, carrier) (:88-91): spc.c:470-474 -> new_view
    # (:478) sets mode 15 and the eye's collision radius (:497-499);
    # rotate_eye_to_goal (spc.c:463) has zero targets, another no-op.
    eye.radius = max(10, claw.radius)
    # the eye doubles as sky.py's player (m, x/y/z, vx/vy/vz, radius,
    # rp/ry); it neither pitches nor yaws, so stars stand still while
    # the dust streams past - the documented deviation in the header
    sky_obj = sky.Sky(eye, FL.FX, FL.FY,
                      (0, S.PIC_Y0, 128, FULL_Y1, 64, 64))
    # launch.c:201-215: the fighter starts at (20, 64) on frame 36 at
    # distance 300, the carrier backdrop at (520, 64) off the right
    # edge, and the approach distance is 20
    st = {'fy': 64, 'fx': 20, 'bdy': 64, 'bgr': 520, 'ap': 20, 'vf': 36,
          'frame': 0}

    def draw_a():
        f = st['frame']                 # launch.c:235-245, the render
        if f < 24:                      # pass runs the schedule for the
            st['fy'] += APPROACH_DY[f]  # frame value before the ++ of
            st['vf'] = APPROACH_FRAMES[f]       # :285
        elif f < 48:
            st['fy'] -= APPROACH_DY[47 - f]
            st['vf'] = APPROACH_FRAMES[47 - f]
        # launch.c:230 clear_view_buffer: the gate fires every pass
        # (nFrameSkipCounter = 1, launch.c:216; main.c:2138-2140), so
        # pieces that moved on are wiped, not painted over
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
        sky_obj.turn(eye)               # the backdrop's upkeep: launch.c
        # :231-234 touch only classed objects (aeObjectClass is set to
        # NULL at :222-223 every pass), so the only per-pass world step
        # is update_star_field (:234) - sky.py runs it as turn + draw,
        # as in the chase (ejectseq.py:756-772)
        # Draw_3Space_Frame (main.c:2010-2037): the stars (the
        # original's update_star_field :2019), the dust, then the
        # objects sorted far to near (sort_object_depth :2025)
        sky_obj.draw(fb, display, eye.m, eye.x, eye.y, eye.z, eye, True)
        sky_obj.draw(fb, display, eye.m, eye.x, eye.y, eye.z, eye, False)
        sc = (scale << 4) // st['ap']   # approachScale, launch.c:247-249
        # sort_object_depth (:262): the fighter's distance 300 + 10 per
        # pass (:209, :278-279) never catches the carrier's fixed 2000
        # (:215), so the fighter is always nearer: drawn far to near,
        # the carrier first and the fighter last, on top
        S._draws(fb, carrier, 3, st['bgr'], st['bdy'], 0, 0x100, 0,
                 FULL_Y1)
        # launch.c:208 sets the fighter's screen angle to 180 and
        # launch.c:196-214 leaves flip at 0; DrawSpriteScaled takes
        # degrees (gr.c:1291-1297 feeds angle * 10 to RotateRLEImage's
        # tenths table, gr.c:558, 901 entries over a 900-tenth quadrant)
        S._draws(fb, fighter, st['vf'], st['fx'], st['fy'], 180, sc, 0,
                 FULL_Y1)

    def step_a(i):                      # launch.c:273-282: these run on
        st['fx'] += 2                   # every pass, rendered or not -
        st['bgr'] -= 2                  # with nFrameSkip = 1 (main.c:28)
        st['ap'] += 2                   # every pass renders anyway
        eye.x += eye.vx                 # the doubled velocity once
        eye.y += eye.vy
        eye.z += eye.vz
        # asObjDistancesTable[0] += 10 (:278-279) is folded away: the
        # draw order is the fixed carrier-then-fighter of draw_a
        st['frame'] += 1                # launch.c:285

    return S._steps(100, draw_a, step_a)    # launch.c:288: while frame < 100


def flyoff(ship, world=None):
    """ShowCarrierLaunchSequence (launch.c:164-446): phase A, the 3D
    scripted approach (_approach), when a live flight world is handed
    in (MainGame.py:554 - the landing flow's own world, holding the
    carrier the player landed on and the player's scale), then phases
    B and C: the fighter slides down the deck and swings out off the
    carrier's edge while the crew watch. flyoff(ship) alone (the
    selfplay harness, wc1_selfplay.py:220) has no world, skips the 3D
    approach and plays B and C, as the door scene's set-only call does.
    Any button that cuts phase A skips phases B and C, as the guard at
    launch.c:292 does; any button that cuts phase B skips phase C
    (:370). Returns True when a button cut it."""
    if ship not in (0, 1, 2, 3):
        return False
    carrier = S._set('scr08.wcs')     # launch.c:192-193
    crew = S._set('scr04.wcs')        # launch.c:194-195
    fighter = S._set('sh%02d.wcs' % ship)     # launch.c:196-197
    if carrier is None or crew is None or fighter is None:
        return False
    fb = display.buffer
    display.fill(0)
    if world is not None:               # phase A: the scripted approach
        esc = _approach(world, carrier, fighter, fb)
        if esc:                         # launch.c:283-284 broke the loop,
            ui.wait_release()           # launch.c:292: B and C are
            return True                 # skipped together with it
    # launch.c:297-301, 312-313: the fly-off starts from the reset
    # background position and the fixed launch geometry
    st = {'bgr': 0, 'bdy': 0, 'lx': 200, 'ly': 32, 'ap': 100, 'cx': 180,
          'ax': 60, 'ay': 10}
    actors = [S._new_actor(i, FLYOFF_ACTORS[i]) if i in FLYOFF_ACTORS
              else S._new_actor(i, (0, 0, 0, 0, 0, 0, 0))
              for i in range(5)]

    def draw_b():
        # RefreshCockpitStatus (:318) clears the space buffer every
        # pass (nFrameSkipCounter = 1, :314; main.c:2138-2140)
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
        # launch.c:319-328: the carrier's two background halves
        S._draw(fb, carrier, 0, st['bgr'] + 239, st['bdy'], FULL_Y1)
        S._draw(fb, carrier, 1, st['bgr'] + 240, st['bdy'], FULL_Y1)
        S._actor(fb, crew, actors[0], st['bgr'], st['bdy'])   # :329
        sc = 0x6000 // st['ap']       # launch.c:330
        st['sc'] = sc                 # the frozen value phase C reuses
        S._draws(fb, fighter, 16, st['lx'], st['ly'], 0, sc, 0, FULL_Y1)
        S._actor(fb, crew, actors[3], st['bgr'], st['bdy'])   # :334-336
        S._actor(fb, crew, actors[4], st['bgr'], st['bdy'])
        S._actor(fb, crew, actors[1], st['bgr'], st['bdy'])   # :337
        # the crew sprites at fixed offsets (launch.c:338-345)
        S._draw(fb, crew, 16, st['bgr'] + 60, st['bdy'] + 10, FULL_Y1)
        S._draw(fb, crew, 8, st['bgr'] + 80, st['bdy'] + 134, FULL_Y1)
        S._draw(fb, carrier, 2, st['cx'], st['bdy'], FULL_Y1) # :347-349

    def step_b(i):                    # launch.c:353-359
        st['bgr'] += 2
        st['cx'] += 4
        st['lx'] -= 2
        st['ly'] += 1
        st['ap'] -= 1

    esc = S._steps(35, draw_b, step_b)        # launch.c:368
    if esc:
        ui.wait_release()
        return True                   # launch.c:370 skips phase C

    # phase C (launch.c:373-432): the scroll has stopped, the geometry
    # is frozen at the end of phase B (bgr 70, cx 320, lx 130, ly 67,
    # ap 65) and the fighter keeps the scale last computed in B (:330)
    sc = st['sc']
    ax_off = {'x': st['ax'], 'y': st['ay']}

    def draw_c():                     # same pieces as B, launch.c:376-405
        # RefreshCockpitStatus (:375) clears the space buffer every
        # pass here too (nFrameSkipCounter = 1, :371)
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
        S._draw(fb, carrier, 0, st['bgr'] + 239, st['bdy'], FULL_Y1)
        S._draw(fb, carrier, 1, st['bgr'] + 240, st['bdy'], FULL_Y1)
        S._actor(fb, crew, actors[0], st['bgr'], st['bdy'])
        S._draws(fb, fighter, 16, st['lx'], st['ly'], 0, sc, 0, FULL_Y1)
        S._actor(fb, crew, actors[3], st['bgr'], st['bdy'])
        S._actor(fb, crew, actors[4], st['bgr'], st['bdy'])
        S._actor(fb, crew, actors[1], st['bgr'], st['bdy'])
        # the crew sprite now rides the walker (launch.c:394-397)
        S._draw(fb, crew, 16, st['bgr'] + ax_off['x'],
                st['bdy'] + ax_off['y'], FULL_Y1)
        S._draw(fb, crew, 8, st['bgr'] + 80, st['bdy'] + 134, FULL_Y1)
        S._draw(fb, carrier, 2, st['cx'], st['bdy'], FULL_Y1)

    t0 = ticks_ms()
    frame = 0
    esc = False
    while frame < 50:                 # launch.c:373
        draw_c()
        display.update()              # :407
        frame += 1                    # :409 (before the path work)
        if frame < 9:                 # launch.c:410-414: entry 0 is
            st['lx'] += FLYOFF_PATH[frame][0]     # never reached
            st['ly'] += FLYOFF_PATH[frame][1]
        elif frame < 23:              # launch.c:415-420 (sfx 11 at 9
            st['ly'] += FLYOFF_DY[frame - 9]      # and 19 at 23: no
        elif frame == 23:             # audio in the port, skipped)
            pass
        ax_off['x'] += 1              # launch.c:425
        if frame % 7 == 0:            # launch.c:426-427
            ax_off['y'] -= 1
        while ticks_diff(ticks_ms(), t0) < frame * S.STEP_MS:
            if S._key():
                esc = True
            display.update()
        if esc:                       # launch.c:430-431
            break
    ui.wait_release()
    return esc


def cleanup():
    """Let go of the cached sets between flights (they live in
    scramble.py's cache)."""
    S.cleanup()
