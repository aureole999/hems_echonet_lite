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
      "name_ja": "積算値"
    }
  ]
}
```

`class_code`, `manufacturer_code`, EPCs, and enum EDT values accept integers
or `0x`-prefixed strings. Numeric formats are `uint8`, `int8`, `uint16`,
`int16`, `uint32`, and `int32`; `scale` is applied after decoding. Enum values
declare their raw byte, stable key, and English/Japanese label. Set
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

Every entity/device key added to this file must also exist in `strings.json`,
`translations/en.json`, and `translations/ja.json`. Run
`python scripts/validate_quirks.py` to validate the schema, translation keys,
matching rules, and captured device decode fixtures.
