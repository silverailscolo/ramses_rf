# Semantic Payload Registry Specification (Issue #837 V3 Standard)

## 1. Overview & Architectural Philosophy

The **RAMSES RF Semantic Payload Registry** defines standard binary serialization and deserialization contracts for RAMSES RF protocol packet payloads.

Historically, payload parsing relied on regular expressions over hexadecimal strings (`hex_regex`) or manual byte slicing (`raw_data[1:3]`). Under **GitHub Issue #837 (*Replace Hex-Regex with Binary Parsing*)**, all payload parsers are standardized to use Python's native `struct` module with declarative, C-level format specifications (`_STRUCT_FMT`).

### Core Design Goals
1. **Type Safety & Immutability**: All payload representations are defined as `@dataclass(frozen=True, slots=True)` subclasses inheriting from `PayloadBase`.
2. **Binary Performance**: Unpacking and packing operate directly on raw binary `bytes` using `struct.unpack_from` and `struct.pack`, eliminating string manipulation overhead.
3. **Self-Documenting Binary Layouts**: Every dataclass docstring includes a **Binary Offset Format Map (BOFM)** table documenting byte offsets, C format specifiers, field lengths, and sample raw hex values.
4. **Backwards Compatibility**: The `.to_dict()` method projects strongly-typed payload fields into legacy dictionary structures consumed by downstream Home Assistant and CQRS read-models.

---

## 2. When to Use `struct` vs. Direct Byte Access

| Data Pattern | Struct Usage Rule | Format Specifier Example |
| :--- | :--- | :--- |
| **Multi-byte fields (2+ bytes)** (int16, uint16, int32, ASCII string buffers) | **MANDATORY**: Must use `struct.unpack_from` and `struct.pack`. | `_STRUCT_FMT = ">h"` (int16), `_STRUCT_FMT = ">H"` (uint16) |
| **Multi-field records** (index + multi-byte value) | **MANDATORY**: Must use `struct.unpack_from` and `struct.pack`. | `_STRUCT_FMT = ">Bh"` (uint8 + int16) |
| **Repeated record arrays** (list of fixed-size binary chunks) | **MANDATORY**: Must use `struct.unpack_from` in list comprehensions. | `(struct.unpack_from(cls._STRUCT_FMT, raw_data, i) for i in range(0, len(raw_data), 3))` |
| **Simple 1-byte payloads / Single-byte flags** | **EXEMPT / OPTIONAL**: Simple single-byte payloads (`len(raw_data) == 1`) MAY use direct `raw_data[0]` indexing and `bytes([val])` packing without requiring `struct`. | `_STRUCT_FMT = ">B"` (Optional for 1-byte payloads) |

---

## 3. Canonical Specification Examples

### Example 1: Fixed / Multi-Field Payload (e.g. `HeatDemandPayload` - Opcode `3150`)

```python
from typing import ClassVar, Self, Any
from dataclasses import dataclass
import struct
from ramses_rf.payloads._base import PayloadBase, register_payload


@register_payload("3150")
@dataclass(frozen=True, slots=True)
class HeatDemandPayload(PayloadBase):
    """Heat demand payload (Opcode 3150).

    2-byte Heat Demand binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       B      1B   Heat Demand uint8 (0-200)    : 64 (50%)
      --------------------------------------------------------------
      Field-spaced hex : 00 64
      Payload hex      : 0064

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param demand_percent: Heat demand percentage (0.0 - 100.0).
    :type demand_percent: float
    """

    _STRUCT_FMT_2B: ClassVar[str] = ">BB"

    domain_or_zone_idx: int
    demand_percent: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack raw binary bytes into payload instance."""
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3150: {len(raw_data)}")
        idx, demand_raw = struct.unpack_from(cls._STRUCT_FMT_2B, raw_data, 0)
        return cls(domain_or_zone_idx=idx, demand_percent=demand_raw / 200.0)

    def to_bytes(self) -> bytes:
        """Pack payload instance into raw binary bytes."""
        demand_raw = min(200, max(0, int(round(self.demand_percent * 200.0))))
        return struct.pack(self._STRUCT_FMT_2B, self.domain_or_zone_idx, demand_raw)

    def to_dict(self) -> dict[str, Any]:
        """Convert payload to legacy dictionary representation."""
        return {
            "domain_or_zone_idx": f"{self.domain_or_zone_idx:02X}",
            "heat_demand": self.demand_percent,
        }
```

---

