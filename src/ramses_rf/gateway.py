#!/usr/bin/env python3

# TODO:
# - sort out gwy.config...
# - sort out reduced processing


"""RAMSES RF -the gateway (i.e. HGI80 / evofw3, not RFG100)."""

from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from logging.handlers import QueueListener
from typing import TYPE_CHECKING, Any, Literal, cast

from ramses_tx.const import (
    DEFAULT_GAP_DURATION,
    DEFAULT_MAX_RETRIES,
    DEFAULT_NUM_REPEATS,
    DEFAULT_SEND_TIMEOUT,
    DEFAULT_WAIT_FOR_REPLY,
    SZ_ACTIVE_HGI,
    SZ_READER_TASK,
)
from ramses_tx.schemas import SZ_BLOCK_LIST, SZ_ENFORCE_KNOWN_LIST, SZ_KNOWN_LIST

from .const import DONT_CREATE_MESSAGES
from .schemas import (
    SCH_GLOBAL_SCHEMAS,
    SZ_CONFIG,
    SZ_ENABLE_EAVESDROP,
    SZ_MAIN_TCS,
    SZ_ORPHANS,
)

from .const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    Code,
)

from ramses_tx import (
    Command,
    Engine,
    Message,
    Packet,
    Priority,
    extract_known_hgi_id,
    protocol_factory,
    set_pkt_logging_config,
    transport_factory,
)
from ramses_tx.transport import TransportConfig
from ramses_tx.typing import PktLogConfigT, PortConfigT

from .database import MessageIndex
from .device import HgiGateway
from .device_filter import DeviceFilter
from .device_registry import DeviceRegistry
from .dispatcher import detect_array_fragment, process_msg
from .interfaces import (
    DeviceFilterInterface,
    DeviceRegistryInterface,
    GatewayInterface,
    MessageIndexInterface,
)
from .schemas import load_schema
from .system import Evohome
from .typing import DeviceListT

if TYPE_CHECKING:
    from ramses_tx import RamsesTransportT

    from .device import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class GatewayConfig:
    """Configuration parameters for the Ramses Gateway.

    :param disable_discovery: Disable device discovery, defaults to False.
    :type disable_discovery: bool
    :param enable_eavesdrop: Enable eavesdropping mode, defaults to False.
    :type enable_eavesdrop: bool
    :param reduce_processing: Level of reduced processing, defaults to 0.
    :type reduce_processing: int
    :param max_zones: Maximum number of zones allowed, defaults to 12.
    :type max_zones: int
    :param use_regex: Regex patterns for matching devices, defaults to empty dict.
    :type use_regex: dict[str, dict[str, str]]
    :param use_aliases: Mapping of aliases for device IDs, defaults to empty dict.
    :type use_aliases: dict[str, str]
    :param enforce_strict_handling: Enforce strict handling of packets, defaults to False.
    :type enforce_strict_handling: bool
    :param use_native_ot: Preference for using native OpenTherm.
    :type use_native_ot: Literal["always", "prefer", "avoid", "never"] | None
    :param app_context: Optional application context object.
    :type app_context: Any | None
    """

    disable_discovery: bool = False
    enable_eavesdrop: bool = False
    reduce_processing: int = 0
    max_zones: int = 12
    use_regex: dict[str, dict[str, str]] = field(default_factory=dict)
    use_aliases: dict[str, str] = field(default_factory=dict)
    enforce_strict_handling: bool = False
    use_native_ot: Literal["always", "prefer", "avoid", "never"] | None = None
    app_context: Any | None = None


