#include "HomeKitBootstrap.h"

#include "App.h"
#include "DB.h"
#include "HAP.h"
#include "HAPPlatformAccessorySetup+Init.h"
#include "HAPPlatformBLEPeripheralManager+Init.h"
#include "HAPPlatformKeyValueStore+Init.h"
#include "HAPPlatformRunLoop+Init.h"

#include <string.h>

extern void EHBootMark(uint8_t stage);

#define EH_HAP_ADV_INTERVAL HAPBLEAdvertisingIntervalCreateFromMilliseconds(417.5f)

static struct {
    HAPPlatformKeyValueStore keyValueStore;
    HAPPlatformBLEPeripheralManager blePeripheralManager;
    HAPPlatformAccessorySetup accessorySetup;
    HAPAccessoryServerOptions serverOptions;
    HAPPlatform platform;
    HAPAccessoryServerCallbacks callbacks;
    bool started;
} hk;

static HAPAccessoryServerRef accessoryServer;

static HAPBLEGATTTableElementRef gattTableElements[kAttributeCount];
static HAPBLESessionCacheElementRef sessionCacheElements[kHAPBLESessionCache_MinElements];
static HAPSessionRef bleSession;
static uint8_t procedureBytes[2048];
static HAPBLEProcedureRef procedures[1];

static HAPBLEAccessoryServerStorage bleStorage = {
    .gattTableElements = gattTableElements,
    .numGATTTableElements = HAPArrayCount(gattTableElements),
    .sessionCacheElements = sessionCacheElements,
    .numSessionCacheElements = HAPArrayCount(sessionCacheElements),
    .session = &bleSession,
    .procedures = procedures,
    .numProcedures = HAPArrayCount(procedures),
    .procedureBuffer = {
        .bytes = procedureBytes,
        .numBytes = sizeof procedureBytes
    }
};

static void HandleUpdatedState(HAPAccessoryServerRef* server, void* context) {
    (void) server;
    (void) context;
}

bool EHHomeKitIsStarted(void) {
    return hk.started;
}

void EHHomeKitStart(void) {
    if (hk.started) return;

    memset(&hk, 0, sizeof hk);

    EHBootMark(1); /* entering HomeKit; before KVS */
    HAPPlatformKeyValueStoreCreate(
            &hk.keyValueStore,
            &(const HAPPlatformKeyValueStoreOptions) {
                .baseOffset = EH_HAP_KVS_DEFAULT_BASE_OFFSET,
                .numSlots = EH_HAP_KVS_DEFAULT_NUM_SLOTS
            });
    hk.platform.keyValueStore = &hk.keyValueStore;

    EHBootMark(2); /* KVS complete; before accessory setup */
    HAPPlatformAccessorySetupCreate(
            &hk.accessorySetup,
            &(const HAPPlatformAccessorySetupOptions) {
                .keyValueStore = &hk.keyValueStore
            });
    hk.platform.accessorySetup = &hk.accessorySetup;

    EHBootMark(3); /* accessory setup complete; before BLE PAL */
    HAPPlatformBLEPeripheralManagerCreate(
            &hk.blePeripheralManager,
            &(const HAPPlatformBLEPeripheralManagerOptions) {
                .firstHandle = 0x0100
            });
    hk.platform.ble.blePeripheralManager = &hk.blePeripheralManager;

    EHBootMark(4); /* BLE PAL complete; before run loop */
    HAPPlatformRunLoopCreate(
            &(const HAPPlatformRunLoopOptions) {
                .keyValueStore = &hk.keyValueStore
            });

    hk.serverOptions.maxPairings = kHAPPairingStorage_MinElements;
    hk.serverOptions.ble.transport = &kHAPAccessoryServerTransport_BLE;
    hk.serverOptions.ble.accessoryServerStorage = &bleStorage;
    hk.serverOptions.ble.preferredAdvertisingInterval = EH_HAP_ADV_INTERVAL;
    hk.serverOptions.ble.preferredNotificationDuration = kHAPBLENotification_MinDuration;

    hk.callbacks.handleUpdatedState = HandleUpdatedState;

    EHBootMark(5); /* platform/options complete; before HAPAccessoryServerCreate */
    HAPAccessoryServerCreate(
            &accessoryServer,
            &hk.serverOptions,
            &hk.platform,
            &hk.callbacks,
            NULL);

    EHBootMark(6); /* HAPAccessoryServerCreate returned; before AppCreate */
    AppCreate(&accessoryServer, &hk.keyValueStore);

    EHBootMark(7); /* AppCreate returned; before AppAccessoryServerStart */
    AppAccessoryServerStart();

    EHBootMark(8); /* AppAccessoryServerStart returned */
    hk.started = true;
}

void EHHomeKitFactoryReset(void) {
    if (!hk.started) {
        HAPPlatformKeyValueStore tempStore;
        HAPPlatformKeyValueStoreCreate(
                &tempStore,
                &(const HAPPlatformKeyValueStoreOptions) {
                    .baseOffset = EH_HAP_KVS_DEFAULT_BASE_OFFSET,
                    .numSlots = EH_HAP_KVS_DEFAULT_NUM_SLOTS
                });
        (void) HAPRestoreFactorySettings(&tempStore);
        return;
    }

    HAPAccessoryServerStop(&accessoryServer);
    (void) HAPRestoreFactorySettings(&hk.keyValueStore);
}

void EHHomeKitDidConnect(uint8_t connId) {
    if (!hk.started) return;
    EH_HAP_BLE_DidConnect(&hk.blePeripheralManager, connId);
}

void EHHomeKitDidDisconnect(uint8_t connId) {
    if (!hk.started) return;
    EH_HAP_BLE_DidDisconnect(&hk.blePeripheralManager, connId);
}

void EHHomeKitDidSendData(uint8_t connId) {
    if (!hk.started) return;
    EH_HAP_BLE_DidSendData(&hk.blePeripheralManager, connId);
}

void EHHomeKitStackReady(void) {
    if (!hk.started) return;
    EH_HAP_BLE_StackReady(&hk.blePeripheralManager);
}
