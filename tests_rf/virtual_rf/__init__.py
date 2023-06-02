#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - A pseudo-mocked serial port used for testing."""

from typing import Callable, TypeVar
from unittest.mock import patch

from ramses_rf import Gateway
from ramses_rf.device import Fakeable

from .helpers import CONFIG, MIN_GAP_BETWEEN_WRITES
from .helpers import FakeableDevice as _FakeableDevice
from .helpers import make_device_fakeable, stifle_impersonation_alert
from .virtual_rf import HgiFwTypes  # noqa: F401, pylint: disable=unused-import
from .virtual_rf import VirtualRf

_Faked = TypeVar("_Faked", bound="_FakeableDevice")


@patch(
    "ramses_rf.protocol.protocol_new._ProtImpersonate._send_impersonation_alert",
    stifle_impersonation_alert,
)
@patch(
    "ramses_rf.protocol.transport_new.MIN_GAP_BETWEEN_WRITES", MIN_GAP_BETWEEN_WRITES
)
async def binding_test_wrapper(
    fnc: Callable, supp_schema: dict, resp_schema: dict, codes: tuple
):
    """Create a virtual RF with two gateways, 18:111111 & 18:222222."""

    rf = VirtualRf(2)

    rf.set_gateway(rf.ports[0], "18:111111")
    rf.set_gateway(rf.ports[1], "18:222222")

    gwy_0 = Gateway(rf.ports[0], **CONFIG, **supp_schema)
    gwy_1 = Gateway(rf.ports[1], **CONFIG, **resp_schema)

    await gwy_0.start()
    await gwy_1.start()

    supplicant = gwy_0.device_by_id[supp_schema["orphans_hvac"][0]]
    respondent = gwy_1.device_by_id[resp_schema["orphans_hvac"][0]]

    if not isinstance(respondent, Fakeable):  # likely respondent is not fakeable...
        make_device_fakeable(respondent)

    await fnc(supplicant, respondent, codes)

    await gwy_0.stop()
    await gwy_1.stop()
    await rf.stop()
