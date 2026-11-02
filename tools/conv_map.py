#!/usr/bin/env python3
"""Convert the static map descriptors of Nether Earth from the Z80 disassembly to MACRO-11 (NEMAP.MAC).

The game has one map. At the start of a game Lbc6f_initialize_map builds it from these tables:
  Lbda9_map_elements_part1, Lbe79_map_elements_part2  elements (type, x, y), x < 256 and x >= 256
  Lbf46_warbases_factories_part1, Lbf6e_..._part2     warbases (type 0) and factories (type 1..6)
  Lbf9c_map_complex_structure_ptrs and the structures they point to (lists of elements with
  relative offsets, ended by an element with x == y == 0)
Bytes are written as they are (this is data, no bit reversal).

--newgame: the state at the start of a new game as the original builds it (La600_start, Lbc6f_initialize_map,
Lbb86_assign_warbase_to_player ...): checksums of the map, the buildings, the decorations and the counters,
as the test build of the port prints them (tools/run_snap_tests.py compares).

--compare SNAPSHOT...: generates the map from the tables the way the original code does and compares
the element types (bits 0..5 of the map bytes) with the map of the snapshots, to find the snapshots
with the original map.
"""
import argparse
import os
import re
import sys

DEFAULT_DIR = r'D:\Work\MyProjects-old\netherearth\netherearth-disassembly-main'
CODE_FILE = 'netherearth-annotated.asm'

ELEMENTS = ('Lbda9_map_elements_part1', 'Lbe79_map_elements_part2')
BUILDINGS = ('Lbf46_warbases_factories_part1', 'Lbf6e_warbases_factories_part2')
PTRS = 'Lbf9c_map_complex_structure_ptrs'
MAP_LENGTH = 512
MAP_SIZE = 8192


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


def read_tables(path):
    """Returns ({label: bytes}, [labels of the structures in the order of the pointer table])."""
    tables = {}
    order = []
    cur = None
    wanted_dw = False
    started = False
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith(ELEMENTS[0] + ':'):
                started = True
            if not started:
                continue
            m = re.match(r'^(\w+):', line)
            if m:
                cur = m.group(1)
                wanted_dw = cur == PTRS
                if cur not in tables:
                    tables[cur] = bytearray()
                if cur == 'Lc100_title_screen':
                    break
                continue
            s = line.split(';')[0].strip()
            if wanted_dw:
                m = re.match(r'^dw\s+(\w+)$', s)
                if m:
                    order.append(m.group(1))
                continue
            d = parse_db(line)
            if d is not None and cur is not None:
                tables[cur].extend(d)
    tables.pop('Lc100_title_screen', None)
    tables.pop(PTRS, None)
    return {k: bytes(v) for k, v in tables.items()}, order


def triples(data, terminator):
    """Records of 3 bytes up to the terminator (a record of one byte)."""
    out = []
    i = 0
    while data[i] != terminator:
        out.append(tuple(data[i:i + 3]))
        i += 3
    return out


def struct_records(data):
    """The records of a complex structure: until an element with x == y == 0 (included)."""
    out = []
    for i in range(0, len(data), 3):
        out.append(tuple(data[i:i + 3]))
        if data[i + 1] == 0 and data[i + 2] == 0:
            break
    return out


def signed(b):
    return b - 256 if b >= 128 else b


# ---------------------------------------------------------------- the generator of the original

def generate_map(tables, order):
    """The map bytes (types only) as Lbc6f_initialize_map builds them."""
    m = bytearray(MAP_SIZE)

    def add_element(ptr, t):
        e = t
        for row in range(2):
            p = ptr - row * MAP_LENGTH
            for col in range(2):
                if 0 <= p + col < MAP_SIZE:
                    m[p + col] = e
                e |= 0x20            # only the bottom left corner has bit 5 = 0

    def add_structure(ptr, index):
        for t, x, y in struct_records(tables[order[index]]):
            if t:
                add_element(ptr, t)
            if x == 0 and y == 0:
                return
            ptr += signed(x) + signed(y) * MAP_LENGTH

    for part, name in enumerate(ELEMENTS):
        for t, x, y in triples(tables[name], 0):
            ptr = (part * 256 + x) + y * MAP_LENGTH
            if t & 0x80:
                add_structure(ptr, t & 0x7F)
            else:
                add_element(ptr, t)
    for part, name in enumerate(BUILDINGS):
        for t, x, y in triples(tables[name], 0xFF):
            ptr = (part * 256 + x) + y * MAP_LENGTH
            add_structure(ptr, 0 if t == 0 else 1)
    return m


