#!/usr/bin/env python3
"""RAMSES RF - Test the packet transceiver with a virtual RF.

NB: This test will likely fail with pytest -n x, because of the protocol's throttle
limits.
"""

import asyncio
import random
from collections.abc import AsyncGenerator, Generator
from datetime import datetime as dt
from typing import cast
from unittest.mock import patch

import pytest
import serial

from ramses_rf import Message, Packet
from ramses_rf.address import HGI_DEV_ADDR, Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command as Intent
from ramses_rf.enums import Action
from ramses_tx.const import DEFAULT_ECHO_TIMEOUT
from ramses_tx.dtos import CommandDTO as Command
from ramses_tx.protocol import PortProtocol, protocol_factory
from ramses_tx.transport import TransportConfig, transport_factory
from ramses_tx.transport.port import PortTransport
from ramses_tx.typing import QosParams

from .virtual_rf import VirtualRf


def _assert_packet_eq_cmd(packet: Packet, cmd: Command, msg: str = "") -> None:
    # We compare the string components directly
    expected_frame = f"{cmd.verb} --- {cmd.addr1} {cmd.addr2} {cmd.addr3} {cmd.code} {int(len(cmd.payload) / 2):03d} {cmd.payload}"
    assert str(packet._frame).endswith(expected_frame), (
        f"{msg} | Expected: {expected_frame}, got: {packet._frame}"
    )


# other constants
CALL_LATER_DELAY = 0.001  # FIXME: this is hardware-specific

ASSERT_CYCLE_TIME = (
    0.0005  # max_cycles_per_assert = max_sleep / ASSERT_CYCLE_TIME
)
DEFAULT_MAX_SLEEP = 0.1


def put_sensor_temp(dev_id: str, temperature: float) -> Command:
    return build_dto(
        Intent(
            src=Address(dev_id),
            dst=Address(dev_id),
            action=Action.PUT_SENSOR_TEMP,
            data={"temperature": temperature},
        )
    )


II_CMD_STR_0 = " I --- 01:006056 --:------ 01:006056 1F09 003 0005C8"
II_CMD_0 = Command.from_cli(II_CMD_STR_0)
II_PKT_0 = Packet(dt.now(), f"... {II_CMD_STR_0}")

# TIP: using 18:000730 as the source will prevent impersonation alerts

RQ_CMD_STR_0 = "RQ --- 18:000730 01:222222 --:------ 12B0 001 00"
RP_CMD_STR_0 = "RP --- 01:222222 18:000730 --:------ 12B0 003 000000"

RQ_CMD_0 = Command.from_cli(RQ_CMD_STR_0)
RQ_PKT_0 = Packet(dt.now(), f"... {RQ_CMD_STR_0}")
RP_PKT_0 = Packet(dt.now(), f"... {RP_CMD_STR_0}")

RQ_CMD_STR_1 = "RQ --- 18:000730 01:222222 --:------ 12B0 001 01"
RP_CMD_STR_1 = "RP --- 01:222222 18:000730 --:------ 12B0 003 010000"

RQ_CMD_1 = Command.from_cli(RQ_CMD_STR_1)
RQ_PKT_1 = Packet(dt.now(), f"... {RQ_CMD_STR_1}")
RP_PKT_1 = Packet(dt.now(), f"... {RP_CMD_STR_1}")


# ### FIXTURES #################################################################


@pytest.fixture(autouse=True)
def patch_port_transport_delays() -> Generator[None, None, None]:
    """Bypass the real-world signature timeouts and duty cycle limits for tests."""
    with (
        patch("ramses_tx.transport.port._DBG_DISABLE_DUTY_CYCLE_LIMIT", True),
        patch("ramses_tx.transport.port._SIGNATURE_MAX_TRYS", 0),
        patch("ramses_tx.transport.port.MIN_INTER_WRITE_GAP", 0),
    ):
        yield


@pytest.fixture()
async def protocol(rf: VirtualRf) -> AsyncGenerator[PortProtocol, None]:
    def _msg_handler(msg: Message) -> None:
        pass

    protocol = protocol_factory(_msg_handler)

    assert isinstance(protocol, PortProtocol)  # mypy
    protocol._disable_qos = False

    assert protocol.echo_timeout == DEFAULT_ECHO_TIMEOUT
    assert protocol.send_timeout_limit == 20.0

    _transport = await transport_factory(
        protocol,
        config=TransportConfig(),
        port_name=rf.ports[0],
        port_config=dict(),
    )
    transport = cast(PortTransport, _transport)
    transport._extra["virtual_rf"] = rf

    assert protocol._is_active is True

    try:
        yield protocol

    except serial.SerialException as err:
        transport._close(exc=err)
        raise

    except (AssertionError, asyncio.InvalidStateError, TimeoutError):
        transport.close()
        raise

    else:
        transport.close()

    finally:
        await rf.stop()


# ### TESTS ####################################################################


