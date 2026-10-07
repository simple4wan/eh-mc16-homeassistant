"""Config flow for EH-MC16 BLE Plug."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ADDRESS, DEVICE_NAME, DOMAIN


class EHMC16ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EH-MC16."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle Bluetooth discovery."""
        if not (discovery_info.name or "").startswith(DEVICE_NAME):
            return self.async_abort(reason="not_supported")

        address = discovery_info.address
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEVICE_NAME,
            "address": address,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Confirm a discovered EH-MC16."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            address = self._discovery_info.address
            return self.async_create_entry(
                title=f"EH-MC16 {address[-5:].replace(':', '')}",
                data={CONF_ADDRESS: address},
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery_info.name or DEVICE_NAME,
                "address": self._discovery_info.address,
            },
        )
