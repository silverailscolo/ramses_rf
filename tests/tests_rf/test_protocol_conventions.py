"""Test protocol coding conventions and forbid magic code/verb strings."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from ramses_tx.const import Code, Verb

VERBS: set[str] = {verb.value for verb in Verb}
KNOWN_CODES: set[str] = {code.value for code in Code}

EXCLUDED_FILES: set[str] = {
    "src/ramses_tx/const.py",
    "tests/tests_rf/test_protocol_conventions.py",
}


class LiteralAuditor(ast.NodeVisitor):
    """AST visitor to detect raw protocol verbs and command code string literals."""

    def __init__(self, filepath: str, lines: list[str]) -> None:
        """Initialise auditor with file path and raw text lines."""
        self.filepath = filepath
        self.lines = lines
        self.findings: list[dict[str, Any]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Skip __all__ export lists."""
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Skip TypedDict calls."""
        if isinstance(node.func, ast.Name) and node.func.id == "TypedDict":
            return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Inspect constant AST node for forbidden verb/code literals."""
        if not isinstance(node.value, str):
            return

        val = node.value
        line_num = node.lineno
        line_content = (
            self.lines[line_num - 1].strip() if line_num <= len(self.lines) else ""
        )

        if line_content.startswith('"""') or line_content.startswith("'''"):
            return
        if line_content.endswith('"""') or line_content.endswith("'''"):
            return

        if val in VERBS:
            if "Verb." in line_content or "class Verb" in line_content:
                return
            self.findings.append(
                {
                    "file": self.filepath,
                    "line": line_num,
                    "type": "VERB",
                    "val": val,
                    "content": line_content,
                }
            )
        elif val in KNOWN_CODES:
            if f"_{val} =" in line_content or f"_{val}=" in line_content:
                return
            if "DEVICE_ID_REGEX" in line_content or "RAW_LINE_REGEX" in line_content:
                return
            if (
                "hex_to_temp" in line_content
                or "hex_from_temp" in line_content
                or "hex_to_percent" in line_content
            ):
                return
            if (
                "null_hex" in line_content
                or 'else "7FFF"' in line_content
                or "self.payload[2:4]" in line_content
            ):
                return
            if (
                'val_30 == "7FFF"' in line_content
                or 'value == "7FFF"' in line_content
                or 'return "7FFF"' in line_content
            ):
                return
            self.findings.append(
                {
                    "file": self.filepath,
                    "line": line_num,
                    "type": "CODE",
                    "val": val,
                    "content": line_content,
                }
            )


def audit_directory(root_dir: str) -> list[dict[str, Any]]:
    """Audit all python files in root_dir for hardcoded literals."""
    all_findings: list[dict[str, Any]] = []
    root = Path(root_dir).resolve()
    base_dir = Path(__file__).parents[2].resolve()

    if root.is_file():
        try:
            rel_path = str(root.relative_to(base_dir))
        except ValueError:
            rel_path = str(root)
        try:
            with open(root, encoding="utf-8") as f:
                content = f.read()
            lines = content.splitlines()
            tree = ast.parse(content, filename=str(root))
            auditor = LiteralAuditor(rel_path, lines)
            auditor.visit(tree)
            all_findings.extend(auditor.findings)
        except SyntaxError:
            pass
        return all_findings

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in ("build", "dist", "__pycache__", "egg-info")
        ]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            py_file = Path(dirpath) / fname
            try:
                rel_path = str(py_file.relative_to(base_dir))
            except ValueError:
                rel_path = str(py_file)
            if rel_path in EXCLUDED_FILES or rel_path.startswith("."):
                continue

            try:
                with open(py_file, encoding="utf-8") as f:
                    content = f.read()
                lines = content.splitlines()
                tree = ast.parse(content, filename=str(py_file))
                auditor = LiteralAuditor(rel_path, lines)
                auditor.visit(tree)
                all_findings.extend(auditor.findings)
            except SyntaxError:
                pass

    return all_findings


def test_no_hardcoded_code_or_verb_literals_in_source() -> None:
    # Arrange
    src_dir = str(Path(__file__).parents[2] / "src")

    # Act
    findings = audit_directory(src_dir)

    # Assert
    assert not findings, (
        f"Found {len(findings)} hardcoded Code/Verb literals in src/: {findings}"
    )


def test_no_hardcoded_code_or_verb_literals_in_tests() -> None:
    # Arrange
    tests_dir = str(Path(__file__).parents[2] / "tests")

    # Act
    findings = audit_directory(tests_dir)

    # Assert
    assert not findings, (
        f"Found {len(findings)} hardcoded Code/Verb literals in tests/: {findings}"
    )
