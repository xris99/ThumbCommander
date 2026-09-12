#!/usr/bin/env python3
"""
Deploy ThumbCommander (and the thumby_engine it depends on) to a device.

The repo is split into a reusable engine (thumby_engine/) and the game
(games/thumbcommander/). Each hardware target only needs the engine
modules it actually imports, so this tool deploys a per-platform
subset - nothing the target never imports is copied or compiled:

  thumby      : grayscale display + 1-bit cutscenes, no audio
  thumbycolor : RGB565 display + IMA-ADPCM audio + TDL8 cutscenes

Device layout after deployment:

  :/lib/thumby_engine/          (the engine as a package of .mpy files -
                                 a proper folder, never the device root)
  :/Games/ThumbCommander/
      ThumbCommander.py         (entry point on the Thumby - the only .py
                                 on the device: the firmware can only
                                 start .py files, so this is a small shim
                                 that puts the game dir on sys.path
                                 and imports MainGame; the engine
                                 resolves from /lib, a firmware default
                                 path. The ThumbyColor firmware starts
                                 main.py, so the same shim is deployed
                                 under that name there)
      MainGame.mpy              (the real entry module)
      ...                       (every other module as its own .mpy)
      manifest.txt, icon.bmp    (game browser metadata - ThumbyColor
                                 only, copied as-is like main.py)
      assets/                   (one flat directory; the per-platform
                                 subset is selected by extension)

Code deployment:
  * every module is compiled to its own .mpy (mpy-cross has no --pack
    - that flag never existed in any version), and MicroPython imports
    a package folder of .mpy files just as well as a single file; on
    the device all code is bytecode, which is what saves the little
    RAM they have;
  * the only exception is the entry point: the firmware can only
    start .py files, so the shim (main.py in the repo) is copied
    as-is - as ThumbCommander.py on the Thumby, as main.py on the
    ThumbyColor - and everything else (including MainGame.py) is
    compiled;
  * a compile failure fails the whole deploy - there is no .py
    fallback, because .py source costs too much RAM on the devices;
  * the native/viper emitter requires an explicit target architecture,
    given with the '=' syntax (-march=<arch>): armv6m for the Thumby
    (RP2040, Cortex-M0+) and armv7emsp for the ThumbyColor (RP2350,
    the arch verified on the device). A file's plain parts stay
    bytecode, its @micropython.native/@viper parts become machine
    code; if the device ever reports an incompatible arch, use
    --arch rv32imc (the firmware's RISC-V core).

Transport:
  * by default everything is staged under build/<platform>/ (inspect
    it, copy it by hand, or point mpremote at it);
  * with --remote [target] the staged files are pushed via mpremote.

The two targets need different mpy-cross builds: Thumby is compiled
with the repo-local tool/mpy-cross (the system binary does not work
for it), ThumbyColor with the system-wide mpy-cross on PATH.
--mpy-cross overrides the choice for whichever platform is built.
This tool prints the mpy-cross version used per platform.

Usage:
    python3 tool/deploy.py                          # stage+compile all platforms
    python3 tool/deploy.py thumbycolor              # one platform
    python3 tool/deploy.py thumby --no-compile      # plain .py (debug only)
    python3 tool/deploy.py thumbycolor --remote 192.168.1.42
"""

import argparse
import os
import shutil
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two targets need different mpy-cross builds. Thumby only works
# with the repo-local build, so it is kept in the repo (tool/);
# ThumbyColor uses the system-wide mpy-cross on PATH.
LOCAL_MPY_CROSS = os.path.join(REPO_ROOT, 'tool', 'mpy-cross')
DEVICE_GAME_DIR = '/Games/ThumbCommander'
# The engine lives in a proper library folder on the device, not in the
# device root. The firmware's default sys.path includes /lib, so the
# engine resolves from there without any main.py setup.
DEVICE_ENGINE_DIR = '/lib/thumby_engine'

# The one file the firmware runs directly. It can only be a .py, so the
# game ships a small shim (main.py in the repo: game dir on sys.path +
# import MainGame); it is the single file deployed as source,
# everything else is .mpy. The name on the device is platform-specific:
# the Thumby firmware starts ThumbCommander.py, the ThumbyColor starts
# main.py.
GAME_ENTRY = 'main.py'
DEVICE_ENTRY = {
    'thumby': 'ThumbCommander.py',
    'thumbycolor': 'main.py',
}

GAME_DIR = 'games/thumbcommander'

