#include "HAPPlatformLog.h"

HAPPlatformLogEnabledTypes HAPPlatformLogGetEnabledTypes(const HAPLogObject* log) {
    (void) log;
    return kHAPPlatformLogEnabledTypes_None;
}

void HAPPlatformLogCapture(
        const HAPLogObject* log,
        HAPLogType type,
        const char* message,
        const void* bufferBytes,
        size_t numBufferBytes) {
    (void) log;
    (void) type;
    (void) message;
    (void) bufferBytes;
    (void) numBufferBytes;
}
