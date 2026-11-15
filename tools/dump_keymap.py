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

# Quantum keycodes (lighting, magic, grave-esc, ...) under their VIA names.
QUANTUM = {
    0x7000:"QK_MAGIC_SWAP_CONTROL_CAPS_LOCK", 0x7001:"QK_MAGIC_UNSWAP_CONTROL_CAPS_LOCK", 0x7002:"QK_MAGIC_TOGGLE_CONTROL_CAPS_LOCK", 0x7003:"QK_MAGIC_CAPS_LOCK_AS_CONTROL_OFF",
    0x7004:"QK_MAGIC_CAPS_LOCK_AS_CONTROL_ON", 0x7005:"QK_MAGIC_SWAP_LALT_LGUI", 0x7006:"QK_MAGIC_UNSWAP_LALT_LGUI", 0x7007:"QK_MAGIC_SWAP_RALT_RGUI",
    0x7008:"QK_MAGIC_UNSWAP_RALT_RGUI", 0x7009:"QK_MAGIC_GUI_ON",  0x700A:"QK_MAGIC_GUI_OFF", 0x700B:"MAGIC_TOGGLE_GUI",
    0x700C:"QK_MAGIC_SWAP_GRAVE_ESC", 0x700D:"QK_MAGIC_UNSWAP_GRAVE_ESC", 0x700E:"QK_MAGIC_SWAP_BACKSLASH_BACKSPACE", 0x700F:"QK_MAGIC_UNSWAP_BACKSLASH_BACKSPACE",
    0x7010:"QK_MAGIC_TOGGLE_BACKSLASH_BACKSPACE", 0x7011:"QK_MAGIC_NKRO_ON", 0x7012:"QK_MAGIC_NKRO_OFF", 0x7013:"QK_MAGIC_TOGGLE_NKRO",
    0x7014:"QK_MAGIC_SWAP_ALT_GUI", 0x7015:"QK_MAGIC_UNSWAP_ALT_GUI", 0x7016:"QK_MAGIC_TOGGLE_ALT_GUI", 0x7017:"QK_MAGIC_SWAP_LCTL_LGUI",
    0x7018:"QK_MAGIC_UNSWAP_LCTL_LGUI", 0x7019:"QK_MAGIC_SWAP_RCTL_RGUI", 0x701A:"QK_MAGIC_UNSWAP_RCTL_RGUI", 0x701B:"QK_MAGIC_SWAP_CTL_GUI",
    0x701C:"QK_MAGIC_UNSWAP_CTL_GUI", 0x701D:"QK_MAGIC_TOGGLE_CTL_GUI", 0x701E:"QK_MAGIC_EE_HANDS_LEFT", 0x701F:"QK_MAGIC_EE_HANDS_RIGHT",
    0x7020:"QK_MAGIC_SWAP_ESCAPE_CAPS_LOCK", 0x7021:"QK_MAGIC_UNSWAP_ESCAPE_CAPS_LOCK", 0x7022:"QK_MAGIC_TOGGLE_ESCAPE_CAPS_LOCK", 0x7800:"BL_ON",           
    0x7801:"BL_OFF",           0x7802:"BL_TOGG",          0x7803:"BL_DEC",           0x7804:"BL_INC",          
    0x7805:"BL_STEP",          0x7806:"BL_BRTG",          0x7810:"QK_LED_MATRIX_ON", 0x7811:"QK_LED_MATRIX_OFF",
    0x7812:"QK_LED_MATRIX_TOGGLE", 0x7813:"QK_LED_MATRIX_MODE_NEXT", 0x7814:"QK_LED_MATRIX_MODE_PREVIOUS", 0x7815:"QK_LED_MATRIX_BRIGHTNESS_UP",
    0x7816:"QK_LED_MATRIX_BRIGHTNESS_DOWN", 0x7817:"QK_LED_MATRIX_SPEED_UP", 0x7818:"QK_LED_MATRIX_SPEED_DOWN", 0x7819:"QK_LED_MATRIX_FLAG_NEXT",
    0x781A:"QK_LED_MATRIX_FLAG_PREVIOUS", 0x7820:"RGB_TOG",          0x7821:"RGB_MOD",          0x7822:"RGB_RMOD",        
    0x7823:"RGB_HUI",          0x7824:"RGB_HUD",          0x7825:"RGB_SAI",          0x7826:"RGB_SAD",         
    0x7827:"RGB_VAI",          0x7828:"RGB_VAD",          0x7829:"RGB_SPI",          0x782A:"RGB_SPD",         
    0x782B:"RGB_M_PLAIN",      0x782C:"RGB_M_BREATHE",    0x782D:"RGB_M_RAINBOW",    0x782E:"RGB_M_SWIRL",     
    0x782F:"RGB_M_SNAKE",      0x7830:"RGB_M_KNIGHT",     0x7831:"RGB_M_XMAS",       0x7832:"RGB_M_GRADIENT",  
    0x7833:"RGB_M_RGBTEST",    0x7834:"RGB_M_TWINKLE",    0x7840:"RM_ON",            0x7841:"RM_OFF",          
    0x7842:"RM_TOGG",          0x7843:"RM_NEXT",          0x7844:"RM_PREV",          0x7845:"RM_HUEU",         
    0x7846:"RM_HUED",          0x7847:"RM_SATU",          0x7848:"RM_SATD",          0x7849:"RM_VALU",         
    0x784A:"RM_VALD",          0x784B:"RM_SPDU",          0x784C:"RM_SPDD",          0x784D:"QK_RGB_MATRIX_FLAG_NEXT",
    0x784E:"QK_RGB_MATRIX_FLAG_PREVIOUS", 0x7C00:"QK_BOOTLOADER",    0x7C01:"QK_REBOOT",        0x7C02:"QK_DEBUG_TOGGLE", 
    0x7C03:"QK_CLEAR_EEPROM",  0x7C04:"QK_MAKE",          0x7C10:"QK_AUTO_SHIFT_DOWN", 0x7C11:"QK_AUTO_SHIFT_UP",
    0x7C12:"QK_AUTO_SHIFT_REPORT", 0x7C13:"QK_AUTO_SHIFT_ON", 0x7C14:"QK_AUTO_SHIFT_OFF", 0x7C15:"QK_AUTO_SHIFT_TOGGLE",
    0x7C16:"KC_GESC",          0x7C17:"QK_VELOCIKEY_TOGGLE", 0x7C18:"QK_SPACE_CADET_LEFT_CTRL_PARENTHESIS_OPEN", 0x7C19:"QK_SPACE_CADET_RIGHT_CTRL_PARENTHESIS_CLOSE",
    0x7C1A:"QK_SPACE_CADET_LEFT_SHIFT_PARENTHESIS_OPEN", 0x7C1B:"QK_SPACE_CADET_RIGHT_SHIFT_PARENTHESIS_CLOSE", 0x7C1C:"QK_SPACE_CADET_LEFT_ALT_PARENTHESIS_OPEN", 0x7C1D:"QK_SPACE_CADET_RIGHT_ALT_PARENTHESIS_CLOSE",
    0x7C1E:"QK_SPACE_CADET_RIGHT_SHIFT_ENTER", 0x7C30:"QK_UNICODE_MODE_NEXT", 0x7C31:"QK_UNICODE_MODE_PREVIOUS", 0x7C32:"QK_UNICODE_MODE_MACOS",
    0x7C33:"QK_UNICODE_MODE_LINUX", 0x7C34:"QK_UNICODE_MODE_WINDOWS", 0x7C35:"QK_UNICODE_MODE_BSD", 0x7C36:"QK_UNICODE_MODE_WINCOMPOSE",
    0x7C37:"QK_UNICODE_MODE_EMACS", 0x7C40:"QK_HAPTIC_ON",     0x7C41:"QK_HAPTIC_OFF",    0x7C42:"QK_HAPTIC_TOGGLE",
    0x7C43:"QK_HAPTIC_RESET",  0x7C44:"QK_HAPTIC_FEEDBACK_TOGGLE", 0x7C45:"QK_HAPTIC_BUZZ_TOGGLE", 0x7C46:"QK_HAPTIC_MODE_NEXT",
    0x7C47:"QK_HAPTIC_MODE_PREVIOUS", 0x7C48:"QK_HAPTIC_CONTINUOUS_TOGGLE", 0x7C49:"QK_HAPTIC_CONTINUOUS_UP", 0x7C4A:"QK_HAPTIC_CONTINUOUS_DOWN",
    0x7C4B:"QK_HAPTIC_DWELL_UP", 0x7C4C:"QK_HAPTIC_DWELL_DOWN", 0x7C50:"QK_COMBO_ON",      0x7C51:"QK_COMBO_OFF",    
    0x7C52:"QK_COMBO_TOGGLE",  0x7C53:"QK_DYNAMIC_MACRO_RECORD_START_1", 0x7C54:"QK_DYNAMIC_MACRO_RECORD_START_2", 0x7C55:"QK_DYNAMIC_MACRO_RECORD_STOP",
    0x7C56:"QK_DYNAMIC_MACRO_PLAY_1", 0x7C57:"QK_DYNAMIC_MACRO_PLAY_2", 0x7C58:"QK_LEADER",        0x7C59:"QK_LOCK",         
    0x7C5A:"QK_ONE_SHOT_ON",   0x7C5B:"QK_ONE_SHOT_OFF",  0x7C5C:"QK_ONE_SHOT_TOGGLE", 0x7C5D:"QK_KEY_OVERRIDE_TOGGLE",
    0x7C5E:"QK_KEY_OVERRIDE_ON", 0x7C5F:"QK_KEY_OVERRIDE_OFF", 0x7C60:"QK_SECURE_LOCK",   0x7C61:"QK_SECURE_UNLOCK",
    0x7C62:"QK_SECURE_TOGGLE", 0x7C63:"QK_SECURE_REQUEST", 0x7C70:"QK_DYNAMIC_TAPPING_TERM_PRINT", 0x7C71:"QK_DYNAMIC_TAPPING_TERM_UP",
    0x7C72:"QK_DYNAMIC_TAPPING_TERM_DOWN", 0x7C73:"QK_CAPS_WORD_TOGGLE", 0x7C74:"QK_AUTOCORRECT_ON", 0x7C75:"QK_AUTOCORRECT_OFF",
    0x7C76:"QK_AUTOCORRECT_TOGGLE", 0x7C77:"QK_TRI_LAYER_LOWER", 0x7C78:"QK_TRI_LAYER_UPPER", 0x7C79:"QK_REPEAT_KEY",   
    0x7C7A:"QK_ALT_REPEAT_KEY", 0x7C7B:"QK_LAYER_LOCK",   
}

