#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <HomeKitADK> <mbedtls> <bee2-sdk> <out-dir>" >&2
  exit 2
fi

ADK="$(cd "$1" && pwd)"
MBED="$(cd "$2" && pwd)"
BEE2="$(cd "$3" && pwd)"
OUT="$4"
mkdir -p "$OUT/obj"

CC="${CC:-arm-none-eabi-gcc}"
AR="${AR:-arm-none-eabi-ar}"

MCU_FLAGS="-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard"
COMMON_FLAGS="$MCU_FLAGS -Os -std=gnu11 -ffunction-sections -fdata-sections -fno-strict-aliasing"
DEFS=(
  '-D__has_feature(x)=0'
  '-D_Nullable='
  '-D_Nonnull='
  '-D_Null_unspecified='
  '-DBLE=1'
  '-DIP=0'
  '-DHAP_ENABLE_DEVELOPMENT_ONLY_CODE=1'
  '-DHAP_LOG_LEVEL=0'
)

INCLUDES=(
  "-I$ADK/HAP"
  "-I$ADK/PAL"
  "-I$ADK/PAL/Crypto/MbedTLS"
  "-I$ADK/External/HTTP"
  "-I$ADK/External/JSON"
  "-I$ADK/External/Base64"
  "-I$MBED/include"
  "-I$BEE2/inc"
  "-I$BEE2/inc/app"
  "-I$BEE2/inc/os"
  "-I$BEE2/inc/platform"
  "-I$BEE2/inc/platform/cmsis"
  "-I$BEE2/inc/peripheral"
  "-I$BEE2/inc/bluetooth"
  "-I$BEE2/inc/bluetooth/gap"
  "-I$BEE2/inc/bluetooth/profile"
  "-I$BEE2/inc/bluetooth/profile/server"
  "-I$PWD/homekit/app"
  "-I$PWD/homekit/bee2"
)

echo "[homekit] building Mbed TLS crypto archive"
# The upstream 2.18 config enables host-only timing code by default.
# HAP BLE does not use it on this MCU.
sed -i 's/^#define MBEDTLS_TIMING_C/\/\/ #undef MBEDTLS_TIMING_C/' "$MBED/include/mbedtls/config.h"
make -C "$MBED/library" clean >/dev/null || true
make -C "$MBED/library" libmbedcrypto.a \
  CC="$CC" AR="$AR" \
  CFLAGS="$MCU_FLAGS -Os -ffunction-sections -fdata-sections -DMBEDTLS_NO_PLATFORM_ENTROPY" >/dev/null
cp "$MBED/crypto/library/libmbedcrypto.a" "$OUT/libmbedcrypto.a"

sources=()
while IFS= read -r p; do sources+=("$p"); done < <(
  find "$ADK/HAP" "$ADK/External/HTTP" "$ADK/External/JSON" "$ADK/External/Base64" \
    -maxdepth 1 -type f -name '*.c' | sort
)
sources+=(
  "$ADK/PAL/HAPBase+Crypto.c"
  "$ADK/PAL/HAPPlatformSystemInit.c"
  "$ADK/PAL/Crypto/MbedTLS/HAPMbedTLS.c"
)

while IFS= read -r p; do sources+=("$p"); done < <(
  find "$PWD/homekit/app" "$PWD/homekit/bee2" -maxdepth 1 -type f -name '*.c' | sort
)

objects=()
idx=0
for src in "${sources[@]}"; do
  obj="$OUT/obj/$(printf '%04d' "$idx").o"
  echo "[homekit] CC ${src#$PWD/}"
  "$CC" $COMMON_FLAGS "${DEFS[@]}" "${INCLUDES[@]}" -c "$src" -o "$obj"
  objects+=("$obj")
  idx=$((idx + 1))
done

"$AR" rcs "$OUT/libhomekit.a" "${objects[@]}"

echo "[homekit] built:"
ls -lh "$OUT/libhomekit.a" "$OUT/libmbedcrypto.a"

cp "$OUT/libhomekit.a" "$BEE2/bin/homekit.a"
cp "$OUT/libmbedcrypto.a" "$BEE2/bin/libmbedcrypto.a"

PROJECT="$BEE2/board/evb/silent_ota_gcc/Makefile"
python3 - "$PROJECT" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()

if "../../../bin/homekit.a" not in s:
    s = s.replace(
        "../../../bin/system_trace.a \\\n# lib_end",
        "../../../bin/system_trace.a \\\n../../../bin/homekit.a \\\n../../../bin/libmbedcrypto.a \\\n# lib_end",
        1,
    )

old = "LDFLAGS = $(MCU) -T$(LDSCRIPT) $(LIBDIR) $(LIBS) -Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref -Wl,--gc-sections -specs=nano.specs"
new = "LDFLAGS = $(MCU) -T$(LDSCRIPT) -Wl,--start-group $(LIBDIR) $(LIBS) -Wl,--end-group -Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref -Wl,--gc-sections -specs=nano.specs"
if old in s:
    s = s.replace(old, new, 1)

p.write_text(s)
PY

echo "[homekit] Bee2 Makefile linked to HomeKit archives"
