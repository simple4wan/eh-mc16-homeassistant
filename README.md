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
