# Wing Commander for the ThumbyColor - a port harness in the spirit of
# https://github.com/neuromancer/wc1-re: the original game's missions,
# campaign tree, conversations, ships, cockpits, flight model and pilot
# AI, driven by this engine instead of DOS/Win32 and SDL.
#
# No Origin data is part of this repository. tool/wc1_convert.py turns
# your own copy of the game (WC.EXE + GAMEDAT) into the files under
# assets/; without them the game only shows how to make them.
#
#   world.py     the simulation (ships, weapons, damage, missions)
#   ai.py        pilot intelligence and the manoeuvre scripts
#   flight.py    cockpit, renderer, controls
#   talk.py      briefing / debriefing / bar conversations
#   campaign.py  series tree, scoring, promotions, the saved game
#   wcdata.py    asset loaders        wcgfx.py  pixel loops (viper)
#   wcmath.py    integer 3-D math     ui.py     menus and text pages
#   scene.py     cutscene interpreter ("Meanwhile..." between series)
#   titleseq.py  the opening cinematic and the title menu
#   introfx.py   the Origin FX startup intro (orchestra, Earth, logo)
#
# The game logic is derived from wc1-re and therefore GPL-3.0 (see
# LICENSE.txt in this directory).

from thumby_engine.platform import (display, IS_THUMBY_COLOR, buttonA,
                                    buttonB, buttonMENU, audio_open_id,
                                    audio_set_volume, audio_stop)
from thumbyHardware import reset
from gc import collect, mem_free
import json
import sys

if IS_THUMBY_COLOR:
    from engine import freq
    freq(300_000_000)

import wcdata as D


def mem(tag):
    """Collect, then report the free heap. The lines tell where the RAM
    goes when the game runs out of it on a device."""
    collect()
    print('WC mem', tag, mem_free())


# Memory plan. The heap of the ThumbyColor is small (about 190 KB once
# the engine is up) and MicroPython's allocator does not move blocks,
# so a large block must be claimed before the heap is cut up:
#   1. the frame cache, the largest block the game ever needs, right
#      here, once, for the whole session. It is the one standing
#      reservation this game keeps; its content is forgotten (reset)
#      at every phase boundary, so no stale frames ride into the
#      phase that follows;
#   2. the code a flight needs is not claimed at start-up: a
#      cinematic never flies. Game.fly claims it at launch, where the
#      room is large again; a pop gives a module back in full, code
#      included, once nothing holds it, so the flight-free stretch
#      holds neither;
#   3. every other large buffer belongs to the phase that uses it:
#      claimed when that phase starts, after everything the last
#      phase held has been popped and collected, and given back whole
#      when the phase ends. Nothing is ever borrowed from a standing
#      reservation, so each phase begins with the room entire.
mem('start')
CACHE = D.FrameCache()
mem('buffers')

import ui
import wcgfx as G
# flight and ai are not here: they are claimed at launch and released
# when the flight lets go, so the flight-free stretch holds neither;
# booting them would hold some 44 KB through the title instead.
# world is not here either: the title's import of titleseq pulls it
# in itself, so a boot copy would spend the title's room twice. The
# mission flow binds the name where it needs the R_* constants; the
# name is free there because flight imported the module first.
# Game.fly claims flight and ai at launch; Game.options borrows
# flight briefly for the speed names.
mem('code')

OPT_FILE = 'wc_settings.json'
SHIP_NAMES = (b'Hornet', b'Rapier', b'Scimitar', b'Raptor')
CAMPAIGNS = (b'Wing Commander', b'Secret Missions', b'Secret Missions 2')
SFX = ('sfx_laser.ima', 'sfx_missile.ima', 'sfx_hit.ima', 'sfx_boom.ima',
       'sfx_pop.ima')


