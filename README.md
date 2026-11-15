# onihhkb

YMDK Oni HHKB (HHKB-style GH60 hotswap PCB, underglow + switch RGB) VIA backup.

- VID/PID: `0x45D4` / `0x0021`
- Matrix: 5 x 15
- Lighting: `qmk_backlight_rgblight`
- QMK source: https://github.com/qmk/qmk_firmware/tree/master/keyboards/ymdk/oni_tsangan

## Files

| File | What it is |
| --- | --- |
| `ONIHHKBVIA.json` | VIA keyboard definition (from the seller's manual) |
| `New Oni HHKB RGB VIA Manuals.pdf` | Seller manual (VIA download links, json link, assembly notes) |
| `70-via-onihhkb.rules` | udev rule so WebHID / hidapi can open the board |
| `personalization/onihhkb.minpeter-layout.json` | The actual keymap, read off the board over the VIA protocol |
| `tools/dump_keymap.py` | Re-reads the keymap from the board (no browser needed) |

## Loading the definition in VIA 3 (usevia.app)

The json is a legacy V2 definition, so:

1. Open the **Design** tab.
2. Turn on **Use V2 definitions (deprecated)**.
3. **Load Draft Definition** -> pick `ONIHHKBVIA.json`.
4. It shows up as `Oni HHKB` / `0x45D40021`.

Without step 2 VIA rejects it with `Object: must NOT have additional properties`.

## Linux: letting VIA see the board

WebHID only lists devices the user can open. Add a udev rule:

```
# /etc/udev/rules.d/70-via-onihhkb.rules
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="45d4", ATTRS{idProduct}=="0021", TAG+="uaccess"
```

```
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw --subsystem-match=usb
```

Then replug the board and reload usevia.app.

Check the ACL without sudo -- all of the board's hidraw nodes should show
`user:<you>:rw-`:

```
for h in /sys/class/hidraw/hidraw*; do
  n=/dev/$(basename $h)
  udevadm info -q property -n $n | grep -q ID_VENDOR_ID=45d4 && \
    echo "$n  $(getfacl -cp $n | grep $USER || echo 'NO ACL')"
done
```

## Backing up the keymap

`personalization/onihhkb.minpeter-layout.json` is the keymap, in the same format
VIA's *Save* produces. It was exported from VIA and every keycode in it is
verified to round-trip through `tools/dump_keymap.py`.

4 layers:

| Layer | Reached by | Contents |
| --- | --- | --- |
| 0 | — | base. `\` at `0,13`, `Bksp` at `1,13`, `Del` at `0,14`, `MO(1)`/`MO(2)` at `3,13`/`3,14`, `RGB_HUI` at `4,12` |
| 1 | `MO(1)` | WASD arrows |
| 2 | `MO(2)` | `F1`-`F12` on the number row, `PrtSc`, `Vol-`/`Vol+`/`Play` |
| 3 | — | unused |

You do not need a browser or WebHID to re-read it:

```sh
./tools/dump_keymap.py            # write the json
./tools/dump_keymap.py --verify   # re-read and compare with the file
./tools/dump_keymap.py --raw      # print the numeric grid
```

The tool decodes basic keycodes, `MO`/`TO`/`TG`/`OSL`/`DF`/`LT`, and the
lighting and magic quantum keycodes under their VIA names (`RGB_HUI`, `RM_HUEU`,
`BL_TOGG`, ...). Anything it cannot name is written as `KC_NO` and reported on
stderr; `--unknown raw` keeps the numeric value instead.

## Notes

- The board does not work over a C-to-C cable; use A-to-C.
- Bottom row is 1u + 1.5u + 7u + 1.5u + 1u (7u spacebar).
- ANSI 1.5x layout adds two 1.5u Ctrl keys; ignore them and it is HHKB.
