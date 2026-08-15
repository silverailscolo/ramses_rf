# Semantic Payload Registry Specification (Issue #837 V4 Standard)

## 1. Overview & Architectural Philosophy

The **RAMSES RF Semantic Payload Registry** defines standard binary serialization and deserialization contracts for RAMSES RF protocol packet payloads.

Under **GitHub Issue #837 (*Replace Hex-Regex with Binary Parsing*)** and **GitHub Issue #1001 / PR #12 (*Polymorphic Factory & Boundary Adapter Retention*)**, all payload parsers are standardized to use Python's native `struct` module with declarative, C-level format specifications (`_STRUCT_FMT`).

### Core Design Goals
1. **Type Safety & Immutability**: All payload representations are defined as `@dataclass(frozen=True, slots=True)` subclasses inheriting from `PayloadBase` (defined in `src/ramses_rf/payloads/base.py`).
2. **Binary Performance**: Unpacking and packing operate directly on raw binary `bytes` using `struct.unpack_from` and `struct.pack`, eliminating string manipulation overhead.
3. **Self-Documenting Binary Layouts**: Every concrete sub-dataclass docstring includes a **Binary Offset Format Map (BOFM)** table documenting byte offsets, C format specifiers, field lengths, and sample raw hex values.
4. **Polymorphic Dispatching**: Opcodes supporting multiple payload lengths or structural variants use a **Master Dispatcher Class** acting as a polymorphic factory, delegating unpacking to dedicated variant sub-dataclasses.
5. **Grouped Code Layout & Comment Separators**: Master Dispatcher classes and their associated variant sub-dataclasses MUST be grouped together in source files, delimited by 72-character comment separator lines (`# ` + 70 `-` characters).
6. **Backwards Compatibility**: The `.to_dict()` boundary adapter projects strongly-typed payload fields into legacy dictionary structures consumed by downstream Home Assistant and CQRS read-models.

---

## 2. When to Use `struct` vs. Direct Byte Access

| Data Pattern | Struct Usage Rule | Format Specifier Example |
| :--- | :--- | :--- |
| **Multi-byte fields (2+ bytes)** (int16, uint16, int32, ASCII string buffers) | **MANDATORY**: Must use `struct.unpack_from` and `struct.pack`. | `_STRUCT_FMT = ">h"` (int16), `_STRUCT_FMT = ">H"` (uint16) |
| **Multi-field records** (index + multi-byte value) | **MANDATORY**: Must use `struct.unpack_from` and `struct.pack`. | `_STRUCT_FMT = ">Bh"` (uint8 + int16) |
| **Repeated record arrays** (list of fixed-size binary chunks) | **MANDATORY**: Must use `struct.unpack_from` in list comprehensions. | `(struct.unpack_from(cls._STRUCT_FMT, raw_data, i) for i in range(0, len(raw_data), 3))` |
| **Simple 1-byte payloads / Single-byte flags** | **EXEMPT / OPTIONAL**: Simple single-byte payloads (`len(raw_data) == 1`) MAY use direct `raw_data[0]` indexing and `bytes([val])` packing. | `_STRUCT_FMT = ">B"` (Optional for 1-byte payloads) |

---

## 3. Polymorphic Factory / Master Dispatcher Specification

When an opcode supports variable byte lengths or structural variants (e.g. 3-byte short vs 6-byte long formats), payload classes MUST implement the **Polymorphic Master Dispatcher Pattern** established in PR #1037:

### Architectural Rules for Variant Payloads:
1. **Master Dispatcher Class (Defined First)**:
   - Decorated with `@register_payload("<OPCODE>")`. Exactly **one** class per opcode carries this decorator.
   - Inherits directly from `PayloadBase` (defined in `src/ramses_rf/payloads/base.py`).
   - Declares `VARIANTS: ClassVar[tuple[type[PayloadBase], ...]] = ()` at class level.
   - Implements `@classmethod from_bytes(cls, raw_data: bytes)` which inspects `len(raw_data)` or header flags and delegates unpacking to the matching concrete sub-dataclass.
   - Implements `to_bytes(self) -> bytes` raising `NotImplementedError("Use concrete variant sub-dataclass")`.
   - Optionally defines `__new__` if dynamic direct instantiation is supported.
