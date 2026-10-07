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
IMAGE_HEADER_SIZE = 1024


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
    expected = IMAGE_HEADER_SIZE + h["payload_len"]
    if len(image) < expected:
        raise ValueError(
            f"truncated image: have {len(image)} bytes, expected at least "
            f"{IMAGE_HEADER_SIZE}+{h['payload_len']}={expected}"
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

    async def probe_buffer_check(self):
        print("probing buffer-check capability...")
        try:
            rsp = await self.command(bytes([OP_BUFFER_CHECK]), timeout=5.0)
        except asyncio.TimeoutError:
            print("buffer-check: no notification (likely unsupported by this firmware)")
            return None

        if len(rsp) < 3:
            print(f"buffer-check: short response: {rsp.hex(' ')}")
            return rsp

        # Realtek response:
        # 10 09 <support/status> [max_buffer_le16] [mtu_le16]
        support = rsp[2]
        if len(rsp) >= 7:
            max_buffer = struct.unpack_from("<H", rsp, 3)[0]
            mtu = struct.unpack_from("<H", rsp, 5)[0]
            print(
                f"buffer-check: support/status=0x{support:02X}, "
                f"max_buffer={max_buffer}, mtu={mtu}"
            )
        else:
            print(f"buffer-check: response={rsp.hex(' ')}")
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

        # START_DFU conveys the first 12 bytes. Realtek Bee2 then resumes the
        # image stream at offset 12, so bytes 12..1023 of the 1 KiB image header
        # MUST also be transferred before the application payload.
        offset = CTRL_HEADER_SIZE
        info = bytes([OP_IMAGE_INFO]) + struct.pack("<HI", image_id, offset)
        await self.client.write_gatt_char(DFU_CTRL, info, response=True)

        image_end = IMAGE_HEADER_SIZE + h["payload_len"]
        payload = image[offset:image_end]
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


async def scan_snapshot(seconds: float = 8.0):
    found: dict[str, tuple[object, object]] = {}

    def on_detect(device, adv):
        found[str(device.address)] = (device, adv)

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    await asyncio.sleep(seconds)
    await scanner.stop()
    return found


async def identify_by_power_cycle():
    print("IDENTIFY MODE")
    print("1) Unplug/power OFF only the EH-MC16 smart plug, then press Enter.")
    await asyncio.to_thread(input)
    print("Scanning baseline...")
    before = await scan_snapshot(8.0)
    print(f"Baseline saw {len(before)} BLE devices.")
    print("2) Plug/power ON the EH-MC16, wait about 2 seconds, then press Enter.")
    await asyncio.to_thread(input)
    print("Scanning after power-on...")
    after = await scan_snapshot(10.0)

    new_ids = [k for k in after.keys() if k not in before]
    if not new_ids:
        print("No new CoreBluetooth UUID appeared. Try again with the plug closer to the Mac.")
        return

    print("New BLE devices seen after EH-MC16 power-on:")
    for k in new_ids:
        device, adv = after[k]
        local_name = getattr(adv, "local_name", None) or ""
        dev_name = getattr(device, "name", None)
        service_uuids = getattr(adv, "service_uuids", None) or []
        mfg = getattr(adv, "manufacturer_data", None) or {}
        print(
            f"  {device.address}  local_name={local_name!r}  device_name={dev_name!r} "
            f"services={service_uuids!r} mfg_ids={[hex(x) for x in mfg.keys()]}"
        )
    print("\nUse a candidate with:")
    print("  python tools/ble_dfu.py --address <UUID>")


async def find_target(name: str | None, address: str | None):
    if address:
        return address

    print("Scanning for BLE devices...")
    found: dict[str, tuple[object, object]] = {}

    def on_detect(device, adv):
        found[str(device.address)] = (device, adv)

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
    dfu_advertised = []

    for device, adv in found.values():
        local_name = getattr(adv, "local_name", None) or ""
        dev_name = getattr(device, "name", None) or ""
        service_uuids = [str(x).lower() for x in (getattr(adv, "service_uuids", None) or [])]
        hay = f"{local_name} {dev_name}".lower()

        if DFU_SERVICE.lower() in service_uuids:
            dfu_advertised.append((device, adv))

        if not needle or needle in hay:
            matches.append((device, adv))

    if len(matches) == 1:
        device, adv = matches[0]
        local_name = getattr(adv, "local_name", None) or getattr(device, "name", None)
        print(f"Found {device.address}  {local_name}")
        return device.address

    if len(matches) > 1:
        print("Multiple name matches:")
        for device, adv in matches:
            local_name = getattr(adv, "local_name", None) or getattr(device, "name", None)
            print(f"  {device.address}  {local_name}")
        raise RuntimeError("multiple devices matched; pass --address")

    if len(dfu_advertised) == 1:
        device, adv = dfu_advertised[0]
        print(f"Found DFU service in advertisement: {device.address}")
        return device.address

    # EH-MC16 may advertise without a local name on macOS. In that case,
    # probe only unnamed devices by connecting and checking discovered GATT services.
    unnamed = []
    for device, adv in found.values():
        local_name = getattr(adv, "local_name", None) or ""
        dev_name = getattr(device, "name", None) or ""
        if not local_name and not dev_name:
            unnamed.append((device, adv))

    if unnamed:
        print(f"No name match; probing {len(unnamed)} unnamed BLE devices for the Realtek DFU service...")
        for idx, (device, adv) in enumerate(unnamed, 1):
            print(f"  [{idx}/{len(unnamed)}] {device.address}", end="", flush=True)
            try:
                async with BleakClient(device, timeout=4.0) as probe_client:
                    uuids = {str(s.uuid).lower() for s in probe_client.services}
                    if DFU_SERVICE.lower() in uuids:
                        print("  <-- EH-MC16 DFU service found")
                        return device.address
                    print("  no")
            except Exception:
                print("  unavailable")

    print("No matching name or DFU service found. Nearby BLE advertisements:")
    for device, adv in sorted(found.values(), key=lambda x: ((getattr(x[1], "local_name", None) or ""), str(x[0].address))):
        local_name = getattr(adv, "local_name", None) or ""
        dev_name = getattr(device, "name", None)
        service_uuids = getattr(adv, "service_uuids", None) or []
        mfg = getattr(adv, "manufacturer_data", None) or {}
        print(
            f"  {device.address}  local_name={local_name!r}  "
            f"device_name={dev_name!r}  services={service_uuids!r}  "
            f"mfg_ids={[hex(k) for k in mfg.keys()]}"
        )

    raise RuntimeError(
        f"no device matched {name!r} and no device exposed the Realtek DFU service"
    )


async def amain(args):
    if args.identify:
        await identify_by_power_cycle()
        return

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
            await s.probe_buffer_check()
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
    p.add_argument(
        "--identify",
        action="store_true",
        help="identify the EH-MC16 by comparing BLE scans before/after a power cycle",
    )
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
