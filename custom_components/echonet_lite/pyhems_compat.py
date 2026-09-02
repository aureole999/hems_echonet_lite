"""Compatibility helpers for released and development pyhems versions."""

from enum import IntEnum

try:
    from pyhems import DeviceClass
except ImportError:
    # pyhems 0.8.8 contains these definitions but does not yet export the
    # generated DeviceClass enum. A future export is used automatically.
    class DeviceClass(IntEnum):
        """ECHONET Lite class codes used by the integration."""

        HOME_AIR_CONDITIONER = 0x0130
        VENTILATION_FAN = 0x0133
        AIR_CONDITIONER_VENTILATION_FAN = 0x0134
        AIR_CLEANER = 0x0135
        ELECTRIC_BLIND_SHADE = 0x0260
        ELECTRIC_RAIN_DOOR = 0x0263
        ELECTRIC_WATER_HEATER = 0x026B
        ELECTRIC_LOCK = 0x026F
        INSTANTANEOUS_WATER_HEATER = 0x0272
        PV_POWER_GENERATION = 0x0279
        FLOOR_HEATER = 0x027B
        STORAGE_BATTERY = 0x027D
        EV_CHARGER_DISCHARGER = 0x027E
        WATT_HOUR_METER = 0x0280
        WATER_FLOW_METER = 0x0281
        GAS_METER = 0x0282
        POWER_DISTRIBUTION_BOARD_METERING = 0x0287
        GENERAL_LIGHTING = 0x0290
        MONO_FUNCTIONAL_LIGHTING = 0x0291
        MULTIPLE_INPUT_PCS = 0x02A5
        HYBRID_WATER_HEATER = 0x02A6
        COMBINATION_MICROWAVE_OVEN = 0x03B8
        RICE_COOKER = 0x03BB
        SWITCH = 0x05FD
        CONTROLLER = 0x05FF


__all__ = ["DeviceClass"]
