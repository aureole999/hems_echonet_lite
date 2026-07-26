"""Constants for the HEMS Echonet Lite integration."""

from datetime import timedelta
import re

from pyhems import EntityDefinition

from homeassistant.components.number import NumberDeviceClass as NumberDC
from homeassistant.components.sensor import SensorDeviceClass as SensorDC
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfSoundPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

DOMAIN = "echonet_lite"
ATTR_EPC = "epc"
CONF_INTERFACE = "interface"
CONF_ENABLE_EXPERIMENTAL = "enable_experimental"
DEFAULT_INTERFACE = "0.0.0.0"
DEFAULT_POLL_INTERVAL = 60
# Fixed cadence for the high-frequency polling tier (instantaneous values
# such as power consumption). Not user-configurable: HA integrations should
# not expose polling intervals as a setting (see developer docs on polling).
# Kept well below DEFAULT_POLL_INTERVAL so it offers a meaningful
# improvement, but not so low that it floods slow devices; PropertyPoller
# separately folds this back into the normal cadence for devices confirmed
# to be slow (see pyhems.poller).
DEFAULT_FAST_POLL_INTERVAL = 10
ISSUE_RUNTIME_CLIENT_ERROR = "runtime_client_error"
ISSUE_RUNTIME_INACTIVE = "runtime_inactive"
RUNTIME_MONITOR_INTERVAL = timedelta(minutes=1)
# Five minutes corresponds to roughly five missed polling cycles
# (``DEFAULT_POLL_INTERVAL`` = 60s). If either constant changes, revisit this
# ratio so the inactivity issue still trips after several missed polls rather
# than firing on a single transient gap.
RUNTIME_MONITOR_MAX_SILENCE = timedelta(minutes=5)
DISCOVERY_INTERVAL = 60.0 * 60.0  # 1 hour

# ============================================================================
# ECHONET Lite class codes used by this integration
# ============================================================================
# Names and values come from the ECHONET Lite specification (Machine Readable
# Appendix). pyhems exposes the same metadata at runtime via
# ``DefinitionsRegistry``; these literals are kept here so that imports stay
# pure (no I/O at import time) and so the integration owns its own naming.
CLASS_CODE_HOME_AIR_CONDITIONER = 0x0130
CLASS_CODE_VENTILATION_FAN = 0x0133
CLASS_CODE_AIR_CONDITIONER_VENTILATION_FAN = 0x0134
CLASS_CODE_AIR_CLEANER = 0x0135
CLASS_CODE_ELECTRICALLY_OPERATED_BLIND = 0x0260
CLASS_CODE_ELECTRICALLY_OPERATED_SHUTTER = 0x0263
CLASS_CODE_ELECTRIC_WATER_HEATER = 0x026B
CLASS_CODE_ELECTRIC_LOCK = 0x026F
CLASS_CODE_HOUSEHOLD_SOLAR_POWER_GENERATION = 0x0279
CLASS_CODE_STORAGE_BATTERY = 0x027D
CLASS_CODE_GENERAL_LIGHTING = 0x0290
CLASS_CODE_MONO_FUNCTIONAL_LIGHTING = 0x0291
CLASS_CODE_SWITCH = 0x05FD  # Switch (supporting JEM-A/HA terminals)
CLASS_CODE_CONTROLLER = 0x05FF

# ============================================================================
# ECHONET Lite property codes (EPCs) used by this integration
# ============================================================================
# Common (super class, 0x80-0x9F) EPCs.
EPC_OPERATION_STATUS = 0x80
EPC_INSTALLATION_LOCATION = 0x81
EPC_MANUFACTURER_CODE = 0x8A
EPC_PRODUCT_CODE = 0x8C
EPC_SERIAL_NUMBER = 0x8D
EPC_INF_PROPERTY_MAP = 0x9D
EPC_SET_PROPERTY_MAP = 0x9E
EPC_GET_PROPERTY_MAP = 0x9F

