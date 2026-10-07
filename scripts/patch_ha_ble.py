#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_ha_ble.py <bee2-sdk-dir>")

sdk = Path(sys.argv[1])
main_c = sdk / "src/app/silent_ota/main.c"
board_h = sdk / "board/evb/silent_ota_gcc/board.h"
ota_service_c = sdk / "src/ble/profile/server/ota_service.c"
flash_map_h = sdk / "board/evb/silent_ota_gcc/flash_map.h"

# 512 KiB map already validated on the target.
flash = flash_map_h.read_text()
for old, new in {
    "#define FLASH_SIZE                      0x00040000  //256K Bytes":
    "#define FLASH_SIZE                      0x00080000  //512K Bytes",
    "#define OTA_BANK0_SIZE                  0x00023000  //140K Bytes":
    "#define OTA_BANK0_SIZE                  0x0003C000  //240K Bytes",
    "#define FTL_ADDR                        0x00825000":
    "#define FTL_ADDR                        0x0083E000",
    "#define OTA_TMP_ADDR                    0x00829000":
    "#define OTA_TMP_ADDR                    0x00842000",
    "#define OTA_TMP_SIZE                    0x00017000  //92K Bytes":
    "#define OTA_TMP_SIZE                    0x00030000  //192K Bytes",
    "#define BANK0_APP_SIZE                  0x00017000  //92K Bytes":
    "#define BANK0_APP_SIZE                  0x00030000  //192K Bytes",
    "#define BANK0_APP_DATA1_ADDR            0x00825000":
    "#define BANK0_APP_DATA1_ADDR            0x0083E000",
}.items():
    if old not in flash:
        raise SystemExit(f"missing flash marker: {old}")
    flash = flash.replace(old, new, 1)
flash_map_h.write_text(flash)

board = board_h.read_text()
board = board.replace("#define KEY                   P2_4       //KEY2 EVB QFN48/QFN40",
                      "#define KEY                   P3_2       // EH-MC16 button", 1)
board = board.replace("#define KEY_IRQ               GPIO20_IRQn",
                      "#define KEY_IRQ               GPIO26_IRQn", 1)
board = board.replace("#define KEY_INT_Handle        GPIO20_Handler",
                      "#define KEY_INT_Handle        GPIO26_Handler", 1)
board = board.replace("#define USE_GPIO_DLPS        1", "#define USE_GPIO_DLPS        0", 1)
board = board.replace("#define DLPS_EN               1", "#define DLPS_EN               0", 1)
board = board.replace("#define DFU_BUFFER_CHECK_ENABLE     (g_ota_mode & 0x1)",
                      "#define DFU_BUFFER_CHECK_ENABLE     1", 1)
board_h.write_text(board)

main = main_c.read_text()
main = main.replace(
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "RealTekDfu";',
    'uint8_t  device_name[GAP_DEVICE_NAME_LEN] = "EH-MC16-HA";',
    1,
)
old_adv = """    0x0B,                               /* length     */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,     /* type="Complete local name" */
    'R', 'e', 'a', 'l', 'T', 'e', 'k', 'D', 'f', 'u',
"""
new_adv = """    0x0B,                               /* type + 10-byte name */
    GAP_ADTYPE_LOCAL_NAME_COMPLETE,
    'E', 'H', '-', 'M', 'C', '1', '6', '-', 'H', 'A',
"""
if old_adv not in main:
    raise SystemExit("advertising marker not found")
main = main.replace(old_adv, new_adv, 1)

# Add relay state and exported control functions.
main = main.replace(
    "uint8_t g_ota_mode;\nuint8_t g_keystatus;\n",
    """uint8_t g_ota_mode;
uint8_t g_keystatus;

static bool eh_plug_on = false;

static void eh_led_apply(void)
{
    if (eh_plug_on)
    {
        GPIO_ResetBits(GPIO_GetPin(P2_2));
        GPIO_SetBits(GPIO_GetPin(P2_3));
    }
    else
    {
        GPIO_SetBits(GPIO_GetPin(P2_2));
        GPIO_ResetBits(GPIO_GetPin(P2_3));
    }
}

bool EHPlugGetOn(void)
{
    return eh_plug_on;
}

void EHPlugSetOn(bool on)
{
    eh_plug_on = on;
    if (on) GPIO_SetBits(GPIO_GetPin(P2_5));
    else GPIO_ResetBits(GPIO_GetPin(P2_5));
    eh_led_apply();
}
""",
    1,
)

