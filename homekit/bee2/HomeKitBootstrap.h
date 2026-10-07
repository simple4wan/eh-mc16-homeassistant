#ifndef EH_MC16_HOMEKIT_BOOTSTRAP_H
#define EH_MC16_HOMEKIT_BOOTSTRAP_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

void EHHomeKitStart(void);
bool EHHomeKitIsStarted(void);
void EHHomeKitFactoryReset(void);

#ifdef __cplusplus
}
#endif
#endif