class Gateway(GatewayInterface):
    """The gateway class.

    This class serves as the primary interface for the RAMSES RF network. It manages
    the serial connection (via ``Engine``), device discovery, schema maintenance,
    and message dispatching.
    """

    def __init__(
        self,
        port_name: str | None = None,
        *,
        config: GatewayConfig | None = None,
        schema: dict[str, Any] | None = None,
        input_file: str | None = None,
        port_config: PortConfigT | None = None,
        packet_log: PktLogConfigT | None = None,
        block_list: DeviceListT | None = None,
        known_list: DeviceListT | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        transport_constructor: Callable[..., Awaitable[RamsesTransportT]] | None = None,
        hgi_id: str | None = None,
        debug_mode: bool = False,
        disable_sending: bool = False,
        disable_qos: bool | None = None,
        enforce_known_list: bool = False,
        evofw_flag: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Gateway instance.

        :param port_name: The serial port name (e.g., '/dev/ttyUSB0') or None if using a file.
        :type port_name: str | None
        :param config: The typed configuration parameters for the Gateway.
        :type config: GatewayConfig | None, optional
        :param schema: Dictionary representing the schema.
        :type schema: dict[str, Any] | None, optional
        :param input_file: Path to a packet log file for playback/parsing, defaults to None.
        :type input_file: str | None, optional
        :param port_config: Configuration dictionary for the serial port, defaults to None.
        :type port_config: PortConfigT | None, optional
        :param packet_log: Configuration for packet logging, defaults to None.
        :type packet_log: PktLogConfigT | None, optional
        :param block_list: A list of device IDs to block/ignore, defaults to None.
        :type block_list: DeviceListT | None, optional
        :param known_list: A list of known device IDs and their traits, defaults to None.
        :type known_list: DeviceListT | None, optional
        :param loop: The asyncio event loop to use, defaults to None.
        :type loop: asyncio.AbstractEventLoop | None, optional
        :param transport_constructor: A factory for creating the transport layer, defaults to None.
        :type transport_constructor: Callable[..., Awaitable[RamsesTransportT]] | None, optional
        :param hgi_id: The Device ID to use for the HGI (gateway), overriding defaults.
        :type hgi_id: str | None, optional
        :param debug_mode: If True, set the logger to debug mode.
        :type debug_mode: bool, optional
        :param disable_sending: Prevent sending any packets from the protocol.
        :type disable_sending: bool, optional
        :param disable_qos: Disable the Quality of Service mechanism.
        :type disable_qos: bool | None, optional
        :param enforce_known_list: Enforce that only known devices can be created.
        :type enforce_known_list: bool, optional
        :param evofw_flag: Specific flag for evofw3 usage.
        :type evofw_flag: str | None, optional
        :param kwargs: Catch-all for legacy keyword arguments.
        :type kwargs: Any
        """
        if kwargs:
            warnings.warn(
                "Initializing Gateway with undocumented **kwargs is deprecated. "
                "Please transition to using GatewayConfig.",
                DeprecationWarning,
                stacklevel=2,
            )

        if debug_mode:
            _LOGGER.setLevel(logging.DEBUG)

        self._gwy_config = config or GatewayConfig()

        self._engine = Engine(
            port_name,
            input_file=input_file,
            port_config=port_config,
            packet_log=packet_log,
            block_list=cast("Any", block_list),
            known_list=cast("Any", known_list),
            loop=loop,
            hgi_id=hgi_id,
            transport_constructor=transport_constructor,
            disable_sending=disable_sending,
            disable_qos=disable_qos,
            enforce_known_list=enforce_known_list,
            evofw_flag=evofw_flag,
            use_regex=self._gwy_config.use_regex,
            app_context=self._gwy_config.app_context,
        )

        # Force the engine's protocol to use Gateway's message handler
        self._engine._set_msg_handler(self._msg_handler)

        if self._engine._disable_sending:
            self._gwy_config.disable_discovery = True

        if self._gwy_config.enable_eavesdrop:
            _LOGGER.warning(
                f"{SZ_ENABLE_EAVESDROP}=True: this is strongly discouraged"
                " for routine use (there be dragons here)"
            )

        self._schema: dict[str, Any] = SCH_GLOBAL_SCHEMAS(schema or {})

        self._tcs: Evohome | None = None

        self._device_registry: DeviceRegistryInterface = DeviceRegistry(self)

        self._device_filter: DeviceFilterInterface = DeviceFilter(
            include=cast(DeviceListT, self._engine._include),
            exclude=cast(DeviceListT, self._engine._exclude),
            unwanted=self._engine._unwanted,
            enforce_known_list=self._engine._enforce_known_list,
            hgi_id_provider=lambda: getattr(self.hgi, "id", None),
        )

        self._msg_db: MessageIndexInterface | None = None
        self._pkt_log_listener: QueueListener | None = None

    def __repr__(self) -> str:
        """Return a string representation of the Gateway.

        :returns: A string describing the gateway's input source (port or file).
        :rtype: str
        """
        if not self._engine.ser_name:
            return f"Gateway(input_file={self._engine._input_file})"
        return f"Gateway(port_name={self._engine.ser_name}, port_config={self._engine._port_config})"

    # ------------------------------------------------------------------------
    # TODO: TEMPORARY PROXIES FOR TEST SUITE BACKWARDS COMPATIBILITY
    # These properties intercept legacy test accesses to Engine internals
    # and route them to the composed Engine. They can be removed in a later
    # PR once the test suite is updated to respect the new API boundaries.
    # ------------------------------------------------------------------------

    @property
    def _transport(self) -> Any:
        return self._engine._transport

    @_transport.setter
    def _transport(self, value: Any) -> None:
        self._engine._transport = value

    @property
    def _protocol(self) -> Any:
        return self._engine._protocol

    @_protocol.setter
    def _protocol(self, value: Any) -> None:
        self._engine._protocol = value

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        return self._engine._loop

    @_loop.setter
    def _loop(self, value: asyncio.AbstractEventLoop) -> None:
        self._engine._loop = value

    @property
    def _disable_sending(self) -> bool:
        return self._engine._disable_sending

    @_disable_sending.setter
    def _disable_sending(self, value: bool) -> None:
        self._engine._disable_sending = value

    @property
    def _include(self) -> Any:
        return self._engine._include

    @_include.setter
    def _include(self, value: Any) -> None:
        self._engine._include = value

    @property
    def _exclude(self) -> Any:
        return self._engine._exclude

    @_exclude.setter
    def _exclude(self, value: Any) -> None:
        self._engine._exclude = value

    @property
    def _enforce_known_list(self) -> bool:
        return self._engine._enforce_known_list

    @_enforce_known_list.setter
    def _enforce_known_list(self, value: bool) -> None:
        self._engine._enforce_known_list = value

    @property
    def _hgi_id(self) -> str | None:
        return self._engine._hgi_id

    @_hgi_id.setter
    def _hgi_id(self, value: str | None) -> None:
        self._engine._hgi_id = value

    @property
    def ser_name(self) -> str | None:
        return self._engine.ser_name

    @ser_name.setter
    def ser_name(self, value: str | None) -> None:
        self._engine.ser_name = value

    @property
    def _this_msg(self) -> Message | None:
        return self._engine._this_msg

    @_this_msg.setter
    def _this_msg(self, value: Message | None) -> None:
        self._engine._this_msg = value

    @property
    def pkt_received(self) -> int:
        return getattr(self._engine, "pkt_received", 0)

    @property
    def wait_for_connection_lost(self) -> Any:
        return getattr(self._engine, "wait_for_connection_lost", None)

    @property
    def _is_evofw3(self) -> bool | None:
        return getattr(self._engine, "_is_evofw3", None)

    @property
    def device_registry(self) -> DeviceRegistryInterface:
        """Return the Device Registry service.

        :returns: The instantiated DeviceRegistryInterface.
        :rtype: DeviceRegistryInterface
        """
        return self._device_registry

    @property
    def config(self) -> GatewayConfig:
        """Return the gateway configuration.

        :returns: The configuration object for this gateway.
        :rtype: GatewayConfig
        """
        return self._gwy_config

    @property
    def msg_db(self) -> MessageIndexInterface | None:
        """Return the message database if configured.

        :returns: The configured MessageIndexInterface or None.
        :rtype: MessageIndexInterface | None
        """
        return self._msg_db

    @msg_db.setter
    def msg_db(self, value: MessageIndexInterface | None) -> None:
        """Set the message database.

        :param value: The MessageIndexInterface instance to set, or None.
        :type value: MessageIndexInterface | None
        """
        self._msg_db = value

    @property
    def hgi(self) -> HgiGateway | None:
        """Return the active HGI80-compatible gateway device, if known.

        :returns: The active HGI gateway device if found, else None.
        :rtype: HgiGateway | None
        """
        if not self._engine._transport:
            return None
        if device_id := self._engine._transport.get_extra_info(SZ_ACTIVE_HGI):
            return self.device_registry.device_by_id.get(device_id)
        return None

    @property
    def _dt_now(self) -> Any:
        return getattr(self._engine, "_dt_now", None)

    @property
    def _tasks(self) -> list[asyncio.Task[Any]]:
        return getattr(self._engine, "_tasks", [])

    @property
    def _sqlite_index(self) -> bool:
        return getattr(self._engine, "_sqlite_index", False)

    @_sqlite_index.setter
    def _sqlite_index(self, value: bool) -> None:
        self._engine._sqlite_index = value

    # ------------------------------------------------------------------------

    async def start(
        self,
        /,
        *,
        start_discovery: bool = True,
        cached_packets: dict[str, str] | None = None,
    ) -> None:
        """Start the Gateway and Initiate discovery as required.

        This method initializes packet logging, the SQLite index, loads the schema,
        and optionally restores state from cached packets before starting the transport.

        :param start_discovery: Whether to initiate the discovery process after start, defaults to True.
        :type start_discovery: bool, optional
        :param cached_packets: A dictionary of packet strings used to restore state, defaults to None.
        :type cached_packets: dict[str, str] | None, optional
        :returns: None
        :rtype: None
        """

        def initiate_discovery(dev_list: list[Device], sys_list: list[Evohome]) -> None:
            """Initiate polling discovery on devices and systems.

            :param dev_list: List of devices to discover.
            :type dev_list: list[Device]
            :param sys_list: List of systems to discover.
            :type sys_list: list[Evohome]
            :returns: None
            :rtype: None
            """
            _LOGGER.debug("Engine: Initiating/enabling discovery...")

            # Routing to components
            for device in dev_list:
                device.discovery.start_poller()

            for system in sys_list:
                system.discovery.start_poller()
                for zone in system.zones:
                    zone.discovery.start_poller()
                if system.dhw:
                    system.dhw.discovery.start_poller()

        _, self._pkt_log_listener = await set_pkt_logging_config(  # type: ignore[arg-type]
            cc_console=self.config.reduce_processing >= DONT_CREATE_MESSAGES,
            **self._engine._packet_log,
        )
        if self._pkt_log_listener:
            self._pkt_log_listener.start()

        # initialize SQLite index, set in _tx/Engine
        if self._engine._sqlite_index:  # TODO(eb): default to True in Q1 2026
            _LOGGER.info("Ramses RF starts SQLite MessageIndex")
            # if activated in ramses_cc > Engine or set in tests
            self.create_sqlite_message_index()

        # temporarily turn on discovery, remember original state
        self.config.disable_discovery, disable_discovery = (
            True,
            self.config.disable_discovery,
        )

        load_schema(
            self, known_list=self._engine._include, **self._schema
        )  # create faked too

        await self._engine.start()  # TODO: do this *after* restore cache
        if cached_packets:
            await self._restore_cached_packets(cached_packets)

        # reset discovery to original state
        self.config.disable_discovery = disable_discovery

        if (
            not self._engine._disable_sending
            and not self.config.disable_discovery
            and start_discovery
        ):
            initiate_discovery(
                self.device_registry.devices, self.device_registry.systems
            )

    def create_sqlite_message_index(self) -> None:
        """Initialize the SQLite MessageIndex.

        :returns: None
        :rtype: None
        """
        self._msg_db = MessageIndex()  # start the index

    async def stop(self) -> None:
        """Stop the Gateway and tidy up.

        Stops the message database and the underlying engine/transport.

        :returns: None
        :rtype: None
        """
        # Stop the Engine first to ensure no tasks/callbacks try to write
        # to the DB while we are closing it.
        await self._engine.stop()

        if self._pkt_log_listener:
            self._pkt_log_listener.stop()
            # Close handlers to ensure files are flushed/closed
            for handler in self._pkt_log_listener.handlers:
                handler.close()
            self._pkt_log_listener = None

        if self._msg_db:
            self._msg_db.stop()

    async def _pause(self, *args: Any) -> None:
        """Pause the (unpaused) gateway (disables sending/discovery).

        There is the option to save other objects, as `args`.

        :param args: Additional objects/state to save during the pause.
        :type args: Any
        :returns: None
        :rtype: None
        :raises RuntimeError: If the engine fails to pause.
        """
        _LOGGER.debug("Gateway: Pausing engine...")

        self.config.disable_discovery, disc_flag = True, self.config.disable_discovery

        try:
            await self._engine._pause(disc_flag, *args)
        except RuntimeError:
            self.config.disable_discovery = disc_flag
            raise

    async def _resume(self) -> tuple[Any, ...]:
        """Resume the (paused) gateway (enables sending/discovery, if applicable).

        Will restore other objects, as `args`.

        :returns: A tuple of arguments saved during the pause.
        :rtype: tuple[Any, ...]
        """
        args: tuple[Any, ...]

        _LOGGER.debug("Gateway: Resuming engine...")

        # args_tuple = await super()._resume()
        # self.config.disable_discovery, *args = args_tuple  # type: ignore[assignment]
        self.config.disable_discovery, *args = await self._engine._resume()  # type: ignore[assignment]

        return args

    async def get_state(
        self, include_expired: bool = False
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Return the current schema & state (may include expired packets).

        :param include_expired: If True, include expired packets in the state, defaults to False.
        :type include_expired: bool, optional
        :returns: A tuple containing the schema dictionary and the packet log dictionary.
        :rtype: tuple[dict[str, Any], dict[str, str]]
        """

        await self._pause()

        def wanted_msg(msg: Message, include_expired: bool = False) -> bool:
            """Determine if a message is wanted for state reconstruction.

            :param msg: The message to evaluate.
            :type msg: Message
            :param include_expired: Whether to include expired messages, defaults to False.
            :type include_expired: bool, optional
            :returns: True if the message should be kept, otherwise False.
            :rtype: bool
            """
            if msg.code == Code._313F:
                return msg.verb in (I_, RP)  # usu. expired, useful 4 back-back restarts
            if msg._expired and not include_expired:
                return False
            if msg.code == Code._0404:
                return msg.verb in (I_, W_) and msg._pkt._len > 7
            if msg.verb in (W_, RQ):
                return False
            # if msg.code == Code._1FC9 and msg.verb != RP:
            #     return True
            return include_expired or not msg._expired

        if self.msg_db:
            pkts = {
                f"{repr(msg._pkt)[:26]}": f"{repr(msg._pkt)[27:]}"
                for msg in await self.msg_db.all(include_expired=True)
                if wanted_msg(msg, include_expired=include_expired)
            }
        else:  # deprecated, to be removed in Q1 2026
            msgs = []
            for device in self.device_registry.devices:
                msgs.extend(await device.state_store._msg_list())
            for system in self.device_registry.systems:
                msgs.extend(list((await system.state_store._msgs()).values()))
                for z in system.zones:
                    msgs.extend(list((await z.state_store._msgs()).values()))

            pkts = {  # BUG: assumes pkts have unique dtms: may be untrue for contrived logs
                f"{repr(msg._pkt)[:26]}": f"{repr(msg._pkt)[27:]}"
                for msg in msgs
                if wanted_msg(msg, include_expired=include_expired)
            }
            # _LOGGER.warning("Missing MessageIndex")

        await self._resume()

        return await self.schema(), dict(sorted(pkts.items()))

    async def _restore_cached_packets(
        self, packets: dict[str, str], _clear_state: bool = False
    ) -> None:
        """Restore cached packets (may include expired packets).

        This process uses a temporary transport to replay the packet history
        into the message handler.

        :param packets: A dictionary of packet strings.
        :type packets: dict[str, str]
        :param _clear_state: If True, reset internal state before restoration (for testing), defaults to False.
        :type _clear_state: bool, optional
        :returns: None
        :rtype: None
        """

        def clear_state() -> None:
            """Clear existing internal schema and state records.

            :returns: None
            :rtype: None
            """
            _LOGGER.info("Gateway: Clearing existing schema/state...")

            # self._schema = {}

            self._tcs = None
            self.device_registry.devices.clear()
            self.device_registry.device_by_id.clear()
            self._engine._prev_msg = None
            self._engine._this_msg = None

        tmp_transport: RamsesTransportT  # mypy hint

        _LOGGER.debug("Gateway: Restoring a cached packet log...")
        await self._pause()

        if _clear_state:  # only intended for test suite use
            clear_state()

        # We do not always enforce the known_list whilst restoring a cache because
        # if it does not contain a correctly configured HGI, a 'working' address is
        # used (which could be different to the address in the cache) & wanted packets
        # can be dropped unnecessarily.

        enforce_include_list = bool(
            self._engine._enforce_known_list
            and extract_known_hgi_id(
                self._engine._include, disable_warnings=True, strict_checking=True
            )
        )

        # The actual HGI address will be discovered when the actual transport was/is
        # started up (usually before now)

        tmp_protocol = protocol_factory(
            self._msg_handler,
            disable_sending=True,
            enforce_include_list=enforce_include_list,
            exclude_list=self._engine._exclude,
            include_list=self._engine._include,
        )

        tmp_transport = await transport_factory(
            tmp_protocol,
            config=TransportConfig(disable_sending=True),
            packet_dict=packets,
        )

        await tmp_transport.get_extra_info(SZ_READER_TASK)

        _LOGGER.debug("Gateway: Restored, resuming")
        await self._resume()

    @property
    def tcs(self) -> Evohome | None:
        """Return the primary Temperature Control System (TCS), if any.

        :returns: The primary Evohome system or None.
        :rtype: Evohome | None
        """

        if self._tcs is None and self.device_registry.systems:
            self._tcs = self.device_registry.systems[0]
        return self._tcs

    async def _config(self) -> dict[str, Any]:
        """Return the working configuration.

        :returns: A dictionary containing the current configuration state.
        :rtype: dict[str, Any]
        """
        return {
            "_gateway_id": self.hgi.id if self.hgi else None,
            SZ_MAIN_TCS: self.tcs.id if self.tcs else None,
            SZ_CONFIG: {SZ_ENFORCE_KNOWN_LIST: self._engine._enforce_known_list},
            SZ_KNOWN_LIST: await self.device_registry.known_list(),
            SZ_BLOCK_LIST: [{k: v} for k, v in self._engine._exclude.items()],
            "_unwanted": sorted(self._engine._unwanted),
        }

    async def schema(self) -> dict[str, Any]:
        """Return the global schema.

        :returns: A dictionary representing the global system schema.
        :rtype: dict[str, Any]
        """

        schema: dict[str, Any] = {SZ_MAIN_TCS: self.tcs.ctl.id if self.tcs else None}

        for tcs in self.device_registry.systems:
            schema[tcs.ctl.id] = await tcs.schema()

        schema[f"{SZ_ORPHANS}_heat"] = await self.device_registry.get_heat_orphans()
        schema[f"{SZ_ORPHANS}_hvac"] = await self.device_registry.get_hvac_orphans()

        return schema

    async def params(self) -> dict[str, Any]:
        """Return the parameters for all devices.

        :returns: A dictionary containing parameters for all devices.
        :rtype: dict[str, Any]
        """
        return await self.device_registry.params()

    async def status(self) -> dict[str, Any]:
        """Return the status for all devices and the transport rate.

        :returns: A dictionary containing device statuses and the transport transmission rate.
        :rtype: dict[str, Any]
        """
        status_dict = await self.device_registry.status()
        tx_rate = (
            self._engine._transport.get_extra_info("tx_rate")
            if self._engine._transport
            else None
        )
        status_dict["_tx_rate"] = tx_rate
        return status_dict

    def _msg_handler(self, msg: Message) -> None:
        """A callback to handle messages from the protocol stack.

        :param msg: The message to be handled and processed.
        :type msg: Message
        :returns: None
        :rtype: None
        """
        # Engine's logic replicated to map directly to the Gateway
        msg.__class__ = Message
        setattr(msg, "_gwy", self)  # noqa: B010

        self._engine._this_msg, self._engine._prev_msg = msg, self._engine._this_msg

        # TODO: ideally remove this feature...
        assert self._engine._this_msg  # mypy check

        if self._engine._prev_msg and detect_array_fragment(
            self._engine._this_msg, self._engine._prev_msg
        ):
            msg._pkt._force_has_array()
            msg._payload = self._engine._prev_msg.payload + (
                msg.payload if isinstance(msg.payload, list) else [msg.payload]
            )

        process_msg(self, msg)

    def add_msg_handler(
        self,
        msg_handler: Callable[[Message], None],
        /,
        *,
        msg_filter: Callable[[Message], bool] | None = None,
    ) -> Callable[[], None]:
        """Add a Message handler to the underlying Protocol.

        :param msg_handler: The message handler callback.
        :type msg_handler: Callable[[Message], None]
        :param msg_filter: An optional filter to only handle specific messages.
        :type msg_filter: Callable[[Message], bool] | None, optional
        :returns: A callable to remove the handler.
        :rtype: Callable[[], None]
        """
        return self._engine.add_msg_handler(msg_handler, msg_filter=msg_filter)

    def add_task(self, task: asyncio.Task[Any]) -> None:
        """Add a task to the engine's task list.

        :param task: The asyncio Task to track.
        :type task: asyncio.Task[Any]
        :returns: None
        :rtype: None
        """
        self._engine.add_task(task)

    @staticmethod
    def create_cmd(
        verb: str, device_id: str, code: Code | str, payload: str, **kwargs: Any
    ) -> Command:
        """Make a command addressed to device_id.

        :param verb: The command verb (e.g. RQ, W).
        :type verb: str
        :param device_id: The target device identifier.
        :type device_id: str
        :param code: The code representing the command.
        :type code: Code | str
        :param payload: The payload of the command.
        :type payload: str
        :param kwargs: Additional arguments for the command generation.
        :type kwargs: Any
        :returns: The created Command instance.
        :rtype: Command
        """
        return Engine.create_cmd(verb, device_id, code, payload, **kwargs)  # type: ignore[arg-type]

    def send_cmd(
        self,
        cmd: Command,
        /,
        *,
        gap_duration: float = DEFAULT_GAP_DURATION,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        priority: Priority = Priority.DEFAULT,
        timeout: float = DEFAULT_SEND_TIMEOUT,
        wait_for_reply: bool | None = DEFAULT_WAIT_FOR_REPLY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> asyncio.Task[Packet]:
        """Wrapper to schedule an async_send_cmd() and return the Task.

        Commands are queued and sent FIFO, except higher-priority Commands are
        always sent first.

        :param cmd: The command object to send.
        :type cmd: Command
        :param gap_duration: The gap between repeats (in seconds), defaults to DEFAULT_GAP_DURATION.
        :type gap_duration: float, optional
        :param num_repeats: Number of times to repeat the command (0 = once, 1 = twice, etc.), defaults to DEFAULT_NUM_REPEATS.
        :type num_repeats: int, optional
        :param priority: The priority of the command, defaults to Priority.DEFAULT.
        :type priority: Priority, optional
        :param timeout: Time to wait for a send to complete, defaults to DEFAULT_SEND_TIMEOUT.
        :type timeout: float, optional
        :param wait_for_reply: Whether to wait for a reply packet, defaults to DEFAULT_WAIT_FOR_REPLY.
        :type wait_for_reply: bool | None, optional
        :param max_retries: Maximum number of retries if sending fails, defaults to DEFAULT_MAX_RETRIES.
        :type max_retries: int, optional
        :returns: The asyncio Task wrapping the send operation.
        :rtype: asyncio.Task[Packet]
        """

        coro = self.async_send_cmd(
            cmd,
            gap_duration=gap_duration,
            num_repeats=num_repeats,
            priority=priority,
            timeout=timeout,
            wait_for_reply=wait_for_reply,
            max_retries=max_retries,
        )

        task = self._engine._loop.create_task(coro)
        self.add_task(task)  # wait for these during stop()
        return task

    async def async_send_cmd(
        self,
        cmd: Command,
        /,
        *,
        gap_duration: float = DEFAULT_GAP_DURATION,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        priority: Priority = Priority.DEFAULT,
        timeout: float = DEFAULT_SEND_TIMEOUT,
        wait_for_reply: bool | None = DEFAULT_WAIT_FOR_REPLY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Packet:
        """Send a Command and return the corresponding (echo or reply) Packet.

        If wait_for_reply is True (*and* the Command has a rx_header), return the
        reply Packet. Otherwise, simply return the echo Packet.

        :param cmd: The command object to send.
        :type cmd: Command
        :param gap_duration: The gap between repeats (in seconds), defaults to DEFAULT_GAP_DURATION.
        :type gap_duration: float, optional
        :param num_repeats: Number of times to repeat the command, defaults to DEFAULT_NUM_REPEATS.
        :type num_repeats: int, optional
        :param priority: The priority of the command, defaults to Priority.DEFAULT.
        :type priority: Priority, optional
        :param max_retries: Maximum number of retries if sending fails, defaults to DEFAULT_MAX_RETRIES.
        :type max_retries: int, optional
        :param timeout: Time to wait for the command to send, defaults to DEFAULT_SEND_TIMEOUT.
        :type timeout: float, optional
        :param wait_for_reply: Whether to wait for a reply packet, defaults to DEFAULT_WAIT_FOR_REPLY.
        :type wait_for_reply: bool | None, optional
        :returns: The echo packet or reply packet depending on wait_for_reply.
        :rtype: Packet
        :raises ProtocolSendFailed: If the command was sent but no reply/echo was received.
        :raises ProtocolError: If the system failed to attempt the transmission.
        """

        return await self._engine.async_send_cmd(
            cmd,
            gap_duration=gap_duration,
            num_repeats=num_repeats,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            wait_for_reply=wait_for_reply,
        )  # may: raise ProtocolError/ProtocolSendFailed
