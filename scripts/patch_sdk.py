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
dfu_application_c = sdk / "src/app/silent_ota/dfu_application.c"
app_task_c = sdk / "src/app/silent_ota/app_task.c"
flash_map_h = sdk / "board/evb/silent_ota_gcc/flash_map.h"

text = main_c.read_text(encoding="utf-8")

# Expand the SDK's default 256 KiB flash layout to the EH-MC16's
# 512 KiB flash. Keep silent-OTA staging as large as the application slot.
# New layout:
#   0x800000..0x80DFFF  reserved/OEM/OTA header/ROM patch/secure boot
#   0x80E000..0x83DFFF  AppPatch (192 KiB)
#   0x83E000..0x841FFF  FTL      (16 KiB)
#   0x842000..0x871FFF  OTA tmp  (192 KiB)
#   0x872000..0x87FFFF  spare    (56 KiB)
flash = flash_map_h.read_text(encoding="utf-8")
flash = flash.replace("#define FLASH_SIZE                      0x00040000  //256K Bytes",
                      "#define FLASH_SIZE                      0x00080000  //512K Bytes")
flash = flash.replace("#define OTA_BANK0_SIZE                  0x00023000  //140K Bytes",
                      "#define OTA_BANK0_SIZE                  0x0003C000  //240K Bytes")
flash = flash.replace("#define FTL_ADDR                        0x00825000",
                      "#define FTL_ADDR                        0x0083E000")
flash = flash.replace("#define OTA_TMP_ADDR                    0x00829000",
                      "#define OTA_TMP_ADDR                    0x00842000")
flash = flash.replace("#define OTA_TMP_SIZE                    0x00017000  //92K Bytes",
                      "#define OTA_TMP_SIZE                    0x00030000  //192K Bytes")
flash = flash.replace("#define BANK0_APP_SIZE                  0x00017000  //92K Bytes",
                      "#define BANK0_APP_SIZE                  0x00030000  //192K Bytes")
flash = flash.replace("#define BANK0_APP_DATA1_ADDR            0x00825000",
                      "#define BANK0_APP_DATA1_ADDR            0x0083E000")
flash_map_h.write_text(flash, encoding="utf-8")

text = text.replace(
    '#include "rtl876x_gpio.h"',
    '#include "rtl876x_gpio.h"\n#include "rtl876x_wdg.h"\nextern void EHHomeKitStart(void);\nextern void EHHomeKitFactoryReset(void);\nextern void EHHomeKitOutletStateChanged(void);',
    1,
)

# Insert plug state + long-press factory-reset state machine before BLE setup.
text = text.replace(
    """uint8_t g_ota_mode;\nuint8_t g_keystatus;\n""",
    """uint8_t g_ota_mode;\nuint8_t g_keystatus;\n\nstatic bool eh_plug_on = false;\nstatic bool eh_reset_warning = false;\nstatic bool eh_reset_done = false;\nstatic bool eh_flash_phase = false;\nstatic void *eh_reset_warn_timer;\nstatic void *eh_reset_commit_timer;\nstatic void *eh_reset_flash_timer;\n\nstatic void eh_led_show_state(void)\n{\n    if (eh_plug_on)\n    {\n        GPIO_ResetBits(GPIO_GetPin(P2_2));\n        GPIO_SetBits(GPIO_GetPin(P2_3));\n    }\n    else\n    {\n        GPIO_SetBits(GPIO_GetPin(P2_2));\n        GPIO_ResetBits(GPIO_GetPin(P2_3));\n    }\n}\n\nstatic void eh_plug_set(bool on)\n{\n    eh_plug_on = on;\n    if (on)\n    {\n        GPIO_SetBits(GPIO_GetPin(P2_5));\n    }\n    else\n    {\n        GPIO_ResetBits(GPIO_GetPin(P2_5));\n    }\n    eh_led_show_state();\n    EHHomeKitOutletStateChanged();\n}\n\nbool EHHomeKitOutletGetOn(void)\n{\n    return eh_plug_on;\n}\n\nvoid EHHomeKitOutletSetOn(bool on)\n{\n    eh_plug_set(on);\n}\n\n/* This hook will erase only the HomeKit pairing/KV area once the HAP\n   persistent store is wired in. Keeping it isolated prevents OTA metadata\n   from ever being erased by a HomeKit factory reset. */\nstatic void eh_homekit_factory_reset(void)\n{\n    EHHomeKitFactoryReset();\n}\n\nstatic void eh_reset_flash_cb(void *timer)\n{\n    (void) timer;\n    eh_flash_phase = !eh_flash_phase;\n    if (eh_flash_phase)\n    {\n        GPIO_SetBits(GPIO_GetPin(P2_2));\n        GPIO_ResetBits(GPIO_GetPin(P2_3));\n    }\n    else\n    {\n        GPIO_ResetBits(GPIO_GetPin(P2_2));\n        GPIO_SetBits(GPIO_GetPin(P2_3));\n    }\n}\n\nstatic void eh_reset_warn_cb(void *timer)\n{\n    (void) timer;\n    if (GPIO_ReadInputDataBit(GPIO_GetPin(P3_2)) == 0)\n    {\n        eh_reset_warning = true;\n        eh_flash_phase = false;\n        os_timer_start(&eh_reset_flash_timer);\n    }\n}\n\nstatic void eh_reset_commit_cb(void *timer)\n{\n    (void) timer;\n    if (GPIO_ReadInputDataBit(GPIO_GetPin(P3_2)) == 0)\n    {\n        eh_reset_done = true;\n        os_timer_stop(&eh_reset_flash_timer);\n        eh_plug_set(false);\n        eh_homekit_factory_reset();\n        WDG_SystemReset(RESET_ALL, (T_SW_RESET_REASON) 0xE1);\n    }\n}\n""",
    1,
)

