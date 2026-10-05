"""Native APS acknowledgements must pace writes without ASCII control traffic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from zigpy import types
from zigpy.zcl import Cluster, foundation

from ramses_tx import exceptions as exc

from .test_transport_zigbee import _VALID_URL, _make_transport


class NativeTXCluster(Cluster):
    """Use the same command schema as the current ELECRAM ZHA quirk."""

    cluster_id = 0xFC01

    class ClientCommandDefs(foundation.BaseCommandDefs):
        set_text = foundation.ZCLCommandDef(
            id=0x00, schema={"text": types.CharacterString}
        )


def test_existing_urls_keep_legacy_acknowledgements():
    transport = _make_transport()
    assert not transport._aps_ack
    with pytest.raises(exc.TransportSourceInvalid):
        _make_transport(f"{_VALID_URL}?ack=unknown")


@pytest.mark.parametrize("callback", ["cluster_command", "attribute_updated"])
def test_aps_reassembly_never_schedules_ascii_ack(callback):
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    transport._frame_read = MagicMock()
    for payload in ("1/2|first", "2/2|second"):
        if callback == "cluster_command":
            transport.cluster_command(1, 0, payload)
        else:
            transport.attribute_updated(transport._attr_id, payload)
    transport._frame_read.assert_called_once()
    assert transport._frame_read.call_args.args[1] == "firstsecond"
    transport._loop.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_real_zigpy_serialization_requests_aps_ack_without_zcl_reply():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    endpoint = MagicMock()
    endpoint.reply = AsyncMock()
    endpoint.device.get_sequence.return_value = 7
    cluster = NativeTXCluster(endpoint, is_server=True)
    transport._get_active_write_cluster = MagicMock(return_value=cluster)
    await transport._send_command("1/2|hello", 1, 2)
    kwargs = endpoint.reply.call_args.kwargs
    assert kwargs["ask_for_ack"] is True
    assert kwargs["expect_reply"] is False
    header, body = foundation.ZCLHeader.deserialize(kwargs["data"])
    assert header.frame_control.disable_default_response
    assert (
        header.frame_control.direction == foundation.Direction.Client_to_Server
    )
    assert body == b"\x091/2|hello"


@pytest.mark.asyncio
async def test_failed_delivery_aborts_remaining_chunks_without_api_fallback():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    cluster = MagicMock()
    cluster.client_commands = {0: object()}
    cluster.client_command = AsyncMock(side_effect=TimeoutError)
    cluster.command = AsyncMock()
    cluster.server_command = AsyncMock()
    transport._get_active_write_cluster = MagicMock(return_value=cluster)
    with pytest.raises(exc.TransportZigbeeError, match="Aborting"):
        await transport._write_frame("x" * 100)
    cluster.client_command.assert_awaited_once()
    cluster.command.assert_not_called()
    cluster.server_command.assert_not_called()


@pytest.mark.asyncio
async def test_next_chunk_waits_for_delivery_and_frames_do_not_interleave():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    first_started = asyncio.Event()
    confirm = asyncio.Event()
    sent = []

    async def send(chunk, sequence, total):
        sent.append(chunk)
        if len(sent) == 1:
            first_started.set()
            await confirm.wait()

    transport._send_command = send
    first = asyncio.create_task(transport._write_frame("a" * 70))
    await first_started.wait()
    second = asyncio.create_task(transport._write_frame("b" * 70))
    await asyncio.sleep(0)
    assert len(sent) == 1
    confirm.set()
    await asyncio.gather(first, second)
    assert len(sent) == 6
    assert all("a" in chunk for chunk in sent[:3])
    assert all("b" in chunk for chunk in sent[3:])


def test_aps_payloads_stay_within_conservative_wire_budget():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    for length in range(1, 256):
        chunks = transport._chunk_payload("x" * length)
        assert all(
            len(chunk.encode("ascii")) + 4 <= 40 for _, _, chunk in chunks
        )


def test_new_message_replaces_incomplete_message_with_same_chunk_count():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    transport._frame_read = MagicMock()
    for payload in ("1/3|old", "2/3|obsolete", "1/3|new", "3/3|end"):
        transport.cluster_command(1, 0, payload)
    transport._frame_read.assert_not_called()
    transport.cluster_command(1, 0, "2/3|middle")
    assert transport._frame_read.call_args.args[1] == "newmiddleend"


def test_malformed_chunk_and_legacy_ack_never_schedule_control_traffic():
    transport = _make_transport(f"{_VALID_URL}?ack=aps")
    transport._frame_read = MagicMock()
    transport.cluster_command(1, 0, "ACK 1/3")
    transport._frame_read.assert_not_called()
    transport.cluster_command(1, 0, "0/3|invalid")
    transport._loop.create_task.assert_not_called()
