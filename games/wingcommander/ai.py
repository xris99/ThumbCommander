# ai.py - pilot intelligence: a port of the original's BRAINS.C, SMART.C
# and the manoeuvre scripts of FL.C (wc1-re src/brains.c, src/smart.c,
# src/fl.c, src/logic.c - GPL-3.0).
#
# A pilot acts every few turns (anPilotTurnInterval). Each time it
#   1. follows its mission type (patrol, wingman, strike, defend, ...),
#   2. when engaged, classifies the situation into one of nine events
#      (intelligence_events), updates its stress, and looks the next
#      manoeuvre up in the original tables (ai.wc: one table per named
#      pilot, one per Kilrathi skill level),
#   3. runs one step of that manoeuvre's script.
# Manoeuvres steer by setting rotation goals (degrees still to turn);
# world.rotate_object_to_goal works them off at the ship's turn rates.

from world import *     # noqa: F401,F403  (class / state constants)
import world as W
import wcmath as M
import wcdata as D

# ShipObjective
O_NONE = -1
O_WANDER = 5
O_ENGAGE = 6
O_HOLD_FORMATION = 8
O_BREAK_FORMATION = 9

# ShipTactic
TA_HEAD_HOME = 8
TA_LOOK_OUT = 10
TA_APPROACH = 11

# ShipManeuver
M_NONE = -1
M_VEER_AWAY = 2
M_FULL_AHEAD = 4
M_THINKING = 5
M_RAM_MISSILE = 6
M_KICK_STOP = 7
M_TIGHT_LOOP = 8
M_HARD_BRAKE = 9
M_SIT_N_SPIN = 10
M_TURN_N_SPIN = 11
M_BURNOUT = 12
M_WABBLE = 13
M_ROLL_OVER = 14
M_HARD_TURN = 15
M_FISH_HOOK = 16
M_SPLIT_LEFT = 17
M_SIT_N_FIRE = 18
M_KICKIT = 19
M_TURN_N_KICK = 20
M_OUTA_HERE = 21
M_DROP_A_MINE = 22
M_SPLIT_RIGHT = 23
M_ZIG_ZAG = 24
M_GLOAT = 25
M_TAIL_FIRE = 26
M_TARGET_LASER = 27
M_TARGET_MISSILE = 28
M_STRAFE_ENEMY = 29
M_STRAFE_N_ROLL = 30
M_KILL_MISSILE = 31
M_SUICIDE_RUN = 32
M_ZIG_ZAG_PITCH = 33
M_SAFE_BRAKE = 34
M_TURN_N_FIRE = 35
M_GET_DISTANCE = 36
M_CORKSCREW = 37
M_INTERCEPT = 38
M_TRY2TAIL = 39
M_ZIP_PAST = 40
M_BUZZ_DEBRIS = 41
M_LINE_UP_DROP = 42
M_CHILL = 43

rnd = W.rnd
rndle = W.rndle


def signed_random(n):
    return W.randint(-n, n)


