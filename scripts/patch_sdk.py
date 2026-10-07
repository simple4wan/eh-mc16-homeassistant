#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_sdk.py <bee2-sdk-dir>")

sdk = Path(sys.argv[1])
main_c = sdk / "src/app/silent_ota/main.c"
board_h = sdk / "board/evb/silent_ota_gcc/board.h"

text = main_c.read_text(encoding="utf-8")

# Give the recovery test a unique, obvious BLE name.
text = text.replace(
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "RealTekDfu";',
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "EH-MC16-TEST";',
    1,
)

old_adv = """    0x0B,                               /* length     */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'R', 'e', 'a', 'l', 'T', 'e', 'k', 'D', 'f', 'u',
"""
new_adv = """    0x0D,                               /* length: type + 12-byte name */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'E', 'H', '-', 'M', 'C', '1', '6', '-', 'T', 'E', 'S', 'T',
"""
if old_adv not in text:
    raise SystemExit("expected RealTekDfu advertising block not found")
text = text.replace(old_adv, new_adv, 1)

# The SDK sample uses EVB GPIOs P0_0/P2_4 to decide OTA mode and handle a key.
# Those pins are unknown on EH-MC16 and must not be touched in the first test.
text = re.sub(
    r"void pinmux_configuration\(void\)\n\{.*?\n\}",
    "void pinmux_configuration(void)\n{\n    /* EH-MC16 recovery test: intentionally do not touch unknown GPIOs. */\n}",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void pad_configuration\(void\)\n\{.*?\n\}",
    "void pad_configuration(void)\n{\n    /* EH-MC16 recovery test: intentionally do not touch unknown pads. */\n}",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void driver_init\(void\)\n\{.*?\n\}",
    "void driver_init(void)\n{\n    /* Enable DFU buffer-check without sampling the EVB TP0 GPIO. */\n    g_ota_mode = 1;\n    g_keystatus = 1;\n}",
    text,
    count=1,
    flags=re.S,
)

# Avoid enabling the sample's low-power GPIO callbacks, which reference EVB pins.
text = text.replace(
    "#define DLPS_EN               1",
    "#define DLPS_EN               0",
) if False else text

main_c.write_text(text, encoding="utf-8")

btext = board_h.read_text(encoding="utf-8")
btext = btext.replace("#define USE_GPIO_DLPS        1", "#define USE_GPIO_DLPS        0", 1)
btext = btext.replace("#define DLPS_EN               1", "#define DLPS_EN               0", 1)
board_h.write_text(btext, encoding="utf-8")

print(f"patched {main_c}")
print(f"patched {board_h}")
print("device_name=EH-MC16-TEST")
print("unknown GPIO init disabled")
print("DFU buffer-check forced enabled")
print("DLPS GPIO callbacks disabled")
