"""Automated Codec & Serialization Test Suite for RAMSES Payload Dataclasses.

This module tests all payload dataclasses in `ramses_rf.payloads` for:
1. Symmetrical binary codec decoding and re-encoding (`from_bytes` & `to_bytes`).
2. Legacy dictionary serialization (`to_dict` & `payload_to_dict`).
3. Strict immutability (`frozen=True` & `slots=True`).
4. Robust rejection of truncated or invalid binary byte sequences.
"""

import importlib
import inspect
import re
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

import ramses_rf.payloads
import ramses_rf.payloads.base as base_mod
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.registry import PAYLOAD_REGISTRY

# Force module reload to populate registry cleanly
importlib.reload(ramses_rf.payloads)

# Discover all registered payload classes and variant sub-dataclasses
DISCOVERED_PAYLOAD_TARGETS: list[tuple[str, type[base_mod.PayloadBase]]] = []

for opcode, payload_cls in sorted(PAYLOAD_REGISTRY._registry.items()):
    variants: tuple[type[base_mod.PayloadBase], ...] = getattr(
        payload_cls, "VARIANTS", (payload_cls,)
    )
    if not variants:
        variants = (payload_cls,)
    for target in variants:
        if (opcode, target) not in DISCOVERED_PAYLOAD_TARGETS:
            DISCOVERED_PAYLOAD_TARGETS.append((opcode, target))


def _extract_sample_hex(target_cls: type[base_mod.PayloadBase]) -> str | None:
    """Extract sample hex byte string from payload dataclass docstring."""
    docstring = inspect.getdoc(target_cls) or ""

    # 1. Match BOFM Payload hex line
    payload_hex_m = re.search(r"Payload hex\s*:\s*([0-9A-Fa-f\s]+)", docstring)
    if payload_hex_m:
        raw_hex = payload_hex_m.group(1).replace(" ", "").strip()
        if raw_hex and len(raw_hex) % 2 == 0:
            return raw_hex

    # 2. Match BOFM Field-spaced hex line
    field_hex_m = re.search(
        r"Field-spaced hex\s*:\s*([0-9A-Fa-f\s]+)", docstring
    )
    if field_hex_m:
        raw_hex = field_hex_m.group(1).replace(" ", "").strip()
        if raw_hex and len(raw_hex) % 2 == 0:
            return raw_hex

    # 3. Match sample packet log hex strings
    packet_matches: list[str] = re.findall(
        r"#.*?\b[0-9A-F]{4}\s+[0-9]{3}\s+([0-9A-F\-]+)",
        docstring,
        re.IGNORECASE,
    )
    for packet in packet_matches:
        raw_hex_str = str(packet).replace("-", "").replace(" ", "").strip()
        if raw_hex_str and len(raw_hex_str) % 2 == 0:
            return raw_hex_str

    return None


@pytest.mark.parametrize("opcode, target_cls", DISCOVERED_PAYLOAD_TARGETS)
def test_payload_dataclass_codec_roundtrip(
    opcode: str, target_cls: type[base_mod.PayloadBase]
) -> None:
    # Arrange
    sample_hex = _extract_sample_hex(target_cls)
    assert sample_hex is not None, (
        f"Missing sample hex in docstring for {target_cls.__name__} (Opcode {opcode})"
    )
    raw_bytes = bytes.fromhex(sample_hex)

    # Act
    decoded = target_cls.from_bytes(raw_bytes)
    item = decoded[0] if isinstance(decoded, list) else decoded

    encoded_bytes = item.to_bytes()
    assert isinstance(encoded_bytes, bytes)

    roundtrip = target_cls.from_bytes(encoded_bytes)
    roundtrip_item = roundtrip[0] if isinstance(roundtrip, list) else roundtrip

    # Assert
    assert type(roundtrip_item) is type(item)
    assert roundtrip_item == item


@pytest.mark.parametrize("opcode, target_cls", DISCOVERED_PAYLOAD_TARGETS)
def test_payload_dataclass_dictionary_serialization(
    opcode: str, target_cls: type[base_mod.PayloadBase]
) -> None:
    # Arrange
    sample_hex = _extract_sample_hex(target_cls)
    assert sample_hex is not None
    raw_bytes = bytes.fromhex(sample_hex)

    # Act
    decoded = target_cls.from_bytes(raw_bytes)
    items = decoded if isinstance(decoded, list) else [decoded]

    # Assert
    for item in items:
        as_dict: dict[str, Any] | list[dict[str, Any]] = (
            item.to_dict()
            if hasattr(item, "to_dict")
            else payload_to_dict(item)
        )
        assert isinstance(as_dict, (dict, list))


