from dataclasses import dataclass
from typing import Self, cast

import pytest

from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.base import PayloadBase
from ramses_rf.payloads.registry import (
    PAYLOAD_REGISTRY,
    PayloadRegistry,
    get_payload_class,
    register_payload,
)
from ramses_tx.const import Code


@dataclass(frozen=True, slots=True)
class DummyPayload(PayloadBase):
    val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        return cls(val=int.from_bytes(raw_data, byteorder="little"))

    def to_bytes(self) -> bytes:
        return self.val.to_bytes(1, byteorder="little")


def test_payload_base_serialization() -> None:
    # Arrange
    raw_input = b"\x05"

    # Act
    payload = DummyPayload.from_bytes(raw_input)
    encoded = payload.to_bytes()

    # Assert
    assert payload.val == 5
    assert encoded == raw_input


def test_payload_registry_registration() -> None:
    # Arrange
    registry = PayloadRegistry()

    # Act
    registry.register(Code._3150)(DummyPayload)

    # Assert
    assert Code._3150 in registry
    assert "3150" in registry
    assert registry.get(Code._3150) is DummyPayload
    assert registry.get("3150") is DummyPayload
    assert registry.get("9999") is None


def test_global_payload_registry_decorator() -> None:
    # Arrange & Act
    try:

        @register_payload("1234")
        @dataclass(frozen=True, slots=True)
        class SamplePayload(PayloadBase):
            data: int

            @classmethod
            def from_bytes(cls, raw_data: bytes) -> Self:
                return cls(data=0)

            def to_bytes(self) -> bytes:
                return b"\x00"

        # Assert
        assert get_payload_class("1234") is SamplePayload
    finally:
        PAYLOAD_REGISTRY._registry.pop("1234", None)


def test_payload_registry_clear() -> None:
    # Arrange
    registry = PayloadRegistry()
    registry.register("ABCD")(DummyPayload)

    # Act
    registry.clear()

    # Assert
    assert "ABCD" not in registry
    assert registry.get("ABCD") is None


def test_payload_to_dict_adapter() -> None:
    # Arrange
    payload = DummyPayload(val=42)

    # Act
    result = payload_to_dict(payload)

    # Assert
    assert result == {"val": 42}


def test_payload_to_dict_invalid_type() -> None:
    # Arrange & Act & Assert
    with pytest.raises(TypeError, match="Expected dataclass instance"):
        payload_to_dict(cast(PayloadBase, "not_a_dataclass"))
