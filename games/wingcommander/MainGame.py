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
#
# The game logic is derived from wc1-re and therefore GPL-3.0 (see
# LICENSE.txt in this directory).

from thumby_engine.platform import (display, IS_THUMBY_COLOR, buttonA,
                                    buttonB, buttonMENU, audio_open_id,
                                    audio_set_volume, audio_stop)
from thumbyHardware import reset
from gc import collect, mem_free
import json

if IS_THUMBY_COLOR:
    from engine import freq
    freq(300_000_000)

import ui
import wcdata as D
import wcgfx as G

OPT_FILE = 'wc_settings.json'
SHIP_NAMES = (b'Hornet', b'Rapier', b'Scimitar', b'Raptor')
CAMPAIGNS = (b'Wing Commander', b'Secret Missions', b'Secret Missions 2')
SFX = ('sfx_laser.ima', 'sfx_missile.ima', 'sfx_hit.ima', 'sfx_boom.ima',
       'sfx_pop.ima')


def load_opts():
    opts = {'cockpit': 1, 'invert': 0, 'sound': 1, 'rumble': 1}
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


class Game:
    def __init__(self):
        self.opts = load_opts()
        self.T = D.Types()
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
        display.setFPS(20)
        print('WC: ready, free memory', mem_free())

    # --- title and main menu ----------------------------------------------------
    def title(self):
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
                self.title()
                continue
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
        o = self.opts
        sel = 0
        while True:
            sel = ui.menu(b'OPTIONS', [
                b'Cockpit: ' + (b'on' if o['cockpit'] else b'off'),
                b'Stick: ' + (b'inverted' if o['invert'] else b'normal'),
                b'Sound: ' + (b'on' if o['sound'] else b'off'),
                b'Rumble: ' + (b'on' if o['rumble'] else b'off')], sel,
                hint=b'UP ON STICK = NOSE DOWN (NORMAL)')
            if sel < 0:
                save_opts(o)
                return
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

    def rec_room(self, mis):
        import talk
        st = self.st
        pk = D.briefing_packet(st.campaign, st.series, st.mission)
        k = 0
        while True:
            k = ui.menu(b'REC ROOM', [b'The bartender', b'Left table',
                                      b'Right table'], k)
            if k < 0:
                return
            t = talk.Talk(self.ai, st, picture='bar_128_61.COL.bin')
            t.run(b'REC ROOM', pk, 2 + k, mis.series_name)

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
        import talk
        import world as W
        st = self.st
        pk = D.briefing_packet(st.campaign, st.series, st.mission)

        def flight_plan(y0, h):
            ui.draw_map(mis, y0, h)

        t = talk.Talk(self.ai, st, map_draw=flight_plan,
                      picture='brief_128_61.COL.bin')
        t.run(b'BRIEFING', pk, 0, mis.series_name)
        k = ui.menu(b'LAUNCH?', [b'Launch', b'Flight plan', b'Back'])
        while k == 1:
            self.show_plan(mis)
            k = ui.menu(b'LAUNCH?', [b'Launch', b'Flight plan', b'Back'])
        if k != 0:
            return
        del t
        collect()
        world, result = self.fly(mis)
        out = campaign.Outcome()
        out.result = result
        if result == W.R_ABORT:
            return
        if result == W.R_DEAD:
            ui.page(b'KILLED IN ACTION', [
                b'Your ship was destroyed.', b'',
                b'The mission can be flown again from the last saved '
                b'game.'], ui.AMBER)
            return
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
            t = talk.Talk(self.ai, st, out,
                          picture='debrief_128_61.COL.bin')
            t.run(b'DEBRIEFING', pk, 1, mis.series_name)
        self.summary(out, mis)
        campaign.apply_awards(st, out)
        st.save()
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
        import flight
        import world as W
        fl = flight.Flight(self.T, self.ai, (ui.small, ui.text), self.pal,
                           self.st, mis, self.opts,
                           self.sfx and self.opts.get('sound', 1))
        collect()
        print('WC: flight ready, free memory', mem_free())
        display.setFPS(20)
        ui.wait_release()
        result = 0
        while result == 0:
            result = fl.frame()
            display.update()
            if result == 0 and buttonMENU.justPressed():
                result = fl.pause()
                ui.wait_release()
        w = fl.w
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
        collect()
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
    game = Game()
    game.title()
    while True:
        if not game.main_menu():
            break
        game.carrier()
    display.fill(0)
    display.update()
    reset()


main()
