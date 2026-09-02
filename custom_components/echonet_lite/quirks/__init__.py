"""Declarative device quirks for the HEMS Echonet Lite integration."""

from .registry import (
    QUIRKS,
    ClimateQuirk,
    QuirkRegistry,
    RawSensorDefinition,
    WaterHeaterQuirk,
)

__all__ = [
    "QUIRKS",
    "ClimateQuirk",
    "QuirkRegistry",
    "RawSensorDefinition",
    "WaterHeaterQuirk",
]
