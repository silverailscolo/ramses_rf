# AI Agent Instructions and Guidelines for ramses_rf

This file contains behavioral rules and guardrails for any AI agent or LLM working on the `ramses_rf` codebase.

For all general coding, typing, docstring, and architectural standards, you **must strictly adhere** to [CONTRIBUTING.md](https://github.com/ramses-rf/ramses_rf/blob/master/CONTRIBUTING.md).

## 1. Identity, Tone & Behavior

* **AI Policy Compliance**: Strictly adhere to the project [AI Policy](AI_POLICY.md). You are an assistant tool; human contributors maintain sole responsibility for all submitted code, documentation, comments, issues, and PRs.
* **No Autonomous Submissions**: Never create pull requests, issues, or comments autonomously. All submissions must be human-verified.
* **No Generating Answers to Maintainers**: Never generate automated responses to maintainer review questions on PRs or issues. All answers must come from the human contributor's own understanding.
* **Professional Tone**: Keep feedback, PR titles, and PR descriptions professional, objective, and concise. Avoid marketing-style hype or aggressive terminology (e.g. avoid words like "lobotomy", "purge", "nuke", "eradicate").
* **No Advertising**: Never add signatures like "co-authored by Devin" or promote AI tools in commits, comments, code, or PR descriptions.
* **Wait for Approval**: Do not automatically commit or push code unless explicitly instructed by the user.
* **Must Pass Tests**: Ensure all linter checks (`prek`, `ruff`, `mypy --strict`) and test suites (`pytest`) pass cleanly before declaring success.
* **PR Description Framing**: Keep PR titles and descriptions lean, factual, and scaled to the complexity of the change. Avoid AI-generated lengthy risk analyses or hypothetical scenarios.

## 2. Code Modification Guardrails

* **Surgical Precision**: Modify only lines strictly necessary to complete the task. Do not perform unrequested "general cleanup" on legacy code.
* **Comment Preservation**: Treat existing inline comments, `#TODO`, `#FIXME`, and `#HACK` markers as sacred anchors. Git relies on line stability; preserving comments preserves history.
* **Wrap, Don't Hack**: When wrapping long comments or docstrings, never truncate sentences or strip English determiners/words to force line limits. Use standard multi-line wrapping.

## 3. Semantic Payload Registry & Binary Parsing (Issue #837 Standard)

* **Use Binary Struct Parsing**: Never implement or use hex string regular expressions (`hex_regex`) or raw byte slicing (`raw_data[1:3]`) for multi-byte binary payload parsing. Use Python's native `struct.unpack_from` and `struct.pack`. Simple 1-byte payloads (`len(raw_data) == 1`) are exempt and may use direct `raw_data[0]` byte indexing.
* **Declarative Format Constants**: Always declare explicit `_STRUCT_FMT: ClassVar[str]` constants on multi-byte payload dataclasses using Big-Endian (`>`) or Little-Endian (`<`) format strings.
* **Sphinx Docstring BOFM Tables**: Always document payload dataclasses with a Binary Offset Format Map (BOFM) table detailing field offsets, struct formats, byte lengths, and sample hex representations.
* **Architecture Spec Reference**: Consult [docs/developer_guide/payload_registry_spec.md](docs/developer_guide/payload_registry_spec.md) for detailed guidelines and opcode struct specifications.

## 4. Protocol Code & Verb Enumerations (Issue #1040 Standard)

* **Use Canonical Enums**: Always use `Code` and `Verb` (or `I_`, `RQ`, `RP`, `W_`) constants instead of hardcoded hex code strings or verb literals.
* **No Raw Magic Strings**: Never introduce raw 4-character hex strings for known RAMSES opcodes or 2-character verb strings.

## 5. Tooling & Execution Protocols

* **Tooling Execution**: Use project virtual environment binaries (e.g., `.venv/bin/pytest`, `.venv/bin/prek run -a`). Do not invent custom runner scripts or bypass existing quality checks.
* **Cross-Repository References**: Fully qualify cross-repository issue and PR references (e.g., `ramses-rf/ramses_cc#123`).
