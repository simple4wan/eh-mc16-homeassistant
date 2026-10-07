#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_sdk.py <bee2-sdk-dir>")

sdk = Path(sys.argv[1])
main_c = sdk / "src/sample/ble_peripheral/main.c"
text = main_c.read_text(encoding="utf-8")

old = 'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "BLE_PERIPHERAL";'
new = 'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "EH-MC16-TEST";'

if old not in text:
    raise SystemExit(f"expected device-name line not found in {main_c}")

main_c.write_text(text.replace(old, new, 1), encoding="utf-8")
print(f"patched {main_c}: BLE_PERIPHERAL -> EH-MC16-TEST")
