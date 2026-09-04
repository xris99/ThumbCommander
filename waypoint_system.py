# waypoint_system.py - Waypoint navigation for multi-stage missions
# Compile to .mpy for deployment: python3 -m mpy_cross waypoint_system.py
from fpmath import fpmul, fpsin, fpcos, project, rotate_z_x, rotate_z_y, sign
from platform_loader import PC, display, IS_THUMBY_COLOR

# Fixed z-distance for waypoint (always at max range)
WP_Z = 60 << 16
# Cross size on 3D view (fixed pixels)
WP_CROSS_SZ = 4 * PC.SCREEN_SCALE
# Reach threshold: waypoint x/y must be within this to count as "reached"
WP_REACH = PC.SPACE_WIDTH // 4 << 16
# FP16 ratio for waypoint X/Y displacement, derived from star parallax:
_WP_STAR_RATIO = const((15 << 16) // 7)  # FP16 ≈ 2.1428 (exact: 140342)

# Pre-computed boundary constants (same as enemies)
_SW = PC.SPACE_WIDTH << 16
_SH = PC.SPACE_HEIGHT << 16
_SW2 = PC.SPACE_WIDTH * 2 << 16
_SH2 = PC.SPACE_HEIGHT * 2 << 16
_SW3 = PC.SPACE_WIDTH * 3 << 16
_SH3 = PC.SPACE_HEIGHT * 3 << 16


class Waypoint:
    __slots__ = ('x', 'y', 'z', 'visible', 'type', 'difficulty',
                 'enemies', 'asteroids', 'front', 'behind',
                 'enemy_types', 'obj_kills', 'obj_time', 'obj_reach')

    def __init__(self, wp_data):
        pos = wp_data.get("position", [0, 0, 45])
        self.x = pos[0] << 16
        self.y = pos[1] << 16
        self.z = WP_Z
        self.visible = True
        self.type = wp_data.get("type", "mixed")
        self.difficulty = wp_data.get("difficulty", 1)
        self.enemies = wp_data.get("enemies", 0)
        self.asteroids = wp_data.get("asteroids", 0)
        self.front = wp_data.get("front")
        self.behind = wp_data.get("behind")
        self.enemy_types = wp_data.get("enemy_types", None)
        obj = wp_data.get("objectives", {})
        self.obj_kills = obj.get("kills", 0)
        self.obj_time = obj.get("survive_time", 0)
        self.obj_reach = obj.get("reach", False)


class WaypointManager:
    def __init__(self, waypoints_data):
        self.waypoints = [Waypoint(w) for w in waypoints_data]
        self.current_idx = 0
        self.total = len(self.waypoints)
        self.kills = 0
        self.survive_ticks = 0
        self.reached = False
        self.wp_complete = False

    def get_current(self):
        if self.current_idx < self.total:
            return self.waypoints[self.current_idx]
        return None

    def update_position(self, wp, player_angle, player_speed):
        """Move waypoint using the same coordinate system as enemies.
        X/Y uses star-speed (no own velocity) for responsive steering.
        Z stays at max distance. Full enemy boundary/wrapping logic applied."""
        z_old = wp.z

        # X/Y: match star background angular velocity via FP multiply (no truncation drift).
        wp.x += fpmul(player_angle[0], _WP_STAR_RATIO) + (player_speed - 65536)
        wp.y += fpmul(player_angle[1], _WP_STAR_RATIO) + (player_speed - 65536)

        # Z: base approach same as enemies
        wp.z -= fpmul(2048, player_speed)

        # Z-rotation not applied here — applied visually in draw_waypoint_3d
        # to prevent cross-axis drift from accumulated camera shift

        # X/Y boundary wrapping — identical to enemies
        if wp.x > _SW3: wp.x = -_SW
        elif wp.x < -_SW3: wp.x = _SW
        if wp.y > _SH3: wp.y = -_SH
        elif wp.y < -_SH3: wp.y = _SH

        # Z-crossing logic — identical to enemies
        if (z_old > 0) != (wp.z > 0):
            if wp.z <= 0:
                if abs(wp.x) <= _SW:
                    wp.x -= _SW2 if wp.x >= 0 else -_SW2
            else:
                if abs(wp.x) > _SW:
                    wp.x -= _SW2 if wp.x >= 0 else -_SW2
                if abs(wp.y) > _SH:
                    wp.y -= _SH2 if wp.y >= 0 else -_SH2

        # Visibility — identical to enemies
        wp.visible = abs(wp.x) <= _SW and abs(wp.y) <= _SH
        wp.z = abs(wp.z) if wp.visible else -abs(wp.z)

        # Z boundary — identical to enemies
        if wp.z > (70 << 16) or wp.z < -(70 << 16):
            wp.z += sign(wp.z) * (-5 << 16)

        # Clamp z magnitude to max distance (waypoint stays far)
        if abs(wp.z) < WP_Z:
            wp.z = WP_Z if wp.z > 0 else -WP_Z

    def check_reached(self, wp):
        """Check if player is heading directly at waypoint (x/y near center)."""
        return wp.visible and abs(wp.x) < WP_REACH and abs(wp.y) < WP_REACH

    def is_heading_towards(self, wp, player_angle, player_speed):
        """Check if player is heading towards waypoint.
        True when waypoint is in front and roughly centered."""
        return wp.z > 0 and player_speed > 0 and abs(wp.x) < _SW

    def add_kill(self):
        self.kills += 1

    def tick_survive(self, heading_towards):
        """Add one frame of survival time if heading towards waypoint."""
        if heading_towards:
            self.survive_ticks += 1

    def check_objectives(self, wp):
        """Check if all objectives for current waypoint are met."""
        if wp.obj_kills > 0 and self.kills < wp.obj_kills:
            return False
        if wp.obj_time > 0:
            survived_sec = self.survive_ticks // PC.FPS
            if survived_sec < wp.obj_time:
                return False
        if wp.obj_reach and not self.reached:
            return False
        return True

    def advance(self):
        """Advance to next waypoint. Returns True if more waypoints remain."""
        self.current_idx += 1
        self.kills = 0
        self.survive_ticks = 0
        self.reached = False
        self.wp_complete = False
        return self.current_idx < self.total

    def get_status_text(self):
        """Get compact HUD status string."""
        wp = self.get_current()
        if not wp:
            return "DONE"
        parts = []
        parts.append(f"WP{self.current_idx+1}/{self.total}")
        if wp.obj_kills > 0:
            parts.append(f"K{self.kills}/{wp.obj_kills}")
        if wp.obj_time > 0:
            survived = self.survive_ticks // PC.FPS
            remaining = max(0, wp.obj_time - survived)
            parts.append(f"T{remaining}")
        if wp.obj_reach:
            parts.append("OK" if self.reached else ">>")
        if self.wp_complete:
            return parts[0] + " CLEAR"
        return " ".join(parts)

    def get_config_for_waypoint(self, wp):
        """Build mission config dict from waypoint data."""
        result = {
            "type": wp.type,
            "difficulty": wp.difficulty,
            "enemies": wp.enemies,
            "asteroids": wp.asteroids,
            "front": wp.front,
            "behind": wp.behind
        }
        if wp.enemy_types is not None: result["enemy_types"] = wp.enemy_types
        return result


def draw_waypoint_3d(wp, roll_angle=0):
    """Draw waypoint marker as a fixed-size cross in 3D space.
    Z-rotation applied here as visual-only transform (not to world coords)."""
    if not wp.visible or wp.z <= (1 << 16):
        return
    cx = project(wp.x, wp.z, PC.CENTER_X, 0)
    cy = project(wp.y, wp.z, PC.CENTER_Y, 0)
    if roll_angle != 0:
        dx = (cx - PC.CENTER_X) << 16
        dy = (cy - PC.CENTER_Y) << 16
        cx = PC.CENTER_X + (rotate_z_x(dx, dy, roll_angle) >> 16)
        cy = PC.CENTER_Y + (rotate_z_y(dx, dy, roll_angle) >> 16)
    sz = WP_CROSS_SZ
    if -sz < cx < PC.WIDTH + sz and -sz < cy < PC.HEIGHT + sz:
        display.drawLine(cx - sz, cy, cx + sz, cy, PC.WHITE)
        display.drawLine(cx, cy - sz, cx, cy + sz, PC.WHITE)


def draw_waypoint_radar(wp, hud_fb):
    """Draw waypoint on radar — identical to enemy radar rendering."""
    zd = abs(wp.z) + 1
    rd = (zd >> 10) + 1
    rd = (rd + zd // rd) >> 1
    rd = (rd + zd // rd) >> 1
    rd = (rd + zd // rd) >> 1
    ra = ((wp.x * 6554) >> 32) - 256
    x = (((rd << 8) * fpcos(ra)) >> 32) + 7
    y = (((rd << 8) * fpsin(ra)) >> 32) + 7
    height = (wp.y >> 16) // 700
    color = PC.WHITE
    if IS_THUMBY_COLOR:
        x += 2
        y += 2
        hud_fb.rect(x, y, 3, 3, color, True)
        if height < 0:
            hud_fb.rect(x + 1, y + height, 2, abs(height), color, True)
        else:
            hud_fb.rect(x + 1, y, 1, abs(height), color, True)
    else:
        x += PC.RADAR_X
        y += PC.RADAR_Y
        display.drawFilledRectangle(x, y, 3, 3, color)
        if height < 0:
            display.drawFilledRectangle(x + 1, y + height, 1, abs(height), color)
        else:
            display.drawFilledRectangle(x + 1, y, 1, abs(height), color)


def convert_legacy_mission(mission_data):
    """Convert legacy mission format to waypoint format.
    Returns list of waypoint dicts (single waypoint for legacy missions)."""
    if "waypoints" in mission_data:
        return mission_data["waypoints"]
    config = mission_data.get("config", {})
    objectives = mission_data.get("objectives", {})
    result = {
        "position": [0, 0, 45],
        "type": config.get("type", "mixed"),
        "difficulty": config.get("difficulty", 1),
        "enemies": config.get("enemies", 0),
        "asteroids": config.get("asteroids", 0),
        "front": config.get("front"),
        "behind": config.get("behind"),
        "objectives": objectives
    }
    et = config.get("enemy_types")
    if et: result["enemy_types"] = et
    return [result]
