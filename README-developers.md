![Linting](https://github.com/ramses-rf/ramses_rf/actions/workflows/check-lint.yml/badge.svg)
![Typing](https://github.com/ramses-rf/ramses_rf/actions/workflows/check-type.yml/badge.svg)
![Testing](https://github.com/ramses-rf/ramses_rf/actions/workflows/check-test.yml/badge.svg)

# Ramses_rf developer's resource

## Installation

Confirm you have Python 3.13.x installed by running:
```
python3 --version
```

### Virtual environment

Create a `venv` virtual environment, for example on macOS or Linux:
```
mkdir /your-path-to/virtual-envs
mkdir /your-path-to/virtual-envs/ramses_rf
cd /your-path-to/virtual-envs/ramses_rf
Python3.13 -m venv ~/your-path-to/virtual-envs/ramses_rf
```
where `Python3.13` is the python version to set for the `venv`.

### Clone this repo

Clone this repo and install the requirements.
Using `pip`, in a location where your IDE has access:
```
git clone https://github.com/ramses-rf/ramses_rf
```

Activate the venv (repeat every new session):
```
cd /your-path-to/ramses_rf
source /your-path-to/virtual-envs/ramses_rf/bin/activate
```
and confirm your Terminal prompt looks like:
`(ramses_rf) user:ramses_rf`

### Install dependencies:
```
cd /your-path-to/ramses_rf
pip install -r requirements.txt
pip install -r requirements_dev.txt
```

Repeat this after a release update and also when dev_requirements change in master.

### Install pre-commit hook
First, verify the installed pre-commit version (compare to requirements_dev.txt):
```
pre-commit --version
```

Install the repo's pre-commit hook:
```
pre-commit install
```

Running `pre-commit run` will only check staged files before a commit, while
`pre-commit run -a` will check all files.

Your IDE should automatically activate the pre-commit check when you try to commit.
The rules for pre-commit are in git in `.pre-commit-config.yaml`.
Check [issue 170](https://github.com/ramses-rf/ramses_rf/issues/170) when you run into troubles here.

## Regression Snapshot Suite

To guarantee packet processing stability, this repository includes a comprehensive regression suite located in:
* `tests/tests_tx/test_regression_tx.py` (Transport Layer / Parsing)
* `tests/tests_rf/test_regression_rf.py` (Application Layer / Device State)

These tests utilize a large dataset of historical raw packets:
* `tests/fixtures/regression_packets_sorted.txt`

### What these tests do
These tests are **Replay Tests**, not functional logic tests. They feed the static packet log through the system and assert that the output exactly matches the stored "Gold Standard" snapshots (`.ambr` files) located in:
* `tests/tests_tx/__snapshots__/test_regression_tx.ambr`
* `tests/tests_rf/__snapshots__/test_regression_rf.ambr`

They ensure that refactoring parsers or device logic does not inadvertently alter how historical devices are detected or how their state is decoded.

### Snapshot Update Policy
**Strict Rule:** The snapshot files (`.ambr`) are treated as source code. They should **not** be altered (through a snapshot update) unless there is a specific, understood reason.

If your PR causes a regression test failure:
1.  **Do not** simply run `--snapshot-update` to make the test pass.
2.  **Inspect the failure:** Determine if the change in output is a **Regression** (you broke support for an old device) or an **Improvement** (you added support for a new device/attribute).
3.  **If it is a Regression:** Fix your code.
4.  **If it is an Improvement:** You may update the snapshot. However, you **must** provide a detailed explanation in your Pull Request description justifying the specific changes seen in the snapshot diff (e.g., *"The snapshot diff shows `device_class` changing from `None` to `CO2Sensor` because this PR adds support for that sensor type"*).

## More
Build and view the code documentation locally for easier access and to confirm that
your own code contribution include proper documentation. See [Usage](docs/source/usage.md) for details.

For more hints, see the [How to submit a PR wiki page](https://github.com/ramses-rf/ramses_cc/wiki/7.-How-to-submit-a-PR)
