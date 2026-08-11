[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## How to contribute to ramses_rf

#### **Did you find a bug?**

* **Do not open up a GitHub issue if the bug is a security vulnerability in ramses_rf**, and instead refer to our [security policy](SECURITY).

* **Ensure the bug was not already reported** by searching on GitHub under [Issues](https://github.com/ramses-rf/ramses_rf/issues).

* If you're unable to find an open issue addressing the problem, [open a new one](https://github.com/ramses-rf/ramses_rf/issues/new). Be sure to include a **title and clear description**, as much relevant information as possible, and a **code sample** or an **executable test case** demonstrating the expected behaviour that is not occurring.

* If possible, use the relevant bug report template to create the issue:
  * [**Bug Report** for other issues](.github/ISSUE_TEMPLATE/bug_report.md)

#### **Did you write a patch that fixes a bug?**

* Open a new GitHub pull request with the patch.

* Ensure the PR description clearly describes the problem and solution. Include the relevant issue number if applicable (e.g. `ramses-rf/ramses_rf#123` or cross-repo `ramses-rf/ramses_cc#456`).

* Before submitting, please read the [Contributing to Ramses RF](https://github.com/ramses-rf/ramses_cc/wiki/7.-How-to-submit-a-PR) guide to know more about coding conventions and benchmarks.

#### **Did you fix whitespace, format code, or make a purely cosmetic patch?**

Changes that are cosmetic in nature and do not add anything substantial to the stability, functionality, or testability of Ramses RF will generally not be accepted. It adds a lot ow work, and is often subjective.

#### **Do you intend to add a new feature or change an existing one?**

* Suggest your change in the [Home Assistant User Forum - Honeywell CH/DHW via RF thread](https://community.home-assistant.io/t/honeywell-ch-dhw-via-rf-evohome-sundial-hometronics-chronotherm/) and start writing code.

* Do not open an issue on GitHub until you have collected positive feedback about the change. GitHub issues are primarily intended for bug reports and fixes.

#### **Do you have questions about the source code?**

* Ask any question about how to use Ramses RF in the [Home Assistant User Forum - Honeywell CH/DHW via RF thread](https://community.home-assistant.io/t/honeywell-ch-dhw-via-rf-evohome-sundial-hometronics-chronotherm/) .

#### **Do you want to contribute to the Ramses RF documentation?**

* Please read [The Ramses RF Dev Wiki](https://github.com/ramses-rf/ramses_rf/wiki).

## AI & LLM Policy

All contributors (human and AI-assisted) must strictly comply with our [AI Policy](AI_POLICY.md).

* **Human Accountability**: AI tools are supported as assistance tools, but human contributors maintain 100% responsibility for all submitted code, documentation, issues, and pull requests.
* **Autonomous Agents Prohibited**: Pull requests, issues, or comments created autonomously without human review will be closed immediately.
* **No AI Answers to Maintainers**: Contributors must understand and be able to explain their changes in their own words. AI must **never** be used to generate answers to maintainer review questions.
* **AI Instructions**: AI coding agents operating on this repository must follow the instructions in [LLM_INSTRUCTIONS.md](LLM_INSTRUCTIONS.md).

---

## Coding & Development Standards

All contributions (whether written by human contributors or generated via AI coding assistants) must strictly adhere to the following standards:

### 1. Code Style & Conventions
* **Line Constraints**: PEP 8 compliance (code ≤ 79 characters, docstrings/comments ≤ 72 characters).
* **EXEMPTION (Raw Data)**: Raw RF packets, hex strings, routing dictionaries, and timestamped packet logs are strictly exempt from line limits to preserve readability and grep-ability.
* **String Literals**: Prefer double quotes (`"`) for all string literals.
* **Deferred Logging**: Always use standard deferred `%`-formatting across all log levels and logger instances (e.g., `_LOGGER.debug(...)`, `_TRACE.info(...)`, `PKT_LOGGER.warning(...)`) instead of `f-strings` to prevent string evaluation and interpolation overhead when logging is disabled or filtered.

### 2. Typing & Type Safety
* **Strict Type Safety**: 100% compliance with `mypy --strict`. Do not introduce untyped definitions (`Any`) without strong technical justification.
* **Domain Types**: Prefer domain-specific types (`Address`, `DeviceIdT`, dataclasses, enums) over primitive `str` or `dict`.
* **Python Syntax**: Use modern Python 3.13+ syntax:
  * Use `|` for unions (e.g., `str | int`).
  * Use native collection types (e.g., `list[int]`, `dict[str, Any]`).
  * **Banned Imports**: Do not import `List`, `Dict`, `Set`, `Tuple`, `Optional`, or `Union` from `typing`.

### 3. Code Quality & Modularity
* **Immutability & State**: Treat data objects as immutable where possible. Avoid unnecessary state mutations and return new instances instead.
* **Context Managers**: Avoid nested `with` statements. Use parenthetical multi-context syntax (`with (A(), B()):`).
* **Imports**: Place imports at module level (top of file). Combine imports from the same module onto a single line (`combine-as-imports = true`).
* **Architectural Layering**: Enforce strict module layering (`ramses_cli` → `ramses_rf` → `ramses_tx`). Read-models (`ramses_rf.devices`, `ramses_rf.systems`) must never import from `pipeline` or `gateway`.

### 4. Documentation & Comments
* **Public APIs**: Require full Sphinx-style docstrings (summary, detailed explanation, `:param:`, `:type:`, `:returns:`, `:rtype:`).
* **Private Helpers**: Concise, single-line summaries are preferred for internal helpers (`_helper`).
* **Preserve Inline Comments**: Treat existing comments, `#TODO`, `#FIXME`, and `#HACK` markers as locked anchors. Multi-line wrap comments rather than truncating text.

### 5. Testing & Verification
* **Test Structure**: Exempt from Sphinx docstrings. Use descriptive test names following the **Arrange, Act, Assert (AAA)** pattern with inline comments.
* **Snapshot Policy**: Regression snapshots (`.ambr` files) are treated as source code. Never run `--snapshot-update` blindly. If output changes, document in the PR whether it is a bug fix or feature improvement.
* **Tooling**: Verify changes locally using `.venv/bin/prek run -a`, `.venv/bin/ruff check .`, `.venv/bin/mypy --strict`, and `.venv/bin/pytest`.

---

Ramses RF is a volunteer effort. We encourage you to pitch in and join us!

Thanks!

Ramses RF Team
