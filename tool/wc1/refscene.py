"""Reference interpreter for MIDGAME scene animations.

This is a headless port of the original interpreter, verbatim in its
semantics, on the UNSCALED disk data:

    LoadSceneAnimationResources  wc1-re src/logic.c:2128 (0x424D00)
    FindSceneAnimationCommand    wc1-re src/logic.c:2234 (0x424DA0)
    SceneAnimationGoalReached    wc1-re src/logic.c:2275 (0x424EA0)
    UpdateSceneAnimationObject   wc1-re src/logic.c:2291 (0x424EF0)
    PlaySceneAnimation           wc1-re src/logic.c:2592 (0x425500)

It exists twice on purpose: the converter runs it to learn which shape
frames an animation actually draws (so only those are converted), and
`tool/wc1_scene.py` runs it against the device interpreter to check that
every object's position agrees at every step (scaled to device pixels).

A "step" here is one pass of the PlaySceneAnimation inner loop, which
the original runs once per display frame; the ThumbyColor port runs one
step per 62 ms (docs/06).
"""

import struct

DEFS_STRIDE = 0x36


def read_disk_objects(defs):
    """LoadSceneAnimationResources: per-animation object count at defs+0,
    the first bytecode stream at defs + diskObjects[0].scriptOffset, the
    table in between. Only the 16-bit fields are read; the 4-byte pointer
    slots are runtime scratch, never copied (logic.c:2192-2193)."""
    per = struct.unpack_from('<h', defs, 0)[0]
    # diskObjects[0] starts at defs+2, its scriptOffset field at defs+4
    # (logic.c:2171,2176)
    first = struct.unpack_from('<h', defs, 4)[0]
    table_size = first - 2
    count = table_size // DEFS_STRIDE
    objects = []
    for i in range(count):
        b = 2 + i * DEFS_STRIDE
        objects.append({
            'layer': struct.unpack_from('<b', defs, b)[0],
            'scriptOffset': struct.unpack_from('<h', defs, b + 2)[0],
            'goalFlags': struct.unpack_from('<H', defs, b + 0x10)[0],
            'delay': struct.unpack_from('<h', defs, b + 0x12)[0],
            'x': struct.unpack_from('<h', defs, b + 0x18)[0],
            'y': struct.unpack_from('<h', defs, b + 0x1A)[0],
            'rotation': struct.unpack_from('<h', defs, b + 0x1C)[0],
            'scale': struct.unpack_from('<h', defs, b + 0x1E)[0],
            'frame': struct.unpack_from('<h', defs, b + 0x20)[0],
            'deltaX': struct.unpack_from('<h', defs, b + 0x22)[0],
            'deltaY': struct.unpack_from('<h', defs, b + 0x24)[0],
            'deltaRotation': struct.unpack_from('<h', defs, b + 0x26)[0],
            'deltaScale': struct.unpack_from('<h', defs, b + 0x28)[0],
            'deltaFrame': struct.unpack_from('<h', defs, b + 0x2A)[0],
            'goalX': struct.unpack_from('<h', defs, b + 0x2C)[0],
            'goalY': struct.unpack_from('<h', defs, b + 0x2E)[0],
            'goalRotation': struct.unpack_from('<h', defs, b + 0x30)[0],
            'goalScale': struct.unpack_from('<h', defs, b + 0x32)[0],
            'goalFrame': struct.unpack_from('<h', defs, b + 0x34)[0],
            'scriptStart': None,
            'scriptCursor': None,
            # The runtime pointer slots are cleared by the allocation and
            # never copied from the file (logic.c:2192-2193); PlaySceneAnimation
            # rebinds scriptStart/scriptCursor per call (logic.c:2623-2625)
            # but never touches repeatCursor. Offset 0 stands for the NULL
            # the original would hold.
            'repeatCursor': 0,
        })
    return per, count, objects


