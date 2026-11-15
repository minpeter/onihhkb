#!/usr/bin/env python3
"""Dump the VIA dynamic keymap from an Oni HHKB (45d4:0021) over hidraw.

No browser or WebHID needed: talks the VIA protocol (version 9) directly to
the raw HID interface (usage page 0xFF60).

Requires hidraw access for your user -- see 70-via-onihhkb.rules.

    ./dump_keymap.py                      # -> onihhkb.minpeter-layout.json
    ./dump_keymap.py --verify             # re-read and compare with the file
    ./dump_keymap.py --raw                # also print the numeric grid

Values outside 0x00-0xFF (layer / mod-tap / custom keycodes) are written as
KC_NO so the file stays importable by VIA, and reported on stderr. Use
--unknown raw to keep the numeric value instead (not VIA-importable), and
--raw to see the numeric grid.
"""
import argparse
import glob
import json
import os
import select
import struct
import sys

ROWS, COLS = 5, 15
VID, PID = 0x45D4, 0x0021

# QMK basic keycode -> VIA 3 keycode name.
NAMES = {
    0x00:"KC_NO",    0x01:"KC_TRNS",  0x04:"KC_A",     0x05:"KC_B",     0x06:"KC_C",     0x07:"KC_D",    
    0x08:"KC_E",     0x09:"KC_F",     0x0A:"KC_G",     0x0B:"KC_H",     0x0C:"KC_I",     0x0D:"KC_J",    
    0x0E:"KC_K",     0x0F:"KC_L",     0x10:"KC_M",     0x11:"KC_N",     0x12:"KC_O",     0x13:"KC_P",    
    0x14:"KC_Q",     0x15:"KC_R",     0x16:"KC_S",     0x17:"KC_T",     0x18:"KC_U",     0x19:"KC_V",    
    0x1A:"KC_W",     0x1B:"KC_X",     0x1C:"KC_Y",     0x1D:"KC_Z",     0x1E:"KC_1",     0x1F:"KC_2",    
    0x20:"KC_3",     0x21:"KC_4",     0x22:"KC_5",     0x23:"KC_6",     0x24:"KC_7",     0x25:"KC_8",    
    0x26:"KC_9",     0x27:"KC_0",     0x28:"KC_ENT",   0x29:"KC_ESC",   0x2A:"KC_BSPC",  0x2B:"KC_TAB",  
    0x2C:"KC_SPC",   0x2D:"KC_MINS",  0x2E:"KC_EQL",   0x2F:"KC_LBRC",  0x30:"KC_RBRC",  0x31:"KC_BSLS", 
    0x32:"KC_NUHS",  0x33:"KC_SCLN",  0x34:"KC_QUOT",  0x35:"KC_GRV",   0x36:"KC_COMM",  0x37:"KC_DOT",  
    0x38:"KC_SLSH",  0x39:"KC_CAPS",  0x3A:"KC_F1",    0x3B:"KC_F2",    0x3C:"KC_F3",    0x3D:"KC_F4",   
    0x3E:"KC_F5",    0x3F:"KC_F6",    0x40:"KC_F7",    0x41:"KC_F8",    0x42:"KC_F9",    0x43:"KC_F10",  
    0x44:"KC_F11",   0x45:"KC_F12",   0x46:"KC_PSCR",  0x47:"KC_SCRL",  0x48:"KC_BRK",   0x49:"KC_INS",  
    0x4A:"KC_HOME",  0x4B:"KC_PGUP",  0x4C:"KC_DEL",   0x4D:"KC_END",   0x4E:"KC_PGDN",  0x4F:"KC_RGHT", 
    0x50:"KC_LEFT",  0x51:"KC_DOWN",  0x52:"KC_UP",    0x53:"KC_NUM",   0x54:"KC_PSLS",  0x55:"KC_PAST", 
    0x56:"KC_PMNS",  0x57:"KC_PPLS",  0x58:"KC_PENT",  0x59:"KC_P1",    0x5A:"KC_P2",    0x5B:"KC_P3",   
    0x5C:"KC_P4",    0x5D:"KC_P5",    0x5E:"KC_P6",    0x5F:"KC_P7",    0x60:"KC_P8",    0x61:"KC_P9",   
    0x62:"KC_P0",    0x63:"KC_PDOT",  0x64:"KC_NUBS",  0x65:"KC_APP",   0x66:"KC_KB_POWER", 0x67:"KC_PEQL", 
    0x68:"KC_F13",   0x69:"KC_F14",   0x6A:"KC_F15",   0x6B:"KC_F16",   0x6C:"KC_F17",   0x6D:"KC_F18",  
    0x6E:"KC_F19",   0x6F:"KC_F20",   0x70:"KC_F21",   0x71:"KC_F22",   0x72:"KC_F23",   0x73:"KC_F24",  
    0x74:"KC_EXEC",  0x75:"KC_HELP",  0x76:"KC_MENU",  0x77:"KC_SLCT",  0x78:"KC_STOP",  0x79:"KC_AGIN", 
    0x7A:"KC_UNDO",  0x7B:"KC_CUT",   0x7C:"KC_COPY",  0x7D:"KC_PSTE",  0x7E:"KC_FIND",  0x7F:"KC_KB_MUTE",
    0x80:"KC_KB_VOLUME_UP", 0x81:"KC_KB_VOLUME_DOWN", 0x82:"KC_LCAP",  0x83:"KC_LNUM",  0x84:"KC_LSCR",  0x85:"KC_PCMM", 
    0x86:"KC_KP_EQUAL_AS400", 0x87:"KC_INT1",  0x88:"KC_INT2",  0x89:"KC_INT3",  0x8A:"KC_INT4",  0x8B:"KC_INT5", 
    0x8C:"KC_INT6",  0x8D:"KC_INT7",  0x8E:"KC_INT8",  0x8F:"KC_INT9",  0x90:"KC_LNG1",  0x91:"KC_LNG2", 
    0x92:"KC_LNG3",  0x93:"KC_LNG4",  0x94:"KC_LNG5",  0x95:"KC_LNG6",  0x96:"KC_LNG7",  0x97:"KC_LNG8", 
    0x98:"KC_LNG9",  0x99:"KC_ERAS",  0x9A:"KC_SYRQ",  0x9B:"KC_CNCL",  0x9C:"KC_CLR",   0x9D:"KC_PRIR", 
    0x9E:"KC_RETN",  0x9F:"KC_SEPR",  0xA0:"KC_OUT",   0xA1:"KC_OPER",  0xA2:"KC_CLAG",  0xA3:"KC_CRSL", 
    0xA4:"KC_EXSL",  0xA5:"KC_PWR",   0xA6:"KC_SLEP",  0xA7:"KC_WAKE",  0xA8:"KC_MUTE",  0xA9:"KC_VOLU", 
    0xAA:"KC_VOLD",  0xAB:"KC_MNXT",  0xAC:"KC_MPRV",  0xAD:"KC_MSTP",  0xAE:"KC_MPLY",  0xAF:"KC_MSEL", 
    0xB0:"KC_EJCT",  0xB1:"KC_MAIL",  0xB2:"KC_CALC",  0xB3:"KC_MYCM",  0xB4:"KC_WSCH",  0xB5:"KC_WHOM", 
    0xB6:"KC_WBAK",  0xB7:"KC_WFWD",  0xB8:"KC_WSTP",  0xB9:"KC_WREF",  0xBA:"KC_WFAV",  0xBB:"KC_MFFD", 
    0xBC:"KC_MRWD",  0xBD:"KC_BRIU",  0xBE:"KC_BRID",  0xBF:"KC_CPNL",  0xC0:"KC_ASST",  0xC1:"KC_MCTL", 
    0xC2:"KC_LPAD",  0xE0:"KC_LCTL",  0xE1:"KC_LSFT",  0xE2:"KC_LALT",  0xE3:"KC_LGUI",  0xE4:"KC_RCTL", 
    0xE5:"KC_RSFT",  0xE6:"KC_RALT",  0xE7:"KC_RGUI", 
}


