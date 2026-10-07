#include "HAPPlatformKeyValueStore+Init.h"

#include <ftl.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define EH_HAP_KVS_MAGIC 0x484B5653u /* "HKVS" */

typedef struct {
    uint32_t magic;
    uint8_t active;
    uint8_t domain;
    uint8_t key;
    uint8_t reserved;
    uint16_t numBytes;
    uint16_t reserved2;
    uint8_t bytes[EH_HAP_KVS_MAX_VALUE_BYTES];
} EHHAPKVSRecord;

static uint16_t SlotOffset(HAPPlatformKeyValueStoreRef store, uint8_t slot) {
    return (uint16_t)(store->baseOffset + ((uint16_t)slot * (uint16_t)sizeof(EHHAPKVSRecord)));
}

static bool ReadSlot(HAPPlatformKeyValueStoreRef store, uint8_t slot, EHHAPKVSRecord* record) {
    memset(record, 0, sizeof *record);
    if (slot >= store->numSlots) return false;
    if (ftl_load(record, SlotOffset(store, slot), sizeof *record) != FTL_READ_SUCCESS) return false;
    if (record->magic != EH_HAP_KVS_MAGIC) return false;
    if (record->numBytes > EH_HAP_KVS_MAX_VALUE_BYTES) return false;
    return true;
}

static bool WriteSlot(HAPPlatformKeyValueStoreRef store, uint8_t slot, const EHHAPKVSRecord* record) {
    if (slot >= store->numSlots) return false;
    return ftl_save((void*)record, SlotOffset(store, slot), sizeof *record) == FTL_WRITE_SUCCESS;
}

void HAPPlatformKeyValueStoreCreate(
        HAPPlatformKeyValueStoreRef store,
        const HAPPlatformKeyValueStoreOptions* options) {
    store->baseOffset =
            options && options->baseOffset ? options->baseOffset : EH_HAP_KVS_DEFAULT_BASE_OFFSET;
    store->numSlots =
            options && options->numSlots ? options->numSlots : EH_HAP_KVS_DEFAULT_NUM_SLOTS;
}

HAPError HAPPlatformKeyValueStoreGet(
        HAPPlatformKeyValueStoreRef store,
        HAPPlatformKeyValueStoreDomain domain,
        HAPPlatformKeyValueStoreKey key,
        void* bytes,
        size_t maxBytes,
        size_t* numBytes,
        bool* found) {
    if (!store || !found || (bytes && !numBytes)) return kHAPError_Unknown;

    *found = false;
    if (numBytes) *numBytes = 0;

    EHHAPKVSRecord record;
    for (uint8_t slot = 0; slot < store->numSlots; slot++) {
        if (!ReadSlot(store, slot, &record) || !record.active) continue;
        if (record.domain != domain || record.key != key) continue;

        *found = true;
        if (bytes) {
            size_t n = record.numBytes < maxBytes ? record.numBytes : maxBytes;
            memcpy(bytes, record.bytes, n);
            *numBytes = n;
        }
        return kHAPError_None;
    }
    return kHAPError_None;
}

HAPError HAPPlatformKeyValueStoreSet(
        HAPPlatformKeyValueStoreRef store,
        HAPPlatformKeyValueStoreDomain domain,
        HAPPlatformKeyValueStoreKey key,
        const void* bytes,
        size_t numBytes) {
    if (!store || !bytes || numBytes > EH_HAP_KVS_MAX_VALUE_BYTES) return kHAPError_Unknown;

    int freeSlot = -1;
    EHHAPKVSRecord record;

    for (uint8_t slot = 0; slot < store->numSlots; slot++) {
        bool valid = ReadSlot(store, slot, &record);
        if (valid && record.active && record.domain == domain && record.key == key) {
            freeSlot = slot;
            break;
        }
        if (freeSlot < 0 && (!valid || !record.active)) freeSlot = slot;
    }

    if (freeSlot < 0) return kHAPError_Unknown;

    memset(&record, 0, sizeof record);
    record.magic = EH_HAP_KVS_MAGIC;
    record.active = 1;
    record.domain = domain;
    record.key = key;
    record.numBytes = (uint16_t)numBytes;
    memcpy(record.bytes, bytes, numBytes);

    return WriteSlot(store, (uint8_t)freeSlot, &record) ? kHAPError_None : kHAPError_Unknown;
}

HAPError HAPPlatformKeyValueStoreRemove(
        HAPPlatformKeyValueStoreRef store,
        HAPPlatformKeyValueStoreDomain domain,
        HAPPlatformKeyValueStoreKey key) {
    if (!store) return kHAPError_Unknown;

    EHHAPKVSRecord record;
    for (uint8_t slot = 0; slot < store->numSlots; slot++) {
        if (!ReadSlot(store, slot, &record) || !record.active) continue;
        if (record.domain != domain || record.key != key) continue;

        record.active = 0;
        record.numBytes = 0;
        memset(record.bytes, 0, sizeof record.bytes);
        return WriteSlot(store, slot, &record) ? kHAPError_None : kHAPError_Unknown;
    }
    return kHAPError_None;
}

HAPError HAPPlatformKeyValueStoreEnumerate(
        HAPPlatformKeyValueStoreRef store,
        HAPPlatformKeyValueStoreDomain domain,
        HAPPlatformKeyValueStoreEnumerateCallback callback,
        void* context) {
    if (!store || !callback) return kHAPError_Unknown;

    EHHAPKVSRecord record;
    bool shouldContinue = true;
    for (uint8_t slot = 0; slot < store->numSlots && shouldContinue; slot++) {
        if (!ReadSlot(store, slot, &record) || !record.active) continue;
        if (record.domain != domain) continue;

        HAPError err = callback(context, store, domain, record.key, &shouldContinue);
        if (err) return err;
    }
    return kHAPError_None;
}

HAPError HAPPlatformKeyValueStorePurgeDomain(
        HAPPlatformKeyValueStoreRef store,
        HAPPlatformKeyValueStoreDomain domain) {
    if (!store) return kHAPError_Unknown;

    EHHAPKVSRecord record;
    for (uint8_t slot = 0; slot < store->numSlots; slot++) {
        if (!ReadSlot(store, slot, &record) || !record.active) continue;
        if (record.domain != domain) continue;

        record.active = 0;
        record.numBytes = 0;
        memset(record.bytes, 0, sizeof record.bytes);
        if (!WriteSlot(store, slot, &record)) return kHAPError_Unknown;
    }
    return kHAPError_None;
}
