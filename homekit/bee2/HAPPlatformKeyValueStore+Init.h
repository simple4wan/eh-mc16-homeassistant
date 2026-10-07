#ifndef EH_MC16_HAP_PLATFORM_KEY_VALUE_STORE_INIT_H
#define EH_MC16_HAP_PLATFORM_KEY_VALUE_STORE_INIT_H

#include "HAPPlatformKeyValueStore.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EH_HAP_KVS_DEFAULT_BASE_OFFSET ((uint16_t) 0x2000)
#define EH_HAP_KVS_DEFAULT_NUM_SLOTS   ((uint8_t) 32)
#define EH_HAP_KVS_MAX_VALUE_BYTES     ((size_t) 128)

typedef struct {
    uint16_t baseOffset;
    uint8_t numSlots;
} HAPPlatformKeyValueStoreOptions;

struct HAPPlatformKeyValueStore {
    uint16_t baseOffset;
    uint8_t numSlots;
};

void HAPPlatformKeyValueStoreCreate(
        HAPPlatformKeyValueStoreRef keyValueStore,
        const HAPPlatformKeyValueStoreOptions* options);

#ifdef __cplusplus
}
#endif
#endif