# Reserve service slots for the 4 legacy OTA services plus the HAP database.
text = text.replace("server_init(4);", "server_init(12);", 1)

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

# Short press toggles on release. Holding 7 s starts red/blue warning;
# holding 10 s invokes the isolated HomeKit factory-reset hook and reboots.
text = re.sub(
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
        eh_reset_warning = false;
        eh_reset_done = false;
        GPIO->INTPOLARITY |= GPIO_GetPin(KEY);
        os_timer_start(&eh_reset_warn_timer);
        os_timer_start(&eh_reset_commit_timer);
    }
    else
    {
        GPIO->INTPOLARITY &= ~GPIO_GetPin(KEY);
        os_timer_stop(&eh_reset_warn_timer);
        os_timer_stop(&eh_reset_commit_timer);
        os_timer_stop(&eh_reset_flash_timer);

        if (!eh_reset_warning && !eh_reset_done)
        {
            eh_plug_set(!eh_plug_on);
        }
        else if (!eh_reset_done)
        {
            /* Released between 7 s and 10 s: cancel reset and restore LED. */
            eh_led_show_state();
        }
        eh_reset_warning = false;
    }

    GPIO_ClearINTPendingBit(GPIO_GetPin(KEY));
    GPIO_MaskINTConfig(GPIO_GetPin(KEY), DISABLE);
#if SUPPORT_ERASE_SUSPEND
    app_flash_erase_resume();
#endif
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

# Add the 7 s warning, 10 s commit, and 250 ms LED warning timers.
text = re.sub(
    r"void sw_timer_init\(void\)\n\{.*?\n\}",
    """void sw_timer_init(void)
{
#if (AON_WDG_ENABLE == 1)
    bool retval = os_timer_create(&xTimerPeriodWakeupDlps, "xTimerPeriodWakeupDlps", 1,
                                  TIMER_WAKEUP_DLPS_PERIOD, true, vTimerPeriodWakeupDlpsCallback);
    if (retval)
    {
        os_timer_start(&xTimerPeriodWakeupDlps);
    }
#endif

    os_timer_create(&eh_reset_warn_timer, "ehResetWarn", 2, 7000, false, eh_reset_warn_cb);
    os_timer_create(&eh_reset_commit_timer, "ehResetCommit", 3, 10000, false, eh_reset_commit_cb);
    os_timer_create(&eh_reset_flash_timer, "ehResetFlash", 4, 250, true, eh_reset_flash_cb);
}""",
    text,
    count=1,
    flags=re.S,
)

main_c.write_text(text, encoding="utf-8")


# Start HAP from the live Bee2 app task, after its queues exist but before
# gap_start_bt_stack(). HAPAccessoryServerStart schedules run-loop work
# immediately; doing this in main() was too early because io_queue_handle /
# evt_queue_handle had not been created yet.
atext = app_task_c.read_text(encoding="utf-8")
if "extern void EHHomeKitStart(void);" not in atext:
    atext = atext.replace(
        '#include "otp_config.h"',
        '#include "otp_config.h"\nextern void EHHomeKitStart(void);',
        1,
    )
atext = atext.replace(
    """    os_msg_queue_create(&evt_queue_handle, MAX_NUMBER_OF_EVENT_MESSAGE, sizeof(uint8_t));

    gap_start_bt_stack(evt_queue_handle, io_queue_handle, MAX_NUMBER_OF_GAP_MESSAGE);
""",
    """    os_msg_queue_create(&evt_queue_handle, MAX_NUMBER_OF_EVENT_MESSAGE, sizeof(uint8_t));

    /* HAP may schedule run-loop callbacks immediately during startup, so the
       Bee2 queues must already exist. Register HAP GATT services before the
       Bluetooth stack is started. */
    EHHomeKitStart();

    gap_start_bt_stack(evt_queue_handle, io_queue_handle, MAX_NUMBER_OF_GAP_MESSAGE);
""",
    1,
)
app_task_c.write_text(atext, encoding="utf-8")