# --- Per-platform manifests -------------------------------------------------
# Engine: only the modules a target actually imports (see the import graph
# of thumby_engine/platform/__init__.py). The pc/ subpackage and audio/pc.py
# exist solely for the CPython target and are never deployed.

ENGINE_COMMON = [
    'thumby_engine/platform/__init__.py',
    'thumby_engine/platform/constants.py',
    'thumby_engine/util/fpmath.py',
    'thumby_engine/util/stream_json.py',
]
ENGINE_THUMBY = [
    'thumby_engine/display/grayscale.py',
    'thumby_engine/cutscene/grayscale.py',
]
ENGINE_THUMBYCOLOR = [
    'thumby_engine/display/color.py',
    'thumby_engine/audio/hardware.py',
    'thumby_engine/cutscene/color.py',
]

GAME_COMMON = [
    GAME_ENTRY,           # shim - deployed as-is (renamed per platform),
                          # never compiled
    'MainGame.py',
    'constants.py',
    'campaign_engine.py',
    'waypoint_system.py',
]
GAME_THUMBY = [
    'intro.py',           # the 1-bit intro animation (timer-driven)
]
GAME_THUMBYCOLOR = [
    'color_enhancements.py',
    'manifest.txt',       # game browser metadata - ThumbyColor only
    'icon.bmp',
]

# One flat assets/ directory in the repo; each platform deploys the
# subset it actually loads (fonts and campaign JSONs are shared, sprite
# and audio files are platform-specific by extension). Runtime state
# (keymap.json, settings.json, campaign_saves.json) lives in the game
# dir root and is created on the device at runtime - not deployed.
ASSETS_DIR = 'assets'

MANIFESTS = {
    'thumby': {
        'engine': ENGINE_COMMON + ENGINE_THUMBY,
        'game': GAME_COMMON + GAME_THUMBY,
    },
    'thumbycolor': {
        'engine': ENGINE_COMMON + ENGINE_THUMBYCOLOR,
        'game': GAME_COMMON + GAME_THUMBYCOLOR,
    },
}


def asset_files_for(platform, names):
    """The per-platform subset of the flat assets/ directory."""
    if platform == 'thumby':
        return [f for f in names
                if f.endswith(('.BIT.bin', '.SHD.bin', '_campaign.json'))
                or f.startswith('font')]
    return [f for f in names
            if f.endswith(('.COL.bin', '.ima', '_campaign.json'))
            or f.startswith('font')]

# mpy-cross -march per target. The native/viper emitter requires an
# explicit arch, and this mpy-cross only accepts the '=' syntax:
# -march=<arch>, not '-march <arch>' (the space form is a usage error).
#   thumby      : RP2040, Cortex-M0+  -> armv6m   (ARMv6-M)
#   thumbycolor : RP2350, Cortex-M33  -> armv7emsp - the arch the device
#                 firmware accepts (verified on the device); use
#                 --arch rv32imc if it ever reports an incompatible
#                 arch (the RP2350's RISC-V core). A single -march
#                 compiles a file's plain parts as bytecode and its
#                 @micropython.native/@viper parts as machine code.
DEFAULT_ARCH = {
    'thumby': 'armv6m',
    'thumbycolor': 'armv7emsp',
}


# --- Helpers ----------------------------------------------------------------

