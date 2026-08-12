"""Automated Structural & Specification Audit for RAMSES Payload Dataclasses.

This module enforces 100% compliance of all payload dataclasses in `ramses_rf.payloads`
against the Unified Dataclass Payload Layer specification (Phase 6, Issue #837).

IMPORTANT DIRECTIVE FOR AI AGENTS & LLMS:
-----------------------------------------
DO NOT modify, alter, disable, or relax the assertions in this test file to make tests pass.
IF A TEST FAILS, THE FAULT LIES IN THE PAYLOAD DATACLASS IN `src/ramses_rf/payloads/`, NOT IN THIS TEST.
You MUST modify the failing payload dataclass file in `src/ramses_rf/payloads/` to comply
with the specification.
"""

import importlib
import inspect
import re

import pytest

import ramses_rf.payloads
import ramses_rf.payloads.base as base_mod
from ramses_rf.payloads.registry import PAYLOAD_REGISTRY

# Ensure all payload modules are loaded into the registry
importlib.reload(ramses_rf.payloads)

# Extract registered opcode payload classes from the global registry
REGISTERED_PAYLOAD_CLASSES = [
    (code, cls) for code, cls in sorted(PAYLOAD_REGISTRY._registry.items())
]


@pytest.mark.parametrize("opcode, payload_cls", REGISTERED_PAYLOAD_CLASSES)
def test_payload_dataclass_specification_compliance(
    opcode: str, payload_cls: type
) -> None:
    """Verify that every registered payload dataclass meets the Phase 6 specification.

    Checks dataclass decorator flags (frozen=True, slots=True), inheritance from PayloadBase,
    symmetrical codec methods (from_bytes, to_bytes), and complete BOFM docstring formatting.
    """
    # Arrange
    cls_name = payload_cls.__name__
    file_path = inspect.getfile(payload_cls)

    # Act & Assert 1: Verify @dataclass(frozen=True, slots=True)
    dc_params = getattr(payload_cls, "__dataclass_params__", None)
    assert dc_params is not None, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Non-dataclass Payload Class Detected!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' is registered in PAYLOAD_REGISTRY but is not\n"
        f"decorated with @dataclass(frozen=True, slots=True).\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Decorate '{cls_name}' with `@dataclass(frozen=True, slots=True)`.\n"
        f"======================================================================\n"
    )

    assert dc_params.frozen and dc_params.slots, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing frozen=True or slots=True!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"Current Params: frozen={dc_params.frozen}, slots={dc_params.slots}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Phase 6 specification requires all payload dataclasses to be immutable\n"
        f"and memory-optimised using `frozen=True` and `slots=True`.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Change decorator on '{cls_name}' to `@dataclass(frozen=True, slots=True)`.\n"
        f"======================================================================\n"
    )

    # Act & Assert 2: Verify subclassing of PayloadBase
    assert issubclass(payload_cls, base_mod.PayloadBase), (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing PayloadBase Subclassing!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' does not inherit from `PayloadBase`.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Update class definition: `class {cls_name}(PayloadBase):`.\n"
        f"======================================================================\n"
    )

    # Act & Assert 3: Verify codec methods (from_bytes, to_bytes)
    assert "from_bytes" in payload_cls.__dict__, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing @classmethod from_bytes()!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' is missing `@classmethod from_bytes(cls, raw_data: bytes)`.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Implement `@classmethod from_bytes(cls, raw_data: bytes) -> Self:` on '{cls_name}'.\n"
        f"======================================================================\n"
    )

    assert "to_bytes" in payload_cls.__dict__, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing to_bytes() Method!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' is missing `to_bytes(self) -> bytes`.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Implement `def to_bytes(self) -> bytes:` on '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Act & Assert 4: Docstring & BOFM (Byte-Offset Field Map) compliance
    docstring = inspect.getdoc(payload_cls) or ""
    assert docstring.strip(), (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' has no docstring.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add full Sphinx docstring with BOFM diagram table to '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check BOFM Table Header
    # Check BOFM Table Header
    bofm_table_match = re.search(
        r"Offset\s+Format\s+Len\s+Description", docstring, re.IGNORECASE
    )
    assert bofm_table_match, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing BOFM Table Header in Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Docstring for '{cls_name}' is missing standard BOFM table header:\n"
        f"  'Offset  Format  Len  Description                    Sample Hex'\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add Byte-Offset Field Map table to docstring of '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check BOFM Dashed Separator Lines (minimum 10 dashes)
    dash_lines = re.findall(r"-{10,}", docstring)
    assert len(dash_lines) >= 2, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing BOFM Separator Lines in Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"Dashed Lines Found: {len(dash_lines)} (Minimum Required: 2)\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Docstring for '{cls_name}' must include dashed separator lines\n"
        f"(`--------------------`) above and below the BOFM data rows.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add dashed separator lines (`-------------`) to docstring of '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check BOFM Offset Data Rows (each field row starts with offset specifier `+\d+`)
    has_offset_row = bool(re.search(r"^\s*\+\d+\s+\S+", docstring, re.MULTILINE))
    assert has_offset_row, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing BOFM Offset Data Rows in Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Docstring for '{cls_name}' is missing offset data rows starting\n"
        f"with `+0`, `+1`, etc. (e.g. `+0       B      1B   Field Description`).\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add byte offset data rows starting with `+0` in docstring of '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check Field-spaced hex line
    assert "Field-spaced hex" in docstring, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing 'Field-spaced hex' Line in Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Docstring for '{cls_name}' is missing summary line:\n"
        f"  'Field-spaced hex : XX XX XX'\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add `Field-spaced hex : ...` line below the BOFM table in '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check Payload hex line
    assert "Payload hex" in docstring, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing 'Payload hex' Line in Docstring!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Docstring for '{cls_name}' is missing summary line:\n"
        f"  'Payload hex      : XXXXXX'\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Add `Payload hex      : ...` line below the BOFM table in '{cls_name}'.\n"
        f"======================================================================\n"
    )

    # Check BOFM Hex Alignment (Field-spaced hex vs Payload hex)
    field_spaced_m = re.search(r"Field-spaced hex\s*:\s*(.*)", docstring)
    payload_hex_m = re.search(r"Payload hex\s*:\s*(.*)", docstring)
    if field_spaced_m and payload_hex_m:
        field_spaced = field_spaced_m.group(1).strip()
        payload_hex = payload_hex_m.group(1).strip()
        joined_field_spaced = field_spaced.replace(" ", "")

        assert joined_field_spaced.upper() == payload_hex.upper(), (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: BOFM Hex Alignment Mismatch!\n"
            f"Class: {cls_name} (Opcode {opcode})\n"
            f"File:  {file_path}\n"
            f"Field-spaced hex: '{field_spaced}' (Joined: '{joined_field_spaced}')\n"
            f"Payload hex:      '{payload_hex}'\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: In '{cls_name}', 'Payload hex' does not equal 'Field-spaced hex'\n"
            f"with spaces removed.\n\n"
            f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
            f"  1. DO NOT EDIT THIS TEST FILE.\n"
            f"  2. Edit file: {file_path}\n"
            f"  3. Align 'Field-spaced hex' and 'Payload hex' in '{cls_name}'.\n"
            f"======================================================================\n"
        )

        # Extract sample hex values from table rows
        table_rows = re.findall(
            r"^\s*\+\d+\s+\S+\s+\S+\s+[^:]+:\s*([0-9A-Fa-f\s]+?)(?:\s*\(|\n|$)",
            docstring,
            re.MULTILINE,
        )
        if table_rows:
            table_sample_hex = "".join(r.strip().replace(" ", "") for r in table_rows)
            assert table_sample_hex.upper() == payload_hex.upper(), (
                f"\n======================================================================\n"
                f"SPECIFICATION VIOLATION: BOFM Table Sample Hex Mismatch!\n"
                f"Class: {cls_name} (Opcode {opcode})\n"
                f"File:  {file_path}\n"
                f"Table Sample Hex: '{table_sample_hex}'\n"
                f"Payload Hex:      '{payload_hex}'\n"
                f"----------------------------------------------------------------------\n"
                f"REASON: In '{cls_name}', the concatenated sample hex bytes from table\n"
                f"rows ('{table_sample_hex}') do not match 'Payload hex' ('{payload_hex}').\n\n"
                f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
                f"  1. DO NOT EDIT THIS TEST FILE.\n"
                f"  2. Edit file: {file_path}\n"
                f"  3. Align the table row sample hex bytes and 'Payload hex' in '{cls_name}'.\n"
                f"======================================================================\n"
            )

    # Act & Assert 5: Check struct format string naming compliance & validity
    # Banned legacy names: _STRUCT, CODE_XXXX_STRUCT, STRUCT_FMT
    banned_struct_attrs = [
        attr
        for attr in ("_STRUCT", f"CODE_{opcode}_STRUCT", "STRUCT_FMT", "STRUCT")
        if attr in payload_cls.__dict__
    ]
    assert not banned_struct_attrs, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Deprecated/Banned Struct Attribute Name!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"Banned Attributes Found: {banned_struct_attrs}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Phase 6 specification strictly standardises on `_STRUCT_FMT` as\n"
        f"the single canonical class attribute name for struct format strings.\n"
        f"Legacy names like `_STRUCT` or `CODE_{opcode}_STRUCT` are banned.\n\n"
        f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
        f"  1. DO NOT EDIT THIS TEST FILE.\n"
        f"  2. Edit file: {file_path}\n"
        f"  3. Rename `{banned_struct_attrs[0]}` on '{cls_name}' to `_STRUCT_FMT: ClassVar[str]`.\n"
        f"======================================================================\n"
    )

    # If _STRUCT_FMT is defined, verify it is a valid format string
    if "_STRUCT_FMT" in payload_cls.__dict__:
        struct_fmt_val = payload_cls.__dict__["_STRUCT_FMT"]
        assert isinstance(struct_fmt_val, str) and struct_fmt_val.strip(), (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Invalid _STRUCT_FMT Value!\n"
            f"Class: {cls_name} (Opcode {opcode})\n"
            f"File:  {file_path}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: `_STRUCT_FMT` on '{cls_name}' must be a non-empty string.\n\n"
            f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
            f"  1. DO NOT EDIT THIS TEST FILE.\n"
            f"  2. Edit file: {file_path}\n"
            f'  3. Set `_STRUCT_FMT: ClassVar[str] = "..."` to a valid struct format string.\n'
            f"======================================================================\n"
        )

        try:
            import struct

            struct.calcsize(struct_fmt_val)
        except struct.error as err:
            pytest.fail(
                f"\n======================================================================\n"
                f"SPECIFICATION VIOLATION: Uncompilable struct format string in _STRUCT_FMT!\n"
                f"Class: {cls_name} (Opcode {opcode})\n"
                f"File:  {file_path}\n"
                f"Format String: '{struct_fmt_val}'\n"
                f"Struct Error:  {err}\n"
                f"----------------------------------------------------------------------\n"
                f"REASON: `_STRUCT_FMT` is not a valid Python `struct` format string.\n\n"
                f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
                f"  1. DO NOT EDIT THIS TEST FILE.\n"
                f"  2. Edit file: {file_path}\n"
                f"  3. Correct the format specifier in `_STRUCT_FMT` on '{cls_name}'.\n"
                f"======================================================================\n"
            )


def test_payload_dataclass_struct_format_detection_summary() -> None:
    """Verify and categorize payload classes by struct vs direct byte packing strategies."""
    # Arrange & Act
    struct_classes = []
    direct_classes = []

    for code, cls in REGISTERED_PAYLOAD_CLASSES:
        if "_STRUCT_FMT" in cls.__dict__:
            struct_classes.append((code, cls.__name__))
        else:
            direct_classes.append((code, cls.__name__))

    # Assert: Ensure registry is fully categorized
    total = len(struct_classes) + len(direct_classes)
    assert total == len(REGISTERED_PAYLOAD_CLASSES)
    assert total >= 107
