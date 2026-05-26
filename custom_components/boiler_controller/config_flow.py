import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_P1_TOTAL_ENTITY,
    CONF_DEVICE_URL,
    CONF_DEVICE_ID,
    BC_HOST_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


def _find_config_entry_for_device(hass, device_id: str | None, *, exclude_entry_id: str | None = None):
    """Return an existing entry that already manages this BC device."""
    if not device_id:
        return None

    normalized = device_id.lower()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if exclude_entry_id and entry.entry_id == exclude_entry_id:
            continue
        entry_device_id = entry.data.get(CONF_DEVICE_ID)
        if entry_device_id and entry_device_id.lower() == normalized:
            return entry
        if entry.unique_id and entry.unique_id.lower() == normalized:
            return entry

    return None


class DeviceValidationMixin:
    """Shared helpers for validating BC device connectivity in flows."""

    def _normalize_url(self, url: str) -> str:
        return url.strip().rstrip("/") if url else url

    async def _test_device_connection(self, url: str) -> bool:
        """Test connectivity to the BC device by calling /api/status."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                f"{url}/api/status", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError as err:
            _LOGGER.warning("Device connection error: %s", err)
        except Exception as err:  # pragma: no cover
            _LOGGER.error("Unexpected device test error: %s", err)
        return False

    @staticmethod
    def _derive_device_id(url: str, hostname: str | None = None) -> str | None:
        """Derive a stable device identifier from the hostname or URL."""
        if hostname:
            short = hostname.rstrip(".").split(".")[0].lower()
            if short:
                return short
        if not url:
            return None
        # Fall back to the host part of the URL
        import re
        m = re.search(r"https?://([^/:]+)", url)
        if m:
            return m.group(1).lower()
        return None

    async def _get_power_sensors(self):
        """Get list of suitable power sensors from HA."""
        sensors = {}
        for entity_id in self.hass.states.async_entity_ids("sensor"):
            state = self.hass.states.get(entity_id)
            if not state:
                continue
            if any(
                keyword in entity_id.lower()
                for keyword in [
                    "power",
                    "watt",
                    "electricity",
                    "current_consumption",
                    "current_production",
                    "energy",
                    "verbruik",
                    "opwek",
                    "net_power",
                ]
            ):
                try:
                    float(state.state)
                    unit = state.attributes.get("unit_of_measurement", "")
                    if any(u in unit.lower() for u in ["w", "kw", "watt"]):
                        friendly_name = state.attributes.get("friendly_name", entity_id)
                        sensors[entity_id] = f"{friendly_name} ({entity_id}) [{unit}]"
                except (ValueError, TypeError):
                    continue
        return sensors


class BoilerControllerConfigFlow(DeviceValidationMixin, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 4

    def __init__(self):
        self.data = {}

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        """Handle Zeroconf discovery for pb-bc-* BC modules."""
        hostname = discovery_info.hostname or discovery_info.name
        if not hostname:
            return self.async_abort(reason="unsupported_device")

        hostname = hostname.rstrip(".")
        short_hostname = hostname.split(".")[0].lower()
        if not any(short_hostname.startswith(prefix) for prefix in BC_HOST_PREFIX):
            return self.async_abort(reason="unsupported_device")

        ip_address = str(discovery_info.host) if discovery_info.host else None
        device_url = f"http://{ip_address}" if ip_address else f"http://{hostname}"
        device_id = short_hostname

        existing_entry = _find_config_entry_for_device(self.hass, device_id)
        if existing_entry:
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_DEVICE_URL: device_url})

        self.data[CONF_DEVICE_URL] = device_url
        self.data[CONF_DEVICE_ID] = device_id
        self.context["title_placeholders"] = {"device": short_hostname}

        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("Boiler Controller config flow started")

        errors = {}

        if user_input is not None:
            # Store user input and proceed to power sensor selection
            self.data.update(user_input)
            return await self.async_step_power_sensor()

        schema = vol.Schema({
            vol.Required("name", default="Boiler Controller"): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_power_sensor(self, user_input=None):
        """Handle power sensor selection."""
        errors = {}

        if user_input is not None:
            # Store power sensor selection
            self.data.update(user_input)
            return await self.async_step_device_config()

        # Get power sensors
        power_sensors = await self._get_power_sensors()

        if not power_sensors:
            return self.async_abort(reason="no_power_sensors")

        schema = vol.Schema({
            vol.Required(CONF_P1_TOTAL_ENTITY): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in power_sensors.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="power_sensor", data_schema=schema, errors=errors
        )

    async def async_step_device_config(self, user_input=None):
        """Handle BC device connection configuration."""
        errors = {}

        stored_url = self.data.get(CONF_DEVICE_URL, "")
        default_url = self._normalize_url(stored_url)

        if user_input is not None:
            device_url = self._normalize_url(user_input.get(CONF_DEVICE_URL, ""))

            if not device_url.startswith(("http://", "https://")):
                errors[CONF_DEVICE_URL] = "invalid_url"
            elif not await self._test_device_connection(device_url):
                errors[CONF_DEVICE_URL] = "cannot_connect"
            else:
                device_id = self._derive_device_id(
                    device_url, self.data.get(CONF_DEVICE_ID)
                )
                if not device_id:
                    errors[CONF_DEVICE_URL] = "cannot_identify"
                else:
                    existing_entry = _find_config_entry_for_device(self.hass, device_id)
                    if existing_entry:
                        return self.async_abort(reason="already_configured")

                    if self.unique_id is None:
                        await self.async_set_unique_id(device_id)

                    self.data.update(
                        {CONF_DEVICE_URL: device_url, CONF_DEVICE_ID: device_id}
                    )
                    return self.async_create_entry(
                        title=self.data.get("name", "Boiler Controller"),
                        data=self.data,
                    )

            default_url = device_url

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_URL, default=default_url): str
        })

        return self.async_show_form(
            step_id="device_config",
            data_schema=schema,
            errors=errors,
            description_placeholders={"example_url": "http://pb-bc-xxxx.local"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BoilerControllerOptionsFlow(config_entry)


class BoilerControllerOptionsFlow(DeviceValidationMixin, config_entries.OptionsFlow):
    """Handle options flow for Boiler Controller."""

    def __init__(self, config_entry):
        super().__init__()
        self._config_entry = config_entry
        self.data = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            if user_input.get("change_devices"):
                return await self.async_step_power_sensor()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Optional("change_devices", default=False): bool}),
        )

    async def async_step_power_sensor(self, user_input=None):
        """Handle power sensor change."""
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_device_config()

        # Get power sensors
        power_sensors = await self._get_power_sensors()
        if not power_sensors:
            return self.async_abort(reason="no_power_sensors")

        # Get current selection
        current_power_sensor = self._config_entry.data.get(CONF_P1_TOTAL_ENTITY)

        schema = vol.Schema({
            vol.Required(CONF_P1_TOTAL_ENTITY, default=current_power_sensor): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in power_sensors.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(step_id="power_sensor", data_schema=schema)

    async def async_step_device_config(self, user_input=None):
        """Handle BC device URL updates."""
        errors = {}

        current_url = self._normalize_url(
            self._config_entry.data.get(CONF_DEVICE_URL, "")
        )

        if user_input is not None:
            device_url = self._normalize_url(user_input.get(CONF_DEVICE_URL, current_url))

            if not device_url.startswith(("http://", "https://")):
                errors[CONF_DEVICE_URL] = "invalid_url"
            elif not await self._test_device_connection(device_url):
                errors[CONF_DEVICE_URL] = "cannot_connect"
            else:
                device_id = self._derive_device_id(
                    device_url, self._config_entry.data.get(CONF_DEVICE_ID)
                )

                existing_entry = _find_config_entry_for_device(
                    self.hass,
                    device_id,
                    exclude_entry_id=self._config_entry.entry_id,
                )
                if existing_entry:
                    errors[CONF_DEVICE_URL] = "device_in_use"
                else:
                    # Update stored data/options
                    new_data = dict(self._config_entry.data)
                    if self.data:
                        new_data.update(self.data)
                    new_data[CONF_DEVICE_URL] = device_url
                    if device_id:
                        new_data[CONF_DEVICE_ID] = device_id

                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        data=new_data,
                        options=dict(self._config_entry.options),
                        unique_id=device_id or self._config_entry.unique_id,
                    )

                    await self.hass.config_entries.async_reload(
                        self._config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data={})

            current_url = device_url

        schema = vol.Schema({vol.Required(CONF_DEVICE_URL, default=current_url): str})

        return self.async_show_form(
            step_id="device_config",
            data_schema=schema,
            errors=errors,
            description_placeholders={"example_url": "http://pb-bc-xxxx.local"},
        )