def find_tool(name, override=None):
    """Locate an executable; an explicit path (e.g. --mpy-cross) wins."""
    if override:
        return override if os.path.exists(override) else None
    found = shutil.which(name)
    if found:
        return found
    # Some shells leave a literal '~' in PATH; shutil.which doesn't
    # expand it, so try the expanded entries too.
    for entry in os.environ.get('PATH', '').split(os.pathsep):
        if '~' in entry:
            cand = os.path.join(os.path.expanduser(entry), name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def run(cmd):
    print('  $ ' + ' '.join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f'command failed ({r.returncode}): {" ".join(cmd)}')
    return r


def check_manifest(platform, manifest):
    """Fail early with a clear list of any missing source files."""
    missing = []
    for f in manifest['engine']:
        if not os.path.isfile(os.path.join(REPO_ROOT, f)):
            missing.append(f)
    for f in manifest['game']:
        if not os.path.exists(os.path.join(REPO_ROOT, GAME_DIR, f)):
            missing.append(GAME_DIR + '/' + f)
    if not os.path.isdir(os.path.join(REPO_ROOT, GAME_DIR, ASSETS_DIR)):
        missing.append(GAME_DIR + '/' + ASSETS_DIR)
    if missing:
        print(f'error: missing files for target {platform}:')
        for f in missing:
            print(f'  {f}')
        raise SystemExit(1)


# --- Staging ----------------------------------------------------------------

def stage(platform, manifest, stage_base):
    """Copy the manifest into stage_base/<platform>/ using the device layout."""
    stage_dir = os.path.join(stage_base, platform)
    if os.path.isdir(stage_dir):
        shutil.rmtree(stage_dir)

    # Engine package, staged in the device layout (:/lib/thumby_engine)
    for f in manifest['engine']:
        rel = f[len('thumby_engine/'):]
        dst = os.path.join(stage_dir, 'lib', 'thumby_engine', rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(REPO_ROOT, f), dst)

    # Game modules (the entry shim included - it stays .py, see
    # compile_dir; on the device it is named per platform)
    game_dir = os.path.join(stage_dir, 'Games', 'ThumbCommander')
    os.makedirs(game_dir, exist_ok=True)
    for f in manifest['game']:
        dst_name = DEVICE_ENTRY[platform] if f == GAME_ENTRY else f
        shutil.copy2(os.path.join(REPO_ROOT, GAME_DIR, f),
                     os.path.join(game_dir, dst_name))

    # Assets: the one flat directory, filtered per platform
    asset_src = os.path.join(REPO_ROOT, GAME_DIR, ASSETS_DIR)
    asset_dst = os.path.join(game_dir, ASSETS_DIR)
    os.makedirs(asset_dst, exist_ok=True)
    for f in asset_files_for(platform, os.listdir(asset_src)):
        shutil.copy2(os.path.join(asset_src, f), os.path.join(asset_dst, f))

    n_engine = len(manifest['engine'])
    n_game = len(manifest['game'])
    n_assets = len(os.listdir(asset_dst))
    print(f'[{platform}] staged {n_engine} engine + {n_game} game modules '
          f'+ {n_assets} assets -> {stage_dir}')
    return stage_dir


# --- Compilation -------------------------------------------------------------

def mpy_cross_version(mpy_cross):
    """Return the version line printed by mpy-cross."""
    try:
        out = subprocess.run([mpy_cross, '--version'],
                             capture_output=True, text=True)
        text = (out.stdout or '') + (out.stderr or '')
        return next((l.strip() for l in text.splitlines()
                     if 'MicroPython v' in l or 'emitting mpy' in l),
                    mpy_cross)
    except Exception:
        return mpy_cross


def compile_dir(dirpath, mpy_cross, keep_py, arch, entry=None):
    """Compile every .py under dirpath in place to .mpy.

    The entry file (main.py) is never compiled: the firmware can only
    start .py files, so it stays source. Any other file that fails to
    compile fails the whole deploy - .py source costs too much RAM on
    the devices to be a fallback.
    """
    # '=' syntax: this mpy-cross rejects the space-separated form.
    cmd_arch = ['-march=' + arch] if arch else []
    for root, dirs, files in os.walk(dirpath):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if not f.endswith('.py') or f == entry:
                continue
            src = os.path.join(root, f)
            out = os.path.splitext(src)[0] + '.mpy'
            cmd = [mpy_cross] + cmd_arch + ['-o', out, src]
            print('  $ ' + ' '.join(cmd))
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                if os.path.exists(out):
                    os.remove(out)
                print(f'error: {src} failed to compile:')
                print((r.stderr or r.stdout).strip() or 'unknown error')
                raise SystemExit(1)
            if not keep_py:
                os.remove(src)


# --- Transport ----------------------------------------------------------------

def push_remote(platform, stage_dir, target):
    """Push the staged files to the device with mpremote."""
    tgt = f'--target {target} ' if target else ''
    engine_local = os.path.join(stage_dir, 'lib', 'thumby_engine')
    game_local = os.path.join(stage_dir, 'Games', 'ThumbCommander')
    mpremote = find_tool('mpremote')
    if not mpremote:
        print(f'[{platform}] mpremote not found - staging only. To push by')
        print(f'[{platform}] hand:')
        print(f'[{platform}]   mpremote {tgt}mkdir :/lib')
        print(f'[{platform}]   mpremote {tgt}cp {engine_local} {DEVICE_ENGINE_DIR}')
        print(f'[{platform}]   mpremote {tgt}mkdir :/Games')
        print(f'[{platform}]   mpremote {tgt}cp {game_local} {DEVICE_GAME_DIR}')
        return
    base = [mpremote] + (['--target', target] if target else [])
    run(base + ['mkdir', ':/lib'])
    run(base + ['cp', engine_local, DEVICE_ENGINE_DIR])
    run(base + ['mkdir', ':/Games'])
    run(base + ['mkdir', DEVICE_GAME_DIR])
    run(base + ['cp', game_local, DEVICE_GAME_DIR])
    print(f'[{platform}] pushed to device'
          f'{f" ({target})" if target else ""}')


# --- Main ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='Stage, compile and deploy ThumbCommander per platform.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='examples:\n'
               '  python3 tool/deploy.py\n'
               '  python3 tool/deploy.py thumbycolor --no-compile\n'
               '  python3 tool/deploy.py thumby --remote 192.168.1.42\n')
    ap.add_argument('platform', nargs='?', default='all',
                    choices=['thumby', 'thumbycolor', 'all'],
                    help='target to deploy (default: all)')
    ap.add_argument('--stage', default=os.path.join(REPO_ROOT, 'build'),
                    help='staging base directory (default: <repo>/build)')
    ap.add_argument('--mpy-cross', metavar='PATH',
                    help='path to the mpy-cross binary, overriding the '
                         'per-platform default (tool/mpy-cross for '
                         'thumby, the PATH one for thumbycolor)')
    ap.add_argument('--arch', metavar='ARCH', default=None,
                    help='mpy-cross -march= override (default per target: '
                         'armv6m for thumby, armv7emsp for thumbycolor; '
                         'rv32imc for the RP2350 RISC-V core)')
    ap.add_argument('--no-compile', action='store_true',
                    help='stage plain .py sources instead of .mpy '
                         '(debug only - source costs a lot of RAM on '
                         'the devices)')
    ap.add_argument('--keep-py', action='store_true',
                    help='keep the .py sources next to the compiled .mpy')
    ap.add_argument('--remote', nargs='?', const='default', default=None,
                    metavar='TARGET',
                    help='push to the device via mpremote (optionally with a'
                         ' target such as an IP address)')
    args = ap.parse_args()

    platforms = (['thumby', 'thumbycolor'] if args.platform == 'all'
                 else [args.platform])

    for platform in platforms:
        manifest = MANIFESTS[platform]
        print(f'=== {platform} ===')
        check_manifest(platform, manifest)

        # Per-platform mpy-cross: the two targets need different builds
        # (see LOCAL_MPY_CROSS), so resolve inside the loop.
        mpy_cross = None
        if not args.no_compile:
            if args.mpy_cross:
                mpy_cross = find_tool('mpy-cross', args.mpy_cross)
                if not mpy_cross:
                    raise SystemExit(
                        f'error: --mpy-cross path not found: {args.mpy_cross}')
            elif platform == 'thumby':
                if not (os.path.isfile(LOCAL_MPY_CROSS)
                        and os.access(LOCAL_MPY_CROSS, os.X_OK)):
                    raise SystemExit(
                        f'error: repo-local mpy-cross not found at '
                        f'{LOCAL_MPY_CROSS} (Thumby needs the local '
                        f'build, the system one does not work for it)')
                mpy_cross = LOCAL_MPY_CROSS
            else:
                mpy_cross = find_tool('mpy-cross')
                if not mpy_cross:
                    raise SystemExit(
                        'error: system mpy-cross not found on PATH - '
                        'install a recent one (pip install mpy-cross) '
                        'or pass --mpy-cross PATH. '
                        '--no-compile is for quick debugging only: '
                        'plain .py source costs too much RAM on the '
                        'devices.')
            print(mpy_cross_version(mpy_cross))
        arch = args.arch if args.arch is not None else DEFAULT_ARCH[platform]
        stage_dir = stage(platform, manifest, args.stage)
        if mpy_cross:
            compile_dir(os.path.join(stage_dir, 'lib', 'thumby_engine'),
                        mpy_cross, args.keep_py, arch)
            compile_dir(os.path.join(stage_dir, 'Games', 'ThumbCommander'),
                        mpy_cross, args.keep_py, arch,
                        entry=DEVICE_ENTRY[platform])
        else:
            print(f'[{platform}] not compiled (--no-compile, debug only)')
        if args.remote:
            target = None if args.remote == 'default' else args.remote
            push_remote(platform, stage_dir, target)
        print()


if __name__ == '__main__':
    main()
