#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_layout_bridge.py <bee2-sdk-dir>")

sdk = Path(sys.argv[1])
main_c = sdk / "src/app/silent_ota/main.c"
board_h = sdk / "board/evb/silent_ota_gcc/board.h"
flash_map_h = sdk / "board/evb/silent_ota_gcc/flash_map.h"

# Expand 256 KiB reference layout to the EH-MC16 512 KiB device.
flash = flash_map_h.read_text()
repls = {
    "#define FLASH_SIZE                      0x00040000  //256K Bytes":
    "#define FLASH_SIZE                      0x00080000  //512K Bytes",
    "#define OTA_BANK0_SIZE                  0x00023000  //140K Bytes":
    "#define OTA_BANK0_SIZE                  0x0003C000  //240K Bytes",
    "#define FTL_ADDR                        0x00825000":
    "#define FTL_ADDR                        0x0083E000",
    "#define OTA_TMP_ADDR                    0x00829000":
    "#define OTA_TMP_ADDR                    0x00842000",
    "#define OTA_TMP_SIZE                    0x00017000  //92K Bytes":
    "#define OTA_TMP_SIZE                    0x00030000  //192K Bytes",
    "#define BANK0_APP_SIZE                  0x00017000  //92K Bytes":
    "#define BANK0_APP_SIZE                  0x00030000  //192K Bytes",
    "#define BANK0_APP_DATA1_ADDR            0x00825000":
    "#define BANK0_APP_DATA1_ADDR            0x0083E000",
}
for old, new in repls.items():
    if old not in flash:
        raise SystemExit(f"missing flash-map marker: {old}")
    flash = flash.replace(old, new, 1)
flash_map_h.write_text(flash)

# Keep the reference silent-OTA application otherwise intact. Enable
# buffer-check because our BLE updater already supports it.
board = board_h.read_text()
board = board.replace(
    "#define DFU_BUFFER_CHECK_ENABLE     (g_ota_mode & 0x1)",
    "#define DFU_BUFFER_CHECK_ENABLE     1",
    1,
)
board_h.write_text(board)

# Make the bridge easy to recognize before the second OTA.
main = main_c.read_text()
main = main.replace(
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "RealTekDfu";',
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "EH-MC16-BRG";',
    1,
)
old_adv = """    0x0B,                               /* length     */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'R', 'e', 'a', 'l', 'T', 'e', 'k', 'D', 'f', 'u',
"""
new_adv = """    0x0C,                               /* type + 11-byte name */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'E', 'H', '-', 'M', 'C', '1', '6', '-', 'B', 'R', 'G',
"""
if old_adv not in main:
    raise SystemExit("missing RealTekDfu advertising marker")
main = main.replace(old_adv, new_adv, 1)
main_c.write_text(main)

print("patched 512KiB layout bridge")
