#!/usr/bin/env python3
"""Convert a ZX Spectrum snapshot (.sna, .z80) of Nether Earth to the UKNC game state (NESNAP.MAC).

The output is the state block of NEGAME.MAC (GSTATE..GSEND, GS_SIZE bytes) with the data of the
snapshot (NEGAME.MAC includes it; the layout must match, tools/run_snap_tests.py checks it). Changes against the
original layout (see NEGAME.MAC): word aligned structures, map offsets instead of Z80 pointers
(offset = pointer - 0xDD00), free robot/bullet slots marked by -1, ZX-only variables dropped.

Optionally (--ref) writes the original game area frame buffer (0x5B00..0x677F, 20 bytes per line)
as REFBUF and the two radar buffers (0xD800, 0xD900) as REFRAD, bit-reversed to the UKNC bit order,
as a reference for testing the renderer and the radar.
"""
import argparse
import struct
import sys

# ZX addresses
MAP = 0xDD00
MAP_SIZE = 8192
BULLETS = 0xD7D3
ROBOTS1 = 0xDA00
ROBOTS2 = 0xDB80
BUILDINGS = 0xFD70          # 4 warbases + 24 factories, 5 bytes each
DECORATIONS = 0xFF01
FRAMEBUF = 0x5B00
FRAMEBUF_SIZE = 3200
RADAR1 = 0xD800             # the two radar views, 256 bytes each
NOSLOT = 0xFFFF
RANDOM_INDEX = 0xD371      # the operand of the self-modifying 'ld l,n' in Ld358_random


# ---------------------------------------------------------------- snapshot loading

def unpack_z80_block(data, size):
    """Z80 run length decoding: ED ED nn bb = nn times bb."""
    out = bytearray()
    i = 0
    while i < len(data) and (size is None or len(out) < size):
        if data[i] == 0xED and i + 3 < len(data) + 0 and data[i + 1] == 0xED:
            out += bytes([data[i + 3]]) * data[i + 2]
            i += 4
        else:
            out.append(data[i])
            i += 1
    return out


def load_sna(d):
    if len(d) not in (49179, 131103, 147487):
        raise SystemExit('unexpected .sna size %d' % len(d))
    mem = bytearray(65536)
    mem[0x4000:0x10000] = d[27:27 + 49152]
    return mem


def load_z80(d):
    mem = bytearray(65536)
    flags = d[12]
    if flags == 255:
        flags = 1
    pc = struct.unpack('<H', d[6:8])[0]
    if pc != 0:                                  # version 1: one block, 48K
        data = d[30:]
        if flags & 0x20:
            if data[-4:] == b'\x00\xED\xED\x00':
                data = data[:-4]
            data = unpack_z80_block(data, 49152)
        mem[0x4000:0x10000] = data[:49152]
        return mem
    extra = struct.unpack('<H', d[30:32])[0]
    version = 2 if extra == 23 else 3
    hw = d[34]
    is128 = hw >= 3 if version == 2 else hw >= 4
    port7ffd = d[35]
    if is128:
        pagemap = {8: 0x4000, 5: 0x8000, (port7ffd & 7) + 3: 0xC000}
    else:
        pagemap = {8: 0x4000, 4: 0x8000, 5: 0xC000}
    i = 32 + extra
    while i + 3 <= len(d):
        length, page = struct.unpack('<HB', d[i:i + 3])
        i += 3
        if length == 0xFFFF:
            block = d[i:i + 16384]
            i += 16384
        else:
            block = unpack_z80_block(d[i:i + length], 16384)
            i += length
        if page in pagemap and len(block) == 16384:
            mem[pagemap[page]:pagemap[page] + 16384] = block
    return mem


def load_snapshot(path):
    with open(path, 'rb') as f:
        d = f.read()
    if path.lower().endswith('.sna'):
        return load_sna(d)
    if path.lower().endswith('.z80'):
        return load_z80(d)
    raise SystemExit('unknown snapshot type: ' + path)


# ---------------------------------------------------------------- state conversion

def w(mem, a):
    return mem[a] | (mem[a + 1] << 8)


