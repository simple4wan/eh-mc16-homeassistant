# EH-MC16 Home Assistant firmware research

Experimental firmware work for the Ehong EH-MC16 (Realtek Bee2 / ic_type 0x05).

## Current hardware/DFU findings

The original device exposes the Realtek Bee2 DFU service:

- Service: `00006287-3c17-d293-8e48-14fe2e4da212`
- Data: `00006387-3c17-d293-8e48-14fe2e4da212`
- Control point: `00006487-3c17-d293-8e48-14fe2e4da212`
- `0x0B` (RECEIVE_IC_TYPE) returns `10 0B 01 05`, confirming Bee2 `ic_type = 0x05`.
- Application image ID used by the Bee2 SDK is `AppPatch = 0x2793`.
- Bee2 application images use a 1024-byte image header.

## First milestone

The first build intentionally does **not** drive the smart-plug relay. It only builds the stock Realtek BLE peripheral example with the Bluetooth device name changed to:

`EH-MC16-TEST`

This is for validating the compiler/toolchain and generated AppPatch image before any OTA write is attempted.

## Build

GitHub Actions clones the public Bee2/RTL8762C GCC SDK mirror and builds the `ble_peripheral_gcc` example.

The workflow uploads the generated firmware files as an Actions artifact.

> WARNING: Do not flash artifacts from this repository until the image header and OTA compatibility have been verified against the target EH-MC16. Smart plugs contain mains voltage; never connect a PC debugger/USB-UART to a mains-powered non-isolated board.


## BLE DFU helper (experimental)

A Python/Bleak helper now lives at `tools/ble_dfu.py`.

Read-only probe on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python tools/ble_dfu.py --name EH-MC16
```

The default mode is probe-only and does not write firmware. It verifies the Bee2 DFU service, reads `ic_type`, and queries AppPatch target info.

Firmware flashing is intentionally gated behind both `--flash` and `--yes`. Do not use it yet until the generated image and target-specific DFU behavior have been validated further.

## Confirmed EH-MC16 hardware map

Hardware probing on the target smart plug established the following GPIO mapping:

- Button: `P3_2` (active low)
- Relay: `P2_5` (`HIGH = outlet ON`, `LOW = outlet OFF`)
- Two-color LED:
  - `P2_2 = HIGH, P2_3 = LOW` -> red
  - `P2_2 = LOW, P2_3 = HIGH` -> blue

The current firmware now boots with the outlet OFF / LED red and toggles the relay + LED on each physical button press.

## Native HomeKit direction

The next target is native HAP over Bluetooth LE, without Home Assistant or Wi-Fi.

For the HAP implementation, use Apple's open-source HomeKit ADK for non-commercial prototyping instead of reimplementing HAP crypto and pairing from scratch.

Pinned upstream:

- Repository: `apple/HomeKitADK`
- Commit: `fb201f98f5fdc7fef6a455054f08b59cca5d1ec8`

The existing Realtek Bee2 BLE/OTA stack remains the hardware transport foundation. The port needs to provide the HomeKit ADK platform layer for BLE GATT, persistent key-value storage, random numbers, clock/timers, and run-loop integration while preserving the verified Bee2 OTA path.