# Route HAP run-loop callbacks through the existing Bee2 app task.
dtext = dfu_application_c.read_text(encoding="utf-8")
if "extern void EHHomeKitStart(void);" not in dtext:
    dtext = dtext.replace(
        '#include "patch_header_check.h"',
        '#include "patch_header_check.h"\n'
        'extern void EH_HAP_RunLoopHandleIO(const T_IO_MSG *msg);\n'
        'extern void EHHomeKitStart(void);\n'
        'extern void EHHomeKitStackReady(void);\n'
        'extern bool EHHomeKitIsStarted(void);\n'
        'extern void EHHomeKitDidConnect(uint8_t conn_id);\n'
        'extern void EHHomeKitDidDisconnect(uint8_t conn_id);\n'
        'extern void EHHomeKitDidSendData(uint8_t conn_id);',
        1,
    )
if "EH_HAP_RunLoopHandleIO" not in dtext:
    dtext = dtext.replace(
        '#include "otp_config.h"',
        '#include "otp_config.h"\nextern void EH_HAP_RunLoopHandleIO(const T_IO_MSG *msg);\nextern void EHHomeKitStart(void);\nextern bool EHHomeKitIsStarted(void);\nextern void EHHomeKitDidConnect(uint8_t conn_id);\nextern void EHHomeKitDidDisconnect(uint8_t conn_id);\nextern void EHHomeKitDidSendData(uint8_t conn_id);',
        1,
    )
    dtext = dtext.replace(
        """    case IO_MSG_TYPE_DFU_VALID_FW:
        {
            APP_PRINT_INFO0("IO_MSG_TYPE_DFU_VALID_FW");
            dfu_service_handle_valid_fw(io_driver_msg_recv.u.param);
        }
        break;
    default:
""",
        """    case IO_MSG_TYPE_DFU_VALID_FW:
        {
            APP_PRINT_INFO0("IO_MSG_TYPE_DFU_VALID_FW");
            dfu_service_handle_valid_fw(io_driver_msg_recv.u.param);
        }
        break;
    case IO_MSG_TYPE_OTHERS:
        {
            EH_HAP_RunLoopHandleIO(&io_driver_msg_recv);
        }
        break;
    default:
""",
        1,
    )
dtext = dtext.replace(
    """        if (new_state.gap_init_state == GAP_INIT_STATE_STACK_READY)
        {
            /*stack ready*/
            le_adv_start();
        }
""",
    """        if (new_state.gap_init_state == GAP_INIT_STATE_STACK_READY)
        {
            /* HAP services were registered before the stack started.
               Now allow the cached HomeKit advertisement to go on air. */
            EHHomeKitStackReady();
        }
""",
    1,
)

# Feed connection lifecycle into HAP. Keep the dedicated OTA reboot path intact.
dtext = dtext.replace(
    """    case GAP_CONN_STATE_DISCONNECTED:
        {
""",
    """    case GAP_CONN_STATE_DISCONNECTED:
        {
            EHHomeKitDidDisconnect(conn_id);
""",
    1,
)
dtext = dtext.replace(
    """    case GAP_CONN_STATE_CONNECTED:
        {
""",
    """    case GAP_CONN_STATE_CONNECTED:
        {
            EHHomeKitDidConnect(conn_id);
""",
    1,
)

# In normal HomeKit mode HAP owns advertising after a disconnect.
dtext = dtext.replace(
    """                {
                    le_adv_start();
                }
""",
    """                {
                    if (!EHHomeKitIsStarted())
                    {
                        le_adv_start();
                    }
                }
""",
    1,
)

# Let HAP know when an indication has completed so it can send the next one.
dtext = dtext.replace(
    """            if (p_param->event_data.send_data_result.cause == GAP_SUCCESS)
            {
                APP_PRINT_INFO0("PROFILE_EVT_SEND_DATA_COMPLETE success");
            }
""",
    """            if (p_param->event_data.send_data_result.cause == GAP_SUCCESS)
            {
                APP_PRINT_INFO0("PROFILE_EVT_SEND_DATA_COMPLETE success");
                EHHomeKitDidSendData(p_param->event_data.send_data_result.conn_id);
            }
""",
    1,
)

dfu_application_c.write_text(dtext, encoding="utf-8")


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
print(f"patched {dfu_application_c}")
print("device_name=EH-MC16-TEST")
print("EH-MC16 plug GPIOs configured: button P3_2, relay P2_5, LED P2_2/P2_3")
print("button behavior: short press toggles; 7s warning; 10s HomeKit reset hook + reboot")
print("DFU buffer-check forced enabled")
print("DLPS GPIO callbacks disabled")
print("D0FF/FFD5 exposes read-only GPIO DATAIN snapshot")
print("D0FF/FFD8 provides guarded candidate GPIO probe control")
