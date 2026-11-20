# world.py - the Wing Commander flight simulation (no drawing, no input).
#
# A port of the reconstructed game core (https://github.com/neuromancer/
# wc1-re, GPL-3.0) to integer MicroPython. Function names follow the
# original so the two can be read side by side:
#
#   spc.c    update_objects_in_space, accelerate_and_move_object,
#            rotate_object, house_keep_objects, object_collision
#   ship.c   inflict_damage, internal_damage, explode, Explosion,
#            explosion_shock_wave, fire_weapon, replenish_*
#   mission.c  init_ship, Set_up_ship_info, set_up_action_sphere,
#            set_up_next_wave
#   screen.c cleanup_objectives     gameflow.c  score handling
#
# One game turn is 1/20 s (the original's default flight frame rate).
# Objects 0..9 are ships (0 = the player), the rest are bolts, missiles,
# explosions and rocks.

from random import randint
import wcmath as M
import wcdata as D

NSHIP = 10
NOBJ = 44

# ObjectClass
C_NULL = 0
C_EXPLOSION = 5
C_DEBRIS = 6
C_PROJECTILE = 8
C_ASTEROID = 9
C_MINE = 10
C_MISSILE = 11
C_SHIP = 12
C_CAPITAL = 13

# SpecialManeuver
SM_NONE = -1
SM_AFTERBURNER = 1
SM_SUPER_BRAKE = 3
SM_KILL_ENGINES = 5
SM_STOP_DRIFT = 6
SM_LOST_CONTROL = 8
SM_DYING = 9

# ShipMissionType
MT_NONE = -1
MT_PATROL = 0
MT_ESCORT = 1
MT_STRIKE = 2
MT_DEFEND = 3
MT_WINGMAN = 4
MT_ROUT = 5
MT_GOTO_WARP = 6
MT_WARP_ARRIVE = 7
MT_RENDEZVOUS = 9
MT_COME_HOME = 10

T_SIT_STILL = 1
T_RAM = 4

SIDE_CONFED = 0
SIDE_KILRATHI = 1

# ObjectType
OT_TIGERS_CLAW = 8
OT_ASTEROID_FIELD = 22
OT_MINE_FIELD = 23
OT_LASER = 24
OT_TURRET = 27
OT_DUMBFIRE = 28
OT_HEATSEEKER = 29
OT_FF = 30
OT_IMREC = 31
OT_MINE = 33
OT_ASTEROID1 = 34
OT_EXPLOSION0 = 48
OT_EXPLOSION1 = 49
OT_EXPLOSION2 = 50
OT_LASER_SPARK = 51

# turns an explosion0/1/2 or a spark stays (two turns per frame)
EXPLOSION_TURNS = (20, 12, 16, 12)

# flight results (nArcadeState)
R_FLYING = 0
R_LANDED = 1
R_EJECTED = 2
R_DEAD = 4
R_ABORT = 5


def rnd(n):
    """RandomBelow: 0 .. n-1"""
    return randint(0, n - 1) if n > 0 else 0


def rndle(n):
    """RandomBelowOrEqual: 0 .. n"""
    return randint(0, n) if n > 0 else 0


def find_ratio(a0, a1, v, b0, b1):
    if a1 == a0:
        return b0
    return b0 + (v - a0) * (b1 - b0) // (a1 - a0)


class Obj:
    def __init__(self, index):
        self.i = index
        self.m = [M.ONE, 0, 0, 0, M.ONE, 0, 0, 0, M.ONE]
        self.weapons = []
        self.sh = [0, 0]
        self.shmax = [0, 0]
        self.ar = [0, 0, 0, 0]
        self.clear()

    def clear(self):
        self.cls = C_NULL
        self.typ = 0
        self.x = self.y = self.z = 0           # 24.8
        self.vx = self.vy = self.vz = 0        # 24.8 per turn
        self.owner = -1
        self.counter = 0
        self.radius = 0
        self.mass = 0
        self.scale = 0
        self.grace = 0
        # ships and missiles
        self.side = 2
        self.speed = 0                          # set speed, 24.8
        self.maxspd = 0
        self.rp = self.ry = self.rr = 0         # rotation, degrees / turn
        self.gp = self.gy = self.gr = 0         # rotation goals, degrees
        self.dmg = 0                            # acShipDmg (core hits)
        self.acc = 0                            # asShipAccumulatedDmg
        self.energy = 100
        self.fuel = 0
        self.special = SM_NONE
        self.abtimer = 0
        self.iondmg = 0
        self.plant = 0
        self.pilot_hp = 4
        self.guns_lost = 0
        self.heat = 0
        # intelligence
        self.target = -1
        self.mtype = MT_NONE
        self.objective = -1
        self.tactic = -1
        self.man = -1
        self.seq = 0
        self.tot = 0
        self.level = 0
        self.rating = -1
        self.stress = 0
        self.cooldown = 0
        self.event = -1
        self.turn_reg = 1
        self.turn_int = 1
        self.turns = 0
        self.mship = -1
        self.mtarget = -1
        self.leader = -1
        self.fdx = self.fdy = self.fdz = 0      # formation offset, units
        self.spx = self.spy = self.spz = 0      # mission spot, 24.8
        self.nav = -1
        self.attacker = -1
        self.pointing = 1
        self.lastcol = -1
        self.alert = 0                          # collision alert turns
        self.msg = -1
        # view (filled by the renderer)
        self.vis = False
        self.rad = 0
        self.sx = self.sy = 0
        self.dist = 0
        self.vz_view = 0


