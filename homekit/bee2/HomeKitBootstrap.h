#ifndef EH_MC16_HOMEKIT_BOOTSTRAP_H
#define EH_MC16_HOMEKIT_BOOTSTRAP_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void EHHomeKitStart(void);
void EHHomeKitStackReady(void);
bool EHHomeKitIsStarted(void);
void EHHomeKitFactoryReset(void);
void EHHomeKitDidConnect(uint8_t connId);
void EHHomeKitDidDisconnect(uint8_t connId);
void EHHomeKitDidSendData(uint8_t connId);

#ifdef __cplusplus
}
#endif
#endif
