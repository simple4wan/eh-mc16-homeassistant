#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: check_hap_adk.py <HomeKitADK-dir>")

root = Path(sys.argv[1])

required = [
    "HAP/HAP.h",
    "HAP/HAPBLEAccessoryServer.c",
    "HAP/HAPBLEAccessoryServer+Advertising.c",
    "PAL/HAPPlatformBLEPeripheralManager.h",
    "PAL/HAPPlatformKeyValueStore.h",
    "PAL/HAPPlatformRandomNumber.h",
    "PAL/HAPPlatformClock.h",
    "PAL/HAPPlatformTimer.h",
    "Applications/Lightbulb/App.c",
    "Applications/Lightbulb/DB.c",
]

missing = [p for p in required if not (root / p).is_file()]
if missing:
    raise SystemExit("missing pinned HomeKit ADK files: " + ", ".join(missing))

ble = (root / "PAL/HAPPlatformBLEPeripheralManager.h").read_text(encoding="utf-8")
apis = [
    "HAPPlatformBLEPeripheralManagerSetDelegate",
    "HAPPlatformBLEPeripheralManagerSetDeviceAddress",
    "HAPPlatformBLEPeripheralManagerSetDeviceName",
    "HAPPlatformBLEPeripheralManagerRemoveAllServices",
    "HAPPlatformBLEPeripheralManagerAddService",
    "HAPPlatformBLEPeripheralManagerAddCharacteristic",
    "HAPPlatformBLEPeripheralManagerAddDescriptor",
    "HAPPlatformBLEPeripheralManagerPublishServices",
    "HAPPlatformBLEPeripheralManagerStartAdvertising",
    "HAPPlatformBLEPeripheralManagerStopAdvertising",
    "HAPPlatformBLEPeripheralManagerCancelCentralConnection",
    "HAPPlatformBLEPeripheralManagerSendHandleValueIndication",
]
missing_apis = [name for name in apis if name not in ble]
if missing_apis:
    raise SystemExit("unexpected ADK BLE API surface: " + ", ".join(missing_apis))

print("HomeKit ADK pin: OK")
print("HAP BLE core: OK")
print("BLE PAL surface: %d functions verified" % len(apis))
print("Next port targets: BLE manager, KVS, RNG, clock/timers, Outlet accessory DB")
