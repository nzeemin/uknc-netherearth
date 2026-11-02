#!/usr/bin/env python3
"""Report symbols longer than 32 characters in .MAC files (macro11 -ysl 32 silently truncates them)."""
import glob
import re
import sys

LIMIT = 32
bad = 0
for path in sorted(glob.glob('*.MAC')):
    with open(path, encoding='ascii') as f:
        for n, line in enumerate(f, 1):
            code = line.split(';')[0]
            for name in set(re.findall(r'[A-Za-z_$.][A-Za-z0-9_$.]*', code)):
                if len(name) > LIMIT:
                    print('%s:%d: %s (%d)' % (path, n, name, len(name)))
                    bad += 1
sys.exit(1 if bad else 0)