2. **Concrete Sub-Dataclasses (Defined Next)**:
   - Inherit **directly** from the Master Dispatcher class (e.g. `class DhwParams3BPayload(DhwParamsPayload):`).
   - Decorated with `@dataclass(frozen=True, slots=True)`.
   - MUST **NEVER** be decorated with `@register_payload` (this prevents dictionary collisions in `PAYLOAD_REGISTRY`).
   - Define an explicit `_STRUCT_FMT: ClassVar[str]` constant matching their exact byte layout.
   - Implement `@classmethod from_bytes(cls, raw_data: bytes)` with an explicit length guard (`if len(raw_data) < N: raise ValueError(...)`).
   - Implement `to_bytes(self) -> bytes` packing their fields with `struct.pack`.
   - Contain a dedicated Sphinx docstring with an exact BOFM layout table containing valid, real-world protocol sample hex.
   - If the Master Dispatcher defines `__new__`, sub-dataclasses MUST accept compatible optional default parameters (e.g. `duration_minutes: int | None = None`) to prevent Python's `__init__` dispatcher from raising keyword argument `TypeError`s.
3. **Module-Level `VARIANTS` Assignment**:
   - Immediately following the sub-dataclass definitions, assign the tuple of variant types to the Master Dispatcher:
     `MasterDispatcher.VARIANTS = (SubVariant1, SubVariant2, ...)`
4. **Grouped Source Placement & 72-Character Separators**:
   - In payload source modules (`dhw.py`, `heating.py`, `hvac.py`, `opentherm.py`, `system.py`), the Master Dispatcher class and all of its associated sub-dataclasses MUST be placed together as a single contiguous logical group.
   - Logical payload groups MUST be separated from adjacent payload groups using 72-character comment lines formatted as `# ` followed by 70 `-` characters:
     `# ----------------------------------------------------------------------`

---

## 4. Canonical Specification Examples

### Standard Imports
When implementing payload dataclasses, the following standard imports are required:
```python
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, ClassVar, Self

from ramses_rf.payloads.base import PayloadBase
from ramses_rf.protocol.messages import register_payload
```

---

### Example 1: Fixed / Single-Layout Payload (e.g. `TemperaturePayload` - Opcode `0002`)

```python
# ----------------------------------------------------------------------


@register_payload("0002")
@dataclass(frozen=True, slots=True)
class TemperaturePayload(PayloadBase):
    """Temperature reading payload (Opcode 0002).

    3-byte Temperature binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       h      2B   Temperature °C (int16*100)   : 08 34 (21.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 0834
      Payload hex      : 000834

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param temperature: Temperature in °C.
    :type temperature: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">Bh"

    zone_idx: int
    temperature: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack raw binary bytes into payload instance."""
        if len(raw_data) < 3:
            raise ValueError(
                f"Invalid payload length for TemperaturePayload: {len(raw_data)}"
            )
        idx, temp_raw = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        temp_val = None if temp_raw in (0x7FFF, 0x31FF) else temp_raw / 100.0
        return cls(zone_idx=idx, temperature=temp_val)

    def to_bytes(self) -> bytes:
        """Pack payload instance into raw binary bytes."""
        temp_raw = (
            0x7FFF
            if self.temperature is None
            else int(round(self.temperature * 100.0))
        )
        return struct.pack(self._STRUCT_FMT, self.zone_idx, temp_raw)

    def to_dict(self) -> dict[str, Any]:
        """Convert payload to legacy dictionary representation."""
        return {
            "zone_idx": f"{self.zone_idx:02X}",
            "temperature": self.temperature,
        }
```

---

### Example 2: Polymorphic Master Dispatcher & Sub-Dataclasses (e.g. `DhwParamsPayload` - Opcode `10A0`)