def map_off(ptr):
    off = ptr - MAP
    if not 0 <= off < MAP_SIZE:
        raise ValueError('map pointer 0x%04X is outside of the map' % ptr)
    return off


def pw(v):
    return struct.pack('<H', v & 0xFFFF)


def convert_structs(mem, base, count, size, new_size):
    """Robots, bullets: map pointer word -> offset (NOSLOT if free), the rest as is, padded."""
    out = bytearray()
    for i in range(count):
        a = base + i * size
        rec = mem[a:a + size]
        # the original frees a record by clearing the high byte of the map pointer
        if rec[1] == 0:
            rec = pw(NOSLOT) + bytes(size - 2)
        else:
            ptr = map_off(rec[0] | (rec[1] << 8))
            rec = pw(ptr) + rec[2:]
        out += rec + bytes(new_size - size)
    return out


def convert_state(mem):
    """Returns list of (label, bytes) in the order of the NEGAME.MAC state block."""
    parts = []

    def add(label, data):
        parts.append((label, bytes(data)))

    # words
    add('Lfd00_random_seed', mem[0xFD00:0xFD04])
    add('Lfd06_scroll_ptr', pw(map_off(w(mem, 0xFD06))))
    add('Lfd0a_scroll_x', mem[0xFD0A:0xFD0C])
    add('Lfd0e_player_x', mem[0xFD0E:0xFD10])
    add('Lfd1c_radar_scroll_x', mem[0xFD1C:0xFD1E])
    add('Lfd37_days', mem[0xFD37:0xFD39])
    # bytes
    add('Lfd0d_player_y', [mem[0xFD0D]])
    add('Lfd10_player_altitude', [mem[0xFD10]])
    add('Lfd1b_radar_scroll_x_tile', [mem[0xFD1B]])
    add('Lfd1e_player_visible_in_radar', [mem[0xFD1E]])
    add('Lfd1f_cursor_position', mem[0xFD1F:0xFD21])
    add('Lfd21_constr_selected_pieces', [mem[0xFD21]])
    add('Lfd30_player_elevate_timer', [mem[0xFD30]])
    add('Lfd35_minutes', [mem[0xFD35]])
    add('Lfd36_hours', [mem[0xFD36]])
    add('Lfd39_current_in_game_right_hud', [mem[0xFD39]])
    add('Lfd51_robot_player_or_enemy', [mem[0xFD51]])
    add('Lfd52_update_radar_buffer_signal', [mem[0xFD52]])
    add('Ld370_random_index', [mem[RANDOM_INDEX]])
    # resources and counts
    add('Lfd22_player1_resource_counts', bytes(mem[0xFD22:0xFD29]) + b'\x00')
    add('Lfd4a_player2_resource_counts', bytes(mem[0xFD4A:0xFD51]) + b'\x00')
    add('Lfd3a_p1_base_factory_counts', mem[0xFD3A:0xFD41])
    add('Lfd41_player1_robot_count', [mem[0xFD41]])
    add('Lfd42_p2_base_factory_counts', mem[0xFD42:0xFD49])
    add('Lfd49_player2_robot_count', [mem[0xFD49]])
    # bullets (5 x 9 -> 10)
    add('Ld7d3_bullets', convert_structs(mem, BULLETS, 5, 9, 10))
    # decorations (56 x 3 -> 4)
    dec = bytearray()
    for i in range(56):
        a = DECORATIONS + i * 3
        ptr = mem[a] | (mem[a + 1] << 8)
        # the original frees a record by clearing the high byte of the pointer
        off = map_off(ptr) if mem[a + 1] else NOSLOT
        dec += pw(off) + bytes([mem[a + 2], 0])
    add('Lff01_building_decorations', dec)
    # buildings (28 x 5 -> 6)
    bld = bytearray()
    for i in range(28):
        a = BUILDINGS + i * 5
        bld += bytes(mem[a:a + 5]) + b'\x00'
    add('Lfd70_warbases', bld[:4 * 6])
    add('Lfd84_factories', bld[4 * 6:])
    # robots
    add('Lda00_player1_robots', convert_structs(mem, ROBOTS1, 24, 16, 16))
    add('Ldb80_player2_robots', convert_structs(mem, ROBOTS2, 24, 16, 16))
    # map
    add('Ldd00_map', mem[MAP:MAP + MAP_SIZE])
    return parts


