#include "HAPPlatformTimer.h"
#include "HAPPlatformRunLoop.h"

#include <os_timer.h>
#include <os_sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define EH_HAP_MAX_TIMERS 12

typedef struct {
    void* osTimer;
    HAPPlatformTimerCallback callback;
    void* context;
    bool inUse;
} EHHAPTimer;

static EHHAPTimer timers[EH_HAP_MAX_TIMERS];

typedef struct {
    HAPPlatformTimerCallback callback;
    HAPPlatformTimerRef ref;
    void* context;
} EHDeferredTimer;

static void RunDeferredTimer(void* bytes, size_t numBytes) {
    if (!bytes || numBytes != sizeof(EHDeferredTimer)) return;
    EHDeferredTimer deferred;
    memcpy(&deferred, bytes, sizeof deferred);
    deferred.callback(deferred.ref, deferred.context);
}

static void TimerFired(void* handle) {
    for (uintptr_t i = 0; i < EH_HAP_MAX_TIMERS; i++) {
        EHHAPTimer* t = &timers[i];
        if (!t->inUse || t->osTimer != handle) continue;

        HAPPlatformTimerCallback callback = t->callback;
        void* context = t->context;
        HAPPlatformTimerRef ref = i + 1;

        t->inUse = false;
        t->callback = NULL;
        t->context = NULL;
        if (t->osTimer) {
            os_timer_delete(&t->osTimer);
        }

        EHDeferredTimer deferred = {
            .callback = callback,
            .ref = ref,
            .context = context
        };
        (void) HAPPlatformRunLoopScheduleCallback(
                RunDeferredTimer,
                &deferred,
                sizeof deferred);
        return;
    }
}

HAPError HAPPlatformTimerRegister(
        HAPPlatformTimerRef* timer,
        HAPTime deadline,
        HAPPlatformTimerCallback callback,
        void* context) {
    if (!timer || !callback) return kHAPError_OutOfResources;

    uintptr_t slot;
    for (slot = 0; slot < EH_HAP_MAX_TIMERS; slot++) {
        if (!timers[slot].inUse) break;
    }
    if (slot == EH_HAP_MAX_TIMERS) return kHAPError_OutOfResources;

    HAPTime now = HAPPlatformClockGetCurrent();
    HAPTime delta = deadline > now ? deadline - now : 1;
    if (delta > UINT32_MAX) delta = UINT32_MAX;

    EHHAPTimer* t = &timers[slot];
    memset(t, 0, sizeof *t);
    t->inUse = true;
    t->callback = callback;
    t->context = context;

    if (!os_timer_create(
            &t->osTimer,
            "hap",
            (uint32_t)(slot + 0x40),
            (uint32_t)delta,
            false,
            (void (*)())TimerFired)) {
        memset(t, 0, sizeof *t);
        return kHAPError_OutOfResources;
    }

    if (!os_timer_start(&t->osTimer)) {
        os_timer_delete(&t->osTimer);
        memset(t, 0, sizeof *t);
        return kHAPError_OutOfResources;
    }

    *timer = slot + 1;
    return kHAPError_None;
}

void HAPPlatformTimerDeregister(HAPPlatformTimerRef timer) {
    if (!timer || timer > EH_HAP_MAX_TIMERS) return;
    EHHAPTimer* t = &timers[timer - 1];
    if (!t->inUse) return;
    if (t->osTimer) {
        os_timer_stop(&t->osTimer);
        os_timer_delete(&t->osTimer);
    }
    memset(t, 0, sizeof *t);
}