def find_node():
    for h in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            desc = open(h + '/device/report_descriptor', 'rb').read()
            uevent = open(h + '/device/uevent').read().upper()
        except OSError:
            continue
        # usage_page(0xFF60) item in the HID report descriptor
        if b'\x06\x60\xff' in desc and ('%04X' % VID) in uevent and ('%04X' % PID) in uevent:
            return '/dev/' + os.path.basename(h)
    return None


class Via:
    def __init__(self, node):
        self.fd = os.open(node, os.O_RDWR)
        self.offset = None

    def close(self):
        os.close(self.fd)

    def _drain(self, t=0.001):
        while True:
            r, _, _ = select.select([self.fd], [], [], t)
            if not r:
                return
            os.read(self.fd, 64)

    def xfer(self, payload, timeout=0.6):
        self._drain()
        # some builds expect a leading report id, some do not
        try:
            os.write(self.fd, bytes([0x00]) + payload.ljust(32, b'\x00')[:32])
        except OSError:
            os.write(self.fd, payload.ljust(32, b'\x00')[:32])
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            raise RuntimeError('timeout waiting for 0x%02X' % payload[0])
        return os.read(self.fd, 64)

    def protocol_version(self):
        return struct.unpack('<I', self.xfer(bytes([0x01]))[2:6])[0]

    def layer_count(self):
        return self.xfer(bytes([0x11]))[1]

    def _raw_keycode(self, layer, row, col, offset):
        r = self.xfer(bytes([0x04, layer, row, col]))
        return struct.unpack('<H', r[offset:offset + 2])[0]

    def detect_offset(self):
        """Some builds pad one byte after the echoed layer/row/col."""
        for off in (5, 4):
            try:
                vals = [self._raw_keycode(0, 0, c, off) for c in range(4)]
            except (RuntimeError, struct.error):
                continue
            if all(v in NAMES for v in vals):
                return off
        raise RuntimeError('could not locate the keycode field in the response')

    def keycode(self, layer, row, col):
        return self._raw_keycode(layer, row, col, self.offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='onihhkb.minpeter-layout.json')
    ap.add_argument('--layers', type=int, help='default: whatever the board reports')
    ap.add_argument('--verify', action='store_true', help='re-read and compare, do not write')
    ap.add_argument('--raw', action='store_true', help='also print the numeric grid')
    ap.add_argument('--unknown', choices=('no', 'raw'), default='no',
                    help="keycodes VIA cannot name: 'no' -> KC_NO (default, VIA-importable), "
                         "'raw' -> keep the numeric value")
    args = ap.parse_args()

    node = find_node()
    if not node:
        sys.exit('Oni HHKB raw HID interface not found. Plugged in? 70-via-onihhkb.rules installed?')
    print('raw HID node: %s' % node)

    via = Via(node)
    try:
        print('VIA protocol version: %d' % via.protocol_version())
        layers_n = args.layers or via.layer_count()
        via.offset = via.detect_offset()
        print('layers: %d  keycode field offset: %d' % (layers_n, via.offset))

        raw, out_layers, unknown = [], [], {}
        for L in range(layers_n):
            grid, flat = [], []
            for r in range(ROWS):
                row = [via.keycode(L, r, c) for c in range(COLS)]
                grid.append(row)
                for c, v in enumerate(row):
                    if v in NAMES:
                        flat.append(NAMES[v])
                    else:
                        unknown.setdefault(v, []).append((L, r, c))
                        flat.append('0x%04X' % v if args.unknown == 'raw' else 'KC_NO')
            raw.append(grid)
            out_layers.append(flat)
    finally:
        via.close()

    for v, where in unknown.items():
        print('WARNING: 0x%04X is not a basic QMK keycode; written as %s (%d site(s), first %s)'
              % (v, '0x%04X' % v if args.unknown == 'raw' else 'KC_NO',
                 len(where), where[0]), file=sys.stderr)
    if args.raw:
        for L, grid in enumerate(raw):
            print('layer %d:' % L)
            for row in grid:
                print('  ' + ' '.join('%04X' % v for v in row))

    doc = {
        'name': 'Oni HHKB',
        'vendorProductId': (VID << 16) | PID,
        'macros': [''] * 16,
        'layers': out_layers,
        'encoders': [],
    }

    if args.verify:
        try:
            old = json.load(open(args.out))
        except OSError:
            sys.exit('nothing to verify against: %s' % args.out)
        if old['layers'] == doc['layers'] and old['vendorProductId'] == doc['vendorProductId']:
            print('OK: %s matches the board' % args.out)
            return
        sys.exit('MISMATCH: %s differs from the board' % args.out)

    with open(args.out, 'w') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('wrote %s (%d layers x %d keys)' % (args.out, len(out_layers), len(out_layers[0])))


if __name__ == '__main__':
    main()