```python
# ----------------------------------------------------------------------


@register_payload("10A0")
class DhwParamsPayload(PayloadBase):
    """Master payload dispatcher for DHW parameters (Opcode 10A0)."""

    VARIANTS: ClassVar[tuple[type[PayloadBase], ...]] = ()

    dhw_idx: int
    setpoint: float | None
    overrun: int | None = None
    differential: float | None = None

    @classmethod
    def from_bytes(
        cls, raw_data: bytes
    ) -> "DhwParams3BPayload | DhwParams6BPayload":
        """Unpack DHW parameters payload, dispatching by length."""
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        if len(raw_data) >= 6:
            return DhwParams6BPayload.from_bytes(raw_data)
        return DhwParams3BPayload.from_bytes(raw_data)

    def to_bytes(self) -> bytes:
        """Pack payload base default method.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        :raises NotImplementedError: Master dispatcher must dispatch to
            variant sub-dataclass.
        """
        raise NotImplementedError("Use concrete variant sub-dataclass")


@dataclass(frozen=True, slots=True)
class DhwParams3BPayload(DhwParamsPayload):
    """DHW 3-byte parameters layout (Opcode 10A0).

    3-byte DHW Parameters binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 13 88 (50.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1388
      Payload hex      : 001388

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param setpoint: Target setpoint temperature in °C.
    :type setpoint: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">Bh"

    dhw_idx: int
    setpoint: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack 3-byte DHW parameters binary payload."""
        if len(raw_data) < 3:
            raise ValueError(
                f"Invalid payload length for DhwParams3BPayload: {len(raw_data)}"
            )
        idx, sp_raw = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        sp_val = None if sp_raw in (0x31FF, 0x7FFF, 0x639C) else sp_raw / 100.0
        return cls(dhw_idx=idx, setpoint=sp_val)

    def to_bytes(self) -> bytes:
        """Pack 3-byte DHW parameters into binary payload."""
        sp_raw = (
            0x7FFF
            if self.setpoint is None
            else int(round(self.setpoint * 100.0))
        )
        return struct.pack(self._STRUCT_FMT, self.dhw_idx, sp_raw)


@dataclass(frozen=True, slots=True)
class DhwParams6BPayload(DhwParamsPayload):
    """DHW 6-byte parameters layout (Opcode 10A0).

    6-byte DHW Parameters binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 13 88 (50.00°C)
      +3       B      1B   Overrun minutes (uint8)      : 00
      +4       h      2B   Differential °C (int16*100)  : 03 E4 (10.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1388 00 03E4
      Payload hex      : 0013880003E4

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param setpoint: Target setpoint temperature in °C.
    :type setpoint: float | None
    :param overrun: Overrun time in minutes.
    :type overrun: int
    :param differential: Temperature differential in °C.
    :type differential: float
    """

    _STRUCT_FMT: ClassVar[str] = ">BhBh"

    dhw_idx: int
    setpoint: float | None
    overrun: int
    differential: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack 6-byte DHW parameters binary payload."""
        if len(raw_data) < 6:
            raise ValueError(
                f"Invalid payload length for DhwParams6BPayload: {len(raw_data)}"
            )
        idx, sp_raw, overrun, diff_raw = struct.unpack_from(
            cls._STRUCT_FMT, raw_data, 0
        )
        sp_val = None if sp_raw in (0x31FF, 0x7FFF, 0x639C) else sp_raw / 100.0
        return cls(
            dhw_idx=idx,
            setpoint=sp_val,
            overrun=overrun,
            differential=diff_raw / 100.0,
        )

    def to_bytes(self) -> bytes:
        """Pack 6-byte DHW parameters into binary payload."""
        sp_raw = (
            0x7FFF
            if self.setpoint is None
            else int(round(self.setpoint * 100.0))
        )
        diff_raw = int(round(self.differential * 100.0))
        return struct.pack(
            self._STRUCT_FMT, self.dhw_idx, sp_raw, self.overrun, diff_raw
        )


# Update VARIANTS property after variants are defined
DhwParamsPayload.VARIANTS = (
    DhwParams3BPayload,
    DhwParams6BPayload,
)
```

---

### Example 3: Repeated Record Arrays (e.g. `ZoneConfigPayload` - Opcode `000A`)

```python
# ----------------------------------------------------------------------


@register_payload("000A")
@dataclass(frozen=True, slots=True)
class ZoneConfigPayload(PayloadBase):
    """Zone config payload (Opcode 000A).

    6-byte Zone Config binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       B      1B   Zone Flags (uint8)           : 0A
      +2       h      2B   Min Temp °C (int16*100)      : 01 F4 (5.00°C)
      +4       h      2B   Max Temp °C (int16*100)      : 0D AC (35.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 0A 01F4 0DAC
      Payload hex      : 000A01F40DAC

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param zone_flags: Zone flags byte.
    :type zone_flags: int
    :param min_temp: Minimum zone temperature setting in °C.
    :type min_temp: float | None
    :param max_temp: Maximum zone temperature setting in °C.
    :type max_temp: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">BBhh"

    zone_idx: int
    zone_flags: int
    min_temp: float | None
    max_temp: float | None

    @classmethod
    def _from_bytes_single(cls, raw_data: bytes, offset: int = 0) -> Self:
        """Unpack a single 6-byte zone config from offset."""
        idx, flags, min_raw, max_raw = struct.unpack_from(
            cls._STRUCT_FMT, raw_data, offset
        )
        return cls(
            zone_idx=idx,
            zone_flags=flags,
            min_temp=None if min_raw in (0x7FFF, 0x31FF) else min_raw / 100.0,
            max_temp=None if max_raw in (0x7FFF, 0x31FF) else max_raw / 100.0,
        )

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self | list[Self]:
        """Unpack single or multi-zone array payload."""
        if len(raw_data) < 6 or len(raw_data) % 6 != 0:
            raise ValueError(
                f"Invalid payload length for ZoneConfigPayload: {len(raw_data)}"
            )
        if len(raw_data) > 6:
            return [
                cls._from_bytes_single(raw_data, i)
                for i in range(0, len(raw_data), 6)
            ]
        return cls._from_bytes_single(raw_data, 0)

    def to_bytes(self) -> bytes:
        """Pack zone config into binary payload."""
        min_raw = (
            0x7FFF
            if self.min_temp is None
            else int(round(self.min_temp * 100.0))
        )
        max_raw = (
            0x7FFF
            if self.max_temp is None
            else int(round(self.max_temp * 100.0))
        )
        return struct.pack(
            self._STRUCT_FMT, self.zone_idx, self.zone_flags, min_raw, max_raw
        )
```

