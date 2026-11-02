#!/usr/bin/env python3
"""Convert Nether Earth isometric graphics from the Z80 disassembly to MACRO-11 (NESPRT.MAC).

Sources (same directory): netherearth-annotated-data.asm (graphics) and
netherearth-annotated.asm (pointer tables, diagonal patterns).

Sprite format is kept as in the original: height (pixels), width (bytes), then
height*width pairs of bytes (AND mask, OR data), rows stored bottom-up.
Every byte is bit-reversed because UKNC pixel order is bit 0 = leftmost
(ZX: bit 7 = leftmost); use --keep-bits to disable. The 4-pixel-shifted copies
are separate sprites in the original and are converted as they are.

The pointer table ISOPTR keeps the original memory layout: 44 entries of
Ld6e8_additional_isometric_graphic_pointers followed by 58 entries of
Ld740_isometric_graphic_pointers (index 44 = first piece graphic), so the
original graphic indices work unchanged. Pointers are 16-bit addresses.
"""
import argparse
import os
import re
import sys

DEFAULT_DIR = r'D:\Work\MyProjects-old\netherearth\netherearth-disassembly-main'
DATA_FILE = 'netherearth-annotated-data.asm'
CODE_FILE = 'netherearth-annotated.asm'
SPRITE_LABEL = re.compile(r'^(L[0-9a-f]{4}_iso_(?:additional_)?graphic_\d+):')


def parse_db(line):
    s = line.split(';')[0].strip()
    m = re.match(r'^db\s+(.*)$', s, re.I)
    if not m:
        return None
    out = []
    for tok in m.group(1).split(','):
        tok = tok.strip()
        out.append(int(tok[1:], 16) if tok.startswith('#') else int(tok, 0))
    return out


def read_sprites(path):
    """Returns list of (label, bytes) in file order."""
    sprites = []
    cur = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = SPRITE_LABEL.match(line)
            if m:
                cur = (m.group(1), [])
                sprites.append(cur)
                continue
            if re.match(r'^\w+:', line):
                cur = None             # some other label (font, alias): not a sprite
                continue
            if cur is not None:
                d = parse_db(line)
                if d is not None:
                    cur[1].extend(d)
    return sprites


def read_pointers(path):
    """Returns (additional, main) lists of sprite labels."""
    tables = {'Ld6e8_additional_isometric_graphic_pointers': [],
              'Ld740_isometric_graphic_pointers': []}
    cur = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^(\w+):', line)
            if m:
                cur = tables.get(m.group(1))
                continue
            if cur is not None:
                s = line.split(';')[0].strip()
                m = re.match(r'^dw\s+(\w+)$', s)
                if m:
                    cur.append(m.group(1))
                elif s:
                    cur = None
    a = tables['Ld6e8_additional_isometric_graphic_pointers']
    b = tables['Ld740_isometric_graphic_pointers']
    if len(a) != 44 or len(b) != 58:
        raise SystemExit('unexpected pointer table sizes %d, %d' % (len(a), len(b)))
    return a, b


def read_labeled_bytes(path, label):
    rows = []
    on = False
    with open(path, encoding='utf-8') as f:
        for line in f:
            if re.match(r'^\w+:', line):
                if on:
                    break
                on = line.startswith(label + ':')
                continue
            if on:
                d = parse_db(line)
                if d is not None:
                    rows.extend(d)
    if not rows:
        raise SystemExit('label %s not found' % label)
    return rows


def rev8(b):
    return int('{:08b}'.format(b)[::-1], 2)


