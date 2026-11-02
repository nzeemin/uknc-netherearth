#!/usr/bin/env python3
"""Speed of the renderer on the CPU, in the console emulator (with the PPU running at the same time).

For each snapshot: builds the project with TESTSPEED=1 (NECORE.MAC: BENCH renders 20 frames of the
blank map, then 20 whole frames, counting the 50Hz ticks passed by the PPU), runs it, waits for the
benchmark, presses STOP and reads the result from the screen.

Usage: python tools/run_speed_test.py [-d SNAPDIR] [snapshot.sna ...]
"""
import argparse
import glob
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_snap_tests as t

N = 20
SCRIPT = '\n'.join([
    'disk1 attach test.dsk', 'reset', 'cf200', 'k 1', 'cf50', 'k ENTER', 'cf600',
    'cf%d' % 3000,                  # the benchmark runs (about a minute of emulated time)
    'kd STOP', 'cf10', 'ku STOP', 'cf150',
    'screentext', 'q',
]) + '\n'


def speed(snapshot):
    with tempfile.TemporaryDirectory(prefix='nespeed_') as workdir:
        t.build(workdir, snapshot, define='TESTSPEED=1')
        t.make_disk(workdir)
        out = t.run_emulator(workdir, SCRIPT)
    m = re.search(r'blank map\s+(\d+),\s+whole frame\s+(\d+)', out)
    if not m:
        return None, None, out
    return int(m.group(1)), int(m.group(2)), out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapshots', nargs='*')
    ap.add_argument('-d', '--snapdir', default=t.DEFAULT_SNAPDIR)
    args = ap.parse_args()
    snaps = args.snapshots or sorted(glob.glob(os.path.join(args.snapdir, '*.sna')))
    for s in snaps:
        name = os.path.splitext(os.path.basename(s))[0]
        blank, frame, out = speed(s)
        if blank is None:
            print('%-24s NO RESULT' % name)
            print(out)
            continue
        print('%-24s blank map %5.0f ms, whole frame %5.0f ms (map %5.0f ms)' % (
            name, blank * 20. / N, frame * 20. / N, (frame - blank) * 20. / N))


if __name__ == '__main__':
    main()