### Example 2: Multi-Record / Array Payload (e.g. `TemperaturePayload` - Opcode `30C9`)

```python
@register_payload("30C9")
@dataclass(frozen=True, slots=True)
class TemperaturePayload(PayloadBase):
    """Temperature payload (Opcode 30C9).

    3-byte Temperature binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       h      2B   Temperature (int16, degC*100): 08 34 (21.00°C)
      --------------------------------------------------------------
    """

    _STRUCT_FMT_3B: ClassVar[str] = ">Bh"
    _STRUCT_FMT_2B: ClassVar[str] = ">h"

    zone_idx: int | str | None
    temperature: float | bool | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self | list[Self]:
        """Unpack single or array temperature payload using struct offset iteration."""
        if len(raw_data) > 3 and len(raw_data) % 3 == 0:
            return [
                cls(
                    zone_idx=idx,
                    temperature=cls._parse_temp_val(temp_raw),
                )
                for idx, temp_raw in (
                    struct.unpack_from(cls._STRUCT_FMT_3B, raw_data, i)
                    for i in range(0, len(raw_data), 3)
                )
            ]

        if len(raw_data) == 2:
            idx_val: int | None = None
            (temp_raw,) = struct.unpack_from(cls._STRUCT_FMT_2B, raw_data, 0)
        elif len(raw_data) >= 3:
            idx_val, temp_raw = struct.unpack_from(cls._STRUCT_FMT_3B, raw_data, 0)
        else:
            raise ValueError(f"Invalid payload length for 30C9: {len(raw_data)}")

        return cls(zone_idx=idx_val, temperature=cls._parse_temp_val(temp_raw))
```

---

### Example 3: Simple 1-Byte Payload Exemption (e.g. `RelayFailsafePayload` - Opcode `0009`)

For simple 1-byte payloads (e.g., single uint8 flags or mode counters), using direct byte indexing (`raw_data[0]`) is simple and exempt from requiring `struct` calls, though `_STRUCT_FMT = ">B"` MAY be declared for completeness:

```python
@register_payload("0009")
@dataclass(frozen=True, slots=True)
class RelayFailsafePayload(PayloadBase):
    """Relay failsafe status payload (Opcode 0009).

    1-byte Failsafe binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Failsafe Mode Flag uint8     : 00
      --------------------------------------------------------------
    """

    failsafe_enabled: bool

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack 1-byte failsafe payload directly."""
        if not raw_data:
            raise ValueError("Payload cannot be empty")
        return cls(failsafe_enabled=bool(raw_data[0]))

    def to_bytes(self) -> bytes:
        """Pack 1-byte failsafe payload directly."""
        return bytes([1 if self.failsafe_enabled else 0])
```

---

## 4. Mandatory Requirements Checklist

1. **Class Decorators**:
   * `@register_payload("<OPCODE>")` MUST decorate the payload dataclass.
   * `@dataclass(frozen=True, slots=True)` MUST be applied for immutability and memory optimization.

2. **Declarative Format String Constants**:
   * `_STRUCT_FMT: ClassVar[str]` (or suffix variants `_STRUCT_FMT_2B`, `_STRUCT_FMT_HEADER`) MUST declare explicit Big-Endian (`>`) or Little-Endian (`<`) format strings for multi-byte payloads.

3. **Method Implementation**:
   * `@classmethod from_bytes(cls, raw_data: bytes)`: Must validate length and return single or list of payload instances using `struct.unpack_from` (or `raw_data[0]` for 1-byte payloads).
   * `to_bytes(self) -> bytes`: Must serialize attributes back to exact binary payload using `struct.pack` (or `bytes([val])` for 1-byte payloads).
   * `to_dict(self) -> dict[str, Any]`: Must return the canonical dictionary projection.

4. **Docstring BOFM Table**:
   * All public payload dataclasses MUST include a Sphinx docstring with a formatted **Binary Layout Table** specifying `Offset`, `Format`, `Len`, `Description`, and `Sample Hex`.

---

## 5. C Struct Format Conventions

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

## 6. Code Quality & Pre-commit Guidelines

All payload dataclass implementations must pass strict code verification:
* **Format & Linting**: `.venv/bin/prek run -a` and `.venv/bin/ruff check --select D <file.py>` (Sphinx docstring checks).
* **Strict Type Checking**: `.venv/bin/mypy --strict src/ tests/`.
* **Parity & Structure Suite**: `.venv/bin/pytest tests/tests_rf/test_payload_structure.py tests/tests_rf/test_payload_parity.py`.
