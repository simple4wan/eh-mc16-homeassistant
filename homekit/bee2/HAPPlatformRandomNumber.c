#include "HAPPlatformRandomNumber.h"
#include <platform_utils.h>
#include <stdint.h>
#include <string.h>

void HAPPlatformRandomNumberFill(void* bytes, size_t numBytes) {
    uint8_t* p = (uint8_t*) bytes;
    while (numBytes) {
        uint32_t r = platform_random(0xFFFFFFFFu);
        size_t n = numBytes < sizeof r ? numBytes : sizeof r;
        memcpy(p, &r, n);
        p += n;
        numBytes -= n;
    }
}