class World:
    def __init__(self, types, ai, mission, camp):
        self.T = types
        self.ai = ai
        self.mis = mission
        self.camp = camp                 # campaign state (campaign.State)
        self.o = [Obj(i) for i in range(NOBJ)]
        self.tick = 0
        self.result = R_FLYING
        self.nav = -1                    # current action sphere
        self.wave = -1
        self.hazards = []                # [x, y, z (units), radius, kind]
        self.wingman = -1
        self.kills = 0
        self.wing_kills = 0
        self.score = 0
        self.medal_score = 0
        self.wingman_lost = False
        self.deaths = []
        self.landing_ok = False
        self.dest = 0                    # index into mission.objectives
        self.messages = []               # pending (text bytes, colour)
        self.sfx = []                    # pending sound ids
        self.flash = 0                   # player hit flash turns
        self.shake = 0
        self.engage_ok = True
        # scratch results of ship_vs_ship (nTgtRange, nFacing..., vToTgt)
        self.RANGE = 0
        self.FACE = 0
        self.TFACE = 0
        self.tx = self.ty = self.tz = 0
        self.brain = None                # set by ai.Brain()
        self.solid = []

    # --- helpers -----------------------------------------------------------
    def say(self, text, colour=0xFFE0):
        if len(self.messages) < 4:
            self.messages.append((text, colour))

    def sound(self, sid):
        if len(self.sfx) < 4:
            self.sfx.append(sid)

    def find_ship(self, mship):
        """find_ship_index"""
        if mship < 0:
            return -1
        o = self.o
        for i in range(NSHIP):
            if o[i].cls >= C_SHIP and o[i].mship == mship:
                return i
        return -1

    def free_ship_slot(self):
        o = self.o
        for i in range(1, NSHIP):
            if o[i].cls == C_NULL:
                return i
        return -1

    def free_slot(self):
        o = self.o
        for i in range(NSHIP, NOBJ):
            if o[i].cls == C_NULL:
                return i
        return -1

    def active(self, i):
        """not unactive()"""
        if i < 0:
            return False
        ob = self.o[i]
        return ob.cls >= C_SHIP and ob.special != SM_DYING

    def dist(self, a, b):
        """Centre distance in world units."""
        return M.mag((b.x - a.x) >> 8, (b.y - a.y) >> 8, (b.z - a.z) >> 8)

    def ship_vs_point(self, ob, px, py, pz):
        """get_facing_range_from_point (point in 24.8)."""
        dx = (px - ob.x) >> 8
        dy = (py - ob.y) >> 8
        dz = (pz - ob.z) >> 8
        d = M.mag(dx, dy, dz)
        self.tx = dx; self.ty = dy; self.tz = dz
        self.RANGE = d - 2 * ob.radius
        if d > 0:
            m = ob.m
            self.FACE = ((dx * m[6] + dy * m[7] + dz * m[8]) // d) * 100 >> 14
        else:
            self.FACE = 100
        return d

    def ship_vs_ship(self, ob, other):
        """get_facing_range_from_object"""
        d = self.ship_vs_point(ob, other.x, other.y, other.z)
        self.RANGE -= other.radius
        if d > 0:
            m = other.m
            self.TFACE = (-(self.tx * m[6] + self.ty * m[7] +
                            self.tz * m[8]) // d) * 100 >> 14
        else:
            self.TFACE = 0

    def distance_from_object(self, ob, other):
        return self.dist(ob, other) - ob.radius - other.radius

    # --- object setup --------------------------------------------------------
    def set_objects_data(self, ob, typ, owner):
        T = self.T
        ob.clear()
        ob.typ = typ
        ob.cls = T.f[D.T_CLASS][typ]
        ob.owner = owner
        ob.radius = T.f[D.T_RADIUS][typ]
        ob.mass = T.f[D.T_MASS][typ]
        ob.scale = T.f[D.T_SCALE][typ]
        if ob.cls >= C_MISSILE:
            ob.maxspd = T.f[D.T_MAX_VEL][typ]
            ob.fuel = T.f[D.T_LIFETIME][typ]
        if ob.cls >= C_SHIP:
            ob.sh[0] = ob.shmax[0] = T.f[D.T_SHIELD_F][typ]
            ob.sh[1] = ob.shmax[1] = T.f[D.T_SHIELD_A][typ]
            ob.ar[0] = T.f[D.T_ARMOR_F][typ]
            ob.ar[1] = T.f[D.T_ARMOR_R][typ]
            ob.ar[2] = T.f[D.T_ARMOR_L][typ]
            ob.ar[3] = T.f[D.T_ARMOR_RT][typ]
            ob.weapons = T.weapons(typ)
            ob.energy = 100

    def new_object(self, typ, owner):
        i = self.free_slot()
        if i < 0:
            return None
        ob = self.o[i]
        self.set_objects_data(ob, typ, owner)
        return ob

    def remove(self, ob):
        ob.cls = C_NULL
        ob.vis = False

    def max_velocity(self, ob):
        """get_ship_max_velocity: the top aces fly a third faster."""
        v = self.T.f[D.T_MAX_VEL][ob.typ]
        if ob.i < NSHIP and ob.rating > 8:
            return v + v // 3
        return v

    def recalc_max_velocity(self, ob):
        if ob.fuel <= 0:
            ob.maxspd = 5
        else:
            ob.maxspd = (self.max_velocity(ob) * (4 - ob.iondmg)) >> 2
        self.celerate(ob, 0)

    def accel_rate(self, ob):
        a = self.T.f[D.T_ACCEL][ob.typ]
        if ob.i < NSHIP and ob.rating > 8:
            return a + a // 3
        return a

    def celerate(self, ob, delta):
        top = ob.maxspd << 8
        s = ob.speed + delta
        if s > top:
            s = top
        if s < 0:
            s = 0
        ob.speed = s

    def approach_speed(self, ob, target):
        a = self.accel_rate(ob)
        d = target - ob.speed
        if d > a:
            d = a
        elif d < -a:
            d = -a
        self.celerate(ob, d)

    def is_alive(self, pilot):
        if 5 <= pilot <= 12:
            return self.camp.death[pilot - 5] == 0
        return True

    def is_team_member(self, ms):
        mis = self.mis
        return ms == mis.player_ship or ms in mis.initial

    # --- mission set-up ------------------------------------------------------
    def sphere_point(self, ms):
        """set_sphere_point: mission ship position, 24.8 world."""
        rec = self.mis.ship(ms)
        nx, ny, nz = self.mis.nav_pos(self.mis.ship_nav[ms])
        return nx + rec[6], ny + rec[7], nz + rec[8]

    def init_ship(self, ms, nav):
        mis = self.mis
        if ms < 0:
            return None
        rec = mis.ship(ms)
        typ = rec[0]
        if typ < 0:
            return None
        if typ == OT_ASTEROID_FIELD or typ == OT_MINE_FIELD:
            nx, ny, nz = mis.nav_pos(nav)
            self.hazards.append([(nx + rec[6]) >> 8, (ny + rec[7]) >> 8,
                                 (nz + rec[8]) >> 8, rec[13] + 3000, typ])
            return None
        if self.find_ship(ms) != -1 or mis.ship_state[ms] != 0:
            return None
        pilot = rec[15]
        if not self.is_alive(pilot):
            if pilot <= 8:
                return None
            pilot = 3
        mis.ship_nav[ms] = nav
        if ms == mis.player_ship:
            ob = self.o[0]
        else:
            i = self.free_ship_slot()
            if i < 0:
                return None
            ob = self.o[i]
        self.set_objects_data(ob, typ, -1)
        ob.nav = -1 if self.is_team_member(ms) else nav
        ob.mship = ms
        ob.x, ob.y, ob.z = self.sphere_point(ms)
        M.identity(ob.m)
        M.yaw(ob.m, -rec[9])
        M.pitch(ob.m, -rec[10])
        M.roll(ob.m, rec[11])
        M.fix(ob.m)
        ob.side = rec[1]
        ob.level = pilot
        ob.mtype = rec[4]
        ob.mtarget = rec[21]
        ob.leader = self.find_ship(rec[19])
        self.recalc_max_velocity(ob)
        ob.speed = min(rec[13] << 8, ob.maxspd << 8)
        self.set_formation_position(ob, rec)
        ob.vx = ob.vy = ob.vz = 0
        if ob.cls == C_SHIP:
            ob.vx = (ob.m[6] * (ob.speed >> 4)) >> 10
            ob.vy = (ob.m[7] * (ob.speed >> 4)) >> 10
            ob.vz = (ob.m[8] * (ob.speed >> 4)) >> 10
        # init_intelligence_data
        nx, ny, nz = mis.nav_pos(max(0, self.nav if self.nav >= 0 else nav))
        ob.spx = nx; ob.spy = ny; ob.spz = nz
        if ob.mtype == MT_GOTO_WARP and 0 <= ob.mtarget < 16:
            ob.spx, ob.spy, ob.spz = mis.nav_pos(ob.mtarget)
        elif ob.mtype in (MT_WARP_ARRIVE, MT_COME_HOME):
            if mis.home_ship >= 0:
                ob.spx, ob.spy, ob.spz = self.sphere_point(mis.home_ship)
        ob.rating = pilot - 5 if pilot > 4 else -1
        # find_next_ship_turn_slot: spread the pilots over the turns
        lvl = min(pilot, 17)
        ob.turn_int = self.ai.turn[lvl]
        ob.turn_reg = 1 + (ob.i % ob.turn_int)
        if ob.mtype == MT_WINGMAN and ob.side == SIDE_CONFED and \
                rec[19] == mis.player_ship:
            self.wingman = ob.i
        return ob

    def set_formation_position(self, ob, rec):
        if rec[20] == -1:
            return
        mis = self.mis
        f = self.ai.formation
        lead = rec
        lead_ms = -1
        src = ob
        while lead[19] != -1:
            lead_ms = lead[19]
            lead = mis.ship(lead_ms)
            i = self.find_ship(lead_ms)
            src = self.o[i] if i >= 0 else None
        a = (rec[20] * 8 + rec[12]) * 3
        b = (lead[20] * 8 + lead[12]) * 3
        if lead[20] < 0 or rec[20] > 4 or lead[20] > 4:
            return
        ob.fdx = f[a] - f[b]
        ob.fdy = f[a + 1] - f[b + 1]
        ob.fdz = f[a + 2] - f[b + 2]
        if lead_ms < 0:
            return
        if src is None:
            M.identity(ob.m)
            M.yaw(ob.m, -lead[9])
            M.pitch(ob.m, -lead[10])
            M.roll(ob.m, lead[11])
            M.fix(ob.m)
            px, py, pz = self.sphere_point(lead_ms)
        else:
            M.copy(src.m, ob.m)
            px, py, pz = src.x, src.y, src.z
        m = ob.m
        ob.x = px + ((m[0] * ob.fdx + m[3] * ob.fdy + m[6] * ob.fdz) >> 6)
        ob.y = py + ((m[1] * ob.fdx + m[4] * ob.fdy + m[7] * ob.fdz) >> 6)
        ob.z = pz + ((m[2] * ob.fdx + m[5] * ob.fdy + m[8] * ob.fdz) >> 6)
        ob.speed = min(lead[13] << 8, ob.maxspd << 8)

    def launch(self):
        """LaunchPlayerShip + the first action sphere."""
        mis = self.mis
        entry = mis.ship(mis.player_ship)[5]
        if mis.entry_nav >= 0:
            entry = mis.entry_nav
        self.nav = entry
        self.init_ship(mis.player_ship, entry)
        for ms in mis.initial:
            self.init_ship(ms, entry)
        self.set_up_action_sphere(entry)
        # first destination that can still be reached
        self.dest = 0

    def set_up_action_sphere(self, nav):
        mis = self.mis
        o = self.o
        self.nav = nav
        self.wave = 2 if nav + 1 < 16 and mis.nav_type[nav + 1] == 2 else -1
        for i in range(1, NSHIP):
            ob = o[i]
            if ob.cls != C_NULL and ob.nav != -1:
                if ob.cls >= C_SHIP and ob.mtype == MT_ROUT:
                    mis.ship_state[ob.mship] = 3
                self.remove(ob)
        for i in range(NSHIP, NOBJ):
            if o[i].cls in (C_ASTEROID, C_MINE):
                self.remove(o[i])
        self.hazards = []
        for ms in mis.nav_ships(nav):
            if ms != -1:
                self.init_ship(ms, nav)
        trig = mis.nav_triggers(nav)
        for k in range(0, 8, 2):
            if trig[k] != -1 and 0 <= trig[k + 1] < 16:
                mis.nav_type[trig[k + 1]] = trig[k] & 0xFF
        self.landing_ok = False
        # leaders that spawned after their wingmen
        for i in range(1, NSHIP):
            ob = o[i]
            if ob.cls >= C_SHIP and ob.leader < 0:
                ob.leader = self.find_ship(mis.ship(ob.mship)[19])

    def enemies_left(self):
        o = self.o
        for i in range(1, NSHIP):
            if o[i].cls >= C_SHIP and o[i].side == SIDE_KILRATHI and \
                    o[i].special != SM_DYING:
                return True
        return False

    def set_up_next_wave(self):
        mis = self.mis
        if self.wave == -1:
            return
        wn = self.wave + self.nav - 1
        if wn < 16 and mis.nav_type[wn] == self.wave:
            self.wave += 1
            mis.nav_type[wn] = 0xFF
            p = self.o[0]
            for ms in mis.nav_ships(wn):
                ob = self.init_ship(ms, self.nav)
                if ob is not None:
                    # approve_xyz: 5000..10000 units around the player
                    r = randint(5000, 10000)
                    a = randint(0, 359)
                    e = randint(-30, 30)
                    h = (r * M.icos(e)) >> 14
                    ob.x = p.x + ((h * M.isin(a)) >> 6)
                    ob.y = p.y + ((r * M.isin(e)) >> 6)
                    ob.z = p.z + ((h * M.icos(a)) >> 6)
        else:
            self.wave = -1

    # --- scoring -------------------------------------------------------------
    def affect_mission_score(self, pilot, event, amount):
        if event == 1:
            score = 7
        elif event == 2:
            score = 10
        elif event in (3, 4):
            score = 15
        elif event in (5, 6, 9, 10, 11):
            score = 25
        elif event == 7:
            score = 50
        elif event == 8:
            score = 75
        elif event == 12:
            score = amount * 2
        else:
            score = amount
        self.score += score
        if pilot == 0:
            self.medal_score += score

    def score_for_kill(self, pilot, victim):
        if victim.side != SIDE_KILRATHI:
            return
        t = victim.typ
        if t == 9:
            ev = 1
        elif t in (10, 11):
            ev = 2
        elif t in (12, 13):
            ev = 3
        elif t in (14, 17):
            ev = 6
        elif t in (15, 16):
            ev = 4
        elif t in (18, 19):
            ev = 7
        elif t in (20, 21):
            ev = 8
        else:
            return
        self.affect_mission_score(pilot, ev, -1)

    def creator(self, i):
        """the_creator: the ship behind a bolt or missile."""
        n = 0
        while i >= 0 and n < 4:
            own = self.o[i].owner
            if own == i or own == -1:
                return i
            i = own
            n += 1
        return i

    # --- damage --------------------------------------------------------------
    def explode(self, attacker, victim):
        """explode + Explosion. attacker / victim are slot indices."""
        ob = self.o[victim]
        if victim < NSHIP and ob.rating != -1 and ob.rating != 3:
            # named pilots survive every other killing blow
            if rndle(1) == 0:
                return 0
        if ob.cls >= C_SHIP and ob.special == SM_DYING:
            return 0
        if victim == 0:
            self.result = R_DEAD
            return 1
        attacker = self.creator(attacker)
        if 0 <= attacker < NSHIP and ob.cls >= C_SHIP:
            att = self.o[attacker]
            if att.side != ob.side:
                self.score_for_kill(attacker, ob)
                if attacker == 0:
                    self.kills += 1
                    self.say(b'Kill: ' + self.T.names[ob.typ], 0x07E0)
                elif attacker == self.wingman:
                    self.wing_kills += 1
        if ob.cls >= C_SHIP:
            if ob.rating != -1 and ob.rating != 3 and 0 <= ob.rating < 8:
                # personality_killed (committed when the mission is over)
                self.deaths.append(ob.rating)
            if self.wingman == victim:
                self.wingman_lost = True
                self.wingman = -1
                self.say(b'Wingman lost!', 0xF800)
            ob.special = SM_DYING
            ob.counter = 8
            if ob.mship >= 0:
                self.mis.ship_state[ob.mship] = 3
            if ob.cls == C_CAPITAL:
                ob.counter = (self.T.f[D.T_DAMAGE][ob.typ] >> 2) + 8
                for _ in range(3):
                    self.onboard_explosion(ob)
            else:
                self.spawn_explosion(ob, OT_EXPLOSION1, ob.scale)
                self.shock_wave(ob, self.T.f[D.T_EXPLOSION][ob.typ])
            self.sound(3)
        else:
            blast = self.T.f[D.T_EXPLOSION][ob.typ]
            etype = OT_EXPLOSION0 if (ob.typ == OT_TURRET or
                                      ob.cls == C_ASTEROID) else OT_EXPLOSION2
            x = ob.x; y = ob.y; z = ob.z
            own = ob.owner
            self.set_objects_data(ob, etype, own)
            ob.x = x; ob.y = y; ob.z = z
            if etype == OT_EXPLOSION0:
                ob.scale = 0x380
            self.shock_wave(ob, blast)
            self.sound(4)
        return 1

    def spawn_explosion(self, src, etype, scale):
        e = self.new_object(etype, src.i)
        if e is not None:
            e.x = src.x; e.y = src.y; e.z = src.z
            e.vx = src.vx; e.vy = src.vy; e.vz = src.vz
            e.scale = max(64, (e.scale * scale) >> 10)
        return e

    def onboard_explosion(self, ob):
        e = self.new_object(OT_EXPLOSION0, ob.i)
        if e is not None:
            r = ob.radius
            e.x = ob.x + (randint(-r, r) << 8)
            e.y = ob.y + (randint(-r, r) << 7)
            e.z = ob.z + (randint(-r, r) << 8)
            e.vx = ob.vx; e.vy = ob.vy; e.vz = ob.vz
            e.scale = 0x300

    def shock_wave(self, src, blast):
        """explosion_shock_wave"""
        if blast <= 0:
            return
        o = self.o
        for i in range(NSHIP):
            ob = o[i]
            if ob is src or ob.cls < C_SHIP:
                continue
            d = self.dist(src, ob) - ob.radius
            if d < 0:
                d = 0
            if d > 1000:
                continue
            if d > 750:
                div = 40
            elif d > 500:
                div = 30
            else:
                div = find_ratio(0, 500, d, 8, 25)
            dmg = blast // div // div
            if i == 0:
                dmg = max(1, dmg * 3 >> 2)
            if dmg > 1:
                self.inflict_damage(src.i, i, min(100, dmg),
                                    ob.x - src.x, ob.y - src.y, ob.z - src.z)

    def inflict_damage(self, attacker, victim, damage, ix, iy, iz):
        """inflict_damage; (ix, iy, iz) is the direction the blow travels."""
        ob = self.o[victim]
        if damage <= 0 or ob.special == SM_DYING or ob.cls < C_MISSILE:
            return 0
        if ob.cls < C_SHIP:
            ob.acc += damage
            cap = self.T.f[D.T_DAMAGE][ob.typ]
            if cap != -1 and cap <= ob.acc:
                return self.explode(attacker, victim)
            return 0
        if victim == 0:
            self.flash = 4
            self.shake = 3
            self.sound(2)
        m = ob.m
        ix >>= 8; iy >>= 8; iz >>= 8
        quad = 1 if (ix * m[6] + iy * m[7] + iz * m[8]) > 0 else 0
        damage -= ob.sh[quad]
        if damage <= 0:
            ob.sh[quad] = -damage
            return 0
        ob.sh[quad] = 0
        n = M.mag(ix, iy, iz)
        if n > 0:
            side = (ix * m[0] + iy * m[1] + iz * m[2]) // n
            if side > 11585:            # 0xb5 / 0x100
                quad = 3
            elif side < -11585:
                quad = 2
        damage -= ob.ar[quad]
        if damage <= 0:
            ob.ar[quad] = -damage
            return 0
        ob.ar[quad] = 0
        if rndle(99) == 0 and attacker > 0:
            return self.explode(attacker, victim)
        return self.internal_damage(attacker, victim, damage, quad)

    def pilot_hit(self, ob):
        """pilot_hit: four hits are all a pilot can take."""
        if ob.pilot_hp > 0:
            ob.pilot_hp -= 1
            if ob.pilot_hp == 0:
                if ob.i == 0:
                    self.result = R_DEAD
                return
            if ob.i != 0 and rndle(8) >= 3:
                ob.special = SM_LOST_CONTROL
                ob.counter = rndle(20) + 30
            elif ob.i == 0:
                self.say(b'You are wounded!', 0xF800)

    def your_internal_damage(self, attacker, damage, quad):
        """your_internal_damage: what an armour-piercing hit does to the
        player's ship (asPlayerDamageSystemTable)."""
        p = self.o[0]
        acls = self.o[attacker].cls if attacker >= 0 else C_SHIP
        if acls == C_PROJECTILE:
            group = 2 if quad == 1 else 0
            events = max(1, damage >> 4)
        elif acls == C_ASTEROID or acls >= C_SHIP:
            group = 4
            events = max(1, damage >> 7)
        else:
            group = 3 if quad == 1 else 1
            events = max(1, damage >> 5)
        table = self.ai.player_damage
        severity = rndle(10)
        p.acc += events
        cap = self.T.f[D.T_DAMAGE][p.typ]
        guard = 0
        while events > 0 and guard < 40 and self.result == R_FLYING:
            guard += 1
            events -= 1
            system = table[group * 10 + rndle(9)]
            if system == 0:
                if severity < 4:
                    self.pilot_hit(p)
                else:
                    self.say(b'Ejection system damaged' if severity < 7
                             else b'Targeting damaged', 0xF800)
            elif system == 1:
                if quad != 1:
                    events += 1
                else:
                    p.iondmg = min(p.iondmg + 1, 3)
                    self.recalc_max_velocity(p)
                    self.say(b'Ion drive damaged', 0xF800)
            elif system == 2:
                if quad != 1:
                    events += 1
                else:
                    if rndle(3) == 0:
                        return self.explode(attacker, 0)
                    p.plant += 1
                    if p.plant >= 4:
                        return self.explode(attacker, 0)
                    self.say(b'Power plant damaged', 0xF800)
            elif system == 3:
                if severity < 9:
                    # revise_shields
                    p.shmax[0] = max(0, p.shmax[0] -
                                     (self.T.f[D.T_SHIELD_F][p.typ] >> 2))
                    p.shmax[1] = max(0, p.shmax[1] -
                                     (self.T.f[D.T_SHIELD_A][p.typ] >> 2))
                    self.say(b'Shield generator damaged', 0xF800)
                else:
                    self.say(b'Autopilot damaged', 0xF800)
            elif system == 4:
                p.dmg += 1
                if p.dmg == 1:
                    events -= 1
                    self.pilot_hit(p)
                elif p.dmg > cap:
                    return self.explode(attacker, 0)
            elif system == 5:
                if quad != 0:
                    events += 1
                elif len(p.weapons) > 1:
                    k = rnd(len(p.weapons) - 1)
                    self.say(self.T.names[p.weapons[k][0]] + b' destroyed',
                             0xF800)
                    p.weapons.pop(k)
            elif system == 6:
                if quad != 0:
                    events += 1
                elif p.guns_lost < 5:
                    p.guns_lost += 1
                    self.say(b'Computer damaged', 0xF800)
            elif system == 7:
                p.fuel -= self.T.f[D.T_LIFETIME][p.typ] // 4
                if rndle(1) != 0 or p.fuel < 0:
                    return self.explode(attacker, 0)
                self.recalc_max_velocity(p)
                self.say(b'Fuel tanks hit', 0xF800)
            else:
                if quad != 0:
                    events += 1
                else:
                    self.say(b'Communications damaged', 0xF800)
        return 1 if self.result == R_DEAD else 0

    def internal_damage(self, attacker, victim, damage, quad):
        if victim == 0:
            return self.your_internal_damage(attacker, damage, quad)
        ob = self.o[victim]
        cap = self.T.f[D.T_DAMAGE][ob.typ]
        if ob.cls == C_CAPITAL:
            if ob.side == SIDE_KILRATHI:
                ob.acc += max(1, damage >> 3)
            else:
                ob.acc += max(1, damage // 10)
            if ob.acc >= cap:
                return self.explode(attacker, victim)
            self.onboard_explosion(ob)
            return 0
        if ob.rating != -1:
            damage = max(1, damage // 40)
            damage = min(randint(3, 4), damage)
        else:
            damage = max(1, damage // 6)
        ob.acc += damage
        guard = 0
        while damage > 0 and guard < 40:
            guard += 1
            if damage == 1 and ob.rating != -1:
                system = 4
            else:
                system = rndle(9)
            if system == 0:
                damage -= 1
                self.pilot_hit(ob)
            elif system == 1:
                if quad == 1:
                    damage -= 1
                    ob.iondmg = min(ob.iondmg + 1, 3)
                    self.recalc_max_velocity(ob)
            elif system == 2:
                if quad == 1:
                    return self.explode(attacker, victim)
            elif system == 3:
                ob.shmax[0] = ob.sh[0] = 0
                ob.shmax[1] = ob.sh[1] = 0
            elif system == 4:
                damage -= 1
                ob.dmg += 1
                if ob.dmg > cap:
                    return self.explode(attacker, victim)
            elif system == 5:
                if quad == 0 and len(ob.weapons) > 0:
                    damage -= 1
                    ob.weapons.pop(rnd(len(ob.weapons)))
            elif system == 6:
                if quad == 0 and ob.guns_lost < 5:
                    damage -= 1
                    ob.guns_lost += 1
            elif system == 7:
                if quad == 1:
                    damage -= 1
                    ob.fuel -= self.T.f[D.T_LIFETIME][ob.typ] // 4
                    if rndle(1) != 0 or ob.fuel < 0:
                        return self.explode(attacker, victim)
            elif system == 8:
                if quad == 0:
                    damage -= 1
        return 0

    def evaluate_damage(self, ob):
        """evaluate_damage: 100 = pristine."""
        if ob.cls < C_SHIP:
            return 100
        f = self.T.f
        t = ob.typ
        return (ob.dmg * -26 // max(1, f[D.T_DAMAGE][t]) +
                ob.ar[1] * 27 // max(1, f[D.T_ARMOR_R][t]) +
                ob.ar[0] * 23 // max(1, f[D.T_ARMOR_F][t]) +
                ob.ar[2] * 12 // max(1, f[D.T_ARMOR_L][t]) +
                ob.ar[3] * 12 // max(1, f[D.T_ARMOR_RT][t]) +
                (ob.sh[0] + ob.sh[1]) * 26 //
                max(1, f[D.T_SHIELD_F][t] + f[D.T_SHIELD_A][t]))

    def damage_level(self):
        """calculate_damage_level of the player's ship: 0..3."""
        ob = self.o[0]
        f = self.T.f
        t = ob.typ
        d = 0
        for k, fld in ((2, D.T_ARMOR_L), (1, D.T_ARMOR_R), (3, D.T_ARMOR_RT),
                       (0, D.T_ARMOR_F)):
            full = max(1, f[fld][t])
            d += (full - ob.ar[k]) * 4 // full
        d = ob.dmg * 30 // max(1, f[D.T_DAMAGE][t]) + d * 2 + ob.acc * 5
        if d < 5:
            return 0
        if d < 40:
            return 1
        if d < 70:
            return 2
        return 3

    # --- weapons -------------------------------------------------------------
    def hardpoint(self, ob, hp):
        """position_child: world position (24.8) of a hardpoint."""
        c = self.T.child
        m = ob.m
        hx = c[hp * 3]; hy = c[hp * 3 + 1]; hz = c[hp * 3 + 2]
        return (ob.x + ((m[0] * hx + m[3] * hy + m[6] * hz) >> 6),
                ob.y + ((m[1] * hx + m[4] * hy + m[7] * hz) >> 6),
                ob.z + ((m[2] * hx + m[5] * hy + m[8] * hz) >> 6))

    def fire_weapon(self, ob, k):
        """fire_weapon: weapon slot k of ship ob."""
        T = self.T.f
        w = ob.weapons[k]
        wtype = w[0]
        wcls = T[D.T_CLASS][wtype]
        if wtype == OT_TURRET:
            wcls = C_PROJECTILE
            wtype = OT_LASER
        if wcls == C_MINE:
            return None
        p = self.new_object(wtype, ob.i)
        if p is None:
            return None
        m = ob.m
        M.copy(m, p.m)
        p.x, p.y, p.z = self.hardpoint(ob, w[1])
        p.side = ob.side
        # the ship's own motion along its nose carries over
        along = (ob.vx * (m[6] >> 4) + ob.vy * (m[7] >> 4) +
                 ob.vz * (m[8] >> 4)) >> 10
        if wcls == C_PROJECTILE:
            p.acc = T[D.T_DAMAGE][wtype]
            ob.energy -= T[D.T_ANIM_DELAY][wtype]
            p.counter = T[D.T_LIFETIME][wtype]
            spd = T[D.T_MAX_VEL][wtype]
            # converge on a point (lifetime + 5) * speed ahead of the ship
            rng = (p.counter + 5) * spd
            dx = ((ob.x + ((m[6] * rng) >> 6)) - p.x) >> 8
            dy = ((ob.y + ((m[7] * rng) >> 6)) - p.y) >> 8
            dz = ((ob.z + ((m[8] * rng) >> 6)) - p.z) >> 8
            n = M.mag(dx, dy, dz)
            if n == 0:
                n = 1
            s = (spd << 8) + along
            p.vx = dx * s // n
            p.vy = dy * s // n
            p.vz = dz * s // n
            if ob.i == 0:
                ob.counter = self.ai.refire[wtype - OT_LASER]
            else:
                ob.counter = 12
            self.sound(0)
        else:
            # missile: drops clear, lights up after a few turns
            s = 10 << 8
            p.vx = ((m[6] * ((along + s) >> 4)) >> 10) + ((m[3] * 0xA0) >> 10)
            p.vy = ((m[7] * ((along + s) >> 4)) >> 10) + ((m[4] * 0xA0) >> 10)
            p.vz = ((m[8] * ((along + s) >> 4)) >> 10) + ((m[5] * 0xA0) >> 10)
            p.grace = 20
            p.tactic = T_SIT_STILL
            p.counter = 5
            p.target = ob.target
            p.speed = T[D.T_MAX_VEL][wtype] << 8
            if wtype == OT_DUMBFIRE:
                p.counter = 1
            elif wtype == OT_FF:
                p.target = -1
                p.counter = 15
            ob.weapons.pop(k)
            if ob.i != 0:
                ob.counter = 12
            self.sound(1)
        return p

    def fire_guns(self, ob):
        """fire_fixed_projectile_weapon: every selected gun."""
        if ob.counter > 0:
            return False
        T = self.T.f
        fired = False
        for k in range(len(ob.weapons)):
            w = ob.weapons[k]
            if T[D.T_CLASS][w[0]] == C_PROJECTILE and w[2] == 0:
                if ob.energy >= T[D.T_ANIM_DELAY][w[0]]:
                    if self.fire_weapon(ob, k) is not None:
                        fired = True
        return fired

    def fire_missile(self, ob):
        T = self.T.f
        for k in range(len(ob.weapons)):
            w = ob.weapons[k]
            if T[D.T_CLASS][w[0]] == C_MISSILE:
                if ob.i != 0 or w[2] == 0:
                    return self.fire_weapon(ob, k)
        return None

    def missile_count(self, ob):
        T = self.T.f
        n = 0
        for w in ob.weapons:
            if T[D.T_CLASS][w[0]] == C_MISSILE:
                n += 1
        return n

    # --- one game turn -------------------------------------------------------
    def update(self):
        """Update_3Space"""
        self.tick += 1
        o = self.o
        brain = self.brain
        # everything a bolt, missile or ship can run into this turn
        solid = self.solid
        del solid[:]
        for i in range(NOBJ):
            c = o[i].cls
            if c >= C_ASTEROID:
                solid.append(i)
        for i in range(NOBJ):
            ob = o[i]
            c = ob.cls
            if c == C_NULL:
                continue
            if c == C_EXPLOSION:
                ob.counter += 1
                if ob.counter >= EXPLOSION_TURNS[ob.typ - OT_EXPLOSION0]:
                    self.remove(ob)
                continue
            if c < C_PROJECTILE:
                continue
            self.house_keep(ob)
            if ob.cls < C_PROJECTILE:
                continue
            self.collide(ob)
            if ob.cls < C_PROJECTILE:
                continue
            if ob.rp or ob.ry or ob.rr:
                self.rotate_object(ob)
            if ob.cls >= C_MISSILE and ob.special != SM_DYING:
                if i != 0 and brain is not None:
                    brain.think(ob)
                if i < NSHIP:
                    if i != 0:
                        self.rotate_object_to_goal(ob)
                    if ob.cls == C_SHIP and ob.energy < 100:
                        full = ob.sh[0] + ob.sh[1] >= ob.shmax[0] + ob.shmax[1]
                        ob.energy = min(100, ob.energy + (2 if full else 1))
        for i in range(NOBJ):
            ob = o[i]
            if ob.cls > C_NULL:
                self.move(ob)
                if ob.cls >= C_SHIP:
                    self.replenish_shields(ob)
                    if ob.speed > 0:
                        ob.fuel -= 5
        if self.tick % 10 == 0:
            self.track_objectives()
            if self.wave != -1 and not self.enemies_left():
                self.set_up_next_wave()
        self.hazard_turn()
        if self.flash > 0:
            self.flash -= 1
        if self.shake > 0:
            self.shake -= 1

    def house_keep(self, ob):
        c = ob.cls
        if c == C_PROJECTILE:
            ob.counter -= 1
            if ob.counter <= 0:
                self.remove(ob)
        elif c == C_MISSILE:
            if ob.grace > 0:
                ob.grace -= 1
            ob.counter -= 1
            if ob.tactic == T_SIT_STILL:
                if ob.counter <= 0:
                    ob.tactic = T_RAM
                    ob.counter = self.T.f[D.T_LIFETIME][ob.typ]
            elif ob.counter <= 0:
                self.explode(ob.i, ob.i)
        elif c == C_MINE:
            if ob.grace > 0:
                ob.grace -= 1
        elif c >= C_SHIP:
            if ob.counter > 0:
                ob.counter -= 1
                if ob.special == SM_DYING:
                    if ob.cls == C_CAPITAL:
                        if ob.counter == 7:
                            self.spawn_explosion(ob, OT_EXPLOSION1, ob.scale)
                            self.shock_wave(
                                ob, self.T.f[D.T_EXPLOSION][ob.typ])
                            self.sound(3)
                        elif rnd(100) < 50:
                            self.onboard_explosion(ob)
                    if ob.counter == 0:
                        self.remove(ob)
                        return
            if ob.typ == OT_TIGERS_CLAW and self.landing_ok:
                p = self.o[0]
                self.ship_vs_ship(p, ob)
                if self.RANGE < 700 and self.FACE > 75:
                    self.result = R_LANDED
                    oi = self.find_objective(1, -1)
                    if oi >= 0:
                        self.mis.objectives[oi][3] |= 3

    def rotate_object(self, ob):
        m = ob.m
        if ob.rp:
            M.pitch(m, ob.rp)
        if ob.ry:
            M.yaw(m, ob.ry)
        if ob.rr:
            M.roll(m, ob.rr)
        M.fix(m)

    def _match(self, rot, goal, total, rate):
        """match_rotation_goal -> (rotation, goal)"""
        if total != 0:
            if goal > 180:
                goal -= 360
            if goal < -180:
                goal += 360
            step = max(1, abs(rot - goal) * rate // total)
            if goal != rot or step < abs(rot):
                if goal > 0:
                    rot += max(min(min(goal, step) - rot, step), -step)
                else:
                    rot += min(max(max(goal, -step) - rot, -step), step)
        if goal > 0:
            goal = max(goal - rot, 0)
        elif goal < 0:
            goal = min(goal - rot, 0)
        return rot, goal

    def rotate_object_to_goal(self, ob):
        f = self.T.f
        if ob.special == SM_LOST_CONTROL:
            ob.counter -= 1
            if ob.counter <= 0:
                ob.special = SM_NONE
            return
        total = abs(ob.ry - ob.gy) + abs(ob.rp - ob.gp) + abs(ob.rr - ob.gr)
        t = ob.typ
        # (the original pairs the pitch axis with yawRate and vice versa)
        ob.rp, ob.gp = self._match(ob.rp, ob.gp, total, f[D.T_YAW][t])
        ob.ry, ob.gy = self._match(ob.ry, ob.gy, total, f[D.T_PITCH][t])
        ob.rr, ob.gr = self._match(ob.rr, ob.gr, total, f[D.T_ROLL][t])

    def move(self, ob):
        """accelerate_and_move_object"""
        if ob.cls >= C_MISSILE and ob.special != SM_DYING:
            sp = ob.special
            if sp == SM_KILL_ENGINES:
                if rndle(100) < 10:
                    ob.special = SM_NONE
            elif ob.tactic != T_SIT_STILL:
                m = ob.m
                s = ob.speed
                boost = False
                if sp == SM_AFTERBURNER:
                    ob.abtimer -= 1
                    if ob.abtimer <= 0:
                        ob.special = SM_NONE
                    else:
                        s = (self.T.f[D.T_MAX_VEL][ob.typ] + 20) * 0x200
                        ob.fuel -= 200
                        ob.heat = 3
                        boost = True
                elif sp == SM_SUPER_BRAKE:
                    ob.abtimer -= 1
                    if ob.abtimer <= 0:
                        ob.special = SM_NONE
                    else:
                        s = 0
                        ob.fuel -= 140
                        boost = True
                s >>= 4
                dx = ((m[6] * s) >> 10) - ob.vx
                dy = ((m[7] * s) >> 10) - ob.vy
                dz = ((m[8] * s) >> 10) - ob.vz
                n = M.mag(dx, dy, dz)
                if n > 0:
                    a = self.accel_rate(ob)
                    if boost:
                        a *= 2
                    if ob.cls == C_MISSILE:
                        a = 0x2000
                    cosang = ((dx * (m[6] >> 6) + dy * (m[7] >> 6) +
                               dz * (m[8] >> 6))) // n
                    a = (a * (cosang + 0x200)) >> 8
                    frac = ((a >> 1) << 8) // n
                    if frac > 0x100:
                        frac = 0x100
                    ob.vx += (dx * frac) >> 8
                    ob.vy += (dy * frac) >> 8
                    ob.vz += (dz * frac) >> 8
        ob.x += ob.vx
        ob.y += ob.vy
        ob.z += ob.vz

    def replenish_shields(self, ob):
        delay = self.T.f[D.T_ANIM_DELAY][ob.typ]
        if delay <= 0:
            delay = 1
        if self.tick % delay:
            return
        sh = ob.sh
        mx = ob.shmax
        if sh[0] < mx[0]:
            sh[0] += 1
        elif sh[0] > mx[0]:
            sh[0] = mx[0]
        if sh[1] < mx[1]:
            sh[1] += 1
        elif sh[1] > mx[1]:
            sh[1] = mx[1]

    # --- collisions ----------------------------------------------------------
    def collide(self, ob):
        """object_collision, for the object classes that initiate one."""
        c = ob.cls
        o = self.o
        if c == C_PROJECTILE or c == C_MISSILE:
            if c == C_MISSILE and ob.tactic == T_SIT_STILL:
                return
            vx = ob.vx >> 8; vy = ob.vy >> 8; vz = ob.vz >> 8
            ox = ob.x >> 8; oy = ob.y >> 8; oz = ob.z >> 8
            for i in self.solid:
                t = o[i]
                tc = t.cls
                if tc < C_ASTEROID or t is ob or i == ob.owner:
                    continue
                if tc == C_MISSILE and c == C_PROJECTILE and \
                        t.owner == ob.owner:
                    continue
                if tc == C_MISSILE and c == C_MISSILE:
                    continue
                if ob.typ == OT_TURRET and t.side == ob.side:
                    # flak passes its own side (the gunners hold fire
                    # when a friend crosses; here the bolt is ignored)
                    continue
                reach = t.radius + ob.radius
                if tc == C_CAPITAL:
                    reach = (t.radius * 3) >> 2
                px = (t.x >> 8) - ox
                lim = reach + 200
                if px > lim or px < -lim:
                    continue
                py = (t.y >> 8) - oy
                if py > lim or py < -lim:
                    continue
                pz = (t.z >> 8) - oz
                if pz > lim or pz < -lim:
                    continue
                # closest approach during this turn (relative motion)
                rx = vx - (t.vx >> 8)
                ry = vy - (t.vy >> 8)
                rz = vz - (t.vz >> 8)
                vv = rx * rx + ry * ry + rz * rz
                if vv > 0:
                    k = ((px * rx + py * ry + pz * rz) << 8) // vv
                    if k < 0:
                        k = 0
                    elif k > 256:
                        k = 256
                    px -= (rx * k) >> 8
                    py -= (ry * k) >> 8
                    pz -= (rz * k) >> 8
                if px * px + py * py + pz * pz > reach * reach:
                    continue
                if c == C_PROJECTILE:
                    self.bolt_hit(ob, t)
                else:
                    self.explode(ob.i, ob.i)
                return
        elif c == C_SHIP:
            # ships against rocks, mines, ships and capital ships
            for i in self.solid:
                t = o[i]
                tc = t.cls
                if tc < C_ASTEROID or t is ob or tc == C_MISSILE:
                    continue
                if i < ob.i and tc == C_SHIP:
                    continue
                reach = t.radius + ob.radius
                if tc == C_SHIP:
                    reach >>= 1
                elif tc == C_CAPITAL:
                    reach = (t.radius * 2) // 3
                px = (t.x - ob.x) >> 8
                if px > reach or px < -reach:
                    continue
                py = (t.y - ob.y) >> 8
                if py > reach or py < -reach:
                    continue
                pz = (t.z - ob.z) >> 8
                if pz > reach or pz < -reach:
                    continue
                if px * px + py * py + pz * pz > reach * reach:
                    continue
                if tc == C_MINE:
                    if t.grace <= 0:
                        self.explode(i, i)
                    continue
                if ob.lastcol == i:
                    return
                ob.lastcol = i
                self.bump(ob, t, px, py, pz)
                return
            ob.lastcol = -1

    def bolt_hit(self, bolt, t):
        if t.cls >= C_MISSILE:
            t.attacker = bolt.owner
            t.cooldown += 4
            dmg = bolt.acc - bolt.counter // 2
            self.inflict_damage(bolt.i, t.i, dmg, bolt.vx, bolt.vy, bolt.vz)
        elif t.cls == C_ASTEROID:
            t.acc += bolt.acc
            if t.acc >= 60:
                self.explode(bolt.i, t.i)
        x = bolt.x; y = bolt.y; z = bolt.z
        sc = bolt.scale
        self.set_objects_data(bolt, OT_LASER_SPARK, bolt.owner)
        bolt.x = x; bolt.y = y; bolt.z = z
        bolt.scale = sc * 2
        bolt.vx = t.vx; bolt.vy = t.vy; bolt.vz = t.vz

    def bump(self, ob, t, px, py, pz):
        """Ship collision: push apart, exchange velocity, ram damage."""
        n = M.mag(px, py, pz)
        if n == 0:
            n = 1
        rvx = (ob.vx - t.vx) >> 8
        rvy = (ob.vy - t.vy) >> 8
        rvz = (ob.vz - t.vz) >> 8
        closing = (rvx * px + rvy * py + rvz * pz) // n
        if closing < 0:
            closing = 0
        dmg = (closing * closing) >> 1
        if dmg > 400:
            dmg = 400
        k = closing << 8
        ob.vx -= px * k // n
        ob.vy -= py * k // n
        ob.vz -= pz * k // n
        if t.cls == C_SHIP:
            t.vx += px * k // n
            t.vy += py * k // n
            t.vz += pz * k // n
            self.inflict_damage(ob.i, t.i, dmg, px << 8, py << 8, pz << 8)
        elif t.cls == C_ASTEROID:
            self.explode(ob.i, t.i)
            dmg = max(dmg, 40)
        else:
            ob.speed = 0
        if dmg > 0:
            self.inflict_damage(t.i, ob.i, dmg, -px << 8, -py << 8, -pz << 8)

    # --- hazard fields -------------------------------------------------------
    def in_hazard(self):
        p = self.o[0]
        px = p.x >> 8; py = p.y >> 8; pz = p.z >> 8
        for h in self.hazards:
            if M.mag(px - h[0], py - h[1], pz - h[2]) < h[3]:
                return h
        return None

    def hazard_turn(self):
        """Keep a handful of rocks / mines around the player while he is
        inside a field (the original recycles its field objects the same
        way)."""
        if self.tick % 5:
            return
        h = self.in_hazard()
        o = self.o
        p = o[0]
        count = 0
        for i in range(NSHIP, NOBJ):
            ob = o[i]
            if ob.cls == C_ASTEROID or (ob.cls == C_MINE and ob.owner == -1):
                if h is None or self.dist(p, ob) > 5000:
                    self.remove(ob)
                else:
                    count += 1
        if h is None or count >= 7:
            return
        mine = h[4] == OT_MINE_FIELD
        ob = self.new_object(OT_MINE if mine else OT_ASTEROID1 + rnd(6), -1)
        if ob is None:
            return
        m = p.m
        ahead = randint(2500, 4500)
        sx = randint(-1500, 1500)
        sy = randint(-1200, 1200)
        ob.x = p.x + ((m[6] * ahead + m[0] * sx + m[3] * sy) >> 6)
        ob.y = p.y + ((m[7] * ahead + m[1] * sx + m[4] * sy) >> 6)
        ob.z = p.z + ((m[8] * ahead + m[2] * sx + m[5] * sy) >> 6)
        if not mine:
            ob.vx = randint(-3, 3) << 8
            ob.vy = randint(-3, 3) << 8
            ob.vz = randint(-3, 3) << 8
        ob.counter = rnd(8)

    # --- objectives ----------------------------------------------------------
    def find_objective(self, typ, index):
        ob = self.mis.objectives
        for i in range(len(ob)):
            if ob[i][0] == typ and (index == -1 or ob[i][1] == index):
                return i
        return -1

    def objective_pos(self, i):
        """World position (24.8) of objective i."""
        ob = self.mis.objectives[i]
        if ob[0] == 0:
            return self.mis.nav_pos(ob[1])
        s = self.find_ship(ob[1])
        if s >= 0:
            t = self.o[s]
            return t.x, t.y, t.z
        return self.sphere_point(ob[1])

    def objective_nav(self, i):
        ob = self.mis.objectives[i]
        if ob[0] == 0:
            return ob[1]
        return self.mis.ship_nav[ob[1]]

    def track_objectives(self):
        """check_sighting / check_visit, the destination pointer and the
        landing clearance; run a couple of times per second."""
        mis = self.mis
        objs = mis.objectives
        p = self.o[0]
        for i in range(len(objs)):
            ob = objs[i]
            x, y, z = self.objective_pos(i)
            rng = M.mag((x - p.x) >> 8, (y - p.y) >> 8, (z - p.z) >> 8)
            if rng < 16000:
                ob[3] |= 4
            if ob[0] != 1 and not ob[3] & 1:
                nav = self.objective_nav(i)
                if nav == self.nav and rng < mis.nav_radius(nav):
                    ob[3] |= 1
                    if i == self.dest:
                        self.say(b'Objective reached')
        n = len(objs)
        while self.dest < n - 1 and objs[self.dest][3] & 1 and \
                not self.enemies_left():
            self.dest += 1
        home = self.find_ship(mis.home_ship)
        if home >= 0 and not self.landing_ok and self.tick > 400 and \
                (self.dest >= n - 1 or objs[self.dest][0] == 1):
            if self.dist(p, self.o[home]) < 6000 and not self.enemies_left():
                self.landing_ok = True
                self.say(b'Cleared to land', 0x07E0)

    def cleanup_objectives(self):
        """cleanup_objectives: settle every objective when the flight
        ends (screen.c)."""
        mis = self.mis
        objs = mis.objectives
        home = self.find_ship(mis.home_ship)
        for i in range(len(objs)):
            ob = objs[i]
            if ob[3] & 2:
                continue
            typ = ob[0]
            idx = ob[1]
            if typ in (0, 1, 3):
                if ob[3] & 1:
                    ob[3] |= 2
            elif typ == 2:
                mt = mis.ship(idx)[4]
                done = False
                if mt == MT_GOTO_WARP:
                    done = mis.ship_state[idx] == 2
                elif mt in (MT_WARP_ARRIVE, MT_COME_HOME):
                    s = self.find_ship(idx)
                    if s >= 0 and home >= 0 and self.distance_from_object(
                            self.o[s], self.o[home]) < \
                            mis.nav_radius(mis.entry_nav):
                        mis.ship_state[idx] = 1
                    done = mis.ship_state[idx] == 1 and ob[3] & 4
                else:
                    done = mis.ship_state[idx] == 0 and ob[3] & 4
                if done:
                    ob[3] |= 2
                    t = mis.ship_type(idx)
                    self.affect_mission_score(0, 5 if t in (0, 6) else 9, -1)
            elif typ == 4:
                if mis.ship_state[idx] == 3:
                    ob[3] |= 2

    def players_score(self, scores):
        """PlayersMissionScore / FullMissionScore from the CAMP record."""
        got = 0
        full = 0
        objs = self.mis.objectives
        for i in range(16):
            full += scores[i]
            if i < len(objs) and objs[i][3] & 2:
                got += scores[i]
        return got, full

    # --- autopilot -----------------------------------------------------------
    def autopilot_ok(self):
        """auto_pilot_valid: no enemy near, no hazard, somewhere to go."""
        p = self.o[0]
        o = self.o
        for i in range(1, NSHIP):
            t = o[i]
            if t.cls >= C_SHIP and t.side == SIDE_KILRATHI and \
                    t.special != SM_DYING and self.dist(p, t) < 10000:
                return 1
        if self.in_hazard() is not None:
            return 2
        return 0

    def autopilot(self):
        """auto_pilot_sequence, without the fly-by film: put the flight a
        short way out from the next destination, pointing at it."""
        if self.dest >= len(self.mis.objectives):
            return False
        x, y, z = self.objective_pos(self.dest)
        nav = self.objective_nav(self.dest)
        p = self.o[0]
        dx = (x - p.x) >> 8; dy = (y - p.y) >> 8; dz = (z - p.z) >> 8
        d = M.mag(dx, dy, dz)
        short = 9000 if self.mis.objectives[self.dest][0] != 1 else 5000
        if d < short + 500:
            return False
        k = d - short
        ox = p.x; oy = p.y; oz = p.z
        p.x += (dx * k // d) << 8
        p.y += (dy * k // d) << 8
        p.z += (dz * k // d) << 8
        # point_at
        yw, pt = M.spherical(dx, dy, dz)
        M.identity(p.m)
        M.yaw(p.m, -yw)
        M.pitch(p.m, -pt)
        M.fix(p.m)
        p.rp = p.ry = p.rr = 0
        p.speed = min(p.maxspd, self.T.f[D.T_CRUISE][p.typ]) << 8
        p.vx = (p.m[6] * (p.speed >> 4)) >> 10
        p.vy = (p.m[7] * (p.speed >> 4)) >> 10
        p.vz = (p.m[8] * (p.speed >> 4)) >> 10
        o = self.o
        for i in range(1, NSHIP):
            t = o[i]
            if t.cls >= C_SHIP and t.nav == -1:
                # team members keep their place relative to the leader
                t.x += p.x - ox; t.y += p.y - oy; t.z += p.z - oz
                M.copy(p.m, t.m)
                t.vx = p.vx; t.vy = p.vy; t.vz = p.vz
                t.speed = p.speed
                t.gp = t.gy = t.gr = 0
                t.rp = t.ry = t.rr = 0
                t.target = -1
                t.man = -1
        for i in range(NSHIP, NOBJ):
            if o[i].cls != C_NULL:
                self.remove(o[i])
        if nav != self.nav:
            self.set_up_action_sphere(nav)
        return True

    def check_sphere(self):
        """Entering another nav point's radius sets up its action sphere."""
        mis = self.mis
        p = self.o[0]
        for n in range(16):
            if mis.nav_type[n] == 1 and n != self.nav:
                x, y, z = mis.nav_pos(n)
                if M.mag((x - p.x) >> 8, (y - p.y) >> 8,
                         (z - p.z) >> 8) < mis.nav_radius(n):
                    self.set_up_action_sphere(n)
                    return
