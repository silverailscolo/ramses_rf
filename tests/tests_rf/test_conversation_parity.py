"""Tests for L7 ConversationManager (Request/Reply tracking and timeouts).

Exempt from formal docstrings under repository rules.
Applies AAA (Arrange, Act, Assert) pattern strictly.
"""

import asyncio
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.address import Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.dispatcher import process_msg
from ramses_rf.enums import Action
from ramses_rf.gateway import Gateway
from ramses_rf.messages import Message
from ramses_rf.pipeline.conversation import ConversationManager
from ramses_tx import RP, Packet
from ramses_tx.exceptions import ProtocolSendFailed, ProtocolTimeoutError
from ramses_tx.helpers import dt_now

LOG_OPENTHERM: Final[Path] = (
    Path(__file__).parent
    / "logs"
    / "test_phase2_95_topology_parity_packet_log_OpenTherm.log"
)


def _create_mock_message(
    verb: str = "RP",
    code: str = "10A0",
    src_id: str = "01:078710",
) -> MagicMock:
    msg = MagicMock()
    msg.verb = verb
    msg.code = code
    msg.src = Address(src_id)
    return msg


@pytest.mark.asyncio
async def test_conversation_manager_successful_match() -> None:
    # Arrange
    loop = asyncio.get_running_loop()
    manager = ConversationManager(loop=loop, default_timeout=1.0, max_retries=2)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )
    dto = build_dto(intent)

    # Act
    fut = await manager.track_intent(intent, dto)
    assert manager.pending_count == 1

    reply_msg = _create_mock_message(verb=RP, code=dto.code, src_id="01:078710")
    matched = manager.process_msg(reply_msg)

    # Assert
    assert matched is True
    assert manager.pending_count == 0
    assert fut.done()
    assert fut.result() == reply_msg


@pytest.mark.asyncio
async def test_conversation_manager_ignores_mismatched_src() -> None:
    # Arrange
    loop = asyncio.get_running_loop()
    manager = ConversationManager(loop=loop, default_timeout=1.0, max_retries=2)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )
    dto = build_dto(intent)

    # Act
    fut = await manager.track_intent(intent, dto)
    mismatched_msg = _create_mock_message(verb=RP, code=dto.code, src_id="01:999999")
    matched = manager.process_msg(mismatched_msg)

    # Assert
    assert matched is False
    assert manager.pending_count == 1
    assert not fut.done()

    manager.cancel_all()


@pytest.mark.asyncio
async def test_conversation_manager_timeout_and_retries() -> None:
    # Arrange
    loop = asyncio.get_running_loop()
    manager = ConversationManager(loop=loop, default_timeout=0.05, max_retries=1)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )
    dto = build_dto(intent)

    # Act
    fut = await manager.track_intent(intent, dto, timeout=0.05)

    # Allow timeouts to fire
    await asyncio.sleep(0.15)

    # Assert
    assert fut.done()
    assert manager.pending_count == 0
    with pytest.raises(ProtocolTimeoutError):
        fut.result()


def test_conversation_manager_accepts_i_for_w_commands() -> None:
    """ConversationManager must accept I responses for W commands (issue 873).

    Evohome DHW controllers acknowledge W 1F41 writes with I 1F41, not RP 1F41.
    """
    import asyncio
    from unittest.mock import MagicMock

    from ramses_rf.address import Address
    from ramses_rf.commands.core import Command
    from ramses_rf.enums import Action
    from ramses_rf.pipeline.conversation import ConversationManager
    from ramses_tx import I_

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    cm = ConversationManager(loop=loop, default_timeout=0.5, max_retries=2)

    intent = Command(
        src=Address("18:191664"),
        dst=Address("01:216136"),
        action=Action.SET_DHW_MODE,
        data={"mode": "permanent_override", "active": False},
        needs_reply=True,
        timeout=0.5,
    )
    fut = loop.run_until_complete(cm.track_intent(intent, timeout=0.5, max_retries=2))

    # Simulate the I 1F41 response from the CTL (broadcast dst)
    mock_msg = MagicMock()
    mock_msg.verb = I_
    mock_msg.src.id = "01:216136"  # from the device we sent to
    mock_msg.code.__str__ = lambda self: "1F41"
    mock_msg._pkt = MagicMock()

    matched = cm.process_msg(mock_msg)
    assert matched is True
    assert fut.done() and not fut.cancelled()


