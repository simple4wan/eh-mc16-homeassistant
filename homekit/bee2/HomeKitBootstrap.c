#include "HomeKitBootstrap.h"

#include "App.h"
#include "DB.h"
#include "HAP.h"
#include "HAPPlatformAccessorySetup+Init.h"
#include "HAPPlatformBLEPeripheralManager+Init.h"
#include "HAPPlatformKeyValueStore+Init.h"
#include "HAPPlatformRunLoop+Init.h"

#include <string.h>

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

    HAPPlatformKeyValueStoreCreate(
            &hk.keyValueStore,
            &(const HAPPlatformKeyValueStoreOptions) {
                .baseOffset = EH_HAP_KVS_DEFAULT_BASE_OFFSET,
                .numSlots = EH_HAP_KVS_DEFAULT_NUM_SLOTS
            });
    hk.platform.keyValueStore = &hk.keyValueStore;

    HAPPlatformAccessorySetupCreate(
            &hk.accessorySetup,
            &(const HAPPlatformAccessorySetupOptions) {
                .keyValueStore = &hk.keyValueStore
            });
    hk.platform.accessorySetup = &hk.accessorySetup;

    HAPPlatformBLEPeripheralManagerCreate(
            &hk.blePeripheralManager,
            &(const HAPPlatformBLEPeripheralManagerOptions) {
                .firstHandle = 0x0100
            });
    hk.platform.ble.blePeripheralManager = &hk.blePeripheralManager;

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

    HAPAccessoryServerCreate(
            &accessoryServer,
            &hk.serverOptions,
            &hk.platform,
            &hk.callbacks,
            NULL);

    AppCreate(&accessoryServer, &hk.keyValueStore);
    AppAccessoryServerStart();
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