# Class-specific EPCs used by the climate / fan platforms.
# 0xA0 has different semantic names per class (fan speed for HOME AC,
# air flow level for ventilation fan / air cleaner). Both aliases are
# defined to keep call sites self-documenting.
EPC_AIR_FLOW_LEVEL = 0xA0
EPC_FAN_SPEED = 0xA0
EPC_SWING_AIR_FLOW = 0xA3
EPC_SPECIAL_STATE = 0xAA
EPC_OPERATION_MODE = 0xB0
EPC_TARGET_TEMPERATURE = 0xB3
EPC_ROOM_HUMIDITY = 0xBA
EPC_ROOM_TEMPERATURE = 0xBB
EPC_MEASURED_WATER_TEMPERATURE = 0xC1

# Class-specific EPCs used by the light platform.
EPC_LIGHT_LEVEL = 0xB0
EPC_LIGHT_COLOR = 0xB1
EPC_LIGHTING_MODE = 0xB6

# Class-specific EPCs used by the cover platform.
EPC_COVER_OPEN_CLOSE = 0xE0
EPC_COVER_POSITION = 0xE1
EPC_COVER_ANGLE = 0xE2
EPC_COVER_OPEN_CLOSED_STATUS = 0xEA

# Class-specific EPCs used by the lock platform.
EPC_LOCK_SETTING_1 = 0xE0
EPC_LOCK_SETTING_2 = 0xE1
EPC_LOCK_ALARM_STATUS = 0xE5

# Stable (non-experimental) device class codes
# These device classes have been verified with real hardware.
# Other device classes are considered experimental.
STABLE_CLASS_CODES: frozenset[int] = frozenset(
    {
        CLASS_CODE_HOME_AIR_CONDITIONER,
        CLASS_CODE_AIR_CLEANER,
        CLASS_CODE_ELECTRIC_WATER_HEATER,
        CLASS_CODE_ELECTRIC_LOCK,
        CLASS_CODE_HOUSEHOLD_SOLAR_POWER_GENERATION,
        CLASS_CODE_STORAGE_BATTERY,
        CLASS_CODE_SWITCH,
        CLASS_CODE_CONTROLLER,
    }
)

# EPCs managed by dedicated platform entities (climate, fan)
# - Excluded from other platforms (sensor/binary_sensor/select/switch) to avoid duplicates
# - Used for polling/notification to keep entity state up-to-date
DEDICATED_PLATFORM_EPCS: dict[int, frozenset[int]] = {
    CLASS_CODE_HOME_AIR_CONDITIONER: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_FAN_SPEED,
            EPC_SWING_AIR_FLOW,
            EPC_SPECIAL_STATE,
            EPC_OPERATION_MODE,
            EPC_TARGET_TEMPERATURE,
        }
    ),
    CLASS_CODE_VENTILATION_FAN: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_AIR_FLOW_LEVEL,
        }
    ),
    CLASS_CODE_AIR_CONDITIONER_VENTILATION_FAN: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_AIR_FLOW_LEVEL,
        }
    ),
    CLASS_CODE_AIR_CLEANER: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_AIR_FLOW_LEVEL,
        }
    ),
    CLASS_CODE_ELECTRIC_WATER_HEATER: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_OPERATION_MODE,
            EPC_TARGET_TEMPERATURE,
        }
    ),
    CLASS_CODE_ELECTRIC_LOCK: frozenset(
        {
            EPC_LOCK_SETTING_1,
            EPC_LOCK_SETTING_2,
            EPC_LOCK_ALARM_STATUS,
        }
    ),
    CLASS_CODE_ELECTRICALLY_OPERATED_BLIND: frozenset(
        {
            EPC_COVER_OPEN_CLOSE,
            EPC_COVER_POSITION,
            EPC_COVER_ANGLE,
            EPC_COVER_OPEN_CLOSED_STATUS,
        }
    ),
    CLASS_CODE_ELECTRICALLY_OPERATED_SHUTTER: frozenset(
        {
            EPC_COVER_OPEN_CLOSE,
            EPC_COVER_POSITION,
            EPC_COVER_ANGLE,
            EPC_COVER_OPEN_CLOSED_STATUS,
        }
    ),
    CLASS_CODE_MONO_FUNCTIONAL_LIGHTING: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_LIGHT_LEVEL,
        }
    ),
    CLASS_CODE_GENERAL_LIGHTING: frozenset(
        {
            EPC_OPERATION_STATUS,
            EPC_LIGHT_LEVEL,
            EPC_LIGHT_COLOR,
            EPC_LIGHTING_MODE,
        }
    ),
}

