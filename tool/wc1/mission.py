"""MODULE.00x / CAMP.00x / BRIEFING.00x records (host side).

Layouts follow wc1-re src/cmpgn.c (LoadMissionData, LoadBriefingData),
src/gameflow.c (UpdateSeries, FullMissionScore) and include/wcdata.h.
The device reads the very same records from the repacked mod/camp/brf
files; this module exists for the converter's sanity checks and for
`wc1_convert.py --dump SERIES MISSION`.
"""

import struct

MISSIONS = 64
NAV_PER_MISSION = 16
SHIPS_PER_MISSION = 32
OBJECTIVES_PER_MISSION = 16
HEADER_SIZE = 24
NAV_SIZE = 77
OBJECTIVE_SIZE = 64
SHIP_SIZE = 42
AUX_SIZE = 40
SERIES_SIZE = 0x5A

NAV_FMT = '<30sb3iH8b2h10h'
SHIP_FMT = '<hhbbhb3i3hbhhhhhbbbb'
assert struct.calcsize(NAV_FMT) == NAV_SIZE
assert struct.calcsize(SHIP_FMT) == SHIP_SIZE


def cstr(raw):
    return raw.split(b'\0', 1)[0].decode('latin1')


def mission_index(series, mission):
    return mission + series * 4


def read_mission(module, series, mission):
    """module: PacketFile of MODULE.00x -> dict (None if the slot is empty)."""
    m = mission_index(series, mission)
    head = struct.unpack_from('<12h', module.section(0), m * HEADER_SIZE)
    if head[2] < 0:
        return None
    navs = []
    data = module.section(1)
    for i in range(NAV_PER_MISSION):
        f = struct.unpack_from(NAV_FMT, data,
                               (m * NAV_PER_MISSION + i) * NAV_SIZE)
        navs.append(dict(name=cstr(f[0]), type=f[1], pos=f[2:5],
                         radius=f[5],
                         triggers=[(f[6 + k * 2], f[7 + k * 2])
                                   for k in range(4)],
                         preload=f[14:16], ships=list(f[16:26])))
    objectives = []
    data = module.section(2)
    for i in range(OBJECTIVES_PER_MISSION):
        off = (m * OBJECTIVES_PER_MISSION + i) * OBJECTIVE_SIZE
        typ, index = struct.unpack_from('<hh', data, off)
        if typ == -1:
            break
        objectives.append(dict(type=typ, index=index,
                               text=cstr(data[off + 4:off + 64])))
    ships = []
    data = module.section(3)
    for i in range(SHIPS_PER_MISSION):
        f = struct.unpack_from(SHIP_FMT, data,
                               (m * SHIPS_PER_MISSION + i) * SHIP_SIZE)
        ships.append(dict(type=f[0], side=f[1], leader=f[2],
                          mission_type=f[4], nav=f[5], pos=f[6:9],
                          pitch=f[9], yaw=f[10], roll=f[11],
                          formation_spot=f[12], speed=f[13], rating=f[14],
                          pilot=f[15], state=f[18],
                          leader_index=f[19], formation=f[20],
                          target=f[21]))
    return dict(entry_nav=head[0], home_ship=head[1], player_ship=head[2],
                initial=list(head[3:11]), navs=navs,
                objectives=objectives, ships=ships)


def read_series(camp_info, series):
    """camp_info: CAMP.00x section 1; series is 1-based."""
    base = (series - 1) * SERIES_SIZE
    if base + SERIES_SIZE > len(camp_info):
        return None
    debrief_pilot, count = struct.unpack_from('<hb', camp_info, base)
    required, = struct.unpack_from('<h', camp_info, base + 3)
    seq, win, win_ship, lose, lose_ship = struct.unpack_from(
        '<5b', camp_info, base + 5)
    missions = []
    for k in range(4):
        off = base + 10 + k * 20
        medal, medal_score = struct.unpack_from('<hh', camp_info, off)
        scores = struct.unpack_from('<16b', camp_info, off + 4)
        missions.append(dict(medal=medal, medal_score=medal_score,
                             scores=list(scores)))
    return dict(debrief_pilot=debrief_pilot, missions=count,
                required=required, sequence=seq, win=win,
                win_ship=win_ship, lose=lose, lose_ship=lose_ship,
                mission_info=missions)


def read_scene(packet, scene_offset, text_offset):
    """One conversation: list of 13-byte ConversationSceneRecord tuples
    with their text resolved (branch tests kept as raw bytes)."""
    out = []
    pos = scene_offset
    while pos + 13 <= len(packet):
        shot, colour, talker, duration, tests, text, mouth, face = \
            struct.unpack_from('<bbbhhhhh', packet, pos)
        if shot == -2:
            break
        t = packet[text_offset + text:].split(b'\0', 1)[0]
        tt = b''
        if tests:
            tt = packet[text_offset + tests:].split(b'\0', 1)[0]
        out.append((shot, colour, talker, duration, tt,
                    t.decode('latin1')))
        pos += 13
    return out
