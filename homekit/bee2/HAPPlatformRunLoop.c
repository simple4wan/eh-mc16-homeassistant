#include "HAPPlatformRunLoop+Init.h"

#include <app_msg.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

extern bool app_send_msg_to_apptask(T_IO_MSG* p_msg);

#define EH_HAP_RUNLOOP_SUBTYPE 0x4841u
#define EH_HAP_RUNLOOP_SLOTS 8
#define EH_HAP_RUNLOOP_CONTEXT_BYTES 256

typedef struct {
    bool inUse;
    HAPPlatformRunLoopCallback callback;
    size_t contextSize;
    uint8_t context[EH_HAP_RUNLOOP_CONTEXT_BYTES];
} EHRunLoopSlot;

static EHRunLoopSlot slots[EH_HAP_RUNLOOP_SLOTS];

void HAPPlatformRunLoopCreate(const HAPPlatformRunLoopOptions* options) {
    (void) options;
    memset(slots, 0, sizeof slots);
}

void HAPPlatformRunLoopRelease(void) {
    memset(slots, 0, sizeof slots);
}

void HAPPlatformRunLoopRun(void) {
    /* Bee2 already owns the application's event loop. HAP callbacks are
       serialized into that loop through app_send_msg_to_apptask(). */
}

void HAPPlatformRunLoopStop(void) {
}

HAPError HAPPlatformRunLoopScheduleCallback(
        HAPPlatformRunLoopCallback callback,
        void* context,
        size_t contextSize) {
    if (!callback || contextSize > EH_HAP_RUNLOOP_CONTEXT_BYTES) {
        return kHAPError_OutOfResources;
    }

    uint8_t slot;
    for (slot = 0; slot < EH_HAP_RUNLOOP_SLOTS; slot++) {
        if (!slots[slot].inUse) break;
    }
    if (slot == EH_HAP_RUNLOOP_SLOTS) return kHAPError_OutOfResources;

    EHRunLoopSlot* s = &slots[slot];
    s->inUse = true;
    s->callback = callback;
    s->contextSize = contextSize;
    if (contextSize) memcpy(s->context, context, contextSize);

    T_IO_MSG msg;
    memset(&msg, 0, sizeof msg);
    msg.type = IO_MSG_TYPE_OTHERS;
    msg.subtype = EH_HAP_RUNLOOP_SUBTYPE;
    msg.u.param = slot;

    if (!app_send_msg_to_apptask(&msg)) {
        memset(s, 0, sizeof *s);
        return kHAPError_OutOfResources;
    }
    return kHAPError_None;
}

void EH_HAP_RunLoopHandleIO(const T_IO_MSG* msg) {
    if (!msg || msg->type != IO_MSG_TYPE_OTHERS || msg->subtype != EH_HAP_RUNLOOP_SUBTYPE) return;

    uint8_t slot = (uint8_t) msg->u.param;
    if (slot >= EH_HAP_RUNLOOP_SLOTS || !slots[slot].inUse) return;

    EHRunLoopSlot s = slots[slot];
    memset(&slots[slot], 0, sizeof slots[slot]);
    s.callback(s.contextSize ? s.context : NULL, s.contextSize);
}
