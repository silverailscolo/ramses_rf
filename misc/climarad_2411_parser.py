"""Parser for ClimaRad Minibox 2411 parameter messages."""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


# Type definitions for parameter definitions
ParameterDef = dict[str, Any]
ParameterValueDef = dict[str, Any]

# ClimaRad Minibox parameter definitions
_CLIMARAD_2411_PARAMS: dict[str, ParameterDef] = {
    "000007": {
        "name": "base_vent_enabled",
        "description": "Base Ventilation Enable/Disable",
        "type": "boolean",
        "offset": 22,  # Byte 11 in payload
    },
    "000087": {
        "name": "parameter_87",
        "description": "Unknown Timer/Threshold (Value: 20)",
        "type": "uint8",
        "offset": 6,  # Byte 3
    },
    "000088": {
        "name": "timer_configuration",
        "description": "Timer Configuration (Multiple Values)",
        "type": "multi",
        "values": [
            {"name": "timer_seconds", "offset": 6, "length": 4, "description": "Timer in seconds (~90 min)"},
            {"name": "value_700", "offset": 10, "length": 8, "description": "Value 700 (unknown unit)"},
            {"name": "value_400", "offset": 18, "length": 8, "description": "Value 400 (unknown unit)"},
            {"name": "value_1900", "offset": 26, "length": 8, "description": "Value 1900 (unknown unit)"},
        ]
    },
    "0000DA": {
        "name": "parameter_da",
        "description": "Unknown Parameter (Value: 127/0x7F)",
        "type": "uint8",
        "offset": 6,  # Byte 3
    },
}


def parser_2411_climarad(payload: str, msg: Any) -> dict[str, Any]:
    """
    Parser for ClimaRad Minibox 2411 messages.

    Message structure:
    Bytes 0-2:   Parameter ID (6 hex chars)
    Bytes 3-19:  Parameter data (varies by parameter)
    Bytes 20-22: Footer/status (typically 01000000018A00 or similar)

    Args:
        payload: Hex string payload
        msg: Message object with verb attribute (RQ/RP/W/I)

    Returns:
        Dictionary with parsed parameter data
    """

    # Extract 3-byte parameter ID
    param_id = payload[:6]

    result: dict[str, Any] = {
        "parameter_id": param_id,
        "parameter_hex": f"0x{param_id}",
    }

    # Get parameter definition
    param_def: ParameterDef | None = _CLIMARAD_2411_PARAMS.get(param_id)

    if param_def:
        result["parameter_name"] = param_def["name"]
        result["description"] = param_def["description"]
    else:
        result["parameter_name"] = f"unknown_{param_id}"
        result["description"] = "Unknown ClimaRad parameter"
        _LOGGER.warning(
            f"Unknown ClimaRad parameter ID: {param_id}. "
            f"Payload: {payload}"
        )

    # For RQ (request) messages, just return parameter info
    if hasattr(msg, 'verb') and msg.verb == "RQ":
        return result

    # Parse payload based on parameter type
    if not param_def:
        # Unknown parameter - return raw data
        result["raw_data"] = payload[6:]
        return result

    param_type: str = param_def.get("type", "")

    try:
        if param_type == "boolean":
            offset = param_def["offset"]
            value = int(payload[offset:offset+2], 16)
            result["value"] = value
            result["enabled"] = bool(value)

        elif param_type == "uint8":
            uint8_offset = param_def["offset"]
            uint8_value = int(payload[uint8_offset:uint8_offset+2], 16)
            result["value"] = uint8_value

        elif param_type == "multi":
            # Parse multiple values
            values: dict[str, dict[str, Any]] = {}
            values_list = param_def.get("values", [])
            for val_def in values_list:
                if isinstance(val_def, dict):
                    multi_offset = val_def["offset"]
                    length = val_def["length"]
                    raw_value = payload[multi_offset:multi_offset+length]
                    parsed_value = int(raw_value, 16)

                    values[val_def["name"]] = {
                        "value": parsed_value,
                        "description": val_def["description"],
                        "raw": raw_value,
                    }

            result["values"] = values

        # Extract footer/status bytes (last 6 bytes typically)
        if len(payload) >= 46:
            result["footer"] = payload[-6:]
            result["status_flag"] = payload[38:40]  # Byte 19

    except (ValueError, IndexError) as err:
        _LOGGER.error(f"Error parsing 2411 payload for param {param_id}: {err}")
        result["error"] = str(err)
        result["raw_data"] = payload[6:]

    return result


def decode_2411_message(raw_message: str) -> dict[str, Any]:
    """
    Convenience function to decode a raw 2411 message.

    Args:
        raw_message: Raw hex payload string

    Returns:
        Parsed message dictionary

    Example:
        >>> decode_2411_message("0000070000000000010000000000000001000000018A00")
        {'parameter_id': '000007', 'parameter_name': 'base_vent_enabled',
         'value': 1, 'enabled': True, ...}
    """

    class MockMessage:
        verb = "RP"

    return parser_2411_climarad(raw_message, MockMessage())


# Example usage and testing
if __name__ == "__main__":
    # Test messages from your logs
    test_messages = [
        # Base vent OFF
        ("0000070000000000000000000000000001000000018A00", "Base vent OFF"),
        # Base vent ON
        ("0000070000000000010000000000000001000000018A00", "Base vent ON"),
        # Parameter 0x87
        ("0000871400000000000000000000000002000000018A00", "Parameter 0x87"),
        # Parameter 0xDA
        ("0000DA7F00000000000000000000000003000000018A00", "Parameter 0xDA"),
        # Parameter 0x88 - Timer config
        ("0000881510000002BC000001900000076C000000018A33", "Timer configuration"),
    ]

    print("ClimaRad Minibox 2411 Message Parser Test\n" + "="*50)

    for payload, description in test_messages:
        print(f"\n{description}:")
        print(f"Payload: {payload}")
        result = decode_2411_message(payload)

        print(f"Parameter: {result['parameter_name']} ({result['parameter_id']})")
        print(f"Description: {result['description']}")

        if "value" in result:
            print(f"Value: {result['value']}")
        if "enabled" in result:
            print(f"Enabled: {result['enabled']}")
        if "values" in result:
            print("Values:")
            for key, val in result["values"].items():
                print(f"  {key}: {val['value']} - {val['description']}")

        print("-" * 50)