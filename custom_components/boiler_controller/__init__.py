import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_RUN_CALIBRATION,
    SERVICE_CANCEL_CALIBRATION,
    ATTR_CONFIG_ENTRY_ID,
)
from .controller import BoilerController

_LOGGER = logging.getLogger(__name__)

ENTRY_ID_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)
RUN_CALIBRATION_SCHEMA = ENTRY_ID_SCHEMA
CANCEL_CALIBRATION_SCHEMA = ENTRY_ID_SCHEMA


# Set up the component
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Boiler Controller from a config entry."""
    _LOGGER.info("Setting up Boiler Controller")

    try:
        integration = await async_get_integration(hass, DOMAIN)
        integration_version = str(integration.version) if integration.version else "unknown"
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Could not get integration version from manifest: %s", err)
        integration_version = "unknown"

    # Create the controller
    controller = BoilerController(hass, entry, integration_version)
    
    # Start the controller (now handles missing entities gracefully)
    success = await controller.async_start()
    if not success:
        _LOGGER.error("Failed to start Boiler Controller")
        # Don't raise ConfigEntryNotReady anymore - let it start and wait for entities
        _LOGGER.warning("Boiler Controller will continue running and wait for entities to become available")
    
    # Store the controller
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "controller": controller,
    }

    await _async_register_services(hass)
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Boiler Controller setup completed")
    return True

# Implement unloading and reloading of the config entry
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Boiler Controller")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Stop the controller
    controller_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if controller_data:
        controller = controller_data.get("controller")
        if controller:
            await controller.async_stop()
    
    # Remove from hass.data
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)

    domain_data = hass.data.get(DOMAIN, {})
    remaining_controllers = [
        value
        for value in domain_data.values()
        if isinstance(value, dict) and value.get("controller")
    ]

    if not remaining_controllers:
        if hass.services.has_service(DOMAIN, SERVICE_RUN_CALIBRATION):
            hass.services.async_remove(DOMAIN, SERVICE_RUN_CALIBRATION)
        if hass.services.has_service(DOMAIN, SERVICE_CANCEL_CALIBRATION):
            hass.services.async_remove(DOMAIN, SERVICE_CANCEL_CALIBRATION)
        domain_data.pop("_services_registered", None)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register the calibration service once per Home Assistant instance."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_services_registered"):
        return

    async def _handle_run_calibration(call: ServiceCall) -> None:
        controller = _async_resolve_controller(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        _LOGGER.info("Starting calibration for entry %s", controller.config_entry.entry_id)
        await controller.async_run_calibration()
        _LOGGER.info("Calibration completed for entry %s", controller.config_entry.entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_CALIBRATION,
        _handle_run_calibration,
        schema=RUN_CALIBRATION_SCHEMA,
    )

    async def _handle_cancel_calibration(call: ServiceCall) -> None:
        controller = _async_resolve_controller(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))

        requested = await controller.async_request_calibration_cancel()
        if not requested:
            raise HomeAssistantError("No calibration run is currently active")

        _LOGGER.info(
            "Calibration cancellation requested for entry %s",
            controller.config_entry.entry_id,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_CALIBRATION,
        _handle_cancel_calibration,
        schema=CANCEL_CALIBRATION_SCHEMA,
    )
    domain_data["_services_registered"] = True


def _async_resolve_controller(hass: HomeAssistant, entry_id: str | None) -> BoilerController:
    controllers = {
        key: value["controller"]
        for key, value in hass.data.get(DOMAIN, {}).items()
        if isinstance(value, dict) and value.get("controller")
    }

    if not controllers:
        raise HomeAssistantError("No Boiler Controller entries loaded")

    if entry_id:
        controller = controllers.get(entry_id)
        if not controller:
            raise HomeAssistantError(f"No Boiler Controller entry with id {entry_id}")
        return controller

    if len(controllers) == 1:
        return next(iter(controllers.values()))

    raise HomeAssistantError("config_entry_id is required when multiple Boiler Controller entries exist")
