#include "HAPPlatform.h"

uint32_t HAPPlatformGetCompatibilityVersion(void) {
    return HAP_PLATFORM_COMPATIBILITY_VERSION;
}

const char* HAPPlatformGetIdentification(void) {
    return "EH-MC16 Bee2";
}

const char* HAPPlatformGetVersion(void) {
    return "1";
}

const char* HAPPlatformGetBuild(void) {
    return "homekit-ble";
}

/* This accessory has no setup display or programmable NFC. These functions
 * are linked because the generic ADK core contains runtime-null checks. */
void HAPPlatformAccessorySetupDisplayUpdateSetupPayload(
        HAPPlatformAccessorySetupDisplayRef setupDisplay,
        const HAPSetupPayload* setupPayload,
        const HAPSetupCode* setupCode) {
    (void) setupDisplay;
    (void) setupPayload;
    (void) setupCode;
}

void HAPPlatformAccessorySetupDisplayHandleStartPairing(
        HAPPlatformAccessorySetupDisplayRef setupDisplay) {
    (void) setupDisplay;
}

void HAPPlatformAccessorySetupDisplayHandleStopPairing(
        HAPPlatformAccessorySetupDisplayRef setupDisplay) {
    (void) setupDisplay;
}

void HAPPlatformAccessorySetupNFCUpdateSetupPayload(
        HAPPlatformAccessorySetupNFCRef setupNFC,
        const HAPSetupPayload* setupPayload,
        bool isPairable) {
    (void) setupNFC;
    (void) setupPayload;
    (void) isPairable;
}

/* No MFi authentication coprocessor is present on this development board. */
bool HAPPlatformMFiHWAuthIsPoweredOn(HAPPlatformMFiHWAuthRef mfiHWAuth) {
    (void) mfiHWAuth;
    return false;
}

HAPError HAPPlatformMFiHWAuthPowerOn(HAPPlatformMFiHWAuthRef mfiHWAuth) {
    (void) mfiHWAuth;
    return kHAPError_Unknown;
}

void HAPPlatformMFiHWAuthPowerOff(HAPPlatformMFiHWAuthRef mfiHWAuth) {
    (void) mfiHWAuth;
}

HAPError HAPPlatformMFiHWAuthWrite(
        HAPPlatformMFiHWAuthRef mfiHWAuth,
        const void* bytes,
        size_t numBytes) {
    (void) mfiHWAuth;
    (void) bytes;
    (void) numBytes;
    return kHAPError_Unknown;
}

HAPError HAPPlatformMFiHWAuthRead(
        HAPPlatformMFiHWAuthRef mfiHWAuth,
        uint8_t registerAddress,
        void* bytes,
        size_t numBytes) {
    (void) mfiHWAuth;
    (void) registerAddress;
    (void) bytes;
    (void) numBytes;
    return kHAPError_Unknown;
}

/* No MFi software token is provisioned. */
HAPError HAPPlatformMFiTokenAuthLoad(
        HAPPlatformMFiTokenAuthRef mfiTokenAuth,
        bool* valid,
        HAPPlatformMFiTokenAuthUUID* mfiTokenUUID,
        void* mfiTokenBytes,
        size_t maxMFiTokenBytes,
        size_t* numMFiTokenBytes) {
    (void) mfiTokenAuth;
    (void) mfiTokenUUID;
    (void) mfiTokenBytes;
    (void) maxMFiTokenBytes;
    if (valid) *valid = false;
    if (numMFiTokenBytes) *numMFiTokenBytes = 0;
    return kHAPError_None;
}

HAPError HAPPlatformMFiTokenAuthUpdate(
        HAPPlatformMFiTokenAuthRef mfiTokenAuth,
        const void* mfiTokenBytes,
        size_t numMFiTokenBytes) {
    (void) mfiTokenAuth;
    (void) mfiTokenBytes;
    (void) numMFiTokenBytes;
    return kHAPError_Unknown;
}