# ---------------------------------------------------------------- the new game

N_DECORATIONS = 56
N_BUILDINGS = 28
N_WARBASES = 4
START_X, START_Y = 17, 10
INITIAL_RESOURCES = 20


def l_add(ptr, d):
    """The original does dec l / add a,8 on the low byte only."""
    return (ptr & ~0xFF) | ((ptr + d) & 0xFF)


def new_game_state(tables, order):
    """Returns the bytes of the map, the buildings, the decorations and the counters of a new game,
    in the layout of NEGAME.MAC."""
    m = bytearray(MAP_SIZE)
    dec = [None] * N_DECORATIONS                 # (ptr, type)
    bld = [None] * N_BUILDINGS                   # [x, y, type]

    def put(ptr, v):
        if 0 <= ptr < MAP_SIZE:
            m[ptr] = v

    def add_element(ptr, t):
        e = t
        for row in range(2):
            p = ptr - row * MAP_LENGTH
            for col in range(2):
                put(p + col, e)
                e |= 0x20

    def add_structure(ptr, index):
        for t, x, y in struct_records(tables[order[index]]):
            if t:
                add_element(ptr, t)
            if x == 0 and y == 0:
                return
            ptr += signed(x) + signed(y) * MAP_LENGTH

    def add_decoration(ptr, c):
        for i in range(N_DECORATIONS):
            if dec[i] is None:
                if 0 <= ptr < MAP_SIZE:
                    m[ptr] |= 0x40
                dec[i] = (ptr, c)
                return

    def remove_decoration(ptr):
        for i in range(N_DECORATIONS):
            if dec[i] is not None and dec[i][0] == ptr:
                dec[i] = None
                if 0 <= ptr < MAP_SIZE:
                    m[ptr] &= ~0x40
                return

    def assign_warbase(a, b):
        rec = bld[a]
        rec[2] = (rec[2] & 31) | (0x40 if b == 0 else 0x20)
        ptr = rec[0] + MAP_LENGTH * rec[1] - 2048
        remove_decoration(ptr)
        ptr = l_add(ptr, -4)
        remove_decoration(ptr)
        ptr = l_add(ptr, 8)
        remove_decoration(ptr)
        if b != 0:
            add_decoration(ptr, 8)
            return
        ptr = l_add(ptr, -4)
        add_decoration(ptr, 0)
        ptr = l_add(ptr, -4)
        add_decoration(ptr, 7)

    for part, name in enumerate(ELEMENTS):
        for t, x, y in triples(tables[name], 0):
            ptr = (part * 256 + x) + y * MAP_LENGTH
            if t & 0x80:
                add_structure(ptr, t & 0x7F)
            else:
                add_element(ptr, t)
    wi, fi = 0, N_WARBASES
    for part, name in enumerate(BUILDINGS):
        for t, x, y in triples(tables[name], 0xFF):
            x += part * 256
            ptr = x + y * MAP_LENGTH
            if t == 0:
                bld[wi] = [x, y, 0]
                wi += 1
                add_structure(ptr, 0)
            else:
                bld[fi] = [x, y, t]
                fi += 1
                add_structure(ptr, 1)
                add_decoration(ptr - 1024, t)
    for a, b in ((0, 0), (1, 1), (2, 1), (3, 1)):
        assign_warbase(a, b)
    counts = [[0] * 8, [0] * 8]                  # 7 counts + the number of robots
    for x, y, t in bld:
        if t & 0x80:
            continue
        if t & 0x40:
            counts[0][t & 7] += 1
        elif t & 0x20:
            counts[1][t & 7] += 1
    m[START_X + START_Y * MAP_LENGTH] |= 0x80   # the player (Lb024_add_player_to_map_and_update_radar)
    buildings = b''.join(bytes([x & 255, x >> 8, y, t, 0, 0]) for x, y, t in bld)
    decorations = b''.join(
        bytes([d[0] & 255, (d[0] >> 8) & 255, d[1], 0]) if d else bytes([255, 255, 0, 0]) for d in dec)
    resources = bytes([INITIAL_RESOURCES] + [0] * 7) * 2
    misc = resources + bytes(counts[0]) + bytes(counts[1])
    return bytes(m), buildings, decorations, misc