# High-frequency ("fast poll") EPCs to exclude per device class code, keyed
# the same way as DEDICATED_PLATFORM_EPCS.
#
# The default fast-poll candidate set is derived automatically from the
# pyhems REGISTRY by matching "instantaneous"/"瞬時" in the entity name (see
# ``_build_fast_poll_epcs`` in ``__init__.py``). This table lets specific
# EPCs be excluded from that automatic classification when the heuristic is
# wrong for a particular device class (e.g. a name containing "instantaneous"
# that does not actually need high-frequency polling). Empty by default;
# add entries here as real-world exceptions are identified.
FAST_POLL_EXCLUDE_EPCS: dict[int, frozenset[int]] = {}


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case.

    MRA enum names use camelCase (e.g., 'automaticAirFlowDirection').
    HA uses snake_case for state keys (e.g., 'automatic_air_flow_direction').
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# ============================================================================
# Installation location (EPC 0x81) — integration-side option keys
# ============================================================================
# The 1-byte format and the standard LLLL labels live in
# :mod:`pyhems.installation_location` and are reused by the select platform,
# the device-info helper, and the strings generator. The constants below are
# integration-only additions that surface alongside the spec values.

# Option key written to EPC 0x81 as 0x00 (LLLL=0, NNN=0).
INSTALLATION_LOCATION_UNSET = "unset"

# NNN (bits 2-0) option keys; "0" is displayed as "Unset".
INSTALLATION_LOCATION_NUMBER_OPTIONS: tuple[str, ...] = tuple(str(n) for n in range(8))


# ============================================================================
# MRA unit -> Home Assistant unit / device class tables
# ============================================================================
# These three tables drive how pyhems' MRA (machine readable appendix) units
# map to Home Assistant's runtime unit strings and device classes for the
# sensor and number platforms. They live here, side-by-side, so adding a new
# MRA unit is a single-file change.

# MRA unit -> HA unit string. A value of ``None`` means HA has no matching
# constant; the MRA string is used verbatim so the unit still appears in the
# UI. Every unit produced by pyhems must appear here; the
# ``test_all_pyhems_units_are_handled`` test enforces this.
MRA_UNIT_TO_HA_UNIT: dict[str, str | None] = {
    "W": UnitOfPower.WATT,
    "kW": UnitOfPower.KILO_WATT,
    "Wh": UnitOfEnergy.WATT_HOUR,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "MJ": UnitOfEnergy.MEGA_JOULE,
    "Celsius": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "%RH": PERCENTAGE,
    "A": UnitOfElectricCurrent.AMPERE,
    "mA": UnitOfElectricCurrent.MILLIAMPERE,
    "V": UnitOfElectricPotential.VOLT,
    "ppm": CONCENTRATION_PARTS_PER_MILLION,
    "lux": LIGHT_LUX,
    "dB": UnitOfSoundPressure.DECIBEL,
    "m/s": UnitOfSpeed.METERS_PER_SECOND,
    "L": UnitOfVolume.LITERS,
    "m3": UnitOfVolume.CUBIC_METERS,
    "m3/h": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "second": UnitOfTime.SECONDS,
    "days": UnitOfTime.DAYS,
    "ms": UnitOfTime.MILLISECONDS,
    "degree": DEGREE,
    "r/min": REVOLUTIONS_PER_MINUTE,
    "µg/m³": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    # No HA equivalent — MRA string is used as-is.
    "mHz": None,  # Will added in HA 2026.5
    "Ah": None,
    "digit": None,
    "klux": None,
}


