#!/usr/bin/env python3
"""RAMSES RF - Regression tests for in-place device class promotion.

When a device is eavesdropped, ramses_rf promotes it by swapping its class:

    self.__class__ = cls

This does NOT invoke the new class's __init__, so any instance state that
subclasses set up in __init__ (e.g. HvacVentilator._bound_devices,
UfhController.circuit_by_id, DhwSensor._child_id, Controller.tcs) would
previously be missing on promoted devices, causing AttributeError at runtime.

These tests verify the _post_class_promote hook called from
DeviceBase._handle_msg initializes subclass state for promoted devices.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

import pytest

from ramses_rf.const import FA
from ramses_rf.device.heat import Controller, DhwSensor, UfhController
from ramses_rf.device.hvac import HvacVentilator
from ramses_rf.system import Evohome

_InstanceT = TypeVar("_InstanceT")


class BareFactory(Protocol):
    def __call__(self, cls: type[_InstanceT]) -> _InstanceT: ...


@pytest.fixture
def bare_instance_factory() -> BareFactory:
    """Build an instance whose __init__ is bypassed (mirrors class swap)."""

    def _factory(cls: type[_InstanceT]) -> _InstanceT:
        return cls.__new__(cls)

    return _factory


def _invoke_post_promote(obj: UfhController) -> None:
    obj._post_class_promote()


def test_hvac_ventilator_post_class_promote_initializes_state(
    bare_instance_factory: BareFactory,
) -> None:
    fan = bare_instance_factory(HvacVentilator)
    fan.__dict__["id"] = "32:150000"  # logger access in subject methods

    # Before the hook, the subclass instance state is missing
    assert "_bound_devices" not in fan.__dict__

    fan._post_class_promote()

    assert fan._bound_devices == {}
    assert fan._supports_2411 is False
    assert fan._params_2411 == {}
    assert fan._initialized_callback is None
    assert fan._param_update_callback is None
    assert fan._hgi is None

    # And the APIs that previously crashed must work
    assert fan.get_bound_rem() is None

    fan.add_bound_device("37:123456", "REM")
    assert fan.get_bound_rem() == "37:123456"

    fan.remove_bound_device("37:123456")
    assert fan.get_bound_rem() is None


def test_hvac_ventilator_hook_is_idempotent(
    bare_instance_factory: BareFactory,
) -> None:
    fan = bare_instance_factory(HvacVentilator)
    fan.__dict__["id"] = "32:150000"
    fan._post_class_promote()

    fan.add_bound_device("37:000001", "REM")
    fan._post_class_promote()  # must NOT wipe existing state

    assert fan.get_bound_rem() == "37:000001"


def test_dhw_sensor_post_class_promote_initializes_child_id(
    bare_instance_factory: BareFactory,
) -> None:
    dhw = bare_instance_factory(DhwSensor)
    assert "_child_id" not in dhw.__dict__

    dhw._post_class_promote()

    assert dhw._child_id == FA


def test_ufh_controller_post_class_promote_initializes_state(
    bare_instance_factory: BareFactory,
) -> None:
    ufh = bare_instance_factory(UfhController)
    _invoke_post_promote(ufh)

    assert set(ufh.circuit_by_id.keys()) == {f"{i:02X}" for i in range(8)}

    for attr in (
        "_setpoints",
        "_heat_demand",
        "_heat_demands",
        "_relay_demand",
        "_relay_demand_fa",
    ):
        assert getattr(ufh, attr) is None


def test_controller_post_class_promote_sets_tcs_attribute(
    bare_instance_factory: BareFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctl = bare_instance_factory(Controller)

    # _make_tcs_controller needs a fully wired gateway; patch it so the
    # test stays focused on the hook's responsibility (initializing `tcs`).
    called = {"count": 0}

    def _fake_make_tcs_controller(self: Controller, **_kwargs: Any) -> None:
        called["count"] += 1
        self.__dict__["tcs"] = bare_instance_factory(Evohome)

    monkeypatch.setattr(Controller, "_make_tcs_controller", _fake_make_tcs_controller)

    ctl._post_class_promote()

    assert "tcs" in ctl.__dict__
    assert ctl.tcs is not None
    assert called["count"] == 1

    # Second call must be idempotent and must not create a second TCS.
    ctl._post_class_promote()
    assert called["count"] == 1
