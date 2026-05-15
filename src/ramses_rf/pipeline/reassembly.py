"""RAMSES RF - Asynchronous packet reassembly pipeline."""

import asyncio
import contextlib
import logging
from datetime import timedelta as td
from typing import Final

from ramses_tx.dtos import PacketDTO

_LOGGER = logging.getLogger(__name__)

_ARRAY_CODES: Final[tuple[str, ...]] = ("000A", "22C9")
_VERB_I: Final[str] = " I"


class ReassemblyBuffer:
    """Asynchronous pipeline task to stitch multi-packet arrays.

    Consumes raw PacketDTOs from the transport layer, buffers potential
    array fragments, and outputs unified PacketDTOs.
    """

    def __init__(
        self,
        in_queue: asyncio.Queue[PacketDTO],
        out_queue: asyncio.Queue[PacketDTO],
        array_timeout: float = 15.0,
    ) -> None:
        """Initialize the reassembly buffer queues.

        :param in_queue: Queue providing raw transport packets.
        :type in_queue: asyncio.Queue[PacketDTO]
        :param out_queue: Queue receiving stitched packets.
        :type out_queue: asyncio.Queue[PacketDTO]
        :param array_timeout: Seconds to wait for the next fragment.
        :type array_timeout: float
        """
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._array_timeout = array_timeout
        self._task: asyncio.Task[None] | None = None

        self._pending_dto: PacketDTO | None = None

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the background consumer task cleanly."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        """Main asynchronous loop consuming the input queue."""
        while True:
            try:
                # Wait for a packet, or timeout if we have a pending array
                timeout = self._array_timeout if self._pending_dto else None
                dto = await asyncio.wait_for(self._in_queue.get(), timeout=timeout)
                await self._process_packet(dto)
                self._in_queue.task_done()

            except TimeoutError:
                # Timeout exceeded, flush the pending packet
                if self._pending_dto:
                    _LOGGER.warning(
                        "%s < Array reassembly timeout (%ss): flushing "
                        "incomplete multi-packet message",
                        self._pending_dto.code,
                        self._array_timeout,
                    )
                    await self._out_queue.put(self._pending_dto)
                    self._pending_dto = None

    async def _process_packet(self, dto: PacketDTO) -> None:
        """Evaluate a packet for array stitching or passthrough.

        :param dto: The inbound packet to evaluate.
        :type dto: PacketDTO
        """
        if self._pending_dto is None:
            if self._is_potential_array_start(dto):
                self._pending_dto = dto
            else:
                await self._out_queue.put(dto)
            return

        if self._is_array_fragment(self._pending_dto, dto):
            stitched_dto = self._stitch_dtos(self._pending_dto, dto)
            await self._out_queue.put(stitched_dto)
            self._pending_dto = None
        else:
            # Flush the old pending dto and evaluate the new one
            _LOGGER.warning(
                "%s < Array reassembly interrupted by %s: flushing "
                "incomplete multi-packet message",
                self._pending_dto.code,
                dto.code,
            )
            await self._out_queue.put(self._pending_dto)
            self._pending_dto = None
            if self._is_potential_array_start(dto):
                self._pending_dto = dto
            else:
                await self._out_queue.put(dto)

    def _is_potential_array_start(self, dto: PacketDTO) -> bool:
        """Return True if the packet might be the start of an array.

        :param dto: The packet to evaluate.
        :type dto: PacketDTO
        :return: True if the packet matches array criteria.
        :rtype: bool
        """
        return dto.code in _ARRAY_CODES and dto.verb == _VERB_I

    def _is_array_fragment(self, prev: PacketDTO, this: PacketDTO) -> bool:
        """Return True if 'this' packet is a fragment of 'prev'.

        :param prev: The previously buffered packet.
        :type prev: PacketDTO
        :param this: The current packet being evaluated.
        :type this: PacketDTO
        :return: True if the packets should be stitched.
        :rtype: bool
        """
        if this.code != prev.code or this.verb != prev.verb:
            return False
        if this.addr1 != prev.addr1:
            return False
        return this.timestamp < prev.timestamp + td(seconds=self._array_timeout)

    def _stitch_dtos(self, prev: PacketDTO, this: PacketDTO) -> PacketDTO:
        """Combine two array fragments into a single PacketDTO.

        :param prev: The first fragment.
        :type prev: PacketDTO
        :param this: The second fragment.
        :type this: PacketDTO
        :return: A new PacketDTO containing the combined payload.
        :rtype: PacketDTO
        """
        combined_payload = f"{prev.payload}{this.payload}"
        combined_length = f"{len(combined_payload) // 2:03d}"

        # DTO is frozen; instantiate a new one with the combined L3 state
        return PacketDTO(
            timestamp=this.timestamp,
            rssi=this.rssi,
            verb=prev.verb,
            seq=prev.seq,
            addr1=prev.addr1,
            addr2=prev.addr2,
            addr3=prev.addr3,
            code=prev.code,
            length=combined_length,
            payload=combined_payload,
        )
