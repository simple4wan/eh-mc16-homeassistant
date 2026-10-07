#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_sdk.py <bee2-sdk-dir>")

sdk = Path(sys.argv[1])
main_c = sdk / "src/app/silent_ota/main.c"
board_h = sdk / "board/evb/silent_ota_gcc/board.h"
ota_service_c = sdk / "src/ble/profile/server/ota_service.c"

text = main_c.read_text(encoding="utf-8")

# Give the recovery test a unique, obvious BLE name.
text = text.replace(
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "RealTekDfu";',
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "EH-MC16-TEST";',
    1,
)

old_adv = """    0x0B,                               /* length     */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'R', 'e', 'a', 'l', 'T', 'e', 'k', 'D', 'f', 'u',
"""
new_adv = """    0x0D,                               /* length: type + 12-byte name */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'E', 'H', '-', 'M', 'C', '1', '6', '-', 'T', 'E', 'S', 'T',
"""
if old_adv not in text:
    raise SystemExit("expected RealTekDfu advertising block not found")
text = text.replace(old_adv, new_adv, 1)

# The SDK sample uses EVB GPIOs P0_0/P2_4 to decide OTA mode and handle a key.
# Those pins are unknown on EH-MC16 and must not be touched in the first test.
text = re.sub(
    r"void pinmux_configuration\(void\)\n\{.*?\n\}",
    """void pinmux_configuration(void)
{
    /* GPIO probe: route only exposed EH-MC16 candidate I/O pads to DWGPIO.
       Do not touch SWD (P1_0/P1_1), LOG/boot (P0_3), UART (P0_0/P0_1),
       reset, power, or ground. */
    const uint8_t pins[] = {
        P0_5, P0_6,
        P2_2, P2_3, P2_4, P2_5, P2_6, P2_7,
        P3_2, P3_3,
        P4_0, P4_1, P4_2, P4_3
    };
    for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i)
    {
        Pinmux_Config(pins[i], DWGPIO);
    }
}""",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void pad_configuration\(void\)\n\{.*?\n\}",
    """void pad_configuration(void)
{
    /* Input-only probe: no pull resistor and output driver disabled.
       This never intentionally drives a candidate pin high or low. */
    const uint8_t pins[] = {
        P0_5, P0_6,
        P2_2, P2_3, P2_4, P2_5, P2_6, P2_7,
        P3_2, P3_3,
        P4_0, P4_1, P4_2, P4_3
    };
    for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i)
    {
        Pad_Config(pins[i], PAD_PINMUX_MODE, PAD_IS_PWRON,
                   PAD_PULL_NONE, PAD_OUT_DISABLE, PAD_OUT_LOW);
    }
}""",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void driver_init\(void\)\n\{.*?\n\}",
    """void driver_init(void)
{
    /* Enable DFU buffer-check without sampling the EVB TP0 GPIO. */
    g_ota_mode = 1;
    g_keystatus = 1;

    /* Configure candidate module pins strictly as GPIO inputs. */
    RCC_PeriphClockCmd(APBPeriph_GPIO, APBPeriph_GPIO_CLOCK, ENABLE);
    GPIO_InitTypeDef gpio;
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin =
        GPIO_GetPin(P0_5) | GPIO_GetPin(P0_6) |
        GPIO_GetPin(P2_2) | GPIO_GetPin(P2_3) |
        GPIO_GetPin(P2_4) | GPIO_GetPin(P2_5) |
        GPIO_GetPin(P2_6) | GPIO_GetPin(P2_7) |
        GPIO_GetPin(P3_2) | GPIO_GetPin(P3_3) |
        GPIO_GetPin(P4_0) | GPIO_GetPin(P4_1) |
        GPIO_GetPin(P4_2) | GPIO_GetPin(P4_3);
    gpio.GPIO_Mode = GPIO_Mode_IN;
    gpio.GPIO_ITCmd = DISABLE;
    GPIO_Init(&gpio);
}""",
    text,
    count=1,
    flags=re.S,
)

# Avoid enabling the sample's low-power GPIO callbacks, which reference EVB pins.
text = text.replace(
    "#define DLPS_EN               1",
    "#define DLPS_EN               0",
) if False else text

main_c.write_text(text, encoding="utf-8")

btext = board_h.read_text(encoding="utf-8")
btext = btext.replace("#define USE_GPIO_DLPS        1", "#define USE_GPIO_DLPS        0", 1)
btext = btext.replace("#define DLPS_EN               1", "#define DLPS_EN               0", 1)
# dfu_service.c uses this inside a preprocessor #if, so it must be a
# compile-time constant. A runtime expression such as (g_ota_mode & 0x1)
# evaluates false in #if and disables buffer-check.
btext = btext.replace(
    "#define DFU_BUFFER_CHECK_ENABLE     (g_ota_mode & 0x1)",
    "#define DFU_BUFFER_CHECK_ENABLE     1",
    1,
)
board_h.write_text(btext, encoding="utf-8")

