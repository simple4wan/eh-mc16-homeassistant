#include "HAPPlatformAbort.h"
#include <rtl876x_wdg.h>

HAP_NORETURN
void HAPPlatformAbort(void) {
    WDG_SystemReset(RESET_ALL, (T_SW_RESET_REASON) 0xE2);
    for (;;) {}
}