main = re.sub(
    r"void pinmux_configuration\(void\)\n\{.*?\n\}",
    """void pinmux_configuration(void)
{
    Pinmux_Config(P3_2, DWGPIO);
    Pinmux_Config(P2_5, DWGPIO);
    Pinmux_Config(P2_2, DWGPIO);
    Pinmux_Config(P2_3, DWGPIO);
}""",
    main, count=1, flags=re.S)

main = re.sub(
    r"void pad_configuration\(void\)\n\{.*?\n\}",
    """void pad_configuration(void)
{
    Pad_Config(P3_2, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_UP, PAD_OUT_DISABLE, PAD_OUT_LOW);
    Pad_Config(P2_5, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_LOW);
    Pad_Config(P2_2, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_HIGH);
    Pad_Config(P2_3, PAD_PINMUX_MODE, PAD_IS_PWRON,
               PAD_PULL_NONE, PAD_OUT_ENABLE, PAD_OUT_LOW);
}""",
    main, count=1, flags=re.S)

main = re.sub(
    r"void driver_init\(void\)\n\{.*?\n\}",
    """void driver_init(void)
{
    g_ota_mode = 1;
    RCC_PeriphClockCmd(APBPeriph_GPIO, APBPeriph_GPIO_CLOCK, ENABLE);

    GPIO_InitTypeDef gpio;
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin = GPIO_GetPin(P2_5) | GPIO_GetPin(P2_2) | GPIO_GetPin(P2_3);
    gpio.GPIO_Mode = GPIO_Mode_OUT;
    gpio.GPIO_ITCmd = DISABLE;
    GPIO_Init(&gpio);
    EHPlugSetOn(false);

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
    main, count=1, flags=re.S)

main = re.sub(
    r"void KEY_INT_Handle\(void\).*?\n\}",
    """void KEY_INT_Handle(void)
{
#if SUPPORT_ERASE_SUSPEND
    app_flash_erase_suspend();
#endif
    GPIO_MaskINTConfig(GPIO_GetPin(KEY), ENABLE);
    g_keystatus = GPIO_ReadInputDataBit(GPIO_GetPin(KEY));

    if (g_keystatus == 0)
    {
        GPIO->INTPOLARITY |= GPIO_GetPin(KEY);
    }
    else
    {
        GPIO->INTPOLARITY &= ~GPIO_GetPin(KEY);
        EHPlugSetOn(!EHPlugGetOn());
    }

    GPIO_ClearINTPendingBit(GPIO_GetPin(KEY));
    GPIO_MaskINTConfig(GPIO_GetPin(KEY), DISABLE);
#if SUPPORT_ERASE_SUSPEND
    app_flash_erase_resume();
#endif
}""",
    main, count=1, flags=re.S)

main_c.write_text(main)

ota = ota_service_c.read_text()
if '#include "rtl876x_gpio.h"' not in ota:
    ota = ota.replace('#include "board.h"',
                      '#include "board.h"\n#include "rtl876x_gpio.h"\nextern bool EHPlugGetOn(void);\nextern void EHPlugSetOn(bool on);', 1)

# FFD5 returns a single byte: 0=off, 1=on.
old = """    case BLE_SERVICE_CHAR_PATCH_EXTENSION_INDEX:        //not used in bee2
        {

        }
        break;
"""
new = """    case BLE_SERVICE_CHAR_PATCH_EXTENSION_INDEX:
        {
            static uint8_t state;
            state = EHPlugGetOn() ? 1 : 0;
            *pp_value = &state;
            *p_length = 1;
        }
        break;
"""
if old not in ota:
    raise SystemExit("FFD5 read case not found")
ota = ota.replace(old, new, 1)

# FFD8 accepts one byte: 0=off, 1=on, 2=toggle.
old = """    else if (BLE_SERVICE_CHAR_TEST_MODE_INDEX == attrib_index)
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
new = """    else if (BLE_SERVICE_CHAR_TEST_MODE_INDEX == attrib_index)
    {
        if ((length != 1) || (p_value == NULL) || p_value[0] > 2)
        {
            wCause = APP_RESULT_INVALID_VALUE_SIZE;
        }
        else
        {
            if (p_value[0] == 2) EHPlugSetOn(!EHPlugGetOn());
            else EHPlugSetOn(p_value[0] != 0);
        }
    }
"""
if old not in ota:
    raise SystemExit("FFD8 write case not found")
ota = ota.replace(old, new, 1)
ota_service_c.write_text(ota)

print("patched EH-MC16 Home Assistant BLE firmware")
print("name=EH-MC16-HA")
print("state=FFD5 read: 00/01")
print("control=FFD8 write: 00 off / 01 on / 02 toggle")
print("DFU/OTA retained")
