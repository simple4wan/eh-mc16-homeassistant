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
from Crypto.Cipher import AES

DFU_SERVICE = "00006287-3c17-d293-8e48-14fe2e4da212"
DFU_DATA = "00006387-3c17-d293-8e48-14fe2e4da212"
DFU_CTRL = "00006487-3c17-d293-8e48-14fe2e4da212"
OTA_SERVICE = "0000d0ff-3c17-d293-8e48-14fe2e4da212"
OTA_COMMAND = "0000ffd1-0000-1000-8000-00805f9b34fb"
OTA_GPIO_SNAPSHOT = "0000ffd5-0000-1000-8000-00805f9b34fb"
OTA_TEST_MODE = "0000ffd8-0000-1000-8000-00805f9b34fb"
OTA_DEVICE_INFO = "0000fff1-0000-1000-8000-00805f9b34fb"

OP_START = 0x01
OP_IMAGE_INFO = 0x02
OP_VALIDATE = 0x03
OP_ACTIVATE_RESET = 0x04
OP_RESET = 0x05
OP_REPORT_TARGET = 0x06
OP_BUFFER_CHECK = 0x09
OP_REPORT_BUFFER_CRC = 0x0A
OP_IC_TYPE = 0x0B
OP_NOTIFICATION = 0x10

STATUS_SUCCESS = 0x01
BEE2_IC_TYPE = 0x05
APP_PATCH_ID = 0x2793
MP_HEADER_SIZE = 512
CTRL_HEADER_SIZE = 12
IMAGE_HEADER_SIZE = 1024