def fold(data):
    """The checksum of the test build: sum = sum * 2 + byte, 16 bits."""
    s = 0
    for b in data:
        s = ((s << 1) + b) & 0xFFFF
    return s


# ---------------------------------------------------------------- output

def emit(out, label, data, record, comment=None):
    out.append('%s:%s' % (label, '	; ' + comment if comment else ''))
    for i in range(0, len(data), record):
        out.append('	.BYTE	' + ','.join('%03o' % b for b in data[i:i + record]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('srcdir', nargs='?', default=DEFAULT_DIR, help='directory with the Z80 disassembly')
    ap.add_argument('-o', '--output', default='NEMAP.MAC')
    ap.add_argument('--compare', nargs='+', metavar='SNAPSHOT', help='compare the generated map with snapshots')
    ap.add_argument('--newgame', action='store_true', help='print the checksums of the state of a new game')
    args = ap.parse_args()

    tables, order = read_tables(os.path.join(args.srcdir, CODE_FILE))
    if len(order) != 11:
        raise SystemExit('expected 11 complex structures, found %d' % len(order))

    if args.newgame:
        print(' '.join('%d' % fold(p) for p in new_game_state(tables, order)))
        return

    if args.compare:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import conv_snap
        gen = generate_map(tables, order)
        for path in args.compare:
            mem = conv_snap.load_snapshot(path)
            snap = mem[conv_snap.MAP:conv_snap.MAP + MAP_SIZE]
            diff = sum(1 for a, b in zip(gen, snap) if a != (b & 0x3F))
            print('%-24s %5d different cells of %d' % (os.path.splitext(os.path.basename(path))[0], diff, MAP_SIZE))
        return

    out = ['; Start of NEMAP.MAC',
           '; Generated by tools/conv_map.py from the Z80 disassembly, do not edit.',
           '; The static description of the map. Lbc6f_initialize_map builds the map from it at the start of a game.',
           '; Element = type, x, y. Types with bit 7 set are complex structures (index = the type without the',
           '; bit 7, see the pointer table). A map element is 2x2 cells, its position is the bottom left cell.',
           '']
    emit(out, ELEMENTS[0], tables[ELEMENTS[0]][:-1], 3, 'map elements with x < 256 (type, x, y)')
    out.append('	.BYTE	0			; the end')
    emit(out, ELEMENTS[1], tables[ELEMENTS[1]][:-1], 3, 'map elements with x >= 256 (x is relative to 256)')
    out.append('	.BYTE	0			; the end')
    out.append('')
    emit(out, BUILDINGS[0], tables[BUILDINGS[0]][:-1], 3, 'warbases (type 0) and factories (type 1..6), x < 256')
    out.append('	.BYTE	377			; the end')
    emit(out, BUILDINGS[1], tables[BUILDINGS[1]][:-1], 3, 'the same, x >= 256 (x is relative to 256)')
    out.append('	.BYTE	377			; the end')
    out.append('	.EVEN')
    out.append('')
    out.append('%s:	; the complex structures: 0 warbase, 1 factory, 2.. parts of the map' % PTRS)
    for label in order:
        out.append('	.WORD	%s' % label)
    out.append('')
    out.append('; Each complex structure is a list of elements (type, x offset, y offset from the previous one),')
    out.append('; it ends with the element with x == y == 0.')
    for label in order:
        emit(out, label, tables[label][:len(struct_records(tables[label])) * 3], 3)
    out.append('	.EVEN')
    out.append('')
    out.append('; End of NEMAP.MAC')
    with open(args.output, 'w', encoding='ascii', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
    total = sum(len(tables[k]) for k in tables)
    print('%s: %d bytes of tables, %d structures' % (args.output, total, len(order)), file=sys.stderr)


if __name__ == '__main__':
    main()