def infer_ha_unit(entity_def: EntityDefinition) -> str | None:
    """Return the HA unit string for ``entity_def`` or ``None``.

    Units with a ``None`` mapping (no HA constant) fall through to the MRA
    string unchanged. Units not listed in :data:`MRA_UNIT_TO_HA_UNIT` also
    fall through, but the coverage test prevents that in practice.
    """
    unit = entity_def.unit
    if not unit:
        return None
    return (
        MRA_UNIT_TO_HA_UNIT.get(unit, unit) or unit
    )  # pragma: no cover - safety net for unmapped MRA units


# Unit -> device class rules, shared between the sensor and number platforms.
#
# Each entry is ``((units, ...), ((keyword, sensor_dc, number_dc), ...))``:
# for each unit, rules are tried in order and the first keyword matched in
# the entity's English name wins. An empty keyword ``""`` matches
# unconditionally and acts as a catch-all default. If no rule matches the
# entity's unit or name, ``(None, None)`` is returned (no device class).
#
# Either column may be ``None`` for units that only make sense as a sensor
# (e.g. ``ppm``/``lux``/``µg/m³``) or have no matching NumberDC.
UNIT_DEVICE_CLASS_RULES: tuple[
    tuple[
        tuple[str, ...],
        tuple[tuple[str, SensorDC | None, NumberDC | None], ...],
    ],
    ...,
] = (
    (("W", "kW"), (("", SensorDC.POWER, NumberDC.POWER),)),
    (("Celsius",), (("", SensorDC.TEMPERATURE, NumberDC.TEMPERATURE),)),
    (("%RH",), (("", SensorDC.HUMIDITY, NumberDC.HUMIDITY),)),
    (("A", "mA"), (("", SensorDC.CURRENT, NumberDC.CURRENT),)),
    (("V",), (("", SensorDC.VOLTAGE, NumberDC.VOLTAGE),)),
    (("ppm",), (("", SensorDC.CO2, None),)),
    (("lux",), (("", SensorDC.ILLUMINANCE, None),)),
    (("dB",), (("", SensorDC.SOUND_PRESSURE, None),)),
    (("m/s",), (("", SensorDC.WIND_SPEED, None),)),
    (("m3/h",), (("", SensorDC.VOLUME_FLOW_RATE, NumberDC.VOLUME_FLOW_RATE),)),
    (("second", "days"), (("", SensorDC.DURATION, NumberDC.DURATION),)),
    (
        ("%",),
        (
            ("humidity", SensorDC.HUMIDITY, NumberDC.HUMIDITY),
            ("battery", SensorDC.BATTERY, NumberDC.BATTERY),
            # Number entities never reach these sensor-only keywords, but
            # keeping both columns in the same row keeps the table flat.
            ("remaining", SensorDC.BATTERY, None),
            ("soc", SensorDC.BATTERY, None),
            ("moisture", SensorDC.MOISTURE, NumberDC.MOISTURE),
        ),
    ),
    (
        ("Wh", "kWh", "MJ"),
        (
            # Static ratings (e.g. "AC chargeable capacity") don't fit
            # measurement device classes.
            ("capacity", None, None),
            ("stored", SensorDC.ENERGY_STORAGE, NumberDC.ENERGY_STORAGE),
            ("", SensorDC.ENERGY, NumberDC.ENERGY),
        ),
    ),
    (
        ("L",),
        (
            # Static tank capacity is not a variable measurement.
            ("capacity", None, None),
            ("tank", SensorDC.VOLUME_STORAGE, NumberDC.VOLUME_STORAGE),
            ("remaining", SensorDC.VOLUME_STORAGE, NumberDC.VOLUME_STORAGE),
            ("", SensorDC.WATER, NumberDC.WATER),
        ),
    ),
    (
        ("m3",),
        (
            ("gas", SensorDC.GAS, NumberDC.GAS),
            ("water", SensorDC.WATER, NumberDC.WATER),
            ("", SensorDC.VOLUME, NumberDC.VOLUME),
        ),
    ),
    (
        ("µg/m³",),
        (
            ("pm2.5", SensorDC.PM25, None),
            ("pm25", SensorDC.PM25, None),
        ),
    ),
)