def gc_pace():
    """Collect whenever half of the free heap has been used up again,
    instead of only when it is full: garbage then never spreads over
    the whole heap, and what stays free stays in larger pieces."""
    try:
        from gc import threshold
        threshold(max(4096, mem_free() // 2))
    except (ImportError, AttributeError):
        pass                        # the PC emulation has no such call


def assets_stale():
    """True if a ship frame is larger than the biggest frame buffer:
    data written by an older tool/wc1_convert.py."""
    for i in range(32):
        try:
            f = open(D.A + 'sh%02d.wcs' % i, 'rb')
        except OSError:
            continue
        head = f.read(8)
        f.close()
        if len(head) == 8 and (head[6] | (head[7] << 8)) > D.MAX_FRAME:
            return True
    return False


def load_opts():
    opts = {'cockpit': 1, 'invert': 0, 'sound': 1, 'rumble': 1, 'speed': 0}
    try:
        with open(OPT_FILE, 'r') as f:
            opts.update(json.load(f))
    except (OSError, ValueError):
        pass
    return opts


def save_opts(opts):
    try:
        with open(OPT_FILE, 'w') as f:
            json.dump(opts, f)
    except OSError:
        pass


def no_data():
    """Shown when assets/ has not been filled by the converter."""
    display.setFPS(15)
    lines = ('WING COMMANDER', '', 'Game data missing.', '',
             'On a PC run', ' tool/', ' wc1_convert.py', 'with your own',
             'copy of the game,', 'then deploy again.', '', 'A: exit')
    while True:
        display.fill(0)
        y = 4
        for ln in lines:
            display.drawText(ln, 0, y, 0xFFFF)
            y += 10
        display.update()
        if buttonA.justPressed() or buttonMENU.justPressed():
            reset()
            return


def ui_notice(lines):
    display.setFPS(15)
    while True:
        display.fill(0)
        y = 4
        for ln in lines:
            display.drawText(ln.decode(), 0, y, 0xFFFF)
            y += 10
        display.update()
        if buttonA.justPressed():
            return


class Game:
    def __init__(self):
        self.opts = load_opts()
        self.T = D.Types()
        # ai.wc - some 2 KB - parsed at start-up; the title world
        # rides the tables read here instead of parsing them again.
        self.ai = D.Ai()
        self.pal = bytearray(D.load('pal.wc'))
        ui.setup(D.Font(2), D.Font(1), self.pal)
        self.sfx = False
        if IS_THUMBY_COLOR:
            ok = 0
            for i in range(len(SFX)):
                if D.exists(SFX[i]):
                    if audio_open_id(D.A + SFX[i], i) >= 0:
                        ok += 1
            self.sfx = ok == len(SFX)
            audio_set_volume(12)
        self.st = None
        self.camp = None
        # The push rate for the menus, the notices and the scenes
        # outside flight; the opening cinematic and the intro run the
        # tick at the picture's own rate (titleseq.title, Game.intro)
        # and flight runs it at flight.PICTURES. docs/06 6.1.
        display.setFPS(20)
        mem('ready')

    # --- title and main menu ----------------------------------------------------
    def static_title(self):
        """The title picture: what shows when titleseq's art is missing,
        and what back from the main menu replays."""
        fb = display.buffer
        display.fill(0)
        if not ui.backdrop('title_128_96.COL.bin', 16):
            ui.text.centre(fb, b'WING COMMANDER', 50, ui.AMBER)
        ui.text.centre(fb, b'WING COMMANDER', 4, ui.AMBER)
        ui.small.centre(fb, b'THUMBYCOLOR EDITION  -  PRESS A', 118,
                        0xBDF7)
        ui.wait_release()
        while True:
            display.update()
            if buttonA.justPressed():
                return

    def intro(self):
        """SdlPlayDosStartupIntro (introfx.play, dos_intro.c:239): the
        Origin FX opening the DOS game shows before its title - the
        orchestra under its spotlight, the Earth behind it, the ORION
        logo zooming in and the fireworks that close it. The original
        plays it once per program start; it is skipped silently when
        its art is missing, as the title falls back to its static
        picture. The module is held only while it runs, like a
        funeral. scramble, its drawing engine, stays loaded
        afterwards; its frame scratch is claimed with the module and
        goes back to the heap when the title's pop list lets go."""
        # The same flicker fix the title's cinematic carries (see
        # titleseq.title): the intro paints one picture every FX_MS
        # (introfx.py:62), so its tick runs at 10 a second while it
        # plays - a still picture pushed once per wait instead of
        # twice - and the menu and the scenes have their 20 back after.
        display.setFPS(10)
        import introfx
        introfx.play()
        display.setFPS(20)
        del introfx
        sys.modules.pop('introfx', None)
        collect()

    def title(self):
        """Title_Sequence (titleseq.title, title.c:135): the opening
        cinematic, then the New Game / Continue menu. Returns True when
        a campaign is ready to fly - New started or a save loaded - and
        False to fall through to the main menu (left the menu, or the
        title art is missing). The module is held only while it runs,
        like a conversation or a funeral."""
        import campaign
        saved = campaign.State(self.ai)
        has_save = saved.load() and saved.over == 0
        # A phase starts with the room entire. Everything a flight or
        # a cutscene ever held - flight and pilot code included, the
        # title never flies - is popped and collected here first, so
        # titleseq and the world it pulls land in one fresh run of the
        # heap instead of small pieces carved out of a fragmented free
        # list. The cache forgets its frames too: what a flight cached
        # is done with.
        if 'flight' in sys.modules:
            sys.modules.pop('flight', None)
            sys.modules.pop('ai', None)
        for m in ('world', 'wcmath', 'sky', 'scramble', 'launchseq',
                  'ejectseq', 'introfx', 'funeralseq', 'deathseq',
                  'scene'):
            sys.modules.pop(m, None)
        CACHE.reset()
        collect()
        mem('pop')
        # The title's canvas, 14 KB in one block, is the title's own:
        # claimed now while the heap is fresh and given back whole when
        # the title ends. If the ask fails, titleseq runs its
        # text-less path instead of raising.
        try:
            TXT = bytearray(128 * 112)
        except MemoryError:
            TXT = None
        import titleseq
        mem('title')
        r = titleseq.title(has_save, self.T, CACHE, TXT, self.ai)
        CACHE.reset()                # the title's frames are done with
        del TXT                      # the canvas goes back to the heap
        del titleseq
        sys.modules.pop('titleseq', None)
        collect()
        if r is None:
            self.static_title()
            return False
        if r == 0:
            self.st = campaign.State(self.ai)
            self.st.campaign = 0
            self.st.save()
            return True
        if r == 1 and has_save:
            self.st = saved
            return True
        return False                    # B / MENU: title.c:432-436, :443


    def main_menu(self):
        import campaign
        while True:
            saved = campaign.State(self.ai)
            has_save = saved.load() and saved.over == 0
            items = []
            acts = []
            if has_save:
                items.append(b'Continue')
                acts.append(-1)
            for c in range(3):
                if D.exists('mod%d.wc' % c):
                    items.append(b'New: ' + CAMPAIGNS[c])
                    acts.append(c)
            items.append(b'Options')
            acts.append(10)
            items.append(b'Exit')
            acts.append(11)
            k = ui.menu(b'WING COMMANDER', items, 0)
            if k < 0:
                self.static_title()     # back replays the picture, not
                continue                # the hundred-second cinematic
            a = acts[k]
            if a == -1:
                self.st = saved
                return True
            if a == 10:
                self.options()
            elif a == 11:
                return False
            else:
                if has_save and ui.menu(b'OVERWRITE SAVE?',
                                        [b'No', b'Yes']) != 1:
                    continue
                self.st = campaign.State(self.ai)
                self.st.campaign = a
                self.st.save()
                return True

    def options(self):
        # The title lets the flight code go until a flight needs it
        # (docs/12 12.2); the speed names live there, so the module
        # comes back for this menu.
        import flight
        o = self.opts
        sel = 0
        while True:
            sp = o.get('speed', 0) % len(flight.TURN_MS)
            sel = ui.menu(b'OPTIONS', [
                b'Cockpit: ' + (b'on' if o['cockpit'] else b'off'),
                b'Stick: ' + (b'inverted' if o['invert'] else b'normal'),
                b'Sound: ' + (b'on' if o['sound'] else b'off'),
                b'Rumble: ' + (b'on' if o['rumble'] else b'off'),
                b'Speed: ' + flight.SPEED_NAMES[sp]], sel,
                hint=b'UP ON STICK = NOSE DOWN (NORMAL)')
            if sel < 0:
                save_opts(o)
                # Let the flight code go again when the menu closes -
                # it came back only for the speed names, and it drags
                # ai with it (flight.py:29); the rest of the flight-
                # free stretch does not want either held in the heap
                # the title churned (docs/12 12.2).
                sys.modules.pop('flight', None)
                sys.modules.pop('ai', None)
                collect()
                return
            if sel == 4:
                o['speed'] = (sp + 1) % len(flight.TURN_MS)
                continue
            key = ('cockpit', 'invert', 'sound', 'rumble')[sel]
            o[key] = 0 if o[key] else 1

    # --- aboard the Tiger's Claw ----------------------------------------------------
    def carrier(self):
        """The ship between missions. Returns False to leave the game."""
        import campaign
        st = self.st
        self.camp = D.Campaign(st.campaign)
        sel = 0
        while True:
            if st.over or st.series < 1:
                return True
            mis = D.Mission(st.campaign, st.series, st.mission)
            if not mis.valid:
                ui.message(b'CAMPAIGN', b'There are no more missions.')
                st.over = 1
                st.save()
                return True
            title = mis.series_name[:14] + b' ' + \
                str(st.mission + 1).encode()
            sel = ui.menu(title, [b'Mission briefing', b'Rec room',
                                  b'Kill board', b'Service record',
                                  b'Options', b'Save and exit'], sel,
                          hint=b'TCS TIGER\'S CLAW',
                          pic='recroom_128_96.COL.bin')
            if sel < 0 or sel == 5:
                st.save()
                return True
            if sel == 0:
                self.mission(mis)
                sel = 0
            elif sel == 1:
                self.rec_room(mis)
            elif sel == 2:
                self.kill_board()
            elif sel == 3:
                self.record()
            elif sel == 4:
                self.options()

    def talk(self, title, mis, which, picture, out=None, map_draw=None):
        """One conversation of this mission's packet. The packet (up to
        some 15 KB), the head and the backdrop are the conversation's
        own: claimed when it starts, given back whole when it ends, so
        the talking head runs in room that is all its own."""
        # Whatever a flight left loaded goes first: the head asks some
        # 18 KB in one block and the heap must be swept clean for it.
        # A later mission re-imports what it needs, and pays its
        # landing again - the price of starting each phase fresh.
        for m in ('flight', 'ai', 'world', 'wcmath', 'sky', 'scene'):
            sys.modules.pop(m, None)
        collect()
        import talk
        st = self.st
        pk = D.briefing_packet(st.campaign, st.series, st.mission)
        t = talk.Talk(self.ai, st, out, map_draw=map_draw,
                      picture=picture)
        t.run(title, pk, which, mis.series_name)
        del t, pk, talk
        sys.modules.pop('talk', None)
        collect()

    def rec_room(self, mis):
        k = 0
        while True:
            k = ui.menu(b'REC ROOM', [b'The bartender', b'Left table',
                                      b'Right table'], k)
            if k < 0:
                return
            self.talk(b'REC ROOM', mis, 2 + k, 'bar_128_61.COL.bin')

    def kill_board(self):
        st = self.st
        rows = []
        for i in range(len(st.pilots)):
            if st.death[i] == 0:
                rows.append((st.pilots[i][1], st.pilots[i][0],
                             self.ai.pilots[i][1]))
        rows.append((st.kills, st.missions, st.callsign.encode()))
        rows.sort(reverse=True)
        fb = display.buffer
        display.fill(0)
        ui.frame_title(b'KILL BOARD')
        ui.small.draw(fb, b'PILOT', 4, 15, ui.GREY)
        ui.small.draw(fb, b'SORTIES', 68, 15, ui.GREY)
        ui.small.draw(fb, b'KILLS', 102, 15, ui.GREY)
        y = 24
        for r in rows:
            me = r[2] == st.callsign.encode()
            col = ui.YELLOW if me else ui.WHITE
            ui.text.draw(fb, r[2], 4, y, col)
            ui.text.draw(fb, str(r[1]).encode(), 76, y, col)
            ui.text.draw(fb, str(r[0]).encode(), 106, y, col)
            y += 10
        ui.wait_key()

    def record(self):
        st = self.st
        lines = [self.ai.ranks[min(4, st.rank)] + b' ' + st.name.encode(),
                 b'Callsign ' + st.callsign.encode(),
                 b'Sorties ' + str(st.missions).encode() +
                 b'   Kills ' + str(st.kills).encode(),
                 b'Flying: ' + SHIP_NAMES[st.ship if 0 <= st.ship < 4 else 0],
                 b'Date ' + ('%04d.%03d' % (st.year, st.day)).encode()]
        for i in range(5):
            if st.medals[i]:
                lines.append(self.ai.medals[i] + b' x' +
                             str(st.medals[i]).encode())
        ui.page(b'SERVICE RECORD', lines)

    # --- one mission -------------------------------------------------------------------
    def mission(self, mis):
        import campaign
        st = self.st

        def flight_plan(y0, h):
            ui.draw_map(mis, y0, h)

        self.talk(b'BRIEFING', mis, 0, 'brief_128_61.COL.bin',
                  map_draw=flight_plan)
        k = ui.menu(b'LAUNCH?', [b'Launch', b'Flight plan', b'Back'])
        while k == 1:
            self.show_plan(mis)
            k = ui.menu(b'LAUNCH?', [b'Launch', b'Flight plan', b'Back'])
        if k != 0:
            return
        # The hard scenes the original plays around the launch
        # (gameflow.c:335-354): the walk through the hangar, the climb
        # onto the deck, the blast doors parting past the cockpit. The
        # ship is the type of the mission's player ship record
        # (gameflow.c:338-340) - the same one init_ship assigns to the
        # flight (world.py:465, 488).
        ship = mis.ship(mis.player_ship)[0]
        import scramble, launchseq
        scramble.hangar()            # PlayScrambleHangarScene :337
        scramble.deck(ship)          # scramble() :341
        launchseq.door(ship)         # LaunchPlayerShip() :354
        launchseq.cleanup()          # let go of the sets: the scenes
                                     # after the flight load them again
        # The two modules leave with this frame's names before the
        # flight is built. fly() pops them from sys.modules, but a pop
        # returns a module only when nothing holds it (docs/12 12.4):
        # these names are the holders, launchseq's globals hold
        # scramble with them, and scramble's hold its 12,288 byte
        # frame scratch. Dropping them here is what gives the flight
        # the room to claim the cockpit's 12 KB with its own code.
        del scramble, launchseq
        world, result = self.fly(mis)
        # world came with flight (flight.py:28), so binding the name
        # here is a hit on the already loaded module, not a copy of
        # code: it is only needed for the R_* constants of the result.
        import world as W
        out = campaign.Outcome()
        out.result = result
        if result == W.R_ABORT:
            return
        if result == W.R_DEAD:
            import deathseq          # the death scene draws with
                                     # scramble's helpers: scramble
                                     # lands again for it (docs/12
                                     # 12.2 - every phase pays its
                                     # landing when it starts fresh)
            deathseq.death(ship)     # death_sequence (gameflow.c:401)
            import scramble
            scramble.cleanup()       # free_3Space (:402) before the funeral
            # the scene is done with them: they go before the funeral
            # and the pages ask their room (docs/12 12.4)
            del scramble, deathseq
            sys.modules.pop('scramble', None)
            sys.modules.pop('deathseq', None)
            collect()
            self.funeral(1)          # funeral_sequence (:407): the
                                     # player's own honour guard, played
                                     # before the campaign is ended
            ui.page(b'KILLED IN ACTION', [
                b'Your ship was destroyed.', b'',
                b'The mission can be flown again from the last saved '
                b'game.'], ui.AMBER)
            return
        if result == W.R_LANDED:
            # gameflow.c:362-369: after landing comes the carrier
            # fly-off, then the deck landing with the crew's look at
            # the damage (calculate_damage_level is world.py:1019-1036)
            # The fly-off's phase A - the 100-frame scripted approach
            # (launch.c:200-288) that gameflow.c:363-364 runs on the
            # object the player landed on - needs the live world for
            # the carrier's frame, position and radius and the player's
            # scale; without it flyoff plays the deck slide alone, as
            # the selfplay harness calls it (wc1_selfplay.py:220).
            import launchseq, scramble   # re-claim what fly() let go
                                         # after the flight (docs/12
                                         # 12.2): flyoff's 3-D approach
                                         # imports the sky and the
                                         # flight code for itself,
                                         # guarded - no room, deck
                                         # slide only
            launchseq.flyoff(ship, world)
            scramble.landing(world.damage_level(), ship)
            scramble.cleanup()           # the scenes are done with
                                         # the sprite sets
            del scramble, launchseq
            sys.modules.pop('scramble', None)
            sys.modules.pop('launchseq', None)
            collect()                    # the debriefing's face asks
                                         # its 18 KB over none of this
        if result == W.R_EJECTED:
            # fly() let the flight code go with the flight (docs/12
            # 12.2); ejectseq lands its own 8.5 KB of code and
            # nothing else now - what the scene draws it imports
            # inside, guarded (docs/12 12.4) - and if even the
            # module does not fit, the pilot is picked up without
            # the chase scene, as a rescue the player never sees,
            # instead of an OOM ending the game.
            try:
                import ejectseq
            except MemoryError:
                ejectseq = None
            if ejectseq is not None:
                # ejection_sequence (:372). The live world, the type
                # table, the palette and the shared cache are what the
                # 3-D chase (eject.c:143-181) needs: the ship snapshot,
                # the pilot's class/radius/scale, the .wcs blits and
                # the sprite sets. Without them eject is the
                # sprite-only scene.
                ejectseq.eject(ship, world, self.T, self.pal, CACHE)
                stranded = ejectseq.check_stranded(world)  # :373
                if stranded:
                    ejectseq.stranded()                    # :374-375
                del ejectseq
                sys.modules.pop('ejectseq', None)
                # the seat scene's helper landed inside eject(),
                # guarded: if it fitted, this pop gives its 22.2 KB
                # back, scratch included (docs/12 12.2); if it did
                # not fit there is nothing to give back.
                if 'scramble' in sys.modules:
                    import scramble
                    scramble.cleanup()       # free_3Space (:402)
                    del scramble
                    sys.modules.pop('scramble', None)
                collect()
                if stranded:
                    return                   # the campaign ends here
            else:
                # the import died on the way in: all that can be
                # reclaimed is what a partial landing left behind -
                # with ejectseq's module-top imports gone there is
                # normally nothing in the modules to reclaim.
                if 'scramble' in sys.modules:
                    import scramble
                    scramble.cleanup()
                    del scramble
                    sys.modules.pop('scramble', None)
                collect()
        world.cleanup_objectives()
        out.ejected = result == W.R_EJECTED
        campaign.post_mission(st, self.camp, world, out)
        del world
        collect()
        if out.ejected:
            ui.page(b'EJECTED', [
                b'You punched out and were picked up by a rescue '
                b'shuttle. Your fighter is lost.'], ui.AMBER)
        else:
            self.talk(b'DEBRIEFING', mis, 1, 'debrief_128_61.COL.bin', out)
        # gameflow.c:468-469: a wingman who did not come back is buried
        # after the debriefing, before the office visit and the report
        if out.wingman_lost:
            self.funeral(0)
        self.summary(out, mis)
        campaign.apply_awards(st, out)
        st.save()
        # A finished series plays the scripted transition the original
        # puts between series (pilot.cpp:36 ShowMeanwhileTransition).
        # The campaign endings 0x40/0x41 are handled by ending().
        if 0 <= out.sequence <= 7:
            self.meanwhile(out.sequence, 1 if out.series_failed else 0,
                           out, mis.series_name)
        if out.finished:
            self.ending(out)

    def show_plan(self, mis):
        fb = display.buffer
        display.fill(0)
        ui.frame_title(b'FLIGHT PLAN')
        ui.draw_map(mis, 13, 62)
        y = 78
        for o in mis.objectives[:6]:
            ui.small.draw(fb, o[2][:31], 3, y, 0xBDF7)
            y += 7
        ui.wait_key()

    def fly(self, mis):
        # Nothing a video or a cutscene held is still around by the
        # time a flight starts: talk, introfx, titleseq, ejectseq, the
        # funeral and the death scene each dropped themselves in the
        # function that ran them, and the launch scenes' sprite sets
        # are freed by scramble.cleanup. The launch scenes' modules go
        # here with the caller's names dropped by mission() (docs/12
        # 12.4): scramble carries its 12,288 byte frame scratch, and
        # launchseq held the sky, the flight and the pilot code with
        # its own imports until those moved into _approach - landing
        # them at the launch is what left no hole for the flight
        # (device log 2026-11-27). With all of them collected, the
        # flight's code landing, its world and its cockpit buffer meet
        # a heap in one piece again.
        sys.modules.pop('scene', None)
        sys.modules.pop('launchseq', None)
        sys.modules.pop('scramble', None)
        collect()
        mem('launch')
        # The title let the flight code go for the flight-free
        # stretch (docs/12 12.2); it comes back here, where the
        # briefing has left its room behind.
        import flight                # noqa: comes back if unloaded
        # flight.py:28 imported world with itself; binding the name
        # now is free - the module is resident, and the end-of-flight
        # screens below read the R_* constants off it.
        import world as W
        # The cockpit's 12 KB are the flight's own buffer: passed in
        # nothing, the flight claims it at start and gives it back
        # whole when the flight ends.
        fl = flight.Flight(self.T, self.ai, (ui.small, ui.text), self.pal,
                           self.st, mis, self.opts,
                           self.sfx and self.opts.get('sound', 1),
                           CACHE)
        mem('flight')
        gc_pace()
        # pictures as fast as the device manages, up to flight.PICTURES (25) a second; game
        # turns come by the clock (flight.TURN_MS), not by the frame
        display.setFPS(flight.PICTURES)
        ui.wait_release()
        result = 0
        while result == 0:
            result = fl.frame()
            display.update()
            if result == 0 and buttonMENU.justPressed():
                result = fl.pause()
                ui.wait_release()
        w = fl.w
        pr, tr = fl.rates()
        print('WC rate pictures/s %d.%d turns/s %d.%d slow %d worst %dms'
              ' sound %d' % (pr // 10, pr % 10, tr // 10, tr % 10,
                             fl.slow, fl.worst, 1 if fl.sfx else 0))
        display.setFPS(20)
        if result == W.R_DEAD:
            for i in range(24):
                G.fill_rows(display.buffer, 0, 128,
                            0xFFFF if i < 4 else (0xF800 if i < 10 else 0))
                display.update()
        elif result == W.R_LANDED:
            for i in range(10):
                G.dim_rows(display.buffer, 0, 128)
                display.update()
        if self.sfx:
            audio_stop()
        save_opts(self.opts)
        del fl
        CACHE.reset()               # the flight's cached frames go too
        collect()                   # cockpit buffer and sets with it
        # flight, ai and sky leave with the flight. The room their
        # code landed into pays for the scenes after it - the fly-off
        # re-imports them through launchseq's _approach, the ejection
        # through ejectseq - and for the debriefing's face (docs/12
        # 12.2). world stays: its objects are the score and the fly-
        # off's carrier, and its constants are read off the name the
        # caller rebinds. The local name goes first: a module held by
        # a live frame's name does not come back on a pop (docs/12
        # 12.4).
        del flight
        sys.modules.pop('flight', None)
        sys.modules.pop('ai', None)
        sys.modules.pop('sky', None)
        collect()
        mem('landed')
        return w, result

    def summary(self, out, mis):
        st = self.st
        lines = [b'Kills: ' + str(out.kills).encode() +
                 b'   Wingman: ' + str(out.wing_kills).encode(), b'']
        for o in out.objectives:
            lines.append((b'+ ' if o[3] & 2 else b'- ') + o[2])
        if out.wingman_lost:
            lines.append(b'')
            lines.append(b'Your wingman did not return.')
        ui.page(b'MISSION REPORT', lines)
        if 0 <= out.medal < 5:
            ui.page(b'DECORATION', [
                b'For your conduct on this mission you are awarded the',
                b'', self.ai.medals[out.medal] + b'.'], ui.YELLOW)
        if out.promoted:
            ui.page(b'PROMOTION', [
                b'You are promoted to',
                b'', self.ai.ranks[min(4, st.rank + 1)]], ui.YELLOW)
        if out.ship_changed and not out.finished:
            ui.page(b'TRANSFER', [
                b'You are reassigned. Your new fighter is the',
                b'', SHIP_NAMES[st.ship if 0 <= st.ship < 4 else 0] + b'.'])

    def meanwhile(self, sc, variant, out=None, series=None):
        """The scripted cutscene between series (docs/06 6.1). The
        interpreter and the mid<NN>.wc block are held only while it
        runs, like a conversation."""
        if not D.exists('mid%02d.wc' % sc):
            return
        import scene
        scene.show(sc, variant, self.st, self.ai, out, series)
        del scene
        sys.modules.pop('scene', None)
        collect()

    def funeral(self, kind):
        """funeral_sequence (docs/06 6.2): the honour guard at the
        casket. kind 1 when the player died (gameflow.c:407), kind 0
        when a wingman did not come back (:469). The scene module is
        held only while it runs, like a conversation or a meanwhile."""
        import funeralseq
        funeralseq.funeral(kind, self.ai, self.st)
        del funeralseq
        sys.modules.pop('funeralseq', None)
        collect()

    def ending(self, out):
        st = self.st
        if out.sequence == 0x40:
            ui.page(b'VICTORY', [
                b'The Kilrathi are driven out of the Vega sector.', b'',
                b'The Terran Confederation owes that to the pilots of '
                b'the Tiger\'s Claw - and to you.'], ui.YELLOW)
        elif out.sequence == 0x41:
            ui.page(b'RETREAT', [
                b'The Tiger\'s Claw withdraws from the Vega sector. '
                b'The campaign is lost.'], ui.AMBER)
        else:
            ui.page(b'THE END', [b'The campaign is over.'])
        st.save()


def main():
    if not (D.exists('pal.wc') and D.exists('types.wc') and
            D.exists('ai.wc') and D.exists('mod0.wc')):
        no_data()
        return
    if assets_stale():
        ui_notice((b'GAME DATA IS OLD', b'', b'Large ships will be',
                   b'invisible. Run', b' tool/', b' wc1_convert.py',
                   b'again and deploy', b'the assets folder.', b'',
                   b'A: go on'))
    game = Game()
    game.intro()               # the Origin FX opening, once per
                               # program start, before the title
    go = game.title()          # the cinematic and its menu: straight
    while True:                # into the campaign when one was picked
        if not go and not game.main_menu():
            break
        game.carrier()
        go = False
    display.fill(0)
    display.update()
    reset()


main()
