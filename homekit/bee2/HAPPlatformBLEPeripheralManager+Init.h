#ifndef EH_MC16_HAP_PLATFORM_BLE_PERIPHERAL_MANAGER_INIT_H
#define EH_MC16_HAP_PLATFORM_BLE_PERIPHERAL_MANAGER_INIT_H

#include "HAPPlatformBLEPeripheralManager.h"
#include <profile_server.h>
#include <gatt.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EH_HAP_MAX_SERVICES 6
#define EH_HAP_MAX_ATTRS_PER_SERVICE 32
#define EH_HAP_MAX_CONST_BYTES 32

typedef struct {
    T_ATTRIB_APPL attrs[EH_HAP_MAX_ATTRS_PER_SERVICE];
    uint8_t uuidValues[EH_HAP_MAX_ATTRS_PER_SERVICE][16];
    uint8_t constValues[EH_HAP_MAX_ATTRS_PER_SERVICE][EH_HAP_MAX_CONST_BYTES];
    uint16_t constLengths[EH_HAP_MAX_ATTRS_PER_SERVICE];
    uint16_t numAttrs;
    uint16_t startHandle;
    T_SERVER_ID serviceId;
    bool registered;
} EH_HAP_BLE_Service;

struct HAPPlatformBLEPeripheralManager {
    HAPPlatformBLEPeripheralManagerDelegate delegate;
    HAPPlatformBLEPeripheralManagerDeviceAddress deviceAddress;
    char deviceName[65];

    EH_HAP_BLE_Service services[EH_HAP_MAX_SERVICES];
    uint8_t numServices;
    int8_t currentService;
    uint16_t nextHandle;

    uint8_t advertisingBytes[31];
    uint8_t scanResponseBytes[31];
    uint8_t numAdvertisingBytes;
    uint8_t numScanResponseBytes;

    bool isDeviceAddressSet;
    bool didPublishAttributes;
    bool stackReady;
    bool advertisingRequested;
    bool advertising;
    bool connected;
    uint8_t connId;
};

typedef struct {
    uint16_t firstHandle;
} HAPPlatformBLEPeripheralManagerOptions;

void HAPPlatformBLEPeripheralManagerCreate(
        HAPPlatformBLEPeripheralManagerRef blePeripheralManager,
        const HAPPlatformBLEPeripheralManagerOptions* options);

/* Hooks called by the Bee2 application's GAP callback. */
void EH_HAP_BLE_StackReady(HAPPlatformBLEPeripheralManagerRef blePeripheralManager);
void EH_HAP_BLE_DidConnect(HAPPlatformBLEPeripheralManagerRef blePeripheralManager, uint8_t connId);
void EH_HAP_BLE_DidDisconnect(HAPPlatformBLEPeripheralManagerRef blePeripheralManager, uint8_t connId);
void EH_HAP_BLE_DidSendData(HAPPlatformBLEPeripheralManagerRef blePeripheralManager, uint8_t connId);

#ifdef __cplusplus
}
#endif
#endif
