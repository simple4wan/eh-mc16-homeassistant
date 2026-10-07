# EH-MC16 native HomeKit BLE port

Pinned HomeKit ADK: `fb201f98f5fdc7fef6a455054f08b59cca5d1ec8`.

The native HomeKit implementation is being brought up in layers so the already-working Bee2 OTA path stays recoverable.

## Port boundary

The first BLE transport layer must implement the ADK's `HAPPlatformBLEPeripheralManager` interface on top of the Realtek Bee2 GATT server. The required operations are:

- publish/remove services, characteristics and descriptors
- start/stop connectable advertising
- surface connect/disconnect callbacks
- surface ATT read/write callbacks
- send indications
- expose stable attribute handles

The non-BLE PAL layer needs:

- `HAPPlatformKeyValueStore`: persistent HomeKit pairing data in a dedicated flash region
- `HAPPlatformRandomNumberFill`: cryptographically secure random bytes
- `HAPPlatformClockGetCurrent`
- `HAPPlatformTimerRegister/Deregister`

Factory reset will purge only the HAP key-value domains, then reboot. It must not erase the Bee2 OTA metadata or application image.

## Accessory model

Target category: Outlet.

Hardware mapping already verified:

- button: P3_2, active low
- relay: P2_5, HIGH = outlet ON
- LED red: P2_2=HIGH / P2_3=LOW
- LED blue: P2_2=LOW / P2_3=HIGH

The HomeKit On characteristic and the physical button will share one internal state setter so events remain synchronized in both directions.

## Bring-up order

1. CI pins and validates the exact HomeKit ADK revision.
2. Implement the Bee2 BLE peripheral-manager PAL.
3. Implement timer/clock/RNG.
4. Implement flash-backed HAP KVS.
5. Define minimal Outlet attribute database.
6. Start HAP accessory server and verify discovery in Apple Home.
7. Enable Pair Setup / Pair Verify and persist pairings.
8. Wire the 10-second factory-reset hook to purge HAP KVS.
