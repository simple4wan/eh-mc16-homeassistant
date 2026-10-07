#!/usr/bin/env python3
"""
Experimental Realtek Bee2 BLE DFU helper for EH-MC16.

Default mode is read-only probe. Flashing requires BOTH --flash and --yes.

The tool understands Realtek *_MP.bin files (512-byte MP metadata prefix) and
extracts the Bee2 AppPatch image beginning with its 1024-byte image header.
"""
from __future__ import annotations

import argparse
import asyncio
import struct
import sys
from pathlib import Path

from bleak import BleakClient, BleakScanner

DFU_SERVICE = "00006287-3c17-d293-8e48-14fe2e4da212"
DFU_DATA = "00006387-3c17-d293-8e48-14fe2e4da212"
DFU_CTRL = "00006487-3c17-d293-8e48-14fe2e4da212"

OP_START = 0x01
OP_IMAGE_INFO = 0x02
OP_VALIDATE = 0x03
OP_ACTIVATE_RESET = 0x04
OP_RESET = 0x05
OP_REPORT_TARGET = 0x06
OP_BUFFER_CHECK = 0x09
OP_IC_TYPE = 0x0B
OP_NOTIFICATION = 0x10

STATUS_SUCCESS = 0x01
BEE2_IC_TYPE = 0x05
APP_PATCH_ID = 0x2793
MP_HEADER_SIZE = 512
CTRL_HEADER_SIZE = 12


def load_image(path: Path) -> tuple[bytes, int]:
    raw = path.read_bytes()
    # Realtek production image: 512-byte MP metadata followed by Bee2 image.
    if path.name.endswith("_MP.bin"):
        if len(raw) <= MP_HEADER_SIZE:
            raise ValueError("MP image is too small")
        return raw[MP_HEADER_SIZE:], MP_HEADER_SIZE
    return raw, 0


def parse_ctrl_header(image: bytes) -> dict[str, int]:
    if len(image) < CTRL_HEADER_SIZE:
        raise ValueError("image too short")
    ic_type, secure_version, ctrl_flag, image_id, crc16, payload_len = struct.unpack_from(
        "<BBHHHI", image, 0
    )
    return {
        "ic_type": ic_type,
        "secure_version": secure_version,
        "ctrl_flag": ctrl_flag,
        "image_id": image_id,
        "crc16": crc16,
        "payload_len": payload_len,
    }


def validate_app_patch(image: bytes) -> dict[str, int]:
    h = parse_ctrl_header(image)
    if h["ic_type"] != BEE2_IC_TYPE:
        raise ValueError(f"wrong ic_type 0x{h['ic_type']:02X}; expected 0x05")
    if h["image_id"] != APP_PATCH_ID:
        raise ValueError(f"wrong image_id 0x{h['image_id']:04X}; expected 0x2793")
    expected = CTRL_HEADER_SIZE + h["payload_len"]
    if len(image) < expected:
        raise ValueError(
            f"truncated image: have {len(image)} bytes, header declares at least {expected}"
        )
    return h