def ascii_dump(name, data):
    """Print a sprite as text, top row first: '#' = set pixel, ' ' = black, '.' = transparent."""
    h, w = data[0], data[1]
    rows = []
    for y in range(h):
        line = ''
        for x in range(w):
            a, o = data[2 + (y * w + x) * 2], data[3 + (y * w + x) * 2]
            for bit in range(7, -1, -1):
                if (a >> bit) & 1:
                    line += '.'
                else:
                    line += '#' if (o >> bit) & 1 else ' '
        rows.append(line)
    print('%s: height %d, width %d bytes' % (name, h, w))
    for line in reversed(rows):     # stored bottom-up
        print(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('srcdir', nargs='?', default=DEFAULT_DIR, help='directory with the Z80 disassembly')
    ap.add_argument('-o', '--output', default='NESPRT.MAC')
    ap.add_argument('--keep-bits', action='store_true', help='do not reverse bit order')
    ap.add_argument('--dump', metavar='LABEL_OR_INDEX', help='print one sprite as text and exit')
    args = ap.parse_args()

    sprites = read_sprites(os.path.join(args.srcdir, DATA_FILE))
    add, main_ptrs = read_pointers(os.path.join(args.srcdir, CODE_FILE))
    by_label = dict(sprites)
    for label, data in sprites:
        if len(data) < 2 or len(data) != 2 + data[0] * data[1] * 2:
            raise SystemExit('%s: bad size %d' % (label, len(data)))
    for label in add + main_ptrs:
        if label not in by_label:
            raise SystemExit('pointer to unknown sprite ' + label)
    unused = [l for l, _ in sprites if l not in add and l not in main_ptrs]

    if args.dump:
        key = args.dump
        if key.isdigit():
            key = (add + main_ptrs)[int(key)]
        elif key not in by_label:
            key = [l for l in by_label if l.startswith(key)][0]
        ascii_dump(key, by_label[key])
        return

    out = ['; Start of NESPRT.MAC',
           '; Generated by tools/conv_sprites.py from the Z80 disassembly, do not edit.',
           '; Isometric graphics. Sprite = height (lines), width (bytes), then height*width pairs',
           '; of bytes (AND mask, OR data), rows are stored bottom-up. %s' % (
               'Bit 0 = leftmost pixel (ZX bits reversed).' if not args.keep_bits
               else 'ZX bit order (bit 7 = leftmost).'),
           '; Odd entries of each pair are pre-shifted by 4 pixels, as in the original.',
           '',
           'ISOADD = %d.		; Entries in the first (additional graphics) part; piece graphics start here' % len(add),
           'ISOPTR:	; %d pointers: original Ld6e8 table (%d), then Ld740 table (%d)' % (
               len(add) + len(main_ptrs), len(add), len(main_ptrs))]
    for i, label in enumerate(add + main_ptrs):
        out.append('	.WORD	%s	; %d.' % (label, i))
    out.append('')
    total = 0
    for label, data in sprites:
        h, w = data[0], data[1]
        out.append('%s:	.BYTE	%d.,%d.	; height, width' % (label, h, w))
        body = data[2:] if args.keep_bits else [rev8(b) for b in data[2:]]
        for y in range(h):
            row = body[y * w * 2:(y + 1) * w * 2]
            out.append('	.BYTE	' + ','.join('%03o' % b for b in row))
        total += len(data)
    out.append('	.EVEN')
    out.append('')

    # Diagonal patterns used to cut the map corners in the frame buffer
    for label, name in (('Ld6a8_diagonal_pattern1', 'top-left painted, bottom-left empty'),
                        ('Ld6b8_diagonal_pattern2', 'top-left empty, bottom-left painted')):
        d = read_labeled_bytes(os.path.join(args.srcdir, CODE_FILE), label)
        if not args.keep_bits:
            d = [rev8(b) for b in d]
        out.append('%s:	; %s' % (label, name))
        out.append('	.BYTE	' + ','.join('%03o' % b for b in d[:8]))
        out.append('	.BYTE	' + ','.join('%03o' % b for b in d[8:]))
    out.append('')
    out.append('; End of NESPRT.MAC')
    with open(args.output, 'w', encoding='ascii', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
    print('%s: %d sprites, %d bytes of graphics, %d pointers' % (
        args.output, len(sprites), total, len(add) + len(main_ptrs)), file=sys.stderr)
    if unused:
        print('note: sprites not referenced by the tables: ' + ', '.join(unused), file=sys.stderr)


if __name__ == '__main__':
    main()
