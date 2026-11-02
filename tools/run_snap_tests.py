#!/usr/bin/env python3
"""Render test: runs the port on ZX snapshots in the console emulator and compares the frame buffer.

For each snapshot: generate NESNAP.MAC / NEREF.MAC (tools/conv_snap.py) in a temporary copy of the
project, assemble and link it, put NEARTH.SAV on a copy of x-ukncbtl/sys1002ex.dsk (STARTS.COM runs
it), boot that disk in x-ukncbtl-debugger/ukncbtldebug.exe, press STOP and read the line
"Different bytes: N  first at: M" printed by the test program (NECORE.MAC).
A screenshot of the game area is saved to x-test/<snapshot>.png.

The test build is assembled with TESTREF=1 (NEREF.MAC and the comparison are not in the normal build).

Usage: python tools/run_snap_tests.py [-d SNAPDIR] [snapshot.sna ...]
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SNAPDIR = r'D:\Work\MyProjects-old\netherearth\NE maps sna'
RT11DSK = r'C:\bin\rt11dsk.exe'
DEBUGGER_DIR = os.path.join(ROOT, 'x-ukncbtl-debugger')
SYSTEM_DISK = os.path.join(ROOT, 'x-ukncbtl', 'sys1002ex.dsk')
OUTDIR = os.path.join(ROOT, 'x-test')

# Boot sequence: ROM boot menu, disk 1, RT-11 boot with STARTS.COM, the program runs the test and
# waits for STOP. Frames: 50 = 1 second of emulated time.
SCRIPT = '\n'.join([
    'disk1 attach test.dsk',
    'reset',
    'cf200',
    'k 1',
    'cf50',
    'k ENTER',
    'cf600',
    'cf600',                    # the program is running: the start (the comparison with the original, the checks) takes about 20 s
    'screen shot.png',
    'kd STOP',                  # the program exits and prints the result
    'cf30',                     # the game loop looks at the keys once per cycle (0.2 s): hold STOP longer
    'ku STOP',
    'cf400',                    # the PPU needs up to 25 ticks for a pass, then the result is printed
    'screentext',
    'q',
]) + '\n'


def run(cmd, cwd, what):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit('%s failed:\n%s%s' % (what, p.stdout, p.stderr))
    return p.stdout


def build(workdir, snapshot, define='TESTREF=1'):
    for f in glob.glob(os.path.join(ROOT, '*.MAC')):
        shutil.copy(f, workdir)
    run([sys.executable, os.path.join(ROOT, 'tools', 'conv_snap.py'), snapshot,
         '-o', 'NESNAP.MAC', '--ref', 'NEREF.MAC'], workdir, 'conv_snap')
    macro11 = os.path.join(ROOT, 'tools', 'macro11.exe')
    pclink11 = os.path.join(ROOT, 'tools', 'pclink11.exe')
    run([macro11, 'NEARTH.MAC', '-l', 'NEARTH.lst', '-o', 'NEARTH.obj', '-rt11', '-se',
         '-yus', '-ysl', '32', '-s', define, '-s', 'NOMENU=1'], workdir, 'macro11')
    with open(os.path.join(workdir, 'NEARTH.lst'), errors='replace') as f:
        errors = [l.rstrip() for l in f if re.match(r'^[ABDEILMNOPQRTUZ*] ', l)]
    if errors:
        raise SystemExit('assembly errors:\n' + '\n'.join(errors[:20]))
    run([pclink11, 'NEARTH.obj', '/EXECUTE:NEARTH.SAV'], workdir, 'pclink11')


def symbols(lst_path):
    """All symbols from the symbol table of a listing: {NAME: value}."""
    syms = {}
    with open(lst_path, errors='replace') as f:
        for line in f:
            for m in re.finditer(r'([A-Z0-9_$.]+)\s*=\s+([0-7]{6})(?![0-9.])', line):
                syms[m.group(1)] = int(m.group(2), 8)
    return syms


def check_layout(snapshot):
    """NESNAP.MAC (data) and the layout in NEGAME.MAC must have the same labels at the same offsets."""
    with tempfile.TemporaryDirectory(prefix='nelayout_') as workdir:
        build(workdir, snapshot)
        with open(os.path.join(workdir, 'NESNAP.MAC')) as f:
            names = {m.group(1).upper() for m in re.finditer(r'^([A-Za-z0-9_]+):', f.read(), re.M)}
        a = symbols(os.path.join(workdir, 'NEARTH.lst'))
        run([os.path.join(ROOT, 'tools', 'macro11.exe'), 'NEARTH.MAC', '-l', 'NOSNAP.lst', '-o', 'NOSNAP.obj',
             '-rt11', '-se', '-yus', '-ysl', '32', '-s', 'NOSNAP=1'], workdir, 'macro11 (layout)')
        b = symbols(os.path.join(workdir, 'NOSNAP.lst'))
    names |= {'GSEND'}
    ra = {k: a[k] - a['GSTATE'] for k in names if k in a}
    rb = {k: b[k] - b['GSTATE'] for k in names if k in b}
    ra['GS_SIZE'], rb['GS_SIZE'] = a['GS_SIZE'], b['GS_SIZE']
    missing = sorted(n for n in names if n not in b)
    diff = sorted(k for k in ra if ra[k] != rb.get(k))
    if missing or diff:
        raise SystemExit('state layout of NESNAP.MAC differs from NEGAME.MAC: missing %s, different %s' % (
            missing, diff))
    return len(ra)


def make_disk(workdir):
    shutil.copy(SYSTEM_DISK, os.path.join(workdir, 'test.dsk'))
    run([RT11DSK, 'a', 'test.dsk', 'NEARTH.SAV'], workdir, 'rt11dsk')


def run_emulator(workdir, script=SCRIPT):
    shutil.copy(os.path.join(DEBUGGER_DIR, 'uknc_rom.bin'), workdir)
    p = subprocess.run([os.path.join(DEBUGGER_DIR, 'ukncbtldebug.exe')], cwd=workdir,
                       input=script.encode('ascii'), capture_output=True, timeout=600)
    return p.stdout.decode('utf-16-le', errors='replace').replace('\r', '')


def z80_random_checksum(snapshot, n=1000):
    """The Z80 generator Ld358_random from the seed of the snapshot: sum = sum * 2 + number, 16 bits."""
    import conv_snap
    mem = conv_snap.load_snapshot(snapshot)
    seed = list(mem[0xFD00:0xFD04])
    idx = mem[conv_snap.RANDOM_INDEX]
    total = 0
    for _ in range(n):
        a = ((seed[0] & 72) + 56) & 0xFF
        carry = (a >> 6) & 1            # the carry of the second rlca
        for i in (3, 2, 1, 0):
            seed[i], carry = ((seed[i] << 1) | carry) & 0xFF, seed[i] >> 7
        idx = seed[idx] & 3
        total = ((total << 1) + seed[idx]) & 0xFFFF
    return total


def check_newgame(snapshot):
    """The state of a new game built by the port (Lnew_game) against the model of the original."""
    import conv_map
    tables, order = conv_map.read_tables(os.path.join(conv_map.DEFAULT_DIR, conv_map.CODE_FILE))
    expected = [conv_map.fold(p) for p in conv_map.new_game_state(tables, order)]
    with tempfile.TemporaryDirectory(prefix='nenew_') as workdir:
        build(workdir, snapshot, define='TESTNEW=1')
        make_disk(workdir)
        out = run_emulator(workdir)
    m = re.search(r'New game checksums:\s*(\d+) (\d+) (\d+) (\d+)', out)
    if not m:
        raise SystemExit('new game: no result\n' + out)
    got = [int(x) for x in m.groups()]
    if got != expected:
        names = ('map', 'buildings', 'decorations', 'counters')
        raise SystemExit('new game differs from the model of the original: ' +
                         ', '.join(n for n, a, b in zip(names, got, expected) if a != b))
    return got


def test_one(snapshot):
    name = os.path.splitext(os.path.basename(snapshot))[0]
    with tempfile.TemporaryDirectory(prefix='netest_') as workdir:
        build(workdir, snapshot)
        make_disk(workdir)
        out = run_emulator(workdir)
        shot = os.path.join(workdir, 'shot.png')
        if os.path.exists(shot):
            os.makedirs(OUTDIR, exist_ok=True)
            shutil.copy(shot, os.path.join(OUTDIR, name + '.png'))
    m = re.search(r'Different bytes:\s*(\d+)\s+first at:\s*(\d+)', out)
    r = re.search(r'Radar different bytes:\s*(\d+)\s+first at:\s*(\d+)', out)
    q = re.search(r'Random checksum:\s*(\d+)', out)
    if not m or not r or not q:
        return name, None, None, None, None, None, out
    rnd_bad = int(q.group(1)) != z80_random_checksum(snapshot)
    return name, int(m.group(1)), int(m.group(2)), int(r.group(1)), int(r.group(2)), rnd_bad, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapshots', nargs='*', help='snapshot files (default: all in SNAPDIR)')
    ap.add_argument('-d', '--snapdir', default=DEFAULT_SNAPDIR)
    ap.add_argument('-v', '--verbose', action='store_true', help='print the emulator screen text on failures')
    args = ap.parse_args()

    snaps = args.snapshots or sorted(glob.glob(os.path.join(args.snapdir, '*.sna')) +
                                     glob.glob(os.path.join(args.snapdir, '*.z80')))
    if not snaps:
        raise SystemExit('no snapshots found')
    print('state layout of NESNAP.MAC = NEGAME.MAC: OK (%d symbols)' % check_layout(snaps[0]))
    check_newgame(snaps[0])
    print('new game = the model of the original (map, buildings, decorations, counters): OK')
    bad = 0
    for s in snaps:
        name, diff, first, rdiff, rfirst, rnd_bad, out = test_one(s)
        if diff is None:
            print('%-24s NO RESULT (the program did not print the result)' % name)
            if args.verbose:
                print(out)
            bad += 1
        elif diff or rdiff or rnd_bad:
            msg = []
            if rnd_bad:
                msg.append('random numbers differ from the Z80 generator')
            if diff:
                msg.append('frame: %d different bytes, first at %d (row %d, column %d)' % (
                    diff, first, first // 20, first % 20))
            if rdiff:
                msg.append('radar: %d different bytes, first at %d (view %d, row %d, byte %d)' % (
                    rdiff, rfirst, rfirst // 256 + 1, rfirst % 256 // 16, rfirst % 16))
            print('%-24s FAIL: %s' % (name, '; '.join(msg)))
            bad += 1
        else:
            print('%-24s OK' % name)
    print('%d of %d failed' % (bad, len(snaps)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
