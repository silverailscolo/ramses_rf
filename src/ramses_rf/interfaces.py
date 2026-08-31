"""RAMSES RF - Abstract Base Classes and Interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeVar,
    overload,
    runtime_checkable,
)

from ramses_tx import CommandDTO, Packet, Priority

from .messages import Message
from .typing import DeviceIdT, DeviceListT

# Callback type invoked when system topology/schema is updated dynamically
SchemaUpdatedCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

if TYPE_CHECKING:
    from .commands.dispatcher import CommandDispatcher as CQRSDispatcher
    from .config import GatewayConfig
    from .devices.dev_base import Device, Fakeable
    from .models import TopologyChangedEvent
    from .routing import StateHeader
    from .topology import Parent

# Generic type variable for downcasting returned Device instances
_DeviceT = TypeVar("_DeviceT", bound="Device")


class CommandDispatcher(Protocol):
    """Protocol for a service that dispatches commands."""

    async def send(
        self,
        intent: Any,
        *,
        priority: Priority | None = None,
        wait_for_reply: bool | None = None,
    ) -> Message:
        """Translate and send a high-level intent.

        :param intent: The command intent to dispatch.
        :type intent: Any
        :param priority: Optional transmission priority.
        :type priority: Priority | None
        :param wait_for_reply: Whether to await a reply message.
        :type wait_for_reply: bool | None
        :returns: The sent or received Message.
        :rtype: Message
        """
        ...

    def send_background(
        self,
        intent: Any,
        *,
        priority: Priority | None = None,
        wait_for_reply: bool | None = None,
    ) -> asyncio.Task[Message]:
        """Schedule command intent transmission as a background task.

        :param intent: The command intent to dispatch.
        :type intent: Any
        :param priority: Optional transmission priority.
        :type priority: Priority | None
        :param wait_for_reply: Whether to await a reply message.
        :type wait_for_reply: bool | None
        :returns: An asyncio Task resolving to the Message.
        :rtype: asyncio.Task[Message]
        """
        ...


class ConversationManagerInterface(Protocol):
    """Protocol for the L7 Conversation Manager."""

    async def track_intent(
        self,
        intent: Any,
        dto: CommandDTO | None = None,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> asyncio.Future[Message]:
        """Track an intent transaction until resolution.

        :param intent: The command intent to track.
        :type intent: Any
        :param dto: The compiled CommandDTO for correlation.
        :type dto: CommandDTO | None
        :param timeout: Optional transaction timeout in seconds.
        :type timeout: float | None
        :param max_retries: Optional maximum retry attempts.
        :type max_retries: int | None
        :returns: A future resolving with the reply Message.
        :rtype: asyncio.Future[Message]
        """
        ...


class MessageStoreInterface(Protocol):
    """Protocol interface for central message store."""

    def add(self, msg: Message) -> Message | None:
        """Add message to store index.

        :param msg: The message to index.
        :type msg: Message
        :returns: The indexed message or None.
        :rtype: Message | None
        """
        ...

    def add_record(
        self,
        source: str,
        code: str = "",
        verb: str = "",
        payload: str = "00",
    ) -> None:
        """Add record without message contents.

        :param source: The source device address string.
        :type source: str
        :param code: The RAMSES command code string, optional.
        :type code: str
        :param verb: The command verb string, optional.
        :type verb: str
        :param payload: The raw hex payload string, optional.
        :type payload: str
        :returns: None
        :rtype: None
        """
        ...

    def start_consumer(self, in_queue: asyncio.Queue[Any]) -> None:
        """Start asynchronous queue consumer task for SSOT ingestion.

        :param in_queue: The input queue for raw packet ingestion.
        :type in_queue: asyncio.Queue[Any]
        :returns: None
        :rtype: None
        """
        ...

    async def get(
        self,
        msg: Any | None = None,
        *,
        dtm: Any | None = None,
        source: str | None = None,
        destination: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        context: Any | None = None,
        hdr: str | StateHeader | None = None,
    ) -> tuple[Message, ...] | list[Message]:
        """Query matching messages from store.

        :param msg: An example message to match against.
        :type msg: Any | None
        :param dtm: Timestamp constraint, optional.
        :type dtm: Any | None
        :param source: Source device identifier constraint.
        :type source: str | None
        :param destination: Destination device identifier constraint.
        :type destination: str | None
        :param verb: Verb constraint, optional.
        :type verb: str | None
        :param code: Command code constraint, optional.
        :type code: str | None
        :param context: Context payload constraint, optional.
        :type context: Any | None
        :param hdr: Packet header string or StateHeader, optional.
        :type hdr: str | StateHeader | None
        :returns: A tuple or list of matching messages.
        :rtype: tuple[Message, ...] | list[Message]
        """
        ...

    async def rem(
        self,
        msg: Any | None = None,
        *,
        dtm: Any | None = None,
        source: str | None = None,
        destination: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        context: Any | None = None,
        hdr: str | None = None,
    ) -> tuple[Any, ...] | None:
        """Remove matching messages from store.

        :param msg: An example message to match against.
        :type msg: Any | None
        :param dtm: Timestamp constraint, optional.
        :type dtm: Any | None
        :param source: Source device identifier constraint.
        :type source: str | None
        :param destination: Destination device identifier constraint.
        :type destination: str | None
        :param verb: Verb constraint, optional.
        :type verb: str | None
        :param code: Command code constraint, optional.
        :type code: str | None
        :param context: Context payload constraint, optional.
        :type context: Any | None
        :param hdr: Packet header string constraint, optional.
        :type hdr: str | None
        :returns: A tuple of removed records, or None.
        :rtype: tuple[Any, ...] | None
        """
        ...

    async def contains(
        self,
        *,
        dtm: Any | None = None,
        source: str | None = None,
        destination: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        context: Any | None = None,
        hdr: str | None = None,
    ) -> bool:
        """Return True if store contains matching record.

        :param dtm: Timestamp constraint, optional.
        :type dtm: Any | None
        :param source: Source device identifier constraint.
        :type source: str | None
        :param destination: Destination device identifier constraint.
        :type destination: str | None
        :param verb: Verb constraint, optional.
        :type verb: str | None
        :param code: Command code constraint, optional.
        :type code: str | None
        :param context: Context payload constraint, optional.
        :type context: Any | None
        :param hdr: Packet header string constraint, optional.
        :type hdr: str | None
        :returns: True if a matching record exists, False otherwise.
        :rtype: bool
        """
        ...

    async def get_rp_codes(self, parameters: tuple[str, ...]) -> list[Any]:
        """Query response opcode codes.

        :param parameters: SQL parameters for opcode filtering.
        :type parameters: tuple[str, ...]
        :returns: A list of response opcode codes.
        :rtype: list[Any]
        """
        ...

    async def all(self, include_expired: bool = False) -> tuple[Any, ...]:
        """Return all indexed messages.

        :param include_expired: Whether to include expired messages.
        :type include_expired: bool
        :returns: A tuple of all indexed messages.
        :rtype: tuple[Any, ...]
        """
        ...

    async def clr(self) -> None:
        """Clear all indexed messages from the store."""
        ...

    async def qry(
        self, sql: str, parameters: tuple[str, ...]
    ) -> tuple[Any, ...]:
        """Execute custom SQL query on store.

        :param sql: The SQL query statement.
        :type sql: str
        :param parameters: The tuple of SQL parameter values.
        :type parameters: tuple[str, ...]
        :returns: A tuple of query results.
        :rtype: tuple[Any, ...]
        """
        ...

    async def qry_field(
        self, sql: str, parameters: tuple[str, ...]
    ) -> list[tuple[Any, ...]]:
        """Execute custom SQL query returning field values.

        :param sql: The SQL query statement.
        :type sql: str
        :param parameters: The tuple of SQL parameter values.
        :type parameters: tuple[str, ...]
        :returns: A list of result tuples.
        :rtype: list[tuple[Any, ...]]
        """
        ...

    @property
    def log_by_dtm(self) -> tuple[Message, ...]:
        """Return in-memory log dictionary keyed by timestamp.

        :returns: A tuple of indexed messages.
        :rtype: tuple[Message, ...]
        """
        ...

    @property
    def state_cache(self) -> dict[StateHeader, Message]:
        """Return in-memory state cache dictionary.

        :returns: The state cache dictionary mapping headers to messages.
        :rtype: dict[StateHeader, Message]
        """
        ...

    def flush(self) -> None:
        """Flush pending disk writes."""
        ...

    def stop(self) -> None:
        """Stop background tasks and close database."""
        ...


class EntityInterface(Protocol):
    """Interface for base RAMSES entities."""

    @property
    def id(self) -> DeviceIdT:
        """Return the entity ID.

        :returns: The entity identifier string.
        :rtype: DeviceIdT
        """
        ...


class DeviceInterface(Protocol):
    """Interface for a standard RF Device."""

    @property
    def id(self) -> DeviceIdT:
        """Return the device ID.

        :returns: The Device ID.
        :rtype: DeviceIdT
        """
        ...

    async def traits(self) -> dict[str, Any]:
        """Return the device traits.

        :returns: A dictionary of device traits.
        :rtype: dict[str, Any]
        """
        ...


@runtime_checkable
class ControllerInterface(DeviceInterface, Protocol):
    """Interface for a RAMSES controller entity."""

    @property
    def tcs(self) -> Any:
        """Return the parent heating system associated with this controller.

        :returns: The parent system, or None if unassociated.
        :rtype: Any
        """
        ...


@runtime_checkable
class ParentInterface(Protocol):
    """Structural interface representing any Parent entity (System, Zone, UFC)."""

    @property
    def zone_index(self) -> str | None:
        """Return the domain or zone index string.

        :returns: The domain or zone index string.
        :rtype: str | None
        """
        ...

    def _add_child(
        self,
        child: Any,
        *,
        child_id: str | None = None,
        is_sensor: bool | None = None,
    ) -> None:
        """Add a child entity to this parent registry."""
        ...

    def _detach_child(self, child: Any) -> None:
        """Detach a child device from this Parent."""
        ...


class DeviceFilterInterface(Protocol):
    """Interface for the Device Filter service."""

    def check_filter_lists(self, device_id: DeviceIdT) -> None:
        """Raise a DeviceNotFoundError if a device_id is filtered out.

        :param device_id: The device identifier to evaluate.
        :type device_id: DeviceIdT
        :returns: None
        :rtype: None
        :raises DeviceNotFoundError: If device is filtered out.
        """
        ...


class DeviceRegistryInterface(Protocol):
    """Interface for the Device Registry service."""

    @property
    def devices(self) -> list[Any]:
        """Return the list of devices.

        :returns: A list of registered device instances.
        :rtype: list[Any]
        """
        ...

    @property
    def device_by_id(self) -> dict[DeviceIdT, Any]:
        """Return the mapping of device IDs to devices.

        :returns: A dictionary mapping device IDs to devices.
        :rtype: dict[DeviceIdT, Any]
        """
        ...

    @property
    def system_by_id(self) -> dict[DeviceIdT, Any]:
        """Return a mapping of device IDs to their associated systems.

        :returns: A dictionary mapping device IDs to systems.
        :rtype: dict[DeviceIdT, Any]
        """
        ...

    @property
    def systems(self) -> list[Any]:
        """Return a list of all identified systems.

        :returns: A list of registered system instances.
        :rtype: list[Any]
        """
        ...

    def _add_device(self, device: Any) -> None:
        """Add a device to the registry."""
        ...

    @overload
    def get_device(
        self,
        device_id: DeviceIdT | str,
        *,
        msg: Message | None = None,
        parent: Parent[Device] | None = None,
        child_id: str | None = None,
        is_sensor: bool | None = None,
        cls: None = None,
    ) -> Device: ...

    @overload
    def get_device(
        self,
        device_id: DeviceIdT | str,
        *,
        msg: Message | None = None,
        parent: Parent[Device] | None = None,
        child_id: str | None = None,
        is_sensor: bool | None = None,
        cls: type[_DeviceT],
    ) -> _DeviceT: ...

    def get_device(
        self,
        device_id: DeviceIdT | str,
        *,
        msg: Message | None = None,
        parent: Parent[Device] | None = None,
        child_id: str | None = None,
        is_sensor: bool | None = None,
        cls: type[_DeviceT] | None = None,
    ) -> Device | _DeviceT:
        """Return a device, creating it if it does not already exist.

        :param device_id: The identifier string for target device.
        :type device_id: DeviceIdT | str
        :param msg: Optional message context for creation.
        :type msg: Message | None
        :param parent: Optional parent entity to attach device to.
        :type parent: Parent[Device] | None
        :param child_id: Optional child domain or index identifier.
        :type child_id: str | None
        :param is_sensor: Optional flag if device acts as sensor.
        :type is_sensor: bool | None
        :param cls: Optional device subclass type to instantiate.
        :type cls: type[_DeviceT] | None
        :returns: The retrieved or newly created device instance.
        :rtype: Device | _DeviceT
        """
        ...

    async def fake_device(
        self,
        device_id: DeviceIdT,
        create_device: bool = False,
    ) -> Device | Fakeable:
        """Create a faked device.

        :param device_id: The target device identifier to fake.
        :type device_id: DeviceIdT
        :param create_device: Whether to instantiate device if missing.
        :type create_device: bool
        :returns: The faked device instance.
        :rtype: Device | Fakeable
        """
        ...

    async def known_list(self) -> DeviceListT:
        """Return the working known_list.

        :returns: The dictionary of configured known devices.
        :rtype: DeviceListT
        """
        ...

    async def get_heat_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned heat devices.

        :returns: A list of device IDs without an associated system.
        :rtype: list[DeviceIdT]
        """
        ...

    async def get_hvac_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned HVAC devices.

        :returns: A list of device IDs without an associated system.
        :rtype: list[DeviceIdT]
        """
        ...

    async def params(self) -> dict[str, Any]:
        """Return the parameters for all devices.

        :returns: A dictionary of parameters for all devices.
        :rtype: dict[str, Any]
        """
        ...

    async def status(self) -> dict[str, Any]:
        """Return the status for all devices.

        :returns: A dictionary of status data for all devices.
        :rtype: dict[str, Any]
        """
        ...

    def handle_topology_event(self, event: TopologyChangedEvent) -> None:
        """Process an immutable structural graph mutation event.

        :param event: The topology change event to handle.
        :type event: TopologyChangedEvent
        :returns: None
        :rtype: None
        """
        ...


class GatewayInterface(Protocol):
    """Interface for the core Gateway orchestrator."""

    @property
    def hgi(self) -> DeviceInterface | None:
        """Return the HGI device if attached.

        :returns: The attached HGI device instance, or None.
        :rtype: DeviceInterface | None
        """
        ...

    @property
    def device_registry(self) -> DeviceRegistryInterface:
        """Return the Device Registry.

        :returns: The device registry instance.
        :rtype: DeviceRegistryInterface
        """
        ...

    @property
    def dispatcher(self) -> CQRSDispatcher:
        """Return the CommandDispatcher for outbound command translation.

        :returns: The command dispatcher instance.
        :rtype: CQRSDispatcher
        """
        ...

    @property
    def message_store(self) -> MessageStoreInterface | None:
        """Return the SQLite message store instance or None.

        :returns: The message store instance, or None if disabled.
        :rtype: MessageStoreInterface | None
        """
        ...

    @message_store.setter
    def message_store(self, value: MessageStoreInterface | None) -> None: ...

    @property
    def config(self) -> GatewayConfig:
        """Return the gateway configuration.

        :returns: The gateway configuration dataclass instance.
        :rtype: GatewayConfig
        """
        ...

    @property
    def conversation_manager(self) -> ConversationManagerInterface | None:
        """Return the ConversationManager instance.

        :returns: The conversation manager instance, or None.
        :rtype: ConversationManagerInterface | None
        """
        ...

    @property
    def schema_updated_callback(self) -> SchemaUpdatedCallback | None:
        """Return the async callback invoked when schema updates.

        :returns: The registered callback callable, or None.
        :rtype: SchemaUpdatedCallback | None
        """
        ...

    def set_schema_updated_callback(
        self, callback: SchemaUpdatedCallback | None
    ) -> None:
        """Set the async callback invoked when system topology updates.

        :param callback: The callback callable or None to clear.
        :type callback: SchemaUpdatedCallback | None
        :returns: None
        :rtype: None
        """
        ...

    async def _async_send_dto(
        self,
        command: CommandDTO,
        /,
        *,
        gap_duration: float = 0.02,
        num_repeats: int = 1,
        priority: Priority = Priority.DEFAULT,
        timeout: float = 3.0,
        max_retries: int = 3,
    ) -> Packet:
        """Send a command DTO over the physical L3 modem."""
        ...
