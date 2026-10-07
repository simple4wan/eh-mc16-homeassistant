"""Switch platform for EH-MC16 BLE Plug."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_CONNECTIONS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_OFF,
    CMD_ON,
    CONF_ADDRESS,
    CONTROL_CHAR_UUID,
    DOMAIN,
    STATE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 15.0
IO_RETRIES = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an EH-MC16 switch."""
    async_add_entities([EHMC16Switch(hass, entry)], update_before_add=True)


class EHMC16Switch(SwitchEntity):
    """Representation of an EH-MC16 BLE smart plug."""

    _attr_has_entity_name = True
    _attr_name = "Outlet"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self.hass = hass
        self._address: str = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{self._address}_outlet"
        self._attr_is_on = False
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=f"EH-MC16 {self._address[-5:].replace(':', '')}",
            manufacturer="Ehong Link",
            model="EH-MC16",
        )

    async def _async_with_device(self, operation):
        """Connect to the nearest HA Bluetooth adapter/proxy and run operation."""
        last_error: Exception | None = None

        for attempt in range(IO_RETRIES):
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if ble_device is None:
                raise BleakError(f"EH-MC16 {self._address} is not reachable")

            try:
                async with BleakClient(ble_device, timeout=CONNECT_TIMEOUT) as client:
                    return await operation(client)
            except (BleakError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt + 1 < IO_RETRIES:
                    await asyncio.sleep(0.4)

        assert last_error is not None
        raise last_error

    async def async_update(self) -> None:
        """Read the current relay state."""
        async def _read(client: BleakClient) -> bool:
            value = await client.read_gatt_char(STATE_CHAR_UUID)
            if not value:
                raise BleakError("Empty EH-MC16 state response")
            return value[0] != 0

        try:
            self._attr_is_on = await self._async_with_device(_read)
            self._attr_available = True
        except (BleakError, asyncio.TimeoutError) as err:
            self._attr_available = False
            _LOGGER.debug("Unable to read EH-MC16 %s: %s", self._address, err)

    async def _async_write(self, value: bytes) -> None:
        """Write relay state."""
        async def _write(client: BleakClient) -> None:
            await client.write_gatt_char(CONTROL_CHAR_UUID, value, response=False)

        try:
            await self._async_with_device(_write)
            self._attr_is_on = value == CMD_ON
            self._attr_available = True
        except (BleakError, asyncio.TimeoutError) as err:
            self._attr_available = False
            self.async_write_ha_state()
            raise RuntimeError(
                f"Unable to control EH-MC16 {self._address}: {err}"
            ) from err

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the outlet on."""
        await self._async_write(CMD_ON)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the outlet off."""
        await self._async_write(CMD_OFF)