class Brain:
    def __init__(self, world):
        self.w = world
        world.brain = self
        self.prox = 0

    # --- entry ---------------------------------------------------------------
    def think(self, ob):
        c = ob.cls
        if c == C_MISSILE:
            self.missile(ob)
        elif c == C_CAPITAL:
            self.capital(ob)
        elif c == C_SHIP:
            self.ship(ob)

    def ship(self, ob):
        """ship_intelligence"""
        if ob.special == SM_LOST_CONTROL:
            return
        if self.prevent_collision(ob):
            return
        if ob.alert > 0:
            ob.alert -= 1
            return
        ob.turn_reg -= 1
        if ob.turn_reg > 0:
            return
        ob.turns += 1
        ob.turn_reg = ob.turn_int
        mt = ob.mtype
        if mt == MT_PATROL:
            self.patrol(ob)
        elif mt == MT_WINGMAN:
            self.wingman(ob)
        elif mt == MT_ESCORT or mt == MT_DEFEND:
            self.defend(ob)
        elif mt == MT_STRIKE:
            self.strike(ob)
        elif mt == MT_ROUT:
            self.run_away(ob)
        elif mt == MT_GOTO_WARP:
            self.reach_warp(ob)
        elif mt == MT_WARP_ARRIVE or mt == MT_COME_HOME or \
                mt == MT_RENDEZVOUS:
            self.coming_home(ob)
        else:
            # inherit_leader_mission
            if ob.leader >= 0 and self.w.active(ob.leader):
                ob.mtype = MT_WINGMAN
            else:
                ob.mtype = MT_PATROL
        if ob.cooldown > 0:
            ob.cooldown -= 1

    # --- small helpers (logic.c) -----------------------------------------------
    def no_goal(self, ob):
        return ob.gp == 0 and ob.gy == 0 and ob.gr == 0

    def steady(self, ob):
        ob.gp = ob.gy = ob.gr = 0

    def cruise(self, ob):
        """approach_cruise_speed"""
        self.w.approach_speed(
            ob, min(ob.maxspd, self.w.T.f[D.T_CRUISE][ob.typ]) << 8)

    def full(self, ob):
        self.w.approach_speed(ob, ob.maxspd << 8)

    def stop(self, ob):
        self.w.approach_speed(ob, 0)

    def normal_speed(self, ob):
        return ob.special == SM_NONE

    def afterburner(self, ob, turns):
        """fire_afterburner"""
        if ob.fuel > 0 and ob.special != SM_AFTERBURNER:
            ob.special = SM_AFTERBURNER
            ob.abtimer = turns

    def super_brake(self, ob):
        ob.special = SM_SUPER_BRAKE
        ob.abtimer = 4

    def point_dir(self, ob, dx, dy, dz):
        """point_ship: aim the nose along a world direction."""
        lx, ly, lz = M.to_frame(ob.m, dx, dy, dz)
        yw, pt = M.spherical(lx, ly, lz)
        ob.gy = M.wrap(-yw)
        ob.gp = M.wrap(-pt)

    def point_at(self, ob, x, y, z):
        """point_ship_at_point (24.8 world position)."""
        self.point_dir(ob, (x - ob.x) >> 8, (y - ob.y) >> 8, (z - ob.z) >> 8)

    def point_obj(self, ob, t):
        self.point_at(ob, t.x, t.y, t.z)

    def point_behind(self, ob, t):
        k = (-500 - t.radius)
        m = t.m
        self.point_at(ob, t.x + ((m[6] * k) >> 6), t.y + ((m[7] * k) >> 6),
                      t.z + ((m[8] * k) >> 6))

    def point_below(self, ob, t):
        k = t.radius + 500
        m = t.m
        self.point_at(ob, t.x + ((m[3] * k) >> 6), t.y + ((m[4] * k) >> 6),
                      t.z + ((m[5] * k) >> 6))

    def veer_random(self, ob, amount):
        k = rndle(3)
        if k == 0:
            ob.gy = amount
        elif k == 1:
            ob.gy = -amount
        elif k == 2:
            ob.gp = amount
        else:
            ob.gp = -amount

    def steer_away(self, ob, t, amount):
        """steer_away_from_object"""
        ob.gr = 0
        lx, ly, lz = M.to_frame(ob.m, (t.x + t.vx - ob.x) >> 8,
                                (t.y + t.vy - ob.y) >> 8,
                                (t.z + t.vz - ob.z) >> 8)
        if abs(lx) < abs(ly):
            ob.gy = -amount if lx > 0 else amount
        else:
            ob.gp = -amount if ly > 0 else amount

    def trim_goals(self, ob, amount):
        if ob.gp > amount:
            ob.gp = amount
        elif ob.gp < -amount:
            ob.gp = -amount
        if ob.gy > amount:
            ob.gy = amount
        elif ob.gy < -amount:
            ob.gy = -amount

    def prevent_collision(self, ob):
        """prevent_collision / crash_time: every turn, look at the ships
        this pilot can run into - his target, the player and anything
        big - and swerve if the closing speed leaves less than about
        ten turns. While the alert lasts the pilot does nothing else."""
        w = self.w
        o = w.o
        for i in range(NSHIP):
            t = o[i]
            if t is ob or t.cls < C_SHIP:
                continue
            if t.cls != C_CAPITAL and i != 0 and i != ob.target:
                continue
            dx = (t.x - ob.x) >> 8
            dy = (t.y - ob.y) >> 8
            dz = (t.z - ob.z) >> 8
            lim = 1600 + t.radius
            if dx > lim or dx < -lim or dy > lim or dy < -lim or \
                    dz > lim or dz < -lim:
                continue
            d = M.mag(dx, dy, dz)
            if d == 0:
                continue
            closing = (((ob.vx - t.vx) >> 8) * dx + ((ob.vy - t.vy) >> 8) * dy
                       + ((ob.vz - t.vz) >> 8) * dz) // d
            gap = d - t.radius - ob.radius
            if closing > 4 and gap < closing * 10 + 60:
                m = ob.m
                ahead = dx * m[6] + dy * m[7] + dz * m[8]
                if ahead > 0:
                    self.steer_away(ob, t, 45)
                    ob.alert = 5
                    return True
        return False

    def scan_for_enemy(self, ob, rng):
        w = self.w
        o = w.o
        best = -1
        bd = rng
        for i in range(NSHIP):
            t = o[i]
            if t.cls < C_SHIP or t.special == SM_DYING or t.side == ob.side \
                    or t.side == 2:
                continue
            d = w.dist(ob, t) - t.radius
            if d < bd:
                bd = d
                best = i
        return best

    def any_enemy(self, ob, rng):
        return self.scan_for_enemy(ob, rng) != -1

    def attacker_in_range(self, victim, rng):
        """Is somebody already hunting this ship?"""
        w = self.w
        o = w.o
        for i in range(1, NSHIP):
            t = o[i]
            if t.cls == C_SHIP and t.target == victim.i and \
                    t.objective == O_ENGAGE and t.special != SM_DYING and \
                    w.dist(victim, t) < rng:
                return True
        return False

    def detect_enemy_tail(self, ob):
        """An enemy sitting on our tail becomes the target."""
        w = self.w
        o = w.o
        for i in range(NSHIP):
            t = o[i]
            if t.cls != C_SHIP or t.side == ob.side or \
                    t.special == SM_DYING:
                continue
            w.ship_vs_ship(ob, t)
            if w.RANGE < 3000 and w.FACE < -50 and w.TFACE > 80:
                return i
        return -1

    def missile_on_tail(self, ob):
        o = self.w.o
        for i in range(NSHIP, NOBJ):
            t = o[i]
            if t.cls == C_MISSILE and t.target == ob.i and \
                    t.tactic != T_SIT_STILL:
                return i
        return -1

    def select_target(self, ob):
        w = self.w
        p = w.o[0]
        if ob.side == SIDE_KILRATHI and rnd(100) < 50 and \
                p.cls == C_SHIP and not self.attacker_in_range(p, 16000) \
                and w.distance_from_object(ob, p) < 5000:
            ob.target = 0
            return
        ob.target = self.scan_for_enemy(ob, 16000)

    def check_engage_target(self, ob):
        t = self.detect_enemy_tail(ob)
        if t != -1 and t != ob.target:
            ob.target = t
        elif not self.w.active(ob.target) or \
                self.w.o[ob.target].side == ob.side:
            self.select_target(ob)
        return ob.target

    def skill_rating(self, ob):
        r = ob.level
        if r <= 4:
            return max(2, r)
        if r == 13:
            return 5
        if r < 14:
            return ((r - 5) >> 1) + 4
        return r - 10

    def message(self, ob, kind):
        """send_message, reduced to a few stock lines."""
        w = self.w
        if ob.i != w.wingman or ob.rating < 0 or ob.rating > 7:
            return
        name = w.ai.pilots[ob.rating][1]
        if kind == 4:
            text = b': I need help!'
        elif kind == 5:
            text = b': Got one!'
        elif kind == 8:
            text = b': You are hit hard!'
        else:
            text = b': Roger.'
        w.say(name + text, 0xFFFF)

    # --- firing (ship.c fire) --------------------------------------------------
    def fire(self, ob, ti):
        w = self.w
        if not w.active(ti):
            return
        t = w.o[ti]
        T = w.T.f
        can = ob.counter <= 0
        w.ship_vs_ship(ob, t)
        rng = w.RANGE
        face = w.FACE
        want_missile = rndle(19) == 0 and rndle(7000) > rng and face > 85
        if not can:
            return
        fired = False
        for k in range(len(ob.weapons)):
            wp = ob.weapons[k]
            wt = wp[0]
            c = T[D.T_CLASS][wt]
            if c == C_PROJECTILE or wt == OT_TURRET:
                if T[D.T_LIFETIME][wt] * T[D.T_MAX_VEL][wt] <= rng:
                    continue
                if wt == OT_LASER:
                    ok = face > 70
                elif wt == 25:
                    ok = face > 80
                elif wt == 26:
                    ok = face > 85
                else:
                    ok = face > 10
                if ok and ob.energy >= T[D.T_ANIM_DELAY][wt]:
                    if w.fire_weapon(ob, k) is not None:
                        fired = True
        if want_missile and not fired:
            w.fire_missile(ob)

    def fire_when_ready(self, ob):
        w = self.w
        if ob.i == w.wingman and ob.level != 11:
            # every wingman but Maniac holds fire when the player is in
            # the line of fire
            w.ship_vs_ship(ob, w.o[0])
            if w.FACE > 80:
                return
        self.fire(ob, ob.target)

    # --- missions (brains.c) ---------------------------------------------------
    def goto(self, ob, x, y, z, near):
        """cruise_to_destination: True once within `near` units."""
        w = self.w
        w.ship_vs_point(ob, x, y, z)
        if w.RANGE < near:
            return True
        if self.no_goal(ob) or ob.turns % 4 == 0:
            self.point_at(ob, x, y, z)
            self.trim_goals(ob, 20)
        return False

    def engage(self, ob):
        """maneuvering(obj, check_engage_target(obj))"""
        ti = self.check_engage_target(ob)
        if ti == -1:
            ob.objective = O_NONE
            ob.man = M_NONE
            return False
        self.intelligence_events(ob)
        self.perform_maneuver(ob)
        return True

    def patrol(self, ob):
        """kilrathi_patrol / patrol_area"""
        w = self.w
        if ob.objective == O_ENGAGE:
            self.engage(ob)
            return
        if ob.objective == O_BREAK_FORMATION:
            # formation_burst: a moment of scatter, then the fight
            self.full(ob)
            ob.tot += 1
            if ob.tot > 3:
                ob.tot = 0
                ob.objective = O_ENGAGE
            return
        if ob.objective == O_NONE:
            ob.objective = O_WANDER
            ob.tactic = TA_APPROACH
        tac = ob.tactic
        if tac == TA_HEAD_HOME:
            self.cruise(ob)
            ob.target = self.scan_for_enemy(ob, 14000)
            if ob.target != -1:
                ob.tactic = TA_APPROACH
            elif self.goto(ob, ob.spx, ob.spy, ob.spz, 3000):
                ob.tactic = TA_LOOK_OUT
        elif tac == TA_LOOK_OUT:
            self.cruise(ob)
            ob.target = self.scan_for_enemy(ob, 14000)
            if ob.target != -1:
                ob.tactic = TA_APPROACH
            else:
                w.ship_vs_point(ob, ob.spx, ob.spy, ob.spz)
                if w.RANGE > 8000:
                    ob.tactic = TA_HEAD_HOME
        elif tac == TA_APPROACH:
            self.full(ob)
            if not w.active(ob.target):
                ob.target = self.scan_for_enemy(ob, 14000)
                if ob.target == -1:
                    ob.tactic = TA_LOOK_OUT
            else:
                t = w.o[ob.target]
                w.ship_vs_ship(ob, t)
                if w.RANGE < 10000:
                    # init_formation_burst
                    ob.objective = O_BREAK_FORMATION
                    ob.tot = 0
                    self.veer_random(ob, 30)
                    return
                if self.no_goal(ob):
                    self.point_obj(ob, t)
        else:
            ob.tactic = TA_APPROACH

    def formation_point(self, ob, lead):
        """compute_formation_destination"""
        m = lead.m
        return (lead.x + lead.vx * 3 +
                ((m[0] * ob.fdx + m[3] * ob.fdy + m[6] * ob.fdz) >> 6),
                lead.y + lead.vy * 3 +
                ((m[1] * ob.fdx + m[4] * ob.fdy + m[7] * ob.fdz) >> 6),
                lead.z + lead.vz * 3 +
                ((m[2] * ob.fdx + m[5] * ob.fdy + m[8] * ob.fdz) >> 6))

    def maintain_formation(self, ob, lead):
        """chase_location on the formation slot."""
        w = self.w
        x, y, z = self.formation_point(ob, lead)
        w.ship_vs_point(ob, x, y, z)
        rng = w.RANGE + 2 * ob.radius
        if rng < 175:
            # in the slot: fly the leader's heading and speed
            m = lead.m
            self.point_dir(ob, m[6] >> 4, m[7] >> 4, m[8] >> 4)
            self.trim_goals(ob, 10)
            w.approach_speed(ob, lead.speed)
            return
        if w.FACE < 0 and rng < 1500:
            # overshot: slow down and let the leader come by
            w.approach_speed(ob, max(0, lead.speed - 0x800))
        else:
            want = lead.speed + min(rng, 4000) * 8
            w.approach_speed(ob, min(want, ob.maxspd << 8))
            if rng > 3000 and w.FACE > 80 and ob.special == SM_NONE and \
                    rng > 8000:
                self.afterburner(ob, 10)
        if self.no_goal(ob) or ob.turns % 3 == 0:
            self.point_at(ob, x, y, z)
            if rng < 600:
                self.trim_goals(ob, 10)

    def wingman(self, ob):
        """imperial_wingman / kilrathi_wingman"""
        w = self.w
        if ob.leader < 0 or not w.active(ob.leader):
            ob.leader = w.find_ship(w.mis.ship(ob.mship)[19]) \
                if ob.mship >= 0 else -1
            if ob.leader < 0 or not w.active(ob.leader):
                ob.mtype = MT_PATROL          # inherit_leader_mission
                ob.objective = O_NONE
                return
        lead = w.o[ob.leader]
        if ob.objective == O_ENGAGE:
            if ob.leader == 0 and not w.engage_ok:
                ob.objective = O_HOLD_FORMATION
                ob.man = M_NONE
                ob.special = SM_NONE
            elif self.engage(ob):
                return
        if ob.objective == O_BREAK_FORMATION:
            self.full(ob)
            ob.tot += 1
            if ob.tot > 3:
                ob.tot = 0
                ob.objective = O_ENGAGE
            return
        # break and attack when the leader does or the enemy closes in
        fight = False
        if ob.leader == 0:
            fight = w.engage_ok and self.any_enemy(ob, 8000)
        else:
            fight = lead.objective in (O_ENGAGE, O_BREAK_FORMATION) or \
                self.any_enemy(ob, 5000)
        if fight:
            ob.objective = O_BREAK_FORMATION
            ob.tot = rnd(3)
            self.veer_random(ob, 40)
            return
        ob.objective = O_HOLD_FORMATION
        self.maintain_formation(ob, lead)

    def defend(self, ob):
        """defend_mission / escort_mission"""
        w = self.w
        if ob.objective == O_ENGAGE and self.engage(ob):
            return
        if self.any_enemy(ob, 14000):
            ob.objective = O_ENGAGE
            return
        b = w.find_ship(ob.mtarget)
        if b >= 0 and b != ob.i:
            lead = w.o[b]
            if w.dist(ob, lead) > 2500 + lead.radius:
                self.full(ob)
                if self.no_goal(ob) or ob.turns % 4 == 0:
                    self.point_obj(ob, lead)
                    self.trim_goals(ob, 20)
            else:
                w.approach_speed(ob, max(lead.speed, 0x800))
                if self.no_goal(ob):
                    m = lead.m
                    self.point_dir(ob, m[6] >> 4, m[7] >> 4, m[8] >> 4)
        else:
            self.cruise(ob)
            if self.goto(ob, ob.spx, ob.spy, ob.spz, 3000):
                if self.no_goal(ob):
                    ob.gy = 30

    def strike(self, ob):
        """strike_mission: go for the assigned ship."""
        w = self.w
        t = w.find_ship(ob.mtarget)
        if t >= 0 and w.o[t].side != ob.side and w.active(t):
            hurt = w.evaluate_damage(ob) <= 70 - min(4, ob.level) * 15
            if hurt or self.detect_enemy_tail(ob) != -1:
                self.engage(ob)
                return
            ob.target = t
            ob.objective = O_ENGAGE
            w.ship_vs_ship(ob, w.o[t])
            if w.RANGE > 9000:
                self.full(ob)
                if self.no_goal(ob):
                    self.point_obj(ob, w.o[t])
                return
            self.intelligence_events(ob)
            self.perform_maneuver(ob)
        else:
            self.patrol(ob)

    def run_away(self, ob):
        """run_away: head out of the sphere and leave."""
        w = self.w
        self.full(ob)
        e = self.scan_for_enemy(ob, 30000)
        if e == -1 or w.dist(ob, w.o[e]) > 16000:
            if ob.mship >= 0:
                w.mis.ship_state[ob.mship] = 2
            w.remove(ob)
            return
        if self.no_goal(ob):
            t = w.o[e]
            self.point_dir(ob, (ob.x - t.x) >> 8, (ob.y - t.y) >> 8,
                           (ob.z - t.z) >> 8)
            self.trim_goals(ob, 30)
        if ob.special == SM_NONE and rnd(100) < 20:
            self.afterburner(ob, 10)

    def reach_warp(self, ob):
        """reach_warp: fly to the jump point and jump out."""
        w = self.w
        self.cruise(ob)
        if self.goto(ob, ob.spx, ob.spy, ob.spz, 1500):
            if ob.mship >= 0:
                w.mis.ship_state[ob.mship] = 2
            if ob.side == SIDE_CONFED:
                w.say(w.T.names[ob.typ] + b' has jumped out', 0x07E0)
            e = w.spawn_explosion(ob, 49, 0x200)
            w.remove(ob)

    def coming_home(self, ob):
        w = self.w
        if ob.side == SIDE_KILRATHI and ob.mtype == MT_WARP_ARRIVE:
            ob.mtype = MT_PATROL
            return
        if self.goto(ob, ob.spx, ob.spy, ob.spz, 2500):
            self.stop(ob)
            if ob.mship >= 0:
                w.mis.ship_state[ob.mship] = 1
        else:
            self.cruise(ob)

    # --- capital ships and missiles ----------------------------------------------
    def capital(self, ob):
        """capital_ship_intelligence: hold course, work the turrets."""
        w = self.w
        ob.turn_reg -= 1
        if ob.turn_reg > 0:
            return
        ob.turn_reg = 4
        ob.turns += 1
        if ob.mtype == MT_GOTO_WARP:
            self.reach_warp(ob)
            if ob.cls == C_NULL:
                return
        elif ob.mtype in (MT_WARP_ARRIVE, MT_COME_HOME):
            self.coming_home(ob)
        else:
            w.approach_speed(ob, ob.speed)
        # fire_turrets
        if not ob.weapons or ob.turns % 2:
            return
        ti = self.scan_for_enemy(ob, 5000)
        if ti == -1:
            return
        t = w.o[ti]
        p = w.new_object(OT_TURRET, ob.i)
        if p is None:
            return
        T = w.T.f
        r = ob.radius >> 1
        p.x = ob.x + (W.randint(-r, r) << 8)
        p.y = ob.y + (W.randint(-r, r) << 8)
        p.z = ob.z + (W.randint(-r, r) << 8)
        p.side = ob.side
        p.acc = T[D.T_DAMAGE][OT_TURRET]
        p.counter = T[D.T_LIFETIME][OT_TURRET]
        spd = T[D.T_MAX_VEL][OT_TURRET]
        lead = w.dist(ob, t) // spd
        err = 60 + 40 * (4 - min(4, ob.level))      # rnd_aim
        dx = ((t.x + t.vx * lead - p.x) >> 8) + W.randint(-err, err)
        dy = ((t.y + t.vy * lead - p.y) >> 8) + W.randint(-err, err)
        dz = ((t.z + t.vz * lead - p.z) >> 8) + W.randint(-err, err)
        n = M.mag(dx, dy, dz)
        if n == 0:
            n = 1
        p.vx = (dx * spd << 8) // n
        p.vy = (dy * spd << 8) // n
        p.vz = (dz * spd << 8) // n

    def missile(self, ob):
        """Missile guidance once the motor has lit."""
        w = self.w
        if ob.tactic == T_SIT_STILL:
            return
        t = ob.typ
        if t == OT_DUMBFIRE:
            return
        if t == OT_FF and (ob.target == -1 or not w.active(ob.target)):
            # friend-or-foe: the nearest ship not on the launcher's side
            ob.target = self.scan_for_enemy(ob, 12000)
        if not w.active(ob.target):
            return
        tg = w.o[ob.target]
        lx, ly, lz = M.to_frame(ob.m, (tg.x - ob.x) >> 8,
                                (tg.y - ob.y) >> 8, (tg.z - ob.z) >> 8)
        yw, pt = M.spherical(lx, ly, lz)
        if t == OT_HEATSEEKER and (abs(yw) > 70 or abs(pt) > 70):
            ob.target = -1              # lost the heat source
            return
        rate = w.T.f[D.T_PITCH][t]
        yw = max(-rate, min(rate, yw))
        pt = max(-rate, min(rate, pt))
        if yw:
            M.yaw(ob.m, -yw)
        if pt:
            M.pitch(ob.m, -pt)
        M.fix(ob.m)

    # --- stress and manoeuvre choice (smart.c) -------------------------------------
    def stress_morale(self, ob):
        if ob.stress < 15:
            return 0
        if ob.stress < 30:
            return 1
        return 2

    def any_defense(self, ob):
        lst = self.w.ai.defense[min(4, ob.level)]
        return lst[rnd(len(lst))]

    def pick_from_list(self, table, base, ob):
        thr = table[base]
        pri = table[base + 1]
        sec = table[base + 2]
        man = ob.man
        again = man == M_NONE
        if pri != man and sec != man and rnd(100) < 10 and \
                pri < 45 and sec < 45:
            again = True
        if not again and rndle(100) < 5:
            again = True
        if again:
            man = sec if rndle(100) >= thr else pri
        if man == 45:
            return M_STRAFE_ENEMY
        if man == 46 or man == 44:
            return self.any_defense(ob)
        return man

    def pick_regular_maneuver(self, ob, event):
        w = self.w
        reroll = rndle(100) < 3 or ob.man == M_NONE
        if self.stress_morale(ob) == 2:
            return M_OUTA_HERE
        if (ob.event == event or rndle(100) < 20) and \
                event in (0, 3, 4, 7) and not reroll:
            return ob.man
        if event == 0:
            if w.o[ob.target].cls == C_CAPITAL:
                return M_STRAFE_ENEMY
            if rnd(100) < ob.level * 5 + 60:
                return M_ZIP_PAST
            return self.any_defense(ob)
        if event == 2:
            return M_TRY2TAIL
        if event == 3 or event == 7:
            return self.any_defense(ob)
        if event == 4:
            if rndle(100) >= ob.level * 20 + 30:
                return self.any_defense(ob)
            return M_STRAFE_ENEMY
        if event == 5:
            return M_TAIL_FIRE
        if event == 6:
            return M_HARD_TURN if ob.level >= 2 else M_WABBLE
        if event == 8:
            return M_LINE_UP_DROP
        return M_ROLL_OVER

    def process_maneuver_node(self, ob, event):
        ai = self.w.ai
        morale = self.stress_morale(ob)
        if ob.rating != -1 and ob.rating < 13:
            man = self.pick_from_list(
                ai.rated, ((ob.rating * 9 + event) * 3 + morale) * 3, ob)
        elif ob.side == SIDE_KILRATHI and ob.level < 5:
            man = self.pick_from_list(
                ai.kilrathi, ((ob.level * 9 + event) * 3 + morale) * 3, ob)
        else:
            man = self.pick_regular_maneuver(ob, event)
        if ob.man != man:
            self.reset_maneuver(ob, man)

    def reset_maneuver(self, ob, man):
        ob.man = man
        ob.seq = 0
        ob.tot = 0

    def maneuver_complete(self, ob):
        ob.special = SM_NONE
        self.reset_maneuver(ob, M_NONE)

    def handle_stress(self, ob, event):
        w = self.w
        lvl = min(ob.level, 17)
        agg = w.ai.aggression[lvl]
        if agg > 127:
            agg -= 256
        if event in (3, 4, 7):
            ob.stress += agg
        elif event == 5:
            ob.stress -= agg
        elif event == 6:
            ob.stress += agg * 2
        elif event == 8:
            ob.stress //= 2
        elif event in (-1, 2):
            ob.stress -= w.ai.recovery[lvl]
        dmg = w.evaluate_damage(ob)
        if dmg < 40:
            ob.stress += agg * 2
        elif dmg < 75:
            ob.stress = min(ob.stress + agg, 28)
        else:
            ob.stress = min(ob.stress, 7)
        if event == 6 and ob.stress >= 30:
            ob.stress = 29
        if ob.stress < 0:
            ob.stress = 0

    def intelligence_events(self, ob):
        w = self.w
        event = -1
        ti = ob.target
        prev = ob.stress
        gone = False
        if self.missile_on_tail(ob) != -1:
            event = 6
        elif w.active(ti):
            t = w.o[ti]
            event = 0
            w.ship_vs_ship(ob, t)
            if w.RANGE > 8000:
                event = 2
            elif ob.cooldown > 0:
                event = 7
            elif w.FACE > 55 and w.TFACE < -55:
                event = 5
            elif w.FACE > 75 and w.TFACE > 75:
                event = 4
            elif w.FACE < -60 and w.TFACE > 85 and w.RANGE < 7000:
                event = 3
            elif t.speed < 20:
                event = 1
        else:
            gone = True
        self.handle_stress(ob, event)
        if event != -1:
            self.process_maneuver_node(ob, event)
        if event == -1 and gone:
            if not self.any_enemy(ob, 16000):
                ob.objective = O_NONE
            else:
                self.select_target(ob)
            ob.stress = 0
        if w.wingman == ob.i and prev < 15 and ob.stress >= 15:
            self.message(ob, 4)
        ob.event = event

    # --- manoeuvres (fl.c) -----------------------------------------------------------
    def close_behind(self, rng):
        w = self.w
        return rng > w.RANGE and w.TFACE < -50

    def chase_speed(self, ob, t, rng):
        w = self.w
        if rng < w.RANGE:
            self.full(ob)
        elif rng > w.RANGE:
            self.stop(ob)
        else:
            w.approach_speed(ob, t.speed)

    def tail_fire(self, ob, t):
        if self.no_goal(ob):
            self.point_obj(ob, t)
        self.chase_speed(ob, t, (t.radius + ob.radius * 6) >> 1)
        self.fire_when_ready(ob)

    def zip_past(self, ob, t):
        w = self.w
        if self.close_behind(t.radius + 2000):
            self.tail_fire(ob, t)
            return
        self.full(ob)
        if self.no_goal(ob):
            if w.TFACE > 80:
                self.point_below(ob, t)
            else:
                self.point_behind(ob, t)
        if w.FACE > 85:
            self.fire_when_ready(ob)

    def strafe_enemy(self, ob, t):
        self.cruise(ob)
        if ob.gp == 0 and ob.gy == 0:
            self.w.ship_vs_ship(ob, t)
            self.point_obj(ob, t)
        self.fire_when_ready(ob)

    def best_strafe(self, ob, t):
        if self.w.TFACE < 80:
            self.strafe_enemy(ob, t)
        else:
            self.zip_past(ob, t)

    def general_zig(self, ob, pitch):
        done = True
        self.full(ob)
        k = ob.seq % 6
        if k == 0:
            ob.gy = -35
            ob.gp = pitch
        elif k == 1 or k == 4:
            done = self.no_goal(ob)
            ob.tot = 0
        elif k == 2 or k == 5:
            ob.tot += 1
            done = ob.tot >= 4
        else:
            ob.gy = 35
            ob.gp = -pitch
        if ob.seq >= 12:
            self.maneuver_complete(ob)
        elif done:
            ob.seq += 1

    def perform_maneuver(self, ob):
        w = self.w
        ti = ob.target
        if not w.active(ti):
            self.maneuver_complete(ob)
            return
        t = w.o[ti]
        w.ship_vs_ship(ob, t)
        if w.TFACE < 0:
            self.prox = (t.radius + ob.radius * 4) >> 1
        else:
            self.prox = (t.radius + ob.radius * 6) >> 1
        man = ob.man
        seq = ob.seq
        done = self.maneuver_complete
        if man == M_TAIL_FIRE:
            self.tail_fire(ob, t)
        elif man == M_ZIP_PAST or man == M_INTERCEPT:
            self.zip_past(ob, t)
        elif man == M_STRAFE_ENEMY or man == M_TURN_N_FIRE:
            self.strafe_enemy(ob, t)
        elif man == M_TARGET_LASER:
            self.best_strafe(ob, t)
        elif man == M_STRAFE_N_ROLL:
            if ob.counter > 0:
                ob.gr = 45
            else:
                self.strafe_enemy(ob, t)
        elif man == M_SIT_N_FIRE:
            if t.cls == C_CAPITAL:
                self.best_strafe(ob, t)
            else:
                if self.no_goal(ob):
                    self.point_obj(ob, t)
                if w.RANGE > 3000:
                    self.cruise(ob)
                else:
                    self.stop(ob)
                self.fire_when_ready(ob)
        elif man == M_TRY2TAIL:
            self.full(ob)
            if self.no_goal(ob):
                self.point_obj(ob, t)
            if rndle(100) < 4:
                self.veer_random(ob, 5)
        elif man == M_SUICIDE_RUN:
            self.full(ob)
            if self.no_goal(ob):
                self.point_obj(ob, t)
        elif man == M_TARGET_MISSILE or man == M_RAM_MISSILE:
            if self.no_goal(ob):
                self.point_obj(ob, t)
            self.cruise(ob)
            if w.missile_count(ob) == 0:
                self.reset_maneuver(ob, M_STRAFE_ENEMY)
            elif w.FACE > 85 and w.RANGE < 6000 and \
                    (w.TFACE > 80 or w.TFACE < -80 or man == M_RAM_MISSILE) \
                    and rndle(5) == 0:
                w.fire_missile(ob)
                done(ob)
        elif man == M_FULL_AHEAD:
            self.full(ob)
            ob.tot -= 1
            if ob.tot < 0:
                done(ob)
        elif man == M_THINKING:
            self.cruise(ob)
            if ob.tot == 0:
                ob.tot = 2
            ob.tot -= 1
            if ob.tot <= 1:
                done(ob)
        elif man == M_TIGHT_LOOP:
            self.cruise(ob)
            if seq == 0 or seq == 2:
                ob.gp = 180
                ob.seq += 1
            elif seq == 1:
                if self.no_goal(ob):
                    ob.seq += 1
            else:
                if self.no_goal(ob):
                    done(ob)
        elif man == M_HARD_BRAKE or man == M_SAFE_BRAKE:
            adv = True
            if seq == 0:
                ob.special = SM_KILL_ENGINES
            elif seq == 1:
                ob.tot += 1
                adv = ob.tot > 3
                if adv:
                    ob.tot = 0
            elif seq == 2:
                self.super_brake(ob)
            else:
                ob.tot += 1
                adv = ob.tot > 3
                if adv:
                    done(ob)
                    return
            if adv:
                ob.seq += 1
        elif man == M_SIT_N_SPIN or man == M_TURN_N_SPIN:
            adv = True
            if seq == 0:
                self.veer_random(ob, 90)
            elif seq == 1:
                ob.tot += 1
                adv = ob.tot > 2
            elif seq == 2:
                if w.TFACE <= 80:
                    ob.special = SM_KILL_ENGINES
                    self.point_obj(ob, t)
                else:
                    done(ob)
                    return
            elif seq == 3:
                adv = self.no_goal(ob)
            elif seq < 9:
                if w.FACE > 85:
                    self.fire(ob, ti)
            else:
                done(ob)
                return
            if adv:
                ob.seq += 1
        elif man == M_BURNOUT:
            if seq == 0:
                self.afterburner(ob, 10)
                ob.seq += 1
            elif seq == 1:
                if ob.special == SM_NONE:
                    ob.gy = 180
                    ob.seq += 1
            elif self.no_goal(ob):
                done(ob)
        elif man == M_KICKIT:
            if seq == 0:
                self.afterburner(ob, 10)
                ob.seq += 1
            elif ob.special == SM_NONE:
                done(ob)
        elif man == M_TURN_N_KICK or man == M_KICK_STOP:
            if seq == 0:
                self.veer_random(ob, 90)
                ob.seq += 1
            elif seq == 1:
                if self.no_goal(ob):
                    self.afterburner(ob, 10)
                    ob.seq += 1
                else:
                    self.full(ob)
            elif ob.special == SM_NONE:
                done(ob)
        elif man == M_ROLL_OVER:
            if seq == 0:
                ob.seq += 1
                ob.gr = rndle(1) * 360 - 180
            elif ob.gr == 0:
                done(ob)
            else:
                self.full(ob)
        elif man == M_HARD_TURN:
            self.full(ob)
            if seq == 0:
                ob.gy = rndle(1) * 360 - 180
                ob.seq += 1
            elif self.no_goal(ob):
                done(ob)
        elif man == M_FISH_HOOK:
            adv = True
            if seq == 0:
                ob.gy = rndle(1) * 240 - 120
                self.afterburner(ob, 5)
            elif seq == 1 or seq == 4:
                adv = self.no_goal(ob)
                self.full(ob)
            elif seq == 2:
                self.super_brake(ob)
                ob.gy = rndle(1) * 90 - 45
            elif seq == 3:
                adv = M.mag(ob.vx, ob.vy, ob.vz) >> 8 <= \
                    w.T.f[D.T_CRUISE][ob.typ]
            elif seq == 5:
                self.afterburner(ob, 10)
            else:
                adv = False
                if self.normal_speed(ob):
                    done(ob)
            if adv:
                ob.seq += 1
        elif man == M_SPLIT_LEFT or man == M_SPLIT_RIGHT:
            if seq == 0:
                ob.gy = 90 if man == M_SPLIT_LEFT else -90
                ob.seq += 1
            elif self.no_goal(ob):
                done(ob)
        elif man == M_GLOAT:
            if seq == 0:
                ob.special = SM_KILL_ENGINES
                ob.seq += 1
            elif seq == 1:
                ob.gp = 15
                if rnd(100) < 50:
                    ob.seq += 1
            else:
                ob.gp = -30
                if rnd(100) < 50:
                    ob.tot += 1
                    if ob.tot < 10:
                        ob.seq = 1
                    else:
                        done(ob)
        elif man == M_KILL_MISSILE:
            mi = self.missile_on_tail(ob)
            if mi == -1:
                done(ob)
            else:
                w.ship_vs_ship(ob, w.o[mi])
                if w.FACE < 0:
                    self.reset_maneuver(ob, M_FISH_HOOK)
                elif w.FACE < 80:
                    self.reset_maneuver(ob, M_BURNOUT)
                else:
                    self.point_obj(ob, w.o[mi])
        elif man == M_GET_DISTANCE:
            rng = w.RANGE
            if rng > 2000:
                done(ob)
            else:
                if rng < 700 and self.normal_speed(ob):
                    self.afterburner(ob, 10)
                else:
                    self.full(ob)
                if w.FACE > 0 and self.no_goal(ob):
                    self.steer_away(ob, t, min(20, w.FACE))
        elif man == M_ZIG_ZAG:
            self.general_zig(ob, 0)
        elif man == M_ZIG_ZAG_PITCH:
            self.general_zig(ob, 35)
        elif man == M_CORKSCREW:
            self.full(ob)
            if self.no_goal(ob):
                ob.tot -= 1
                if ob.tot <= 0:
                    k = seq % 4
                    if k == 0:
                        ob.gy = -20
                    elif k == 2:
                        ob.gy = 20
                    else:
                        ob.gr = 20
                    ob.tot = 4
                    ob.seq += 1
            if ob.seq > 8:
                done(ob)
        elif man == M_VEER_AWAY or man == M_BUZZ_DEBRIS:
            if seq == 0:
                self.steer_away(ob, t, 40 if w.FACE > 80 else 10)
                ob.seq += 1
            elif t.radius * 3 < w.RANGE:
                self.veer_random(ob, 8)
                done(ob)
            else:
                if self.no_goal(ob):
                    if w.FACE > 80:
                        self.steer_away(ob, t, 40)
                    elif w.FACE < -65 or rndle(100) < 4:
                        self.veer_random(ob, 16)
                if (self.prox >= w.RANGE or rndle(100) < 10) and \
                        self.normal_speed(ob):
                    self.afterburner(ob, 10)
                else:
                    self.full(ob)
        elif man == M_WABBLE:
            ob.tot += 1
            if ob.tot > 20:
                done(ob)
            else:
                self.full(ob)
                if self.no_goal(ob):
                    k = rndle(2)
                    if k == 0:
                        ob.gy = signed_random(6) * 5
                    elif k == 1:
                        ob.gp = signed_random(6) * 5
                    else:
                        ob.gr = signed_random(10) * 5
        elif man == M_OUTA_HERE:
            # Mrout_me / try2rout: break off for good
            ob.mtype = MT_ROUT
            ob.objective = O_NONE
            ob.man = M_NONE
            if ob.side == SIDE_KILRATHI and rnd(100) < 40:
                w.say(w.T.names[ob.typ] + b' breaks off', 0xFFE0)
        elif man == M_CHILL:
            self.cruise(ob)
            if self.no_goal(ob):
                self.point_behind(ob, t)
            if self.close_behind(1000):
                self.reset_maneuver(ob, M_TAIL_FIRE)
        elif man == M_LINE_UP_DROP:
            if self.no_goal(ob):
                self.point_obj(ob, t)
                ob.gr = 360
        else:
            # M_NONE, M_DROP_A_MINE and the unused slots
            self.full(ob)
            done(ob)
