#ifndef EH_MC16_HAP_PLATFORM_RUN_LOOP_INIT_H
#define EH_MC16_HAP_PLATFORM_RUN_LOOP_INIT_H

#include "HAPPlatformRunLoop.h"
#include <app_msg.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    HAPPlatformKeyValueStoreRef keyValueStore;
} HAPPlatformRunLoopOptions;

void HAPPlatformRunLoopCreate(const HAPPlatformRunLoopOptions* options);
void HAPPlatformRunLoopRelease(void);

/* Called from silent_ota app_handle_io_msg for IO_MSG_TYPE_OTHERS. */
void EH_HAP_RunLoopHandleIO(const T_IO_MSG* msg);

#ifdef __cplusplus
}
#endif
#endif