def find_command(script, pos, command):
    """FindSceneAnimationCommand verbatim (logic.c:2234). `script` is the
    whole definition packet, `pos` a byte offset inside it; returns the
    offset of the command byte, or None at the terminating 0 byte."""
    end = len(script)
    while pos < end and script[pos] != 0:
        opcode = script[pos]
        pos += 1
        if opcode == command:
            return pos - 1
        if opcode in (0x41, 0x4C, 0x51):          # 'A' 'L' 'Q'
            pos += 1                               # the property byte
            pos += 2                               # ... and the value
        elif opcode in (0x42, 0x47, 0x4A, 0x52, 0x57):   # B G J R W
            pos += 2
        elif opcode == 0x44:                       # 'D': until -1
            while pos < end and script[pos] != 0xFF:
                pos += 1
            pos += 1
        elif opcode in (0x45, 0x50, 0x53):         # E P S
            pos += 1
        elif opcode == 0x58:                       # 'X'
            pos += 10
    return None


def goal_reached(delta, current, goal):
    """SceneAnimationGoalReached verbatim (logic.c:2275)."""
    if delta < 0:
        return 1 if current <= goal else 0
    if delta > 0:
        return 1 if current >= goal else 0
    return 1 if current == goal else 0


def _rotation_wrap(r):
    """The two wrap expressions inside the 'R' property (logic.c:2338)."""
    if r < 0:
        r = (((0x167 - r) & 0xFFFF) // 0x168) * 0x168 + r
    if r >= 0x168:
        r = r - ((r & 0xFFFF) // 0x168) * 0x168
    return r


def update_object(defs, objects, i, n_frame_skip, draw, state):
    """UpdateSceneAnimationObject verbatim (logic.c:2291).

    objects[i] is mutated in place. `draw(layer, frame, x, y)` is called
    for every frame the original would have drawn with the current
    nFrameSkipCounter guard; `state` carries the two globals
    (delayFrames, waitCommand) set by 'W'. Returns the object's
    contribution to `complete`.
    """
    obj = objects[i]
    complete = 0
    delay = obj['delay']
    stop = 0
    cursor = obj['repeatCursor'] if delay != 0 else obj['scriptCursor']

    while defs[cursor] != 0 and stop == 0:
        opcode = defs[cursor]
        cursor += 1
        if opcode == 0x41:                          # 'A' adjust
            prop = defs[cursor]; cursor += 1
            value = struct.unpack_from('<h', defs, cursor)[0]; cursor += 2
            if prop == 0x46:                        # 'F'
                obj['frame'] = obj['frame'] + value
                obj['deltaFrame'] = value
            elif prop == 0x52:                      # 'R'
                obj['rotation'] = obj['rotation'] + value
                obj['deltaRotation'] = value
                obj['rotation'] = _rotation_wrap(obj['rotation'])
            elif prop == 0x53:                      # 'S'
                obj['scale'] = obj['scale'] + value
                obj['deltaScale'] = value
                if obj['scale'] < 0x40:
                    obj['scale'] = 0x40
                elif obj['scale'] > 0x1FFF:
                    obj['scale'] = 0x1FFF
            elif prop == 0x54:                      # 'T' - local delay
                delay = delay + value
            elif prop == 0x58:                      # 'X'
                obj['x'] = obj['x'] + value
                obj['deltaX'] = value
            elif prop == 0x59:                      # 'Y'
                obj['y'] = obj['y'] + value
                obj['deltaY'] = value
        elif opcode == 0x42:                        # 'B' label
            cursor += 2
        elif opcode == 0x44:                        # 'D' repeat group
            command_start = cursor - 1
            obj['repeatCursor'] = command_start
            x_offset = 0
            layer = obj['layer']
            frame = defs[cursor]; cursor += 1
            while frame != 0xFF:
                if layer != 2 and n_frame_skip <= 0:
                    draw(layer, frame & 0xFF,
                         obj['x'] + x_offset, obj['y'])
                if layer == 0:
                    x_offset = x_offset + 320
                frame = defs[cursor]; cursor += 1
            stop += 1
        elif opcode == 0x45:                        # 'E' end group
            command_start = cursor - 1
            x_offset = 0
            layer = obj['layer']
            complete = 1
            frame = defs[cursor]; cursor += 1
            while frame != 0xFF:
                if layer != 2 and n_frame_skip <= 0:
                    draw(layer, frame & 0xFF,
                         obj['x'] + x_offset, obj['y'])
                x_offset = x_offset + 320
                frame = defs[cursor]; cursor += 1
            cursor = command_start
            stop += 1
        elif opcode in (0x47, 0x4A):                # 'G' goto / 'J' jump
            if opcode == 0x4A:
                stop += 1
            label_number = struct.unpack_from('<h', defs, cursor)[0]
            label = obj['scriptStart']
            while True:
                label = find_command(defs, label, 0x42)   # 'B'
                if label is None:
                    raise ValueError('label %d not found' % label_number)
                label += 1
                value = struct.unpack_from('<h', defs, label)[0]
                label += 2
                if value == label_number:
                    break
            cursor = label
        elif opcode == 0x4C:                        # 'L' load
            prop = defs[cursor]; cursor += 1
            value = struct.unpack_from('<h', defs, cursor)[0]; cursor += 2
            if prop == 0x46:
                obj['frame'] = value
            elif prop == 0x52:
                obj['rotation'] = value
                obj['rotation'] = _rotation_wrap(obj['rotation'])
            elif prop == 0x53:
                obj['scale'] = value
                if obj['scale'] < 0x40:
                    obj['scale'] = 0x40
                elif obj['scale'] > 0x1FFF:
                    obj['scale'] = 0x1FFF
            elif prop == 0x54:
                delay = value
            elif prop == 0x58:
                obj['x'] = value
            elif prop == 0x59:
                obj['y'] = value
        elif opcode == 0x50:                        # 'P' stop
            stop += 1
        elif opcode == 0x51:                        # 'Q' goal
            prop = defs[cursor]; cursor += 1
            value = struct.unpack_from('<h', defs, cursor)[0]; cursor += 2
            if prop == 0x46:
                obj['goalFlags'] |= 0x10
                obj['goalFrame'] = value
            elif prop == 0x52:
                obj['goalFlags'] |= 1
                obj['goalRotation'] = value
            elif prop == 0x53:
                obj['goalFlags'] |= 2
                obj['goalScale'] = value
            elif prop == 0x58:
                obj['goalFlags'] |= 4
                obj['goalX'] = value
            elif prop == 0x59:
                obj['goalFlags'] |= 8
                obj['goalY'] = value
        elif opcode == 0x52:                        # 'R' copy another
            per = struct.unpack_from('<h', defs, 0)[0]
            o_set = defs[cursor]; cursor += 1
            o_index = defs[cursor]; cursor += 1
            src = objects[per * o_set + o_index]
            obj['x'] = src['x']
            obj['y'] = src['y']
            obj['rotation'] = src['rotation']
            obj['scale'] = src['scale']
            obj['frame'] = src['frame']
        elif opcode == 0x57:                        # 'W' global wait
            state['delayFrames'] = struct.unpack_from('<h', defs, cursor)[0]
            cursor += 2
            state['waitCommand'] = 1
        elif opcode == 0x58:                        # 'X' load all
            obj['x'] = struct.unpack_from('<h', defs, cursor)[0]
            obj['y'] = struct.unpack_from('<h', defs, cursor + 2)[0]
            obj['rotation'] = struct.unpack_from('<h', defs, cursor + 4)[0]
            obj['scale'] = struct.unpack_from('<h', defs, cursor + 6)[0]
            obj['frame'] = struct.unpack_from('<h', defs, cursor + 8)[0]
            cursor += 10

    # The persistence order is deliberate: with an old delay the cursor
    # and the goal test are both skipped (logic.c:2562-2565), so the
    # group under repeatCursor just re-runs and holds the picture.
    if obj['delay'] != 0:
        obj['delay'] -= 1
        return 0
    obj['scriptCursor'] = cursor
    obj['delay'] = delay
    goal_flags = obj['goalFlags']
    if complete == 0 and goal_flags != 0:
        if goal_flags & 0x10:
            complete |= goal_reached(obj['deltaFrame'], obj['frame'],
                                     obj['goalFrame'])
        if goal_flags & 4:
            complete |= goal_reached(obj['deltaX'], obj['x'], obj['goalX'])
        if goal_flags & 8:
            complete |= goal_reached(obj['deltaY'], obj['y'], obj['goalY'])
        if goal_flags & 2:
            complete |= goal_reached(obj['deltaScale'], obj['scale'],
                                     obj['goalScale'])
        if goal_flags & 1:
            complete |= goal_reached(obj['deltaRotation'], obj['rotation'],
                                     obj['goalRotation'])
    return complete


class RefAnimation:
    """One PlaySceneAnimation call (logic.c:2592), stepped by hand."""

    def __init__(self, defs, objects, animation):
        self.defs = defs
        self.objects = objects          # the whole variant table: 'R'
        # copies x/y/rotation/scale/frame from objects of the *other*
        # animations (logic.c:2515-2525), so those must stay reachable.
        per = struct.unpack_from('<h', defs, 0)[0]
        self.lo = animation * per
        self.hi = self.lo + per
        # PlaySceneAnimation rebinds only scriptStart/scriptCursor on every
        # call (logic.c:2616-2627). Delay, repeatCursor, positions, frame,
        # scale, rotation, deltas and goals all persist - including across a
        # replay of the same animation number, which the scene packets do
        # pervasively (tool/wc1_scene probe). A delayed object therefore
        # continues its held group from the persisted repeatCursor instead of
        # restarting from a cleared state.
        for obj in self.objects[self.lo:self.hi]:
            obj['scriptStart'] = obj['scriptOffset']
            obj['scriptCursor'] = obj['scriptStart']
        self.state = {'delayFrames': -1, 'waitCommand': 0}
        self.complete = 0
        self.frame_skip = 1
        self.draws = []            # (layer, frame, x, y) this step
        self.finished = False

    def _anim(self):
        return [(o['x'], o['y'], o['scale'])
                for o in self.objects[self.lo:self.hi]]

    def step(self, draw=None):
        """One pass of the inner do-loop. `draw` is called for every
        frame the original would draw this pass."""
        self.draws = []
        def _draw(layer, frame, x, y):
            if draw is not None:
                draw(layer, frame, x, y)
        self.frame_skip -= 1
        for i in range(self.lo, self.hi):
            self.complete |= update_object(
                self.defs, self.objects, i, self.frame_skip, _draw,
                self.state)
        if self.state['delayFrames'] != -1:
            if self.state['delayFrames'] != 0:
                self.state['delayFrames'] -= 1
            else:
                self.complete += 1
        if self.frame_skip == 0:
            self.frame_skip = 1
        if self.complete != 0:
            self.finished = True
        return self.draws, self._anim()

    def skip(self):
        """The Esc fast-forward: run objects without drawing until the
        wait command is gone or the animation is complete, then cut the
        global wait to zero (logic.c:2663-2681)."""
        while self.complete == 0 and self.state['waitCommand'] == 0:
            for i in range(self.lo, self.hi):
                self.complete |= update_object(
                    self.defs, self.objects, i, 2, lambda *a: None,
                    self.state)
        self.state['delayFrames'] = 0


def load_variant(defs):
    """Everything the reference needs from one definition section."""
    per, count, objects = read_disk_objects(defs)
    return per, count, objects
