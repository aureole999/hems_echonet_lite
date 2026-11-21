# Device quirks

`devices.json` contains device-specific protocol definitions and small behavior
adaptations that are not available from the upstream pyhems registry.

The file is loaded when the integration modules are imported, so Home Assistant
must be restarted after editing it. The integration validates the schema and
fails early on malformed class codes, EPCs, access rules, or numeric formats.

Profiles match by ECHONET Lite class code and may additionally match a
manufacturer code and one or more product codes. Entity entries support:

- `numeric`: signed/unsigned 8-, 16-, or 32-bit values, unit and scale;
- `enum`: read-only enum sensors or writable switches/selects;
- `raw`: read-only diagnostic sensors exposing EDT as hexadecimal text.

Example:

```json
{
  "id": "vendor_model",
  "match": {
    "class_code": "0x027C",
    "manufacturer_code": "0x00000B",
    "product_codes": ["MODEL-CODE"]
  },
  "verified": true,
  "entities": [
    {
      "id": "quirk_vendor_total",
      "epc": "0xF6",
      "type": "numeric",
      "format": "uint32",
      "unit": "L",
      "scale": 0.01,
      "minimum": 0,
      "maximum": 4294967293,
      "get": "optional",
      "set": "notApplicable",
      "name_en": "Cumulative total",
      "name_ja": "積算値",
      "name_zh": "累计值",
      "quantity": "water_volume",
      "value_kind": "cumulative"
    }
  ]
}
```

`class_code`, `manufacturer_code`, EPCs, and enum EDT values accept integers
or `0x`-prefixed strings. Numeric formats are `uint8`, `int8`, `uint16`,
`int16`, `uint32`, and `int32`; `scale` is applied after decoding. Enum values
declare their raw byte, stable key, and English/Japanese/Chinese label
(`name_en`, `name_ja`, `name_zh`). Set
`settle_seconds` on a writable binary enum when the appliance reports the old
state for a while after accepting a command.

Local definitions are fallbacks by default. If a future pyhems release defines
the same EPC, the upstream definition wins automatically. Use
`replace_upstream: true` only when a real device advertises a different access
rule than the generic MRA definition.

Behavior entries currently support:

- claiming generic EPCs for a dedicated platform entity;
- optimistic switch state settling delays;
- raw-value based sensor suppression with declared dependency EPCs;
- climate fan labels, target humidity and power-saving presets;
- a water-heater aggregate backed by configurable operation and temperature
  EPCs.

## Names and translations

Names are written once, here, with `name_en`, `name_ja` and `name_zh`
fields: on entities and enum values, `device_name_*` next to
`device_translation_key`, on each climate `fan_mode_labels` item, and
`name_*`/`operation_on_name_*`/`operation_off_name_*` on the water-heater
behavior. Other fork strings (Chinese names for upstream entities, config
titles) live in `quirks/translations/<lang>.json` in Home Assistant's
translation layout.

Upstream's `strings.json` and `translations/*.json` are never edited in the
repository. `scripts/fork_build.py` merges the fork strings into a copy when
building the release archive. To try a local checkout in Home Assistant, run
`python scripts/quirk_translations.py --write` first and do not commit the
result.

## Platform behavior

Quirk behavior lives in this package (`climate.py`, `switch.py`, `sensor.py`,
`water_heater.py`). Upstream platform modules only wrap their entity class,
for example `quirk_climate(EchonetLiteClimate)`, or call one
`async_setup_quirk_*` function, so merges from upstream touch a few lines.

## Validation

Run `python scripts/validate_quirks.py` to validate the schema, generated
translation keys, matching rules and captured device decode fixtures, and
`python scripts/validate_platforms.py` (needs Home Assistant installed) for
the platform behavior.

Numeric definitions declare `quantity` (for example `water_volume`, `energy`
or `temperature`) and `value_kind` (`measurement`, `total`, `cumulative`).
These set Home Assistant device classes and state classes; there is no
separate `state_class` field.

Counters that the device clears every day (for example ENE-FARM's "today"
hot-water volumes) use `"value_kind": "total"` with `"daily_reset": true`.
The sensor then reports `last_reset`, and a new cycle starts only when the
value falls to half or less after local midnight. Unlike `cumulative`
(`total_increasing`), a brief lower reading during the day is recorded as a
small negative change instead of a meter reset that counts the whole value
again.
