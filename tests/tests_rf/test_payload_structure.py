"""Automated Structural & Specification Audit for RAMSES Payload Dataclasses.

This module enforces 100% compliance of all payload dataclasses in `ramses_rf.payloads`
against the Unified Dataclass Payload Layer specification (Issue #837 V4 Standard).

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
    """Verify that every registered payload class meets the Issue #837 V4 specification.

    Checks Master Dispatcher interfaces, variant sub-dataclasses (frozen=True, slots=True),
    subclassing of PayloadBase, symmetrical codec methods (from_bytes, to_bytes),
    and complete BOFM docstring formatting.
    """
    cls_name = payload_cls.__name__
    file_path = inspect.getfile(payload_cls)

    # Master Dispatchers must implement from_bytes
    assert "from_bytes" in payload_cls.__dict__, (
        f"\n======================================================================\n"
        f"SPECIFICATION VIOLATION: Missing @classmethod from_bytes() on Dispatcher!\n"
        f"Class: {cls_name} (Opcode {opcode})\n"
        f"File:  {file_path}\n"
        f"----------------------------------------------------------------------\n"
        f"REASON: Class '{cls_name}' is registered in PAYLOAD_REGISTRY but missing\n"
        f"`@classmethod from_bytes(cls, raw_data: bytes)`.\n"
        f"======================================================================\n"
    )

    # Resolve target dataclasses to check (variants if dispatcher, else payload_cls)
    variants: tuple[type, ...] = getattr(
        payload_cls, "VARIANTS", (payload_cls,)
    )

    for target_cls in variants:
        target_name = target_cls.__name__
        target_file = inspect.getfile(target_cls)

        # Act & Assert 1: Verify @dataclass(frozen=True, slots=True)
        dc_params = getattr(target_cls, "__dataclass_params__", None)
        assert dc_params is not None, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Non-dataclass Payload Class Detected!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Variant payload class '{target_name}' is not decorated with\n"
            f"`@dataclass(frozen=True, slots=True)`.\n\n"
            f"ACTION REQUIRED FOR LLM / DEVELOPER:\n"
            f"  1. Edit file: {target_file}\n"
            f"  2. Decorate '{target_name}' with `@dataclass(frozen=True, slots=True)`.\n"
            f"======================================================================\n"
        )

        assert dc_params.frozen and dc_params.slots, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing frozen=True or slots=True!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"Current Params: frozen={dc_params.frozen}, slots={dc_params.slots}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: V4 specification requires all payload sub-dataclasses to be\n"
            f"immutable and memory-optimised using `frozen=True` and `slots=True`.\n"
            f"======================================================================\n"
        )

        # Act & Assert 2: Verify subclassing of PayloadBase
        assert issubclass(target_cls, base_mod.PayloadBase), (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing PayloadBase Subclassing!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Class '{target_name}' does not inherit from `PayloadBase`.\n"
            f"======================================================================\n"
        )

        # Act & Assert 3: Verify codec methods (from_bytes, to_bytes)
        assert "from_bytes" in target_cls.__dict__, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing @classmethod from_bytes()!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Class '{target_name}' missing `from_bytes(cls, raw_data: bytes)`.\n"
            f"======================================================================\n"
        )

        assert "to_bytes" in target_cls.__dict__, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing to_bytes() Method!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Class '{target_name}' missing `to_bytes(self) -> bytes`.\n"
            f"======================================================================\n"
        )

        # Act & Assert 4: Docstring & BOFM (Byte-Offset Field Map) compliance
        docstring = inspect.getdoc(target_cls) or ""
        assert docstring.strip(), (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Class '{target_name}' has no docstring.\n"
            f"======================================================================\n"
        )

        # Check BOFM Table Header
        bofm_table_match = re.search(
            r"Offset\s+Format\s+Len\s+Description", docstring, re.IGNORECASE
        )
        assert bofm_table_match, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing BOFM Table Header in Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Docstring for '{target_name}' missing BOFM table header.\n"
            f"======================================================================\n"
        )

        # Check BOFM Dashed Separator Lines (minimum 10 dashes)
        dash_lines = re.findall(r"-{10,}", docstring)
        assert len(dash_lines) >= 2, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing BOFM Separator Lines in Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Docstring for '{target_name}' must include dashed separator lines.\n"
            f"======================================================================\n"
        )

        # Check BOFM Offset Data Rows (each field row starts with offset specifier `+\d+`)
        has_offset_row = bool(
            re.search(r"^\s*\+\d+\s+\S+", docstring, re.MULTILINE)
        )
        assert has_offset_row, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing BOFM Offset Data Rows in Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Docstring for '{target_name}' missing byte offset data rows.\n"
            f"======================================================================\n"
        )

        # Check Field-spaced hex line
        assert "Field-spaced hex" in docstring, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing 'Field-spaced hex' Line in Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Docstring for '{target_name}' missing 'Field-spaced hex' line.\n"
            f"======================================================================\n"
        )

        # Check Payload hex line
        assert "Payload hex" in docstring, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Missing 'Payload hex' Line in Docstring!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: Docstring for '{target_name}' missing 'Payload hex' line.\n"
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
                f"Class: {target_name} (Opcode {opcode})\n"
                f"File:  {target_file}\n"
                f"Field-spaced hex: '{field_spaced}' (Joined: '{joined_field_spaced}')\n"
                f"Payload hex:      '{payload_hex}'\n"
                f"----------------------------------------------------------------------\n"
                f"REASON: In '{target_name}', 'Payload hex' does not equal 'Field-spaced hex'\n"
                f"with spaces removed.\n"
                f"======================================================================\n"
            )

        # Act & Assert 5: Check struct format string naming compliance & validity
        banned_struct_attrs = [
            attr
            for attr in (
                "_STRUCT",
                f"CODE_{opcode}_STRUCT",
                "STRUCT_FMT",
                "STRUCT",
            )
            if attr in target_cls.__dict__
        ]
        assert not banned_struct_attrs, (
            f"\n======================================================================\n"
            f"SPECIFICATION VIOLATION: Deprecated/Banned Struct Attribute Name!\n"
            f"Class: {target_name} (Opcode {opcode})\n"
            f"File:  {target_file}\n"
            f"Banned Attributes Found: {banned_struct_attrs}\n"
            f"----------------------------------------------------------------------\n"
            f"REASON: V4 specification strictly standardises on `_STRUCT_FMT` as\n"
            f"the single canonical class attribute name for struct format strings.\n"
            f"======================================================================\n"
        )

        # If _STRUCT_FMT is defined, verify it is a valid format string
        if "_STRUCT_FMT" in target_cls.__dict__:
            struct_fmt_val = target_cls.__dict__["_STRUCT_FMT"]
            assert (
                isinstance(struct_fmt_val, str) and struct_fmt_val.strip()
            ), (
                f"\n======================================================================\n"
                f"SPECIFICATION VIOLATION: Invalid _STRUCT_FMT Value!\n"
                f"Class: {target_name} (Opcode {opcode})\n"
                f"File:  {target_file}\n"
                f"======================================================================\n"
            )

            try:
                import struct

                struct.calcsize(struct_fmt_val)
            except struct.error as err:
                pytest.fail(
                    f"\n======================================================================\n"
                    f"SPECIFICATION VIOLATION: Uncompilable struct format string in _STRUCT_FMT!\n"
                    f"Class: {target_name} (Opcode {opcode})\n"
                    f"File:  {target_file}\n"
                    f"Format String: '{struct_fmt_val}'\n"
                    f"Struct Error:  {err}\n"
                    f"======================================================================\n"
                )


def test_payload_dataclass_struct_format_detection_summary() -> None:
    """Verify and categorize payload classes by struct vs direct byte packing strategies."""
    struct_classes: list[tuple[str, str]] = []
    direct_classes: list[tuple[str, str]] = []

    for code, cls in REGISTERED_PAYLOAD_CLASSES:
        variants: tuple[type, ...] = getattr(cls, "VARIANTS", (cls,))
        for target_cls in variants:
            if "_STRUCT_FMT" in target_cls.__dict__:
                struct_classes.append((code, target_cls.__name__))
            else:
                direct_classes.append((code, target_cls.__name__))

    total = len(struct_classes) + len(direct_classes)
    assert total >= 107


def test_all_discovered_payload_dataclasses_specification_compliance() -> None:
    """Verify that all payload classes defined across all payload modules meet the specification."""
    import ramses_rf.payloads.dhw as dhw_mod
    import ramses_rf.payloads.heating as heating_mod
    import ramses_rf.payloads.hvac as hvac_mod
    import ramses_rf.payloads.opentherm as opentherm_mod
    import ramses_rf.payloads.system as system_mod

    payload_modules = [
        dhw_mod,
        heating_mod,
        hvac_mod,
        opentherm_mod,
        system_mod,
    ]
    discovered_classes: list[type] = []

    for mod in payload_modules:
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                cls.__module__ == mod.__name__
                and issubclass(cls, base_mod.PayloadBase)
                and cls is not base_mod.PayloadBase
                and not name.endswith("BasePayload")
                and not name.endswith("Base")
            ):
                discovered_classes.append(cls)

    assert len(discovered_classes) >= 120, (
        f"Expected at least 120 payload classes across modules, found {len(discovered_classes)}"
    )

    for target_cls in discovered_classes:
        target_name = target_cls.__name__
        target_file = inspect.getfile(target_cls)

        # Check @dataclass(frozen=True, slots=True) for concrete dataclasses
        dc_params = getattr(target_cls, "__dataclass_params__", None)
        if dc_params is not None:
            assert dc_params.frozen and dc_params.slots, (
                f"Class '{target_name}' in {target_file} must have frozen=True, slots=True"
            )

        # Check presence of from_bytes and to_bytes
        assert "from_bytes" in target_cls.__dict__ or hasattr(
            target_cls, "from_bytes"
        ), f"Class '{target_name}' in {target_file} missing from_bytes"
        assert "to_bytes" in target_cls.__dict__ or hasattr(
            target_cls, "to_bytes"
        ), f"Class '{target_name}' in {target_file} missing to_bytes"


def test_master_dispatcher_variant_subclassing_and_decorator_exclusivity() -> (
    None
):
    """Verify polymorphic Master Dispatcher inheritance and @register_payload exclusivity.

    Enforces the PR #1037 / Issue #837 rule:
    1. Every variant in MasterDispatcher.VARIANTS must inherit directly from MasterDispatcher.
    2. Variant sub-dataclasses must NEVER carry @register_payload themselves.
    """
    for opcode, payload_cls in REGISTERED_PAYLOAD_CLASSES:
        variants: tuple[type, ...] = getattr(payload_cls, "VARIANTS", ())
        if not variants:
            continue

        assert isinstance(variants, tuple), (
            f"Master Dispatcher '{payload_cls.__name__}' VARIANTS must be a tuple"
        )

        for variant_cls in variants:
            v_name = variant_cls.__name__

            # 1. Direct inheritance check
            assert issubclass(variant_cls, payload_cls), (
                f"SPECIFICATION VIOLATION: Variant '{v_name}' does not inherit from "
                f"Master Dispatcher '{payload_cls.__name__}' for Opcode {opcode}!"
            )

            # 2. Decorator exclusivity check
            assert variant_cls not in PAYLOAD_REGISTRY._registry.values(), (
                f"SPECIFICATION VIOLATION: Variant '{v_name}' is decorated with @register_payload! "
                f"Only the Master Dispatcher '{payload_cls.__name__}' must be decorated."
            )


def test_opcode_registration_coverage_against_known_opcodes() -> None:
    """Verify that all known opcodes in CODE_NAME_LOOKUP are registered in PAYLOAD_REGISTRY."""
    from ramses_rf.protocol.ramses import CODE_NAME_LOOKUP

    missing_opcodes = [
        code.value
        for code in CODE_NAME_LOOKUP
        if str(code.value) not in PAYLOAD_REGISTRY._registry
    ]
    assert not missing_opcodes, (
        f"The following opcodes in CODE_NAME_LOOKUP are missing from PAYLOAD_REGISTRY: {missing_opcodes}"
    )
    assert len(PAYLOAD_REGISTRY._registry) >= 100