async def _test_flow_30x(protocol: PortProtocol) -> None:
    assert protocol._transport is not None
    rf: VirtualRf = protocol._transport.get_extra_info("virtual_rf")
    ser = serial.Serial(rf.ports[1])

    qos = QosParams()

    # STEP 1: Send an I cmd (no reply)...
    task = rf._loop.create_task(
        protocol.send_cmd(II_CMD_0, qos=qos), name="send_1"
    )
    _assert_packet_eq_cmd(await task, II_CMD_0)

    # STEP 2: Send an RQ cmd (returns echo at L3)...
    task = rf._loop.create_task(
        protocol.send_cmd(RQ_CMD_0, qos=qos), name="send_2"
    )
    protocol._loop.call_later(
        CALL_LATER_DELAY,
        ser.write,
        bytes(str(RP_PKT_0).encode("ascii")) + b"\r\n",
    )
    _assert_packet_eq_cmd(await task, RQ_CMD_0)

    # STEP 3: Send an I cmd (no reply) *twice*...
    task = rf._loop.create_task(
        protocol.send_cmd(II_CMD_0, qos=qos), name="send_3A"
    )
    _assert_packet_eq_cmd(await task, II_CMD_0)

    task = rf._loop.create_task(
        protocol.send_cmd(II_CMD_0, qos=qos), name="send_3B"
    )
    _assert_packet_eq_cmd(await task, II_CMD_0)

    # STEP 4: Send an RQ cmd (returns echo at L3)...
    task = rf._loop.create_task(
        protocol.send_cmd(RQ_CMD_1, qos=qos), name="send_4A"
    )

    protocol._loop.call_later(
        CALL_LATER_DELAY,
        ser.write,
        bytes(str(RP_PKT_0).encode("ascii")) + b"\r\n",
    )
    protocol._loop.call_later(
        CALL_LATER_DELAY,
        ser.write,
        bytes(str(RP_PKT_1).encode("ascii")) + b"\r\n",
    )

    _assert_packet_eq_cmd(await task, RQ_CMD_1)


async def _test_flow_401(protocol: PortProtocol) -> None:
    qos = QosParams()

    numbers = list(range(24))
    tasks = dict()

    for i in numbers:
        cmd = put_sensor_temp("03:123456", i)
        tasks[i] = protocol._loop.create_task(protocol.send_cmd(cmd, qos=qos))

    assert await asyncio.gather(*tasks.values())

    for i in numbers:
        packet = tasks[i].result()
        _assert_packet_eq_cmd(packet, put_sensor_temp("03:123456", i))


async def _test_flow_402(protocol: PortProtocol) -> None:
    qos = QosParams()

    numbers = list(range(24))
    tasks = dict()

    for i in numbers:
        cmd = put_sensor_temp("03:123456", i)
        tasks[i] = protocol._loop.create_task(protocol.send_cmd(cmd, qos=qos))

    random.shuffle(numbers)

    for i in numbers:
        packet = await tasks[i]
        _assert_packet_eq_cmd(packet, put_sensor_temp("03:123456", i))


async def _test_flow_60x(protocol: PortProtocol, num_cmds: int = 1) -> None:
    tasks = list()
    for index in range(num_cmds):
        cmd = build_dto(
            Intent(
                src=HGI_DEV_ADDR,
                dst=Address("01:123456"),
                action=Action.GET_ZONE_TEMP,
                data={"zone_index": f"{index:02X}"},
            )
        )
        coro = protocol.send_cmd(cmd, qos=QosParams())
        tasks.append(protocol._loop.create_task(coro, name=f"cmd_{index:02X}"))

    assert await asyncio.gather(*tasks)


async def _test_flow_qos(protocol: PortProtocol) -> None:
    protocol._send_timeout_limit = 0.2
    protocol.max_retry_limit = 0

    # Simple test for an I
    cmd = put_sensor_temp("03:000111", 19.5)
    packet = await protocol.send_cmd(cmd)
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = put_sensor_temp("03:000222", 19.5)
    packet = await protocol.send_cmd(cmd, qos=None)
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = put_sensor_temp("03:000333", 19.5)
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = put_sensor_temp("03:000444", 19.5)
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "should be echo as there is no wait_for_reply"
    )

    cmd = put_sensor_temp("03:000555", 19.5)
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "should be echo as there is no wait_for_reply"
    )

    cmd = put_sensor_temp("03:000666", 19.5)
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    # Simple test for an RQ
    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000111"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd)
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000222"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd, qos=None)
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000333"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000444"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there is no wait_for_reply"
    )

    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000555"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd, qos=QosParams())
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there is no wait_for_reply"
    )

    cmd = build_dto(
        Intent(
            src=HGI_DEV_ADDR,
            dst=Address("01:000666"),
            action=Action.GET_SYSTEM_TIME,
            data={},
        )
    )
    packet = await protocol.send_cmd(cmd, qos=QosParams(timeout=0.05))
    _assert_packet_eq_cmd(
        packet, cmd, "Should be echo as there's no reply to wait for"
    )

    cmd = put_sensor_temp("03:000999", 19.5)
    packet = await protocol.send_cmd(cmd)
    _assert_packet_eq_cmd(packet, cmd)


# ######################################################################################


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_300(protocol: PortProtocol) -> None:
    """Check state change of RQ/I/RQ cmds using protocol methods."""
    await _test_flow_30x(protocol)


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_401(protocol: PortProtocol) -> None:
    """Throw a bunch of commands in a random order, and see that all are echo'd."""
    await _test_flow_401(protocol)


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_402(protocol: PortProtocol) -> None:
    """Throw a bunch of commands in a random order, and see that all are echo'd."""
    await _test_flow_402(protocol)


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_601(protocol: PortProtocol) -> None:
    """Check the wait_for_reply kwarg."""
    await _test_flow_60x(protocol)


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_602(protocol: PortProtocol) -> None:
    """Check the wait_for_reply kwarg."""
    await _test_flow_60x(protocol, num_cmds=2)


@pytest.mark.xdist_group(name="virt_serial")
async def test_flow_qos(protocol: PortProtocol) -> None:
    """Check the wait_for_reply kwarg."""
    await _test_flow_qos(protocol)