# Realtek reference OTA-client default AES-256 key.
DEFAULT_AES_KEY = bytes([
    0x4E, 0x46, 0xF8, 0xC5, 0x09, 0x2B, 0x29, 0xE2,
    0x9A, 0x97, 0x1A, 0x0C, 0xD1, 0xF6, 0x10, 0xFB,
    0x1F, 0x67, 0x63, 0xDF, 0x80, 0x7A, 0x7E, 0x70,
    0x96, 0x0D, 0x4C, 0xD3, 0x11, 0x8E, 0x60, 0x1A,
])


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

    def _find_char(self, service_uuid: str, char_uuid: str):
        for service in self.client.services:
            if str(service.uuid).lower() != service_uuid.lower():
                continue
            for char in service.characteristics:
                if str(char.uuid).lower() == char_uuid.lower():
                    return char
        return None

    async def enter_ota_mode(self):
        ota_char = self._find_char(OTA_SERVICE, OTA_COMMAND)
        if ota_char is None:
            raise RuntimeError("FFD1 OTA command characteristic not found under D0FF service")

        print(
            f"OTA command handle=0x{ota_char.handle:04X} "
            f"service={OTA_SERVICE}"
        )
        print("writing OTA enter command: 01")
        try:
            await self.client.write_gatt_char(ota_char, b"\x01", response=False)
        except Exception as exc:
            # The firmware intentionally disconnects immediately after accepting
            # OTA_VALUE_ENTER, so CoreBluetooth may surface the disconnect here.
            print(f"OTA enter write ended with disconnect/exception (often expected): {exc}")

        print("waiting for reboot into OTA mode...")
        await asyncio.sleep(5.0)

    async def command(self, payload: bytes, timeout: float = 5.0) -> bytes:
        while not self.queue.empty():
            self.queue.get_nowait()
        print("  write :", payload.hex(" "))
        await self.client.write_gatt_char(DFU_CTRL, payload, response=True)
        while True:
            rsp = await asyncio.wait_for(self.queue.get(), timeout)
            if len(rsp) >= 3 and rsp[0] == OP_NOTIFICATION and rsp[1] == payload[0]:
                return rsp

    async def read_gpio_snapshot(self) -> int:
        gpio_char = self._find_char(OTA_SERVICE, OTA_GPIO_SNAPSHOT)
        if gpio_char is None:
            raise RuntimeError("FFD5 GPIO snapshot characteristic not found under D0FF service")
        raw = bytes(await self.client.read_gatt_char(gpio_char))
        if len(raw) != 4:
            raise RuntimeError(f"unexpected GPIO snapshot length {len(raw)}: {raw.hex(' ')}")
        return struct.unpack("<I", raw)[0]

    async def watch_gpio(self, seconds: float = 15.0):
        gpio_char = self._find_char(OTA_SERVICE, OTA_GPIO_SNAPSHOT)
        if gpio_char is None:
            raise RuntimeError(
                "FFD5 GPIO snapshot characteristic not found; flash the GPIO-probe firmware first"
            )
        print(
            f"GPIO watch: handle=0x{gpio_char.handle:04X}, duration={seconds:g}s"
        )
        print("Press and release the physical button several times during this window.")
        prev = None
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            raw = bytes(await self.client.read_gatt_char(gpio_char))
            if len(raw) != 4:
                raise RuntimeError(f"unexpected GPIO snapshot: {raw.hex(' ')}")
            value = struct.unpack("<I", raw)[0]
            if prev is None:
                print(f"  DATAIN=0x{value:08X}")
            elif value != prev:
                diff = value ^ prev
                changed = [str(bit) for bit in range(32) if diff & (1 << bit)]
                print(
                    f"  DATAIN 0x{prev:08X} -> 0x{value:08X} "
                    f"changed GPIO bits: {', '.join(changed)}"
                )
            prev = value
            await asyncio.sleep(0.10)
        print("GPIO watch complete; no GPIO configuration or output writes were performed")

    async def test_p05(self):
        test_char = self._find_char(OTA_SERVICE, OTA_TEST_MODE)
        if test_char is None:
            raise RuntimeError("FFD8 probe-control characteristic not found under D0FF service")

        print("Testing P0_5 only: LOW -> input -> HIGH -> input")
        print("Watch the LED and listen for a relay click.")
        try:
            await self.client.write_gatt_char(test_char, bytes([1]), response=False)
            await asyncio.sleep(0.7)
            await self.client.write_gatt_char(test_char, bytes([0]), response=False)
            await asyncio.sleep(0.7)
            await self.client.write_gatt_char(test_char, bytes([2]), response=False)
            await asyncio.sleep(0.7)
        finally:
            try:
                await self.client.write_gatt_char(test_char, bytes([0]), response=False)
            except Exception:
                pass
        print("P0_5 restored to input mode")

    async def read_device_info(self):
        try:
            target_char = self._find_char(OTA_SERVICE, OTA_DEVICE_INFO)

            if target_char is None:
                raise RuntimeError("FFF1 device-info characteristic not found under D0FF service")

            raw = bytes(await self.client.read_gatt_char(target_char))
            print(
                f"device-info handle=0x{target_char.handle:04X} "
                f"service={OTA_SERVICE}: {raw.hex(' ')}"
            )
        except Exception as exc:
            print(f"device-info: unavailable ({exc})")
            return None

        if len(raw) == 12 and raw[1] == 0x01:
            mode = raw[3]
            info = {
                "ic_type": raw[0],
                "ota_version": raw[1],
                "secure_version": raw[2],
                "buffer_check": bool(mode & 0x01),
                "aes": bool(mode & 0x02),
                "aes_mode_all": bool(mode & 0x04),
                "copy_img": bool(mode & 0x08),
                "multi_img": bool(mode & 0x10),
                "max_buffer": struct.unpack_from("<H", raw, 4)[0],
            }
            print(
                "device-info parsed: "
                f"ic_type=0x{info['ic_type']:02X}, ota_version={info['ota_version']}, "
                f"buffer_check={info['buffer_check']}, aes={info['aes']}, "
                f"aes_mode_all={info['aes_mode_all']}, max_buffer={info['max_buffer']}"
            )
            return info

        print("device-info: unrecognized format")
        return None

    @staticmethod
    def _aes_encrypt_blocks(data: bytes, key: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_ECB)
        full = len(data) // 16 * 16
        if full == 0:
            return data
        return cipher.encrypt(data[:full]) + data[full:]

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
            return None

        # Realtek response:
        # 10 09 <support> <max_buffer_le16> <mtu_le16>
        support = rsp[2]
        if len(rsp) >= 7:
            max_buffer = struct.unpack_from("<H", rsp, 3)[0]
            mtu = struct.unpack_from("<H", rsp, 5)[0]
            print(
                f"buffer-check: support/status=0x{support:02X}, "
                f"max_buffer={max_buffer}, mtu={mtu}"
            )
            return support, max_buffer, mtu

        print(f"buffer-check: response={rsp.hex(' ')}")
        return None

    @staticmethod
    def _buffer_crc(data: bytes) -> int:
        # Matches Realtek OTACommand.m: XOR little-endian uint16 words, then htons().
        # Buffer-check blocks are normally even-sized. Pad an odd final byte with 0.
        if len(data) & 1:
            data = data + b"\x00"
        value = 0
        for i in range(0, len(data), 2):
            value ^= data[i] | (data[i + 1] << 8)
        return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)

    @staticmethod
    def _send_unit_from_mtu(mtu: int) -> int:
        # Matches Realtek iOS OTA client's getMaxTxUnitFromMtu().
        unit = 16
        while mtu // unit > 1:
            unit *= 2
        return unit

    async def _send_buffer_checked(self, data: bytes, max_buffer: int, mtu: int, encrypt: bool = False):
        send_unit = self._send_unit_from_mtu(mtu)
        check_unit = (max_buffer // send_unit) * send_unit
        if check_unit <= 0:
            raise RuntimeError(f"invalid buffer parameters: max_buffer={max_buffer}, mtu={mtu}")

        print(f"buffer-check transfer: send_unit={send_unit}, check_unit={check_unit}")
        total = len(data)
        pos = 0

        while pos < total:
            # The first transmitted region starts at image offset 12. Realtek's
            # reference client therefore fills the first check-buffer only up
            # to absolute image offset check_unit.
            if pos == 0:
                block_len = min(total, max(1, check_unit - CTRL_HEADER_SIZE))
            else:
                block_len = min(total - pos, check_unit)

            block = data[pos:pos + block_len]

            # Realtek's reference client encrypts each buffer-check block
            # independently, and only complete 16-byte AES blocks. This matters
            # for the first block (2036 bytes when starting at image offset 12):
            # its final 4 bytes are intentionally left plaintext, and the next
            # 2048-byte check block restarts AES alignment from byte 0.
            wire_block = self._aes_encrypt_blocks(block, DEFAULT_AES_KEY) if encrypt else block

            for off in range(0, len(wire_block), send_unit):
                chunk = wire_block[off:off + send_unit]
                await self.client.write_gatt_char(DFU_DATA, chunk, response=False)
                await asyncio.sleep(0.003)

            crc = self._buffer_crc(wire_block)
            rsp = await self.command(
                bytes([OP_REPORT_BUFFER_CRC]) + struct.pack("<HH", len(block), crc),
                timeout=12.0,
            )
            if len(rsp) < 3:
                raise RuntimeError(f"buffer-check short response: {rsp.hex(' ')}")
            if rsp[2] != STATUS_SUCCESS:
                retry_addr = struct.unpack_from("<I", rsp, 3)[0] if len(rsp) >= 7 else None
                raise RuntimeError(
                    f"buffer-check failed status=0x{rsp[2]:02X}, retry_addr={retry_addr!r}"
                )

            pos += len(block)
            print(f"  checked: {pos}/{total} bytes ({pos * 100 // total}%)")

    async def flash(self, image: bytes, devinfo_override=None):
        h = validate_app_patch(image)
        image_id = h["image_id"]

        # Read-only checks first.
        await self.probe()
        if devinfo_override is not None:
            devinfo = devinfo_override
            print("using OTA device-info captured before reboot")
        else:
            devinfo = await self.read_device_info()

        use_aes = bool(devinfo and devinfo.get("aes"))
        aes_all = bool(devinfo and devinfo.get("aes_mode_all"))
        if use_aes:
            print("target requires encrypted OTA; using Realtek reference AES-256 key")

        # Bee2 START_DFU: opcode + 16-byte encrypted/plain control block.
        start_block = image[:CTRL_HEADER_SIZE] + bytes(4)
        if use_aes:
            start_block = self._aes_encrypt_blocks(start_block, DEFAULT_AES_KEY)
        start = bytes([OP_START]) + start_block
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

        buf = await self.probe_buffer_check()
        if not buf or buf[0] != 0x01:
            raise RuntimeError(
                "target did not enable buffer-check; refusing first experimental flash"
            )
        _, max_buffer, mtu = buf
        await self._send_buffer_checked(
            payload, max_buffer, mtu, encrypt=(use_aes and aes_all)
        )

        rsp = await self.command(bytes([OP_VALIDATE]) + struct.pack("<H", image_id), timeout=12.0)
        if rsp[2] != STATUS_SUCCESS:
            raise RuntimeError(f"VALIDATE rejected: {rsp.hex(' ')}")

        print("validation successful")
        print("")
        print("Firmware has been transferred and validated, but is NOT active yet.")
        print("Type ACTIVATE to switch to the new image and reboot, or anything else to stop here.")
        answer = (await asyncio.to_thread(input, "> ")).strip()
        if answer != "ACTIVATE":
            print("activation cancelled; current running firmware remains active for now")
            return

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


async def find_beetgt_after_reboot(timeout: float = 15.0):
    print("Scanning immediately for BeeTgt...")
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        found = await scan_snapshot(2.0)
        for device, adv in found.values():
            local_name = getattr(adv, "local_name", None) or ""
            dev_name = getattr(device, "name", None) or ""
            service_uuids = [
                str(x).lower()
                for x in (getattr(adv, "service_uuids", None) or [])
            ]
            mfg = getattr(adv, "manufacturer_data", None) or {}
            if (
                "beetgt" in f"{local_name} {dev_name}".lower()
                or (DFU_SERVICE.lower() in service_uuids and 0x005D in mfg)
            ):
                print(f"Found OTA target {device.address}  {local_name or dev_name or 'BeeTgt'}")
                return device.address
        await asyncio.sleep(0.5)
    raise RuntimeError("BeeTgt OTA target was not found after reboot")


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
    if args.enter_ota_flash:
        if image is None:
            raise RuntimeError("--enter-ota-flash requires --image")
        if not args.yes:
            raise RuntimeError("--enter-ota-flash also requires --yes")

        async with BleakClient(target, timeout=15.0) as client:
            print("connected to application")
            s = DfuSession(client)
            await s.start_notify()
            await s.probe()
            devinfo = await s.read_device_info()
            if not devinfo:
                raise RuntimeError("could not capture OTA device-info before reboot")
            await s.enter_ota_mode()

        beetgt = await find_beetgt_after_reboot()
        async with BleakClient(beetgt, timeout=15.0) as client:
            print("connected to BeeTgt OTA mode")
            s = DfuSession(client)
            await s.start_notify()
            await s.flash(image, devinfo_override=devinfo)
        return

    if args.enter_ota:
        async with BleakClient(target, timeout=15.0) as client:
            print("connected")
            s = DfuSession(client)
            await s.enter_ota_mode()

        print("Scanning after OTA-mode reboot...")
        after = await scan_snapshot(12.0)
        if not after:
            print("No BLE advertisements seen after OTA-mode reboot.")
            return

        print("BLE devices seen after OTA-mode reboot:")
        for device, adv in sorted(
            after.values(),
            key=lambda x: ((getattr(x[1], "local_name", None) or ""), str(x[0].address)),
        ):
            local_name = getattr(adv, "local_name", None) or ""
            dev_name = getattr(device, "name", None)
            service_uuids = getattr(adv, "service_uuids", None) or []
            mfg = getattr(adv, "manufacturer_data", None) or {}
            if (
                "realtek" in local_name.lower()
                or "eh-mc16" in local_name.lower()
                or DFU_SERVICE.lower() in [str(x).lower() for x in service_uuids]
                or OTA_SERVICE.lower() in [str(x).lower() for x in service_uuids]
                or 0x005D in mfg
            ):
                print(
                    f"  {device.address}  local_name={local_name!r}  "
                    f"device_name={dev_name!r} services={service_uuids!r} "
                    f"mfg_ids={[hex(x) for x in mfg.keys()]}"
                )
        print("enter-ota complete; no firmware image was transmitted")
        return

    async with BleakClient(target, timeout=15.0) as client:
        print("connected")
        s = DfuSession(client)

        if args.gpio_watch is not None:
            await s.watch_gpio(args.gpio_watch)
            return

        if args.test_p05:
            await s.test_p05()
            return

        await s.start_notify()

        if not args.flash:
            await s.probe()
            await s.read_device_info()
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
    p.add_argument(
        "--enter-ota",
        action="store_true",
        help="write OTA_VALUE_ENTER (0x01) to D0FF/FFD1, reboot into OTA mode, then rescan",
    )
    p.add_argument(
        "--enter-ota-flash",
        action="store_true",
        help="capture OTA policy, reboot into BeeTgt, then perform DFU there",
    )
    p.add_argument(
        "--gpio-watch",
        nargs="?",
        const=15.0,
        type=float,
        metavar="SECONDS",
        help="watch the read-only D0FF/FFD5 GPIO DATAIN snapshot (default: 15s)",
    )
    p.add_argument(
        "--test-p05",
        action="store_true",
        help="briefly test only P0_5, then restore input mode",
    )
    p.add_argument("--flash", action="store_true", help="perform DFU (writes flash)")
    p.add_argument("--yes", action="store_true", help="required acknowledgement for --flash")
    args = p.parse_args()

    if args.gpio_watch is not None and (args.enter_ota or args.enter_ota_flash or args.flash or args.image or args.test_p05):
        p.error("--gpio-watch cannot be combined with OTA/flash/image/test options")
    if args.test_p05 and (args.enter_ota or args.enter_ota_flash or args.flash or args.image):
        p.error("--test-p05 cannot be combined with OTA/flash/image options")
    if sum(bool(x) for x in (args.enter_ota, args.enter_ota_flash, args.flash)) > 1:
        p.error("--enter-ota, --enter-ota-flash and --flash are mutually exclusive")
    if args.enter_ota and args.image:
        p.error("--enter-ota does not use --image")
    if args.flash and not args.image:
        p.error("--flash requires --image")
    if args.enter_ota_flash and not args.image:
        p.error("--enter-ota-flash requires --image")
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
