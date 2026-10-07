#include "HAPPlatformAbort.h"

extern void EHBootFatal(void);

HAP_NORETURN
void HAPPlatformAbort(void) {
    /* Diagnostic build: keep the current HomeKit stage visible instead of
       instantly resetting and losing the failure location. The timer service
       keeps running and EHBootFatal switches the stage pulses to blue. */
    EHBootFatal();
    for (;;) {}
}