# Expose a read-only GPIO DATAIN snapshot through the otherwise-unused
# D0FF/FFD5 Patch Extension characteristic.  This deliberately does NOT
# configure pinmux, pulls, GPIO direction, or output values; it only reads the
# hardware input register, so unknown relay/LED pins are never driven.
otext = ota_service_c.read_text(encoding="utf-8")
if '#include "rtl876x_gpio.h"' not in otext:
    otext = otext.replace(
        '#include "board.h"',
        '#include "board.h"\n#include "rtl876x_gpio.h"',
        1,
    )

old_gpio_case = """    case BLE_SERVICE_CHAR_PATCH_EXTENSION_INDEX:        //not used in bee2
        {

        }
        break;
"""
new_gpio_case = """    case BLE_SERVICE_CHAR_PATCH_EXTENSION_INDEX:        // EH-MC16 read-only GPIO probe
        {
            static uint32_t gpio_datain_snapshot;
            gpio_datain_snapshot = GPIO_ReadInputData();
            *pp_value = (uint8_t *)&gpio_datain_snapshot;
            *p_length = sizeof(gpio_datain_snapshot);
        }
        break;
"""
if old_gpio_case not in otext:
    raise SystemExit("expected unused PATCH_EXTENSION read case not found")
otext = otext.replace(old_gpio_case, new_gpio_case, 1)

old_test_write = """    else if (BLE_SERVICE_CHAR_TEST_MODE_INDEX == attrib_index)
    {
        /* Make sure written value size is valid. */
        if ((length != sizeof(uint8_t)) || (p_value == NULL))
        {
            wCause  = APP_RESULT_INVALID_VALUE_SIZE;
        }
        else
        {
            /* Notify Application. */
            callback_data.msg_type = SERVICE_CALLBACK_TYPE_WRITE_CHAR_VALUE;
            callback_data.msg_data.write.opcode = OTA_WRITE_TEST_MODE_CHAR_VAL;
            callback_data.msg_data.write.u.value = p_value[0];

            if (pfnOTAExtendedCB)
            {
                pfnOTAExtendedCB(service_id, (void *)&callback_data);
            }
        }
    }
"""
new_test_write = """    else if (BLE_SERVICE_CHAR_TEST_MODE_INDEX == attrib_index)
    {
        /* EH-MC16 guarded GPIO probe on FFD8.
           Payload: [pin_num, action]
             action 0x00 = restore high-impedance input
             action 0x01 = drive LOW
             action 0x02 = drive HIGH

           Only exposed candidate pins are allowed.  The confirmed button P3_2
           and boot/debug/UART pins are intentionally excluded.
        */
        if ((length != 2) || (p_value == NULL) || p_value[1] > 0x02)
        {
            wCause = APP_RESULT_INVALID_VALUE_SIZE;
        }
        else
        {
            uint8_t pin_num = p_value[0];
            uint8_t action = p_value[1];
            bool allowed =
                pin_num == P0_5 || pin_num == P0_6 ||
                pin_num == P2_2 || pin_num == P2_3 ||
                pin_num == P2_4 || pin_num == P2_5 ||
                pin_num == P2_6 || pin_num == P2_7 ||
                pin_num == P3_3 ||
                pin_num == P4_0 || pin_num == P4_1 ||
                pin_num == P4_2 || pin_num == P4_3;

            if (!allowed)
            {
                wCause = APP_RESULT_APP_ERR;
            }
            else
            {
                uint32_t pin = GPIO_GetPin(pin_num);
                Pinmux_Config(pin_num, DWGPIO);

                GPIO_InitTypeDef gpio;
                GPIO_StructInit(&gpio);
                gpio.GPIO_Pin = pin;
                gpio.GPIO_ITCmd = DISABLE;

                if (action == 0x00)
                {
                    Pad_Config(pin_num, PAD_PINMUX_MODE, PAD_IS_PWRON,
                               PAD_PULL_NONE, PAD_OUT_DISABLE, PAD_OUT_LOW);
                    gpio.GPIO_Mode = GPIO_Mode_IN;
                    GPIO_Init(&gpio);
                }
                else
                {
                    if (action == 0x01)
                    {
                        GPIO_ResetBits(pin);
                        Pad_Config(pin_num, PAD_PINMUX_MODE, PAD_IS_PWRON,
                                   PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_LOW);
                    }
                    else
                    {
                        GPIO_SetBits(pin);
                        Pad_Config(pin_num, PAD_PINMUX_MODE, PAD_IS_PWRON,
                                   PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_HIGH);
                    }
                    gpio.GPIO_Mode = GPIO_Mode_OUT;
                    GPIO_Init(&gpio);
                }
            }
        }
    }
"""
"""
if old_test_write not in otext:
    raise SystemExit("expected TEST_MODE write handler not found")
otext = otext.replace(old_test_write, new_test_write, 1)

ota_service_c.write_text(otext, encoding="utf-8")

print(f"patched {main_c}")
print(f"patched {board_h}")
print("device_name=EH-MC16-TEST")
print("candidate EH-MC16 pins configured input-only for GPIO probing")
print("DFU buffer-check forced enabled")
print("DLPS GPIO callbacks disabled")
print("D0FF/FFD5 exposes read-only GPIO DATAIN snapshot")
print("D0FF/FFD8 provides guarded candidate GPIO probe control")
