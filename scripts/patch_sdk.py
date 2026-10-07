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

# Insert the minimal plug state machine before BLE setup.
text = text.replace(
    """uint8_t g_ota_mode;\nuint8_t g_keystatus;\n""",
    """uint8_t g_ota_mode;\nuint8_t g_keystatus;\n\nstatic bool eh_plug_on = false;\n\nstatic void eh_plug_set(bool on)\n{\n    eh_plug_on = on;\n    if (on)\n    {\n        GPIO_SetBits(GPIO_GetPin(P2_5));\n        GPIO_ResetBits(GPIO_GetPin(P2_2));\n        GPIO_SetBits(GPIO_GetPin(P2_3));\n    }\n    else\n    {\n        GPIO_ResetBits(GPIO_GetPin(P2_5));\n        GPIO_SetBits(GPIO_GetPin(P2_2));\n        GPIO_ResetBits(GPIO_GetPin(P2_3));\n    }\n}\n""",
    1,
)

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

# EH-MC16 functional GPIO mapping confirmed on hardware:
# P3_2 = button (active low), P2_5 = relay (high=on),
# P2_2/P2_3 = red/blue two-color LED.
text = re.sub(
    r"void pinmux_configuration\(void\)\n\{.*?\n\}",
    """void pinmux_configuration(void)
{
    Pinmux_Config(P3_2, DWGPIO); /* button */
    Pinmux_Config(P2_5, DWGPIO); /* relay */
    Pinmux_Config(P2_2, DWGPIO); /* LED red side */
    Pinmux_Config(P2_3, DWGPIO); /* LED blue side */
}""",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void pad_configuration\(void\)\n\{.*?\n\}",
    """void pad_configuration(void)
{
    /* Button: active-low, internal pull-up. */
    Pad_Config(P3_2, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_UP, PAD_OUT_DISABLE, PAD_OUT_LOW);

    /* Start in OFF state: relay LOW, LED red (P2_2 high / P2_3 low). */
    Pad_Config(P2_5, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_LOW);
    Pad_Config(P2_2, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_HIGH);
    Pad_Config(P2_3, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_LOW);
}""",
    text,
    count=1,
    flags=re.S,
)
text = re.sub(
    r"void driver_init\(void\)\n\{.*?\n\}",
    """void driver_init(void)
{
    g_ota_mode = 1;
    RCC_PeriphClockCmd(APBPeriph_GPIO, APBPeriph_GPIO_CLOCK, ENABLE);

    /* Initial power state: outlet OFF, LED red. */
    GPIO_ResetBits(GPIO_GetPin(P2_5));
    GPIO_SetBits(GPIO_GetPin(P2_2));
    GPIO_ResetBits(GPIO_GetPin(P2_3));

    GPIO_InitTypeDef gpio;
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin = GPIO_GetPin(P2_5) | GPIO_GetPin(P2_2) | GPIO_GetPin(P2_3);
    gpio.GPIO_Mode = GPIO_Mode_OUT;
    gpio.GPIO_ITCmd = DISABLE;
    GPIO_Init(&gpio);

    /* Physical button P3_2, active low, both press/release handled by
       changing interrupt polarity. */
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin = GPIO_GetPin(P3_2);
    gpio.GPIO_Mode = GPIO_Mode_IN;
    gpio.GPIO_ITCmd = ENABLE;
    gpio.GPIO_ITTrigger = GPIO_INT_Trigger_EDGE;
    gpio.GPIO_ITPolarity = GPIO_INT_POLARITY_ACTIVE_LOW;
    gpio.GPIO_ITDebounce = GPIO_INT_DEBOUNCE_ENABLE;
    gpio.GPIO_DebounceTime = 20;
    GPIO_Init(&gpio);

    g_keystatus = GPIO_ReadInputDataBit(GPIO_GetPin(P3_2));
    GPIO_MaskINTConfig(GPIO_GetPin(P3_2), DISABLE);
    GPIO_INTConfig(GPIO_GetPin(P3_2), ENABLE);

    NVIC_InitTypeDef nvic;
    nvic.NVIC_IRQChannel = GPIO26_IRQn;
    nvic.NVIC_IRQChannelPriority = 3;
    nvic.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&nvic);
}""",
    text,
    count=1,
    flags=re.S,
)

    flags=re.S,
)

# Toggle the outlet once on each button press. Release only rearms the edge.
text = text.replace(
    """    g_keystatus = GPIO_ReadInputDataBit(GPIO_GetPin(KEY));

    if (g_keystatus == 0)
    {
        GPIO->INTPOLARITY |= GPIO_GetPin(KEY);
    }
    else
    {
        GPIO->INTPOLARITY &= ~GPIO_GetPin(KEY);
    }
""",
    """    g_keystatus = GPIO_ReadInputDataBit(GPIO_GetPin(KEY));

    if (g_keystatus == 0)
    {
        eh_plug_set(!eh_plug_on);
        GPIO->INTPOLARITY |= GPIO_GetPin(KEY);
    }
    else
    {
        GPIO->INTPOLARITY &= ~GPIO_GetPin(KEY);
    }
""",
    1,
)

# Avoid enabling the sample's low-power GPIO callbacks, which reference EVB pins.
text = text.replace(
    "#define DLPS_EN               1",
    "#define DLPS_EN               0",
) if False else text

main_c.write_text(text, encoding="utf-8")

btext = board_h.read_text(encoding="utf-8")
btext = btext.replace("#define KEY                   P2_4       //KEY2 EVB QFN48/QFN40",
                      "#define KEY                   P3_2       // EH-MC16 physical button", 1)
btext = btext.replace("#define KEY_IRQ               GPIO20_IRQn",
                      "#define KEY_IRQ               GPIO26_IRQn", 1)
btext = btext.replace("#define KEY_INT_Handle        GPIO20_Handler",
                      "#define KEY_INT_Handle        GPIO26_Handler", 1)
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
if old_test_write not in otext:
    raise SystemExit("expected TEST_MODE write handler not found")
otext = otext.replace(old_test_write, new_test_write, 1)

ota_service_c.write_text(otext, encoding="utf-8")

print(f"patched {main_c}")
print(f"patched {board_h}")
print("device_name=EH-MC16-TEST")
print("EH-MC16 plug GPIOs configured: button P3_2, relay P2_5, LED P2_2/P2_3")
print("DFU buffer-check forced enabled")
print("DLPS GPIO callbacks disabled")
print("D0FF/FFD5 exposes read-only GPIO DATAIN snapshot")
print("D0FF/FFD8 provides guarded candidate GPIO probe control")
