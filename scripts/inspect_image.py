#!/usr/bin/env python3
from pathlib import Path
import struct
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: inspect_image.py <image.bin> <report.txt>")

path = Path(sys.argv[1])
out = Path(sys.argv[2])
data = path.read_bytes()

if len(data) < 12:
    raise SystemExit("image is too short to contain a Bee2 control header")

ic_type, secure_version, ctrl_flag, image_id, crc16, payload_len = struct.unpack_from("<BBHHHI", data, 0)

lines = [
    f"file={path}",
    f"size={len(data)}",
    f"ic_type=0x{ic_type:02X}",
    f"secure_version=0x{secure_version:02X}",
    f"ctrl_flag=0x{ctrl_flag:04X}",
    f"image_id=0x{image_id:04X}",
    f"crc16=0x{crc16:04X}",
    f"payload_len={payload_len}",
    f"header_prefix={data[:32].hex(' ')}",
]

# Expected for RTL8762C/Bee2 application image.
if ic_type != 0x05:
    lines.append("WARNING: unexpected ic_type (expected 0x05 for Bee2)")
if image_id != 0x2793:
    lines.append("WARNING: unexpected image_id (expected 0x2793 / AppPatch)")
else:
    lines.append("app_patch_header=OK")

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
