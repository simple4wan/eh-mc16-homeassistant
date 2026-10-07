#include "HAPPlatformClock.h"
#include <os_sched.h>

HAPTime HAPPlatformClockGetCurrent(void) {
    return (HAPTime) os_sys_time_get();
}
