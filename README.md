# Boiler Controller HA Integration

Boiler Controller turns your electric boiler into a water battery. Instead of exporting surplus energy, it sends the excess reported by your P1 meter straight into the boiler so you store free solar or dynamic-tariff energy as hot water.

## Features

- Reads live consumption/production from your P1 smart meter — either a single signed net sensor or a pair of separate return + usage sensors
- Controls a Boiler Controller (BC) device over HTTP using watt-based setpoints
- Four control modes: `auto`, `manual`, `on`, `off`
- Exposes device telemetry sensors (power, heating percentage, temperature, energy, RSSI)
- Built-in calibration support — run a manual sweep to build the watt/percentage curve immediately, or let the device calibrate itself automatically over time

## Installation

1. Install via HACS or copy the `custom_components/boiler_controller` folder to your Home Assistant configuration
2. Restart Home Assistant
3. Go to **Settings › Devices & Services**
4. Click **Add Integration** and search for **Boiler Controller**
5. Follow the configuration steps:
   - Pick the power-sensor mode that matches your P1 setup:
     - **Net (1 sensor)** — one signed sensor where negative values mean you are exporting to the grid
     - **Split (2 sensors)** — two non-negative sensors: one for grid return (export) and one for grid usage (import)
   - Select the matching sensor entity (or entities)
   - Enter the URL of your BC device (e.g. `http://192.168.1.50`)

### Power-sensor modes

The integration computes a signed surplus (positive = exporting) from your configuration:

- **Net mode**: `surplus = -net_value`
- **Split mode**: `surplus = return - usage`

In `auto` mode the boiler setpoint is `max(0, min(MAX_EXPORT_WATTS, boiler_watts + surplus))`. Because the surplus goes negative as soon as you start importing, the controller automatically backs off instead of getting stuck at 100%.

## Control Modes

| Mode | Behaviour |
| --- | --- |
| `auto` | Continuously reads the P1 surplus and sends the matching wattage to the boiler |
| `manual` | Sends a fixed wattage you specify with the **Manual Power** entity |
| `on` | Sets the boiler to 100% |
| `off` | Sets the boiler to 0% (default on startup) |

Switch modes with the **Control Mode** select entity on the device page or via automations.

## Calibration

Run the calibration sweep once so the BC device knows how many watts correspond to each output percentage. This is stored on the device itself.

1. Open the Boiler Controller device page and press **Calibrate Start**.
2. The integration sets the status to `Calibrating` and the Control Mode entity becomes unavailable while the sweep runs.
3. When the sweep finishes the integration returns to the previous control mode automatically.

To abort a running calibration press **Calibrate Stop**.

> **Before you start a manual calibration:**
> - The boiler must be **cooled down**. If it is already at temperature the heating element cannot reach the higher setpoints and the curve will be incomplete.
> - The sweep takes **at least 6 minutes** while it measures every percentage point against the actual wattage.
> - Running it manually is **optional** — the controller will calibrate itself automatically over time. Use the button only when you want an immediate, complete curve.


## Entities

### Controls

| Entity | Type | Description |
| --- | --- | --- |
| **Control Mode** | Select | Active control mode: `auto`, `manual`, `on`, `off`. Disabled during calibration. |
| **Manual Power** | Number (W) | Target wattage used in `manual` mode. Only available in `manual` mode. |
| **Calibrate Start** | Button | Starts an automated calibration run on the BC device. |
| **Calibrate Stop** | Button | Requests the active calibration run to stop. |

### Sensors

| Entity | Type | Description |
| --- | --- | --- |
| **Status** | Sensor (text) | `Running` when the boiler is heating, `Idle` when off, `Calibration` during a calibration run. |
| **Net Power** | Sensor (W) | *Net mode only.* Mirrors the configured signed P1 entity so you can confirm the source data. |
| **Grid Return** | Sensor (W) | *Split mode only.* Mirrors the configured grid-return (export) entity. |
| **Grid Usage** | Sensor (W) | *Split mode only.* Mirrors the configured grid-usage (import) entity. |
| **Last Control Update** | Sensor (timestamp) | Timestamp of the last heating command sent to the device. |
| **Device Power** | Sensor (W) | Live power draw reported by the BC device. |
| **Heating Percentage** | Sensor (%) | Current output percentage reported by the BC device. |
| **Device Temperature** | Sensor (°C) | External temperature sensor (I/O) reported by the BC device. |
| **Device Energy** | Sensor (kWh) | Cumulative energy consumed by the boiler. |
| **Firmware Version** | Sensor | BC device firmware version. |
| **IP Address** | Sensor | IP address of the BC device. |
| **WiFi Strength / RSSI / Uptime / Up Since** | Sensors | BC device diagnostics. |

## Example Automations

**Force the boiler on during off-peak hours:**
```yaml
alias: "Boiler on during off-peak"
trigger:
  - platform: time
    at: "23:00:00"
action:
  - service: select.select_option
    target:
      entity_id: select.boiler_controller_control_mode
    data:
      option: "on"
```

**Return to auto mode in the morning:**
```yaml
alias: "Boiler back to auto"
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: select.select_option
    target:
      entity_id: select.boiler_controller_control_mode
    data:
      option: auto
```

**Set a fixed wattage manually:**
```yaml
action:
  - service: select.select_option
    target:
      entity_id: select.boiler_controller_control_mode
    data:
      option: manual
  - service: number.set_value
    target:
      entity_id: number.boiler_controller_manual_power
    data:
      value: 1000
```

> Replace `boiler_controller` in the entity IDs with the slug of your config entry name if you chose a different name during setup.