class DfuSession:
    def __init__(self, client: BleakClient):
        self.client = client
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def _notify(self, _sender, data: bytearray):
        b = bytes(data)
        print("  notify:", b.hex(" "))
        self.queue.put_nowait(b)

    async def start_notify(self):
        await self.client.start_notify(DFU_CTRL, self._notify)

    async def command(self, payload: bytes, timeout: float = 5.0) -> bytes:
        while not self.queue.empty():
            self.queue.get_nowait()
        print("  write :", payload.hex(" "))
        await self.client.write_gatt_char(DFU_CTRL, payload, response=True)
        while True:
            rsp = await asyncio.wait_for(self.queue.get(), timeout)
            if len(rsp) >= 3 and rsp[0] == OP_NOTIFICATION and rsp[1] == payload[0]:
                return rsp

    async def probe(self):
        rsp = await self.command(bytes([OP_IC_TYPE]))
        if len(rsp) < 4 or rsp[2] != STATUS_SUCCESS:
            raise RuntimeError(f"IC type query failed: {rsp.hex(' ')}")
        print(f"ic_type: 0x{rsp[3]:02X}")
        if rsp[3] != BEE2_IC_TYPE:
            raise RuntimeError("target is not Bee2 ic_type 0x05")

        rsp = await self.command(bytes([OP_REPORT_TARGET]) + struct.pack("<H", APP_PATCH_ID))
        if len(rsp) < 3 or rsp[2] != STATUS_SUCCESS:
            raise RuntimeError(f"AppPatch query failed: {rsp.hex(' ')}")

        # EH-MC16 firmware observed in the wild returns either an older 9-byte
        # form (16-bit version + 32-bit offset) or newer 11-byte form
        # (32-bit version + 32-bit offset).
        if len(rsp) >= 11:
            version = struct.unpack_from("<I", rsp, 3)[0]
            offset = struct.unpack_from("<I", rsp, 7)[0]
        elif len(rsp) >= 9:
            version = struct.unpack_from("<H", rsp, 3)[0]
            offset = struct.unpack_from("<I", rsp, 5)[0]
        else:
            version = None
            offset = None
        print(f"AppPatch target info: version={version!r}, offset={offset!r}")
        return rsp

    async def flash(self, image: bytes):
        h = validate_app_patch(image)
        image_id = h["image_id"]

        # Read-only checks first.
        await self.probe()

        # Bee2 START_DFU: opcode + first 12 bytes of T_IMG_CTRL_HEADER_FORMAT
        # + 4 bytes reserved/padding.
        start = bytes([OP_START]) + image[:CTRL_HEADER_SIZE] + bytes(4)
        rsp = await self.command(start, timeout=8.0)
        if rsp[2] != STATUS_SUCCESS:
            raise RuntimeError(f"START_DFU rejected: {rsp.hex(' ')}")

        # Header is conveyed in START_DFU. Begin payload transfer after byte 12.
        offset = CTRL_HEADER_SIZE
        info = bytes([OP_IMAGE_INFO]) + struct.pack("<HI", image_id, offset)
        await self.client.write_gatt_char(DFU_CTRL, info, response=True)

        payload = image[offset:CTRL_HEADER_SIZE + h["payload_len"]]
        total = len(payload)
        sent = 0

        # Conservative 20-byte chunks for maximum compatibility with the
        # observed EH-MC16 GATT implementation.
        for pos in range(0, total, 20):
            chunk = payload[pos:pos + 20]
            await self.client.write_gatt_char(DFU_DATA, chunk, response=False)
            sent += len(chunk)
            if sent % 1024 < 20 or sent == total:
                print(f"  data  : {sent}/{total} bytes ({sent * 100 // total}%)")
            # Small pacing delay avoids overrunning old Bee2 firmware.
            await asyncio.sleep(0.006)

        rsp = await self.command(bytes([OP_VALIDATE]) + struct.pack("<H", image_id), timeout=12.0)
        if rsp[2] != STATUS_SUCCESS:
            raise RuntimeError(f"VALIDATE rejected: {rsp.hex(' ')}")

        print("validation successful")
        print("activating image; device should reboot...")
        try:
            await self.client.write_gatt_char(DFU_CTRL, bytes([OP_ACTIVATE_RESET]), response=True)
        except Exception as exc:
            # Disconnect during activation is expected on many Bee2 builds.
            print(f"activation write ended with disconnect/exception (often expected): {exc}")


async def find_target(name: str | None, address: str | None):
    if address:
        return address

    print("Scanning for BLE devices...")
    found: dict[str, tuple[object, str]] = {}

    def on_detect(device, adv):
        local_name = getattr(adv, "local_name", None) or getattr(device, "name", None) or ""
        found[str(device.address)] = (device, local_name)

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    await asyncio.sleep(10.0)
    await scanner.stop()

    if not found:
        raise RuntimeError(
            "no BLE advertisements were seen at all; check macOS Bluetooth permission "
            "for Terminal/Python and make sure the device is not still connected to the phone"
        )

    needle = (name or "").lower()
    matches = []
    for device, local_name in found.values():
        dev_name = getattr(device, "name", None) or ""
        hay = f"{local_name} {dev_name}".lower()
        if not needle or needle in hay:
            matches.append((device, local_name))

    if not matches:
        print("No matching name. Nearby BLE advertisements:")
        for device, local_name in sorted(found.values(), key=lambda x: (x[1] or "", str(x[0].address))):
            print(f"  {device.address}  local_name={local_name!r}  device_name={getattr(device, 'name', None)!r}")
        raise RuntimeError(
            f"no device matched {name!r}; on macOS use the CoreBluetooth UUID shown above with --address"
        )

    if len(matches) > 1:
        print("Multiple matches:")
        for device, local_name in matches:
            print(f"  {device.address}  {local_name or getattr(device, 'name', None)}")
        raise RuntimeError("multiple devices matched; pass --address")

    device, local_name = matches[0]
    print(f"Found {device.address}  {local_name or getattr(device, 'name', None)}")
    return device.address


async def amain(args):
    image = None
    if args.image:
        image, skipped = load_image(Path(args.image))
        h = validate_app_patch(image)
        print(
            f"image OK: skipped_mp={skipped}, ic_type=0x{h['ic_type']:02X}, "
            f"image_id=0x{h['image_id']:04X}, crc16=0x{h['crc16']:04X}, "
            f"payload_len={h['payload_len']}"
        )

    target = await find_target(args.name, args.address)
    async with BleakClient(target, timeout=15.0) as client:
        print("connected")
        s = DfuSession(client)
        await s.start_notify()

        if not args.flash:
            await s.probe()
            print("probe complete; no flash writes were performed")
            return

        if image is None:
            raise RuntimeError("--flash requires --image")
        if not args.yes:
            raise RuntimeError("--flash also requires --yes")
        await s.flash(image)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--address", help="BLE address/UUID; on macOS Bleak may use a UUID")
    p.add_argument("--name", default="EH-MC16", help="scan-name substring")
    p.add_argument("--image", help="Bee2 app bin or Realtek *_MP.bin")
    p.add_argument("--flash", action="store_true", help="perform DFU (writes flash)")
    p.add_argument("--yes", action="store_true", help="required acknowledgement for --flash")
    args = p.parse_args()

    if args.flash and not args.image:
        p.error("--flash requires --image")
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