---

## 5. Mandatory Requirements Checklist

1. **Class Decorators & Exclusivity**:
   - Single-layout classes: `@register_payload("<OPCODE>")` and `@dataclass(frozen=True, slots=True)`.
   - Multi-variant opcodes: Exactly **one** Master Dispatcher carries `@register_payload("<OPCODE>")`. Sub-dataclasses inherit from the Master Dispatcher and carry `@dataclass(frozen=True, slots=True)`. Sub-dataclasses must **never** be decorated with `@register_payload`.

2. **Declarative Format String Constants**:
   - Concrete sub-dataclasses MUST declare explicit `_STRUCT_FMT: ClassVar[str]` specifiers for multi-byte layouts (Big-Endian `>` or Little-Endian `<`).

3. **Method Implementation & Length Guards**:
   - `@classmethod from_bytes(cls, raw_data: bytes)`: Must unpack raw binary data and include an explicit length guard (`if len(raw_data) < N: raise ValueError(...)`).
   - `to_bytes(self) -> bytes`: Must serialize attributes back into exact raw binary payload bytes using `struct.pack`.
   - `to_dict(self) -> dict[str, Any]`: The `PayloadBase.to_dict()` adapter automatically calls `dataclasses.asdict()`. You MUST NOT override `to_dict()` unless downstream legacy test compatibility strictly requires field key or hex formatting transforms.

4. **Docstring BOFM Table & Group Comment Separators**:
   - All concrete payload dataclasses MUST include a Sphinx docstring with a formatted **Binary Offset Format Map (BOFM)** table specifying `Offset`, `Format`, `Len`, `Description`, and valid protocol `Sample Hex` that round-trips cleanly.
   - Docstring lines MUST comply with PEP 8 standards (<= 72 characters).
   - Master Dispatcher classes and associated sub-dataclasses MUST be grouped together and separated using `# ` + 70 `-` characters (`# ----------------------------------------------------------------------`).

---

## 6. C Struct Format Conventions

| Struct Format Code | C Type | Bytes | Python Equivalent | Protocol Usage |
| :--- | :--- | :--- | :--- | :--- |
| `>B` | `unsigned char` | 1 | `int` | Zone index, domain ID, flags, demand uint8 |
| `>b` | `signed char` | 1 | `int` | Signed offset or temperature difference |
| `>H` | `unsigned short` | 2 | `int` | 16-bit counter, cycle countdown, minutes |
| `>h` | `signed short` | 2 | `int` / `float` | Temperature (degC * 100), pressure |
| `>I` | `unsigned int` | 4 | `int` | 32-bit timestamp, device address integer |
| `>20s` | `char[]` | 20 | `bytes` / `str` | Null-padded ASCII zone names |
| `x` | Pad byte | 1 | (ignored) | Reserved / alignment padding byte |

---

## 7. Code Quality & Pre-commit Guidelines

All payload dataclass implementations must pass strict code verification:
* **Format & Linting**: `.venv/bin/prek run -a` and `.venv/bin/ruff check --select D <file.py>` (Sphinx docstring checks).
* **Strict Type Checking**: `.venv/bin/mypy --strict src/ tests/`.
* **Parity & Structure Suite**: `.venv/bin/pytest tests/tests_rf/test_payload_structure.py tests/tests_rf/test_payload_parity.py tests/tests_rf/test_payload_codecs.py`.