def infer_device_classes(
    entity_def: EntityDefinition,
) -> tuple[SensorDC | None, NumberDC | None]:
    """Return the ``(sensor_dc, number_dc)`` tuple for ``entity_def``.

    See :data:`UNIT_DEVICE_CLASS_RULES` for the rule format. Returns
    ``(None, None)`` when the unit is unknown or no rule matches the entity's
    English name.
    """
    unit = entity_def.unit
    if not unit:
        return None, None
    name_lower = entity_def.name_en.lower()
    for units, rules in UNIT_DEVICE_CLASS_RULES:
        if unit not in units:
            continue
        for keyword, sensor_dc, number_dc in rules:
            if keyword == "" or keyword in name_lower:
                return sensor_dc, number_dc
        return None, None
    return None, None  # pragma: no cover - safety net for unmapped MRA units


# ============================================================================
# EntityCategory inference
# ============================================================================
# Home Assistant distinguishes three tiers:
# - DIAGNOSTIC: fault / error / cumulative counters / identification, etc.
# - CONFIG: writable settings (thresholds, schedules, reservations, ...)
# - None: primary user-facing entities (e.g. temperature, power reading)
#
# ``None`` applies to common (super class) EPCs. Class-specific entries take
# precedence. Keep EPCs as MRA literals with their property names so additions
# can be reviewed directly against the specification.
ENTITY_CATEGORY_EPCS: dict[EntityCategory, dict[int | None, frozenset[int]]] = {
    EntityCategory.DIAGNOSTIC: {
        None: frozenset(
            {
                0x88,  # Fault status
                0x89,  # Fault description
            }
        ),
        0x0023: frozenset(  # Current sensor
            {
                0xE1,  # Rated voltage to be measured
            }
        ),
        0x0135: frozenset(  # Air cleaner
            {
                0xE1,  # Filter change notice
            }
        ),
        0x0260: frozenset(  # Electrically operated blind/shade
            {
                0xE8,  # Remote operation setting status
            }
        ),
        0x0263: frozenset(  # Electrically operated rain sliding door/shutter
            {
                0xE8,  # Remote operation setting status
            }
        ),
        0x026B: frozenset(  # Electric water heater
            {
                0xDB,  # Rated power consumption of H/P unit in wintertime
                0xDC,  # Rated power consumption of H/P unit in in-between seasons
                0xDD,  # Rated power consumption of H/P unit in summertime
                0xE2,  # Tank capacity
            }
        ),
        0x026F: frozenset(  # Electric lock
            {
                0xE7,  # Battery level
            }
        ),
        0x0279: frozenset(  # Household solar power generation
            {
                0xB2,  # Function to control the type of surplus electricity purchase
                0xB3,  # Output power change time setting value
                0xB4,  # Upper limit clip setting value
                0xC0,  # Operation power factor setting value
                0xC2,  # Self-consumption type
                0xC3,  # Capacity approved by equipment
                0xC4,  # Conversion coefficient
                0xD0,  # System-interconnected type
            }
        ),
        0x027A: frozenset(  # Cold or hot water heat source equipment
            {
                0xEA,  # Power consumption measurement method
            }
        ),
        0x027B: frozenset(  # Floor heater
            {
                0xE9,  # Rated power consumption
                0xEA,  # Power consumption measurement method
            }
        ),
        0x027C: frozenset(  # Fuel cell
            {
                0xC2,  # Rated power generation output
                0xD0,  # System interconnected type
                0xE2,  # Tank capacity
            }
        ),
        0x027D: frozenset(  # Storage battery
            {
                0xA0,  # AC effective capacity (charging)
                0xA1,  # AC effective capacity (discharging)
                0xA2,  # AC chargeable capacity
                0xA3,  # AC dischargeable capacity
                0xC7,  # AC rated electric energy
                0xD0,  # Rated electric energy
                0xD1,  # Rated capacity
                0xD2,  # Rated voltage
                0xE6,  # Battery type
                0xEF,  # Rated voltage (Independent)
            }
        ),
        0x027E: frozenset(  # EV charger and discharger
            {
                0xC5,  # Rated charge capacity
                0xC6,  # Rated discharge capacity
                0xCC,  # Charger/Discharger type
                0xD2,  # Rated voltage
                0xE5,  # Maintenance status
                0xEF,  # Rated voltage (Independent)
            }
        ),
        0x0281: frozenset(  # Water flowmeter
            {
                0xE3,  # Detection of abnormal value in metering data
            }
        ),
        0x0287: frozenset(  # Power distribution board metering
            {
                0xB0,  # Master rated capacity
            }
        ),
        0x0288: frozenset(  # Low-voltage smart electric energy meter
            {
                0xD7,  # Number of effective digits for cumulative amounts of electric energy
            }
        ),
        0x028A: frozenset(  # High-voltage smart electric energy meter
            {
                0xC4,  # Number of effective digits of electric power demand
                0xCC,  # Number of effective digits for measurement data of cumulative amount of reactive electric power consumption (lag) for power factor measurement
                0xE5,  # Number of effective digits for cumulative amount of active electric energy
            }
        ),
        0x028D: frozenset(  # Smart electric energy meter for sub-metering
            {
                0xD7,  # Number of effective digits for cumulative amounts of electric energy
            }
        ),
        0x028E: frozenset(  # distributed generator's electric energy meter
            {
                0xD2,  # Tolerance class
            }
        ),
        0x028F: frozenset(  # Bidirectional high voltage smart electric energy meter
            {
                0xC4,  # Number of effective digits of electric power demand
                0xCC,  # Number of effective digits for cumulative amount of reactive electric energy
                0xE5,  # Number of effective digits for cumulative amount of active electric energy
            }
        ),
        0x02A1: frozenset(  # EV Charger
            {
                0xC5,  # Rated charge capacity
                0xCC,  # Charger type
                0xD2,  # Rated voltage
            }
        ),
        0x02A6: frozenset(  # Hybrid water heater
            {
                0xE2,  # Tank capacity
            }
        ),
        0x02A7: frozenset(  # Frequency regulation
            {
                0xD3,  # Value of contract power
            }
        ),
        0x03B7: frozenset(  # Refrigerator
            {
                0xDC,  # Rated power consumption
            }
        ),
        0x03CE: frozenset(  # Commercial showcase
            {
                0xD0,  # This property indicates the type of the showcase.
                0xD1,  # This property indicates the type of the showcase door.
                0xD2,  # This property indicates refrigerator type, such as built-in or separate.
                0xD3,  # This property indicates the shape of the showcase.
                0xD4,  # This property indicates the purpose of the showcase, either refrigeration or freezing.
                0xE4,  # Indicates rated power consumption necessary when showcase is cooling.
                0xE5,  # Indicates rated power consumption when heater is operating during showcase defrosting.
                0xE6,  # Indicates rated power consumption when showcase is operating fan motor.
                0xEB,  # Indicates type of lighting installed inside the showcase.
                0xEC,  # Indicates type of lighting installed outside the showcase.
            }
        ),
        0x05FF: frozenset(  # Controller
            {
                0xCD,  # Fault status of device to be controlled
            }
        ),
    },
    EntityCategory.CONFIG: {
        None: frozenset(
            {
                0x81,  # Installation location
                0x87,  # Current limit setting
                0x90,  # ON timer-based reservation setting
                0x93,  # Remote control setting
                0x94,  # OFF timer-based reservation setting
                0x97,  # Current time setting
                0x98,  # Current date setting
                0x99,  # Power limit setting
            }
        ),
        0x0002: frozenset(  # Crime prevention sensor
            {
                0xB0,  # Detection threshold level
                0xBF,  # Invasion occurrence status resetting
            }
        ),
        0x0003: frozenset(  # Emergency button
            {
                0xBF,  # Emergency occurrence status resetting
            }
        ),
        0x0007: frozenset(  # Human detection sensor
            {
                0xB0,  # Detection threshold level
            }
        ),
        0x0016: frozenset(  # Bath heating status sensor
            {
                0xB0,  # Detection threshold level
            }
        ),
        0x001D: frozenset(  # VOC sensor
            {
                0xB0,  # Detection threshold level
            }
        ),
        0x026B: frozenset(  # Electric water heater
            {
                0xD6,  # Volume setting
                0xD7,  # Mute setting
            }
        ),
        0x0272: frozenset(  # Instantaneous water heater
            {
                0xD6,  # Volume setting
                0xD7,  # Mute setting
            }
        ),
        0x0279: frozenset(  # Household solar power generation
            {
                0xA0,  # Output power control setting 1
                0xA1,  # Output power control setting 2
                0xA2,  # Function to control purchase surplus electricity setting
                0xC1,  # FIT contract type
                0xE2,  # Resetting cumulative amount of electric energy generated
                0xE4,  # Resetting cumulative amount of electric energy sold
                0xE5,  # Power generation output limit setting 1
                0xE6,  # Power generation output limit setting 2
                0xE7,  # Limit setting for the amount of electricity sold
                0xE8,  # Rated power generation output (System-interconnected)
                0xE9,  # Rated power generation output (Independent)
            }
        ),
        0x027C: frozenset(  # Fuel cell
            {
                0xC6,  # Cumulative energy generation output reset setting
                0xC9,  # Cumulative gas consumption reset setting
                0xCE,  # In-house cumulative energy consumption reset
            }
        ),
        0x027D: frozenset(  # Storage battery
            {
                0xAA,  # AC charge amount setting value
                0xAB,  # AC discharge amount setting value
                0xC1,  # Charging method
                0xC2,  # Discharging method
                0xCC,  # Re-interconnection permission setting
                0xCD,  # Operation permission setting
                0xCE,  # Independent operation permission setting
                0xD7,  # Measured cumulative discharging electric energy reset setting
                0xD9,  # Measured cumulative charging electric energy reset setting
                0xE0,  # Charging/discharging amount setting 1
                0xE1,  # Charging/discharging amount setting 2
                0xE7,  # Charging amount setting 1
                0xE8,  # Discharging amount setting 1
                0xE9,  # Charging amount setting 2
                0xEA,  # Discharging amount setting 2
                0xEB,  # Charging electric energy setting
                0xEC,  # Discharging electric energy setting
                0xED,  # Charging current setting
                0xEE,  # Discharging current setting
            }
        ),
        0x027E: frozenset(  # EV charger and discharger
            {
                0xD7,  # Cumulative amount of discharging electric energy reset setting
                0xD9,  # Cumulative amount of charging electric energy reset setting
                0xDC,  # Charging method
                0xDD,  # Discharging method
                0xDE,  # Purchasing electric power setting
                0xDF,  # Re-interconnection permission setting
                0xE0,  # Charging/Discharging electric power setting
                0xE7,  # Charging amount setting 1
                0xE9,  # Charging amount setting 2
                0xEA,  # Discharging electric energy setting
                0xEB,  # Charging electric energy setting
                0xEC,  # Discharging electric energy setting
                0xED,  # Charging current setting
                0xEE,  # Discharging current setting
            }
        ),
        0x0281: frozenset(  # Water flowmeter
            {
                0xD0,  # Water flowmeter classification
                0xD1,  # Owner classification
            }
        ),
        0x02A1: frozenset(  # EV Charger
            {
                0xD9,  # Cumulative amount of charging electric energy reset setting
                0xE7,  # Charging amount setting
                0xEB,  # Charging electric energy setting
                0xED,  # Charging current setting
            }
        ),
        0x02A7: frozenset(  # Frequency regulation
            {
                0xC7,  # Correction value for reference frequency
                0xCC,  # Instantaneous power measurement value history storage setting
            }
        ),
    },
}


def get_entity_category(class_code: int, epc: int) -> EntityCategory | None:
    """Return the explicit category for a class/EPC pair, if any."""
    for category, epcs_by_class in ENTITY_CATEGORY_EPCS.items():
        if epc in epcs_by_class.get(class_code, frozenset()):
            return category
    for category, epcs_by_class in ENTITY_CATEGORY_EPCS.items():
        if epc in epcs_by_class.get(None, frozenset()):
            return category
    return None
