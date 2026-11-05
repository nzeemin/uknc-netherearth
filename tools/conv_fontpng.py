# Makes the bitmaps of NEFONT.MAC from nefont.png and rewrites NEFONT.MAC (the comments and everything else stay).
# nefont.png: 151x61, a grey margin of 4 pixels, 16 glyphs in a row, 6 rows, glyph 8x8, one grey line between the glyphs
# (pitch 9). Rows 0..3: ASCII 32..95 (FONT), rows 4..5: Cyrillic 224..255 (FONTR). A white pixel (> 127) is a set bit,
# bit 0 = the leftmost pixel, the first byte = the top row.
import os
import re
import sys

from PIL import Image

MARGIN = 4
PITCH = 9
COLS = 16
ROWS = 6
SIZE = (MARGIN * 2 + COLS * PITCH - 1, MARGIN * 2 + ROWS * PITCH - 1)
NASCII = 64
NCYR = 32

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
png = os.path.join(base, 'nefont.png')
mac = os.path.join(base, 'NEFONT.MAC')

im = Image.open(png).convert('L')
if im.size != SIZE:
    sys.exit('nefont.png must be %dx%d, it is %dx%d' % (SIZE + im.size))
px = im.load()


def glyph(n):
    gx = MARGIN + (n % COLS) * PITCH
    gy = MARGIN + (n // COLS) * PITCH
    return [sum(1 << x for x in range(8) if px[gx + x, gy + y] > 127) for y in range(8)]


glyphs = [glyph(n) for n in range(NASCII + NCYR)]

with open(mac, encoding='utf-8', newline='') as f:
    text = f.read()
nl = '\r\n' if '\r\n' in text else '\n'
lines = text.replace('\r\n', '\n').split('\n')
out = []
n = 0
changed = 0
for line in lines:
    m = re.match(r'^((?:[A-Z0-9]+:)?\s*\.BYTE\s+)([0-7]{3}(?:,[0-7]{3}){7})(.*)$', line)
    if m:
        if n >= len(glyphs):
            sys.exit('NEFONT.MAC has more than %d glyph lines' % len(glyphs))
        new = ','.join('%03o' % b for b in glyphs[n])
        if new != m.group(2):
            changed += 1
        line = m.group(1) + new + m.group(3)
        n += 1
    out.append(line)
if n != len(glyphs):
    sys.exit('NEFONT.MAC has %d glyph lines, expected %d' % (n, len(glyphs)))
with open(mac, 'w', encoding='utf-8', newline='') as f:
    f.write(nl.join(out))
print('NEFONT.MAC: %d glyphs, %d changed' % (n, changed))
