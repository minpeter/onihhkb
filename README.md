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
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then replug the board and reload usevia.app.

## Notes

- The board does not work over a C-to-C cable; use A-to-C.
- Bottom row is 1u + 1.5u + 7u + 1.5u + 1u (7u spacebar).
- ANSI 1.5x layout adds two 1.5u Ctrl keys; ignore them and it is HHKB.