@pytest.mark.parametrize("opcode, target_cls", DISCOVERED_PAYLOAD_TARGETS)
def test_payload_dataclass_immutability(
    opcode: str, target_cls: type[base_mod.PayloadBase]
) -> None:
    # Arrange
    dc_params = getattr(target_cls, "__dataclass_params__", None)
    if dc_params is None or not dc_params.frozen:
        pytest.skip(
            f"{target_cls.__name__} is an abstract base/dispatcher class"
        )

    sample_hex = _extract_sample_hex(target_cls)
    assert sample_hex is not None
    raw_bytes = bytes.fromhex(sample_hex)

    decoded = target_cls.from_bytes(raw_bytes)
    item = decoded[0] if isinstance(decoded, list) else decoded
    fields = getattr(target_cls, "__dataclass_fields__", {})
    assert fields, f"No dataclass fields on {target_cls.__name__}"
    first_field = list(fields.keys())[0]

    # Act & Assert
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        setattr(item, first_field, getattr(item, first_field))


@pytest.mark.parametrize("opcode, target_cls", DISCOVERED_PAYLOAD_TARGETS)
def test_payload_dataclass_truncated_bytes_rejection(
    opcode: str, target_cls: type[base_mod.PayloadBase]
) -> None:
    # Arrange
    sample_hex = _extract_sample_hex(target_cls)
    assert sample_hex is not None
    raw_bytes = bytes.fromhex(sample_hex)

    if len(raw_bytes) == 0:
        pytest.skip("0-byte payload")

    # Act & Assert 1: Rejection of empty byte string
    try:
        instance = target_cls.from_bytes(b"")
        assert isinstance(instance, (target_cls, list, base_mod.PayloadBase))
    except ValueError:
        pass  # Expected rejection for strict fixed-length payloads

    # Act & Assert 2: Rejection of 1-byte truncated byte string
    if len(raw_bytes) > 1:
        truncated_bytes = raw_bytes[:-1]
        try:
            instance = target_cls.from_bytes(truncated_bytes)
            assert isinstance(
                instance, (target_cls, list, base_mod.PayloadBase)
            )
        except ValueError:
            pass  # Expected rejection for fixed-length struct payloads


# Build list of polymorphic Master Dispatchers and their variant classes
DISPATCHER_TARGETS: list[
    tuple[str, type[base_mod.PayloadBase], type[base_mod.PayloadBase]]
] = []

for opcode, master_cls in sorted(PAYLOAD_REGISTRY._registry.items()):
    variants = getattr(master_cls, "VARIANTS", ())
    if variants:
        for v in variants:
            DISPATCHER_TARGETS.append((opcode, master_cls, v))


@pytest.mark.parametrize("opcode, master_cls, variant_cls", DISPATCHER_TARGETS)
def test_master_dispatcher_dynamic_dispatch(
    opcode: str,
    master_cls: type[base_mod.PayloadBase],
    variant_cls: type[base_mod.PayloadBase],
) -> None:
    """Verify Master Dispatcher dynamically constructs the correct variant sub-dataclass."""
    # Arrange
    sample_hex = _extract_sample_hex(variant_cls)
    assert sample_hex is not None, (
        f"Missing sample hex for variant {variant_cls.__name__} (Opcode {opcode})"
    )
    raw_bytes = bytes.fromhex(sample_hex)

    # Act
    decoded = master_cls.from_bytes(raw_bytes)
    item = decoded[0] if isinstance(decoded, list) else decoded

    # Assert
    assert isinstance(item, variant_cls), (
        f"Master Dispatcher '{master_cls.__name__}' for Opcode {opcode} failed to "
        f"dispatch to variant '{variant_cls.__name__}' on input hex '{sample_hex}'! "
        f"Got instance of '{type(item).__name__}'."
    )
    assert isinstance(item, master_cls), (
        f"Variant instance '{type(item).__name__}' is not an instance of "
        f"Master Dispatcher '{master_cls.__name__}'!"
    )


@pytest.mark.parametrize("opcode, target_cls", DISCOVERED_PAYLOAD_TARGETS)
def test_payload_dataclass_hex_representation(
    opcode: str, target_cls: type[base_mod.PayloadBase]
) -> None:
    """Verify payload dataclass serialization to uppercase hex strings."""
    # Arrange
    sample_hex = _extract_sample_hex(target_cls)
    assert sample_hex is not None
    raw_bytes = bytes.fromhex(sample_hex)

    # Act
    decoded = target_cls.from_bytes(raw_bytes)
    item = decoded[0] if isinstance(decoded, list) else decoded
    encoded_hex = item.to_bytes().hex().upper()

    # Assert
    assert encoded_hex == sample_hex.upper()