@pytest.mark.asyncio
async def test_conversation_manager_idx_matching_prevents_cross_matching() -> None:
    # Arrange
    loop = asyncio.get_running_loop()
    manager = ConversationManager(loop=loop, default_timeout=1.0, max_retries=2)
    intent1 = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )
    dto1 = build_dto(intent1)

    intent2 = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "01", "setpoint": 19.0},
    )
    dto2 = build_dto(intent2)

    # Act
    fut1 = await manager.track_intent(intent1, dto1)
    fut2 = await manager.track_intent(intent2, dto2)

    reply_msg2 = _create_mock_message(verb=RP, code=dto2.code, src_id="01:078710")
    reply_msg2.context.value = "01"

    matched2 = manager.process_msg(reply_msg2)

    # Assert
    assert matched2 is True
    assert fut2.done()
    assert fut2.result() == reply_msg2
    assert not fut1.done()
    assert manager.pending_count == 1

    manager.cancel_all()


@pytest.mark.asyncio
async def test_conversation_manager_superseded_intent_cancels_old_timer() -> None:
    # Arrange
    loop = asyncio.get_running_loop()
    manager = ConversationManager(loop=loop, default_timeout=1.0, max_retries=2)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )
    dto = build_dto(intent)

    # Act
    fut1 = await manager.track_intent(intent, dto)
    pending1 = manager._pending[manager._conversation_key(intent, dto)]
    timer1 = pending1.timer_task

    fut2 = await manager.track_intent(intent, dto)
    await asyncio.sleep(0)

    # Assert
    assert timer1 is not None and timer1.cancelled()
    assert fut1.done()
    with pytest.raises(ProtocolSendFailed):
        fut1.result()
    assert manager.pending_count == 1
    assert not fut2.done()

    manager.cancel_all()


# --- Live Pipeline Conversation Parity Tests ---


@pytest.mark.asyncio
async def test_live_gateway_conversation_manager_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live Gateway integration with ConversationManager."""
    gwy = Gateway("/dev/null")
    mock_packet = MagicMock(spec=Packet)
    monkeypatch.setattr(gwy, "async_send_cmd", AsyncMock(return_value=mock_packet))

    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )

    send_task = asyncio.create_task(gwy.dispatcher.send(intent, wait_for_reply=True))
    await asyncio.sleep(0.01)

    assert gwy.conversation_manager.pending_count == 1

    rp_frame = "000 RP --- 01:078710 18:000730 --:------ 2309 003 000834"
    rp_pkt = Packet.from_port(dt_now(), rp_frame)
    reply_msg = Message._from_pkt(rp_pkt)

    gwy.conversation_manager.process_msg(reply_msg)
    msg = await send_task

    assert msg == reply_msg
    assert gwy.conversation_manager.pending_count == 0

    await gwy.stop()


@pytest.mark.asyncio
async def test_live_dispatcher_process_msg_routes_to_conversation_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify dispatcher process_msg routes to ConversationManager."""
    gwy = Gateway("/dev/null")
    mock_packet = MagicMock(spec=Packet)
    monkeypatch.setattr(gwy, "async_send_cmd", AsyncMock(return_value=mock_packet))

    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:078710"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "00", "setpoint": 21.0},
    )

    send_task = asyncio.create_task(gwy.dispatcher.send(intent, wait_for_reply=True))
    await asyncio.sleep(0.01)
    assert gwy.conversation_manager.pending_count == 1

    rp_frame = "000 RP --- 01:078710 18:000730 --:------ 2309 003 000834"
    rp_pkt = Packet.from_port(dt_now(), rp_frame)
    reply_msg = Message._from_pkt(rp_pkt)

    await process_msg(gwy, reply_msg)
    await send_task

    assert gwy.conversation_manager.pending_count == 0

    await gwy.stop()
