"""Parameter 52 sensitivity must not change the existing timer encoding."""

from datetime import datetime as dt, timedelta as td
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.address import Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.commands.dispatcher import CommandDispatcher
from ramses_rf.enums import Action
from ramses_rf.messages import Message
from ramses_rf.state import MessageStore
from ramses_tx import Packet


@pytest.mark.parametrize("value", [0, 0.5, 1, 1.5, 2, 10, 25])
@pytest.mark.parametrize(
    "definition",
    [
        "sensitivity",
        "timer",
        "missing",
        "other_fan",
        "no_store",
        "timer_after_sensitivity",
    ],
)
async def test_parameter_52_scaling(value: float, definition: str) -> None:
    # Arrange: actual message store, no model information or HA entities.
    gateway = MagicMock()
    gateway.message_store = MessageStore(maintain=False)
    gateway.device_registry.device_by_id = {}
    gateway.conversation_manager = None
    source = "32:333333" if definition == "other_fan" else "32:222222"
    payload = (
        "00005200000000000F00000000000000B4000000010001"
        if definition.startswith("timer")
        else "00005257010000000A00000000000000FA00000001C832"
    )
    packet = Packet.from_port(
        dt.now(), f"000 RP --- {source} 37:111111 --:------ 2411 023 {payload}"
    )
    if definition == "timer_after_sensitivity":
        previous = Packet.from_port(
            packet.dtm - td(seconds=1),
            "000 RP --- 32:222222 37:111111 --:------ 2411 023 "
            "00005257010000000A00000000000000FA00000001C832",
        )
        gateway.message_store.add(Message._from_packet(previous))
    if definition not in ("missing", "no_store"):
        gateway.message_store.add(Message._from_packet(packet))
    if definition == "no_store":
        gateway.message_store = None
    gateway._async_send_dto = AsyncMock(return_value=packet)
    intent = Command(
        src=Address("37:111111"),
        dst=Address("32:222222"),
        action=Action.SET_FAN_PARAM,
        data={"param_id": "52", "value": value},
    )

    # Act
    await CommandDispatcher(gateway).send(intent)
    payload = gateway._async_send_dto.call_args.args[0].payload

    # Assert: full byte-level result, including unchanged timer fallback.
    if definition == "sensitivity":
        assert (
            payload
            == f"0000520001{round(value * 10):08X}00000000000000FA000000010032"
        )
    else:
        assert payload == build_dto(intent).payload