# Parametric layer keycodes: base value -> (prefix, mask)
LAYER_KEYS = (
    (0x5200, 0x521F, 'TO'),
    (0x5220, 0x523F, 'MO'),
    (0x5240, 0x525F, 'DF'),
    (0x5260, 0x527F, 'TG'),
    (0x5280, 0x529F, 'OSL'),
)


def name(v):
    """QMK keycode value -> VIA keycode name, or None if unknown."""
    if v in NAMES:
        return NAMES[v]
    if v in QUANTUM:
        return QUANTUM[v]
    if 0x4000 <= v <= 0x4FFF:  # LT(layer, kc)
        inner = NAMES.get(v & 0xFF, '0x%02X' % (v & 0xFF))
        return 'LT(%d,%s)' % ((v >> 8) & 0x0F, inner)
    for lo, hi, prefix in LAYER_KEYS:
        if lo <= v <= hi:
            return '%s(%d)' % (prefix, v & 0x1F)
    return None


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
            if all(name(v) is not None for v in vals):
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
                    n = name(v)
                    if n is not None:
                        flat.append(n)
                    else:
                        unknown.setdefault(v, []).append((L, r, c))
                        flat.append('0x%04X' % v if args.unknown == 'raw' else 'KC_NO')
            raw.append(grid)
            out_layers.append(flat)
    finally:
        via.close()

    for v, where in unknown.items():
        print('WARNING: 0x%04X is not a known QMK keycode; written as %s (%d site(s), first %s)'
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
