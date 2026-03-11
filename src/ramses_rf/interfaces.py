"""RAMSES RF - Abstract Base Classes and Interfaces."""

from typing import TYPE_CHECKING, Any, Protocol

from ramses_tx import Code, Command, Message, Packet, Priority, QosParams

from .typing import DeviceIdT, DeviceListT

if TYPE_CHECKING:
    from .topology import Parent


class CommandDispatcher(Protocol):
    """Protocol for a service/callback that dispatches commands."""

    async def __call__(
        self,
        cmd: Command,
        *,
        priority: Priority | None = None,
        qos: QosParams | None = None,
    ) -> Packet | None:
        """Dispatch a command asynchronously."""
        ...


class MessageIndexInterface(Protocol):
    """Interface for the SQLite Message Index database."""

    def add(self, msg: Message) -> Message | None:
        """Add a message to the index."""
        ...

    def add_record(
        self, src: str, code: str = "", verb: str = "", payload: str = "00"
    ) -> None:
        """Add a single record to the index."""
        ...

    async def rem(
        self, msg: Message | None = None, **kwargs: Any
    ) -> tuple[Message, ...] | None:
        """Remove a set of message(s) from the index."""
        ...

    async def get(
        self, msg: Message | None = None, **kwargs: Any
    ) -> tuple[Message, ...]:
        """Get a set of message(s) from the index."""
        ...

    async def contains(self, **kwargs: Any) -> bool:
        """Check if the index contains at least 1 record matching the fields."""
        ...

    async def qry(self, sql: str, parameters: tuple[str, ...]) -> tuple[Message, ...]:
        """Execute a custom SQL query returning messages."""
        ...

    async def qry_field(
        self, sql: str, parameters: tuple[str, ...]
    ) -> list[tuple[Any, ...]]:
        """Execute a custom SQL query returning raw fields."""
        ...

    async def get_rp_codes(self, parameters: tuple[str, ...]) -> list[Code]:
        """Get a list of Codes from the index."""
        ...

    async def all(self, include_expired: bool = False) -> tuple[Message, ...]:
        """Get all messages from the index."""
        ...

    def flush(self) -> None:
        """Flush the storage worker queue."""
        ...

    def stop(self) -> None:
        """Stop the database and close connections."""
        ...


class DeviceInterface(Protocol):
    """Interface for a standard RF Device."""

    @property
    def id(self) -> DeviceIdT:
        """Return the device ID.

        :return: The Device ID.
        """
        ...

    async def traits(self) -> dict[str, Any]:
        """Return the device traits.

        :return: A dictionary of device traits.
        """
        ...

    def _handle_msg(self, msg: Message) -> None:
        """Process an incoming message.

        :param msg: The message to process.
        """
        ...


class DeviceFilterInterface(Protocol):
    """Interface for the Device Filter service."""

    def check_filter_lists(self, dev_id: DeviceIdT) -> None:
        """Raise a DeviceNotFoundError if a device_id is filtered out.

        :param dev_id: The device identifier to evaluate.
        """
        ...


class DeviceRegistryInterface(Protocol):
    """Interface for the Device Registry service."""

    @property
    def devices(self) -> list[Any]:
        """Return the list of devices."""
        ...

    @property
    def device_by_id(self) -> dict[DeviceIdT, Any]:
        """Return the mapping of device IDs to devices."""
        ...

    @property
    def system_by_id(self) -> dict[DeviceIdT, Any]:
        """Return a mapping of device IDs to their associated systems."""
        ...

    @property
    def systems(self) -> list[Any]:
        """Return a list of all identified systems."""
        ...

    def _add_device(self, dev: Any) -> None:
        """Add a device to the registry."""
        ...

    def get_device(
        self,
        device_id: DeviceIdT,
        *,
        msg: Message | None = None,
        parent: "Parent | None" = None,
        child_id: str | None = None,
        is_sensor: bool | None = None,
    ) -> Any:
        """Return a device, creating it if it does not already exist."""
        ...

    async def fake_device(
        self,
        device_id: DeviceIdT,
        create_device: bool = False,
    ) -> Any:
        """Create a faked device."""
        ...

    async def known_list(self) -> DeviceListT:
        """Return the working known_list."""
        ...

    async def get_heat_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned heat devices."""
        ...

    async def get_hvac_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned HVAC devices."""
        ...

    async def params(self) -> dict[str, Any]:
        """Return the parameters for all devices."""
        ...

    async def status(self) -> dict[str, Any]:
        """Return the status for all devices."""
        ...


class GatewayInterface(Protocol):
    """Interface for the core Gateway orchestrator."""

    @property
    def device_registry(self) -> DeviceRegistryInterface:
        """Return the Device Registry."""
        ...

    @property
    def msg_db(self) -> MessageIndexInterface | None:
        """Return the message database if configured."""
        ...

    @msg_db.setter
    def msg_db(self, value: MessageIndexInterface | None) -> None:
        """Set the message database."""
        ...

    @property
    def config(self) -> Any:
        """Return the gateway configuration."""
        ...

    async def async_send_cmd(
        self,
        cmd: Command,
        /,
        *,
        priority: Priority = Priority.DEFAULT,
        wait_for_reply: bool | None = True,
        max_retries: int = 3,
        timeout: float = 3.0,
    ) -> Packet:
        """Send a command asynchronously and return the resulting packet."""
        ...
