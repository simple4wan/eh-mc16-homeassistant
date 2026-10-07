#include "HAP.h"
#include "App.h"
#include "DB.h"

typedef struct {
    HAPAccessoryServerRef* server;
    HAPPlatformKeyValueStoreRef keyValueStore;
} AccessoryConfiguration;

static AccessoryConfiguration accessoryConfiguration;

static HAPAccessory accessory = {
    .aid = 1,
    .category = kHAPAccessoryCategory_Outlets,
    .name = "EH-MC16 Outlet",
    .manufacturer = "Ehong Link",
    .model = "EH-MC16",
    .serialNumber = "EHMC16-0001",
    .firmwareVersion = "1",
    .hardwareVersion = "3.1",
    .services = (const HAPService* const[]) {
        &accessoryInformationService,
        &hapProtocolInformationService,
        &pairingService,
        &outletService,
        NULL
    },
    .callbacks = { .identify = IdentifyAccessory }
};

HAPError IdentifyAccessory(
        HAPAccessoryServerRef* server HAP_UNUSED,
        const HAPAccessoryIdentifyRequest* request HAP_UNUSED,
        void* _Nullable context HAP_UNUSED) {
    return kHAPError_None;
}

HAPError HandleOutletOnRead(
        HAPAccessoryServerRef* server HAP_UNUSED,
        const HAPBoolCharacteristicReadRequest* request HAP_UNUSED,
        bool* value,
        void* _Nullable context HAP_UNUSED) {
    *value = EHHomeKitOutletGetOn();
    return kHAPError_None;
}

HAPError HandleOutletOnWrite(
        HAPAccessoryServerRef* server HAP_UNUSED,
        const HAPBoolCharacteristicWriteRequest* request HAP_UNUSED,
        bool value,
        void* _Nullable context HAP_UNUSED) {
    EHHomeKitOutletSetOn(value);
    return kHAPError_None;
}

HAPError HandleOutletInUseRead(
        HAPAccessoryServerRef* server HAP_UNUSED,
        const HAPBoolCharacteristicReadRequest* request HAP_UNUSED,
        bool* value,
        void* _Nullable context HAP_UNUSED) {
    *value = EHHomeKitOutletGetOn();
    return kHAPError_None;
}

void AppCreate(HAPAccessoryServerRef* server, HAPPlatformKeyValueStoreRef keyValueStore) {
    accessoryConfiguration.server = server;
    accessoryConfiguration.keyValueStore = keyValueStore;
}

void AppRelease(void) {}

void AppAccessoryServerStart(void) {
    HAPAccessoryServerStart(accessoryConfiguration.server, &accessory);
}

void AccessoryServerHandleUpdatedState(HAPAccessoryServerRef* server HAP_UNUSED, void* _Nullable context HAP_UNUSED) {}
void AccessoryServerHandleSessionAccept(HAPAccessoryServerRef* server HAP_UNUSED, HAPSessionRef* session HAP_UNUSED, void* _Nullable context HAP_UNUSED) {}
void AccessoryServerHandleSessionInvalidate(HAPAccessoryServerRef* server HAP_UNUSED, HAPSessionRef* session HAP_UNUSED, void* _Nullable context HAP_UNUSED) {}
void RestorePlatformFactorySettings(void) {}
const HAPAccessory* AppGetAccessoryInfo(void) { return &accessory; }

void EHHomeKitOutletStateChanged(void) {
    if (!accessoryConfiguration.server) return;
    HAPAccessoryServerRaiseEvent(
            accessoryConfiguration.server,
            &outletOnCharacteristic,
            &outletService,
            &accessory);
    HAPAccessoryServerRaiseEvent(
            accessoryConfiguration.server,
            &outletInUseCharacteristic,
            &outletService,
            &accessory);
}
