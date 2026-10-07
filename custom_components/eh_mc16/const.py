"""Constants for the EH-MC16 BLE integration."""

DOMAIN = "eh_mc16"

CONF_ADDRESS = "address"

DEVICE_NAME = "EH-MC16-HA"

# The Realtek OTA service contains 16-bit characteristics.  The HA firmware
# repurposes two otherwise unused characteristics for simple plug control.
STATE_CHAR_UUID = "0000ffd5-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "0000ffd8-0000-1000-8000-00805f9b34fb"

CMD_OFF = b"\x00"
CMD_ON = b"\x01"
CMD_TOGGLE = b"\x02"
