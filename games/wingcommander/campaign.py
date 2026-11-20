# campaign.py - campaign state and the rules between missions
# (wc1-re src/gameflow.c PostMission / UpdateSeries, src/killbrd.c
# stInitialCampaignState; GPL-3.0).
#
# The saved game is one small JSON file next to the game (wc_save.json).

import json
from random import randint

SAVE_FILE = 'wc_save.json'

# badges[] slots (the ribbons of the original's medal case)
B_FIRST_MISSION = 0
B_FIVE_MISSIONS = 1
B_TEN_MISSIONS = 2
B_FIFTEEN_MISSIONS = 3
B_FIVE_KILLS = 4
B_TWENTY_FIVE_KILLS = 5
B_SHIP_BASE = 6


class State:
    def __init__(self, ai=None):
        self.campaign = 0
        self.callsign = 'MAVERICK'
        self.name = 'BLAIR'
        self.rank = 0
        self.missions = 0
        self.kills = 0
        self.ship = 0
        self.medals = [0, 0, 0, 0, 0]
        self.badges = [0] * 12
        self.series = 1
        self.mission = 0
        self.history = []
        self.death = [0] * 8          # personalityDeathMission
        self.day = 110
        self.year = 2654
        self.ejects = 0
        self.promotion_score = 0
        self.mission_score = 0
        self.series_score = 0
        self.over = 0                 # 0 running, 1 won, 2 lost, 3 dead
        # wingmen statistics for the kill board: [missions, kills]
        self.pilots = []
        if ai is not None:
            for p in ai.pilots[:8]:
                self.pilots.append([p[3], p[4]])

    def to_dict(self):
        return {k: getattr(self, k) for k in (
            'campaign', 'callsign', 'name', 'rank', 'missions', 'kills',
            'ship', 'medals', 'badges', 'series', 'mission', 'history',
            'death', 'day', 'year', 'ejects', 'promotion_score',
            'mission_score', 'series_score', 'over', 'pilots')}

    def save(self):
        try:
            with open(SAVE_FILE, 'w') as f:
                json.dump(self.to_dict(), f)
            return True
        except OSError:
            return False

    def load(self):
        try:
            with open(SAVE_FILE, 'r') as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        for k in d:
            setattr(self, k, d[k])
        return True


class Outcome:
    """What the debriefing and the next briefing need to know."""

    def __init__(self):
        self.result = 0
        self.kills = 0
        self.wing_kills = 0
        self.score = 0
        self.full_score = 0
        self.ejected = False
        self.promoted = False
        self.medal = -1
        self.ship_changed = False
        self.prev_ship = 0
        self.series_failed = False
        self.office = False
        self.flown_series = 1
        self.flown_mission = 0
        self.wingman_lost = False
        self.objectives = []          # copies of [type, index, text, flags]
        self.sequence = -1
        self.finished = False


def post_mission(st, camp, world, out):
    """PostMission + UpdateSeries. Returns the Outcome for the debrief."""
    out.flown_series = st.series
    out.flown_mission = st.mission
    out.kills = world.kills
    out.wing_kills = world.wing_kills
    out.wingman_lost = world.wingman_lost
    out.objectives = [list(o) for o in world.mis.objectives]
    minfo = camp.mission(st.series, st.mission)
    got, full = world.players_score(minfo[2:])
    out.score = got
    out.full_score = full
    st.mission_score = world.score
    # --- PostMission ---
    old = st.kills
    if old < 5 <= old + world.kills:
        st.badges[B_FIVE_KILLS] = 1
    elif old < 25 <= old + world.kills:
        st.badges[B_TWENTY_FIVE_KILLS] = 1
    if B_SHIP_BASE + st.ship < 12:
        st.badges[B_SHIP_BASE + st.ship] = 1
    st.missions += 1
    if st.missions == 1:
        st.badges[B_FIRST_MISSION] = 1
    if st.missions in (1, 5):
        st.badges[B_FIVE_MISSIONS] = 1 if st.missions == 5 else \
            st.badges[B_FIVE_MISSIONS]
    elif st.missions == 10:
        st.badges[B_TEN_MISSIONS] = 1
    elif st.missions == 15:
        st.badges[B_FIFTEEN_MISSIONS] = 1
    st.kills += world.kills
    if old // 5 < st.kills // 5:
        st.promotion_score += 1
    for r in world.deaths:
        st.death[r] = out.flown_mission + out.flown_series * 4
    wing_rating = -1
    if world.wingman >= 0:
        wing_rating = world.o[world.wingman].rating
    for p in range(len(st.pilots)):
        if p == wing_rating:
            st.pilots[p][0] += 1
            st.pilots[p][1] += world.wing_kills
        elif st.death[p] == 0:
            flown = randint(0, 2)
            st.pilots[p][0] += flown
            if flown:
                st.pilots[p][1] += randint(0, world.kills)
    # --- UpdateSeries ---
    sinfo = camp.series(st.series)
    if got == full:
        st.promotion_score += 1
    st.series_score += got
    medal_score = world.medal_score
    if world.wingman_lost:
        medal_score = max(0, world.score - 15)
    if minfo[1] <= medal_score:
        out.medal = minfo[0]
    st.mission += 1
    if st.mission >= sinfo[1]:
        out.prev_ship = st.ship
        out.sequence = sinfo[3]
        st.history.append(st.series)
        if st.series_score >= sinfo[2]:
            st.series = sinfo[4]
            st.ship = sinfo[5]
            out.series_failed = False
        else:
            st.series = sinfo[6]
            st.ship = sinfo[7]
            out.series_failed = True
        if st.series != -1 and out.prev_ship != st.ship:
            out.ship_changed = True
            out.office = True
        st.series_score = 0
        st.mission = 0
        if st.series == -1 or st.series == 255:
            st.series = -1
            out.finished = True
            st.over = 2 if out.sequence == 0x41 else 1
    # --- GameFlow: promotion ---
    if not out.ejected:
        if randint(0, 5) + st.promotion_score > 7:
            st.promotion_score = 0
            top = 3 if st.campaign == 0 else 4
            if st.rank < top:
                out.promoted = True
                out.office = True
    else:
        st.promotion_score = max(0, st.promotion_score - 1)
        st.ejects += 1
        if st.ejects == 1:
            out.medal = 3             # Golden Sun for the first ejection
        out.office = True
    # MoveNewCampaign: the calendar
    st.day += randint(0, 1) + (5 if st.mission == 0 else 0)
    if st.day >= 366:
        st.day -= 365
        st.year += 1
    return out


def apply_awards(st, out):
    """After the debriefing has been shown."""
    if out.promoted:
        st.rank += 1
    if 0 <= out.medal < 5:
        st.medals[out.medal] += 1