# ---------------------------------------------------------------- output

def rev8(b):
    return int('{:08b}'.format(b)[::-1], 2)


def emit_bytes(out, data, per_line=16):
    for i in range(0, len(data), per_line):
        out.append('	.BYTE	' + ','.join('%03o' % b for b in data[i:i + per_line]))


def summary(mem, parts):
    names = {}
    print('player x=%d y=%d altitude=%d, scroll_x=%d' % (w(mem, 0xFD0E), mem[0xFD0D], mem[0xFD10], w(mem, 0xFD0A)))
    for base, nm in ((ROBOTS1, 'player 1'), (ROBOTS2, 'player 2')):
        n = [i for i in range(24) if mem[base + 16 * i + 1]]
        print('%s robots: %d' % (nm, len(n)))
    bl = [i for i in range(5) if mem[BULLETS + 9 * i + 1]]
    print('bullets: %d' % len(bl))
    print('resources p1: %s' % ' '.join('%d' % b for b in mem[0xFD22:0xFD29]))
    print('map types: ' + ' '.join('%d:%d' % (t, c) for t, c in sorted(
        {t: sum(1 for b in mem[MAP:MAP + MAP_SIZE] if b & 31 == t) for t in range(32)}.items()) if c))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapshot', help='.sna or .z80 file')
    ap.add_argument('-o', '--output', default='NESNAP.MAC')
    ap.add_argument('--ref', metavar='FILE', help='also write the original frame buffer as MACRO-11 (REFBUF)')
    ap.add_argument('--info', action='store_true', help='print a summary of the state and exit')
    args = ap.parse_args()

    mem = load_snapshot(args.snapshot)
    try:
        parts = convert_state(mem)
    except ValueError as e:
        raise SystemExit('bad snapshot: %s' % e)
    if args.info:
        summary(mem, parts)
        return

    out = ['; Start of NESNAP.MAC',
           '; Generated by tools/conv_snap.py from %s, do not edit.' % args.snapshot.replace(chr(92), '/').split('/')[-1],
           '; Initial game state: the state block of NEGAME.MAC (included from there) with the data of the',
           '; snapshot. The labels and their order must be the same as in the layout of NEGAME.MAC:',
           '; tools/run_snap_tests.py compares them (symbol tables of both builds).',
           '',
           '	.EVEN',
           'GSTATE:']
    for label, data in parts:
        out.append('%s:' % label if label else '	; padding')
        emit_bytes(out, data)
    out.append('GSEND:')
    out.append('GS_SIZE = GSEND-GSTATE		; Size of the state block in bytes (snapshot/save size)')
    out.append('	.EVEN')
    out.append('; End of NESNAP.MAC')
    with open(args.output, 'w', encoding='ascii', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
    total = sum(len(d) for _, d in parts)
    print('%s: state image %d bytes' % (args.output, total), file=sys.stderr)

    if args.ref:
        buf = [rev8(b) for b in mem[FRAMEBUF:FRAMEBUF + FRAMEBUF_SIZE]]
        lines = ['; Start of %s' % args.ref,
                 '; Original game area frame buffer (ZX 0x5B00), 20 bytes per line, bits reversed to UKNC order.',
                 '	.EVEN',
                 'REFBUF:']
        emit_bytes(lines, buf, 20)
        rad = [rev8(b) for b in mem[RADAR1:RADAR1 + 512]]
        lines += ['	.EVEN',
                  '; Original radar buffers (ZX 0xD800 and 0xD900), 256 bytes each, bits reversed.',
                  'REFRAD:']
        emit_bytes(lines, rad, 16)
        lines += ['	.EVEN', '; End of %s' % args.ref]
        with open(args.ref, 'w', encoding='ascii', newline='\r\n') as f:
            f.write('\n'.join(lines) + '\n')
        print('%s: reference buffer %d bytes' % (args.ref, len(buf)), file=sys.stderr)


if __name__ == '__main__':
    main()
