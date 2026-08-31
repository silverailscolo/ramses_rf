#!/usr/bin/env python3
"""RAMSES RF - discovery scripts."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from ramses_rf import exceptions as exc
from ramses_rf.address import HGI_DEV_ADDR, Address
from ramses_rf.commands.core import Command as Intent
from ramses_rf.const import (
    FC,
    HW,
    SZ_FRAGMENT_NUMBER,
    SZ_LOG_INDEX,
    SZ_MESSAGE_ID,
    SZ_SCHEDULE,
    SZ_TOTAL_FRAGMENTS,
    SZ_ZONE_INDEX,
)
from ramses_rf.devices import Controller, Fakeable
from ramses_rf.enums import Action
from ramses_rf.protocol.opentherm import OPENTHERM_DATA_IDS
from ramses_rf.protocol.ramses import CODE_NAME_LOOKUP, RQ_NO_PAYLOAD
from ramses_tx import CommandDTO, DeviceIdT, Packet, Priority
from ramses_tx.address import NON_DEV_ADDR
from ramses_tx.const import RQ, W_, Code

if TYPE_CHECKING:
    from ramses_rf import Gateway
    from ramses_rf.devices import Controller
    from ramses_tx import IndexT


EXEC_CMD: Final = "exec_cmd"
GET_FAULTS: Final = "get_faults"
GET_SCHED: Final = "get_schedule"
SET_SCHED: Final = "set_schedule"

EXEC_SCR: Final = "exec_scr"
SCAN_DISC: Final = "scan_disc"
SCAN_FULL: Final = "scan_full"
SCAN_HARD: Final = "scan_hard"
SCAN_XXXX: Final = "scan_xxxx"

_LOGGER = logging.getLogger(__name__)


def _send_probe_dto(
    gateway: Gateway,
    command: CommandDTO,
    /,
    *,
    priority: Priority = Priority.DEFAULT,
    num_repeats: int = 1,
) -> asyncio.Task[Packet]:
    """Schedule low-level command transmission as a background task for CLI discovery scripts."""
    coro = gateway._async_send_dto(
        command, priority=priority, num_repeats=num_repeats
    )
    task = gateway._engine._loop.create_task(coro)

    def _clear_exc(fut: asyncio.Task[Any]) -> None:
        if not fut.cancelled() and fut.exception():
            _LOGGER.debug(
                "Background discovery task failed: %s", fut.exception()
            )

    task.add_done_callback(_clear_exc)
    gateway.add_task(task)
    return task


def script_decorator(fnc: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a script to broadcast 'Script begins:' and 'Script done.' messages.

    :param fnc: The asynchronous script function to decorate.
    :return: The wrapped asynchronous function.
    """

    @functools.wraps(fnc)
    async def wrapper(gateway: Gateway, *args: Any, **kwargs: Any) -> None:
        start_intent = Intent(
            src=HGI_DEV_ADDR,
            dst=HGI_DEV_ADDR,
            action=Action.SEND_PUZZLE,
            data={"message": "Script begins:"},
        )
        gateway.dispatcher.send_background(
            start_intent, priority=Priority.HIGHEST
        )

        await fnc(gateway, *args, **kwargs)

        finish_intent = Intent(
            src=HGI_DEV_ADDR,
            dst=HGI_DEV_ADDR,
            action=Action.SEND_PUZZLE,
            data={"message": "Script done."},
        )
        gateway.dispatcher.send_background(
            finish_intent, priority=Priority.LOWEST
        )

    return wrapper


def spawn_scripts(gateway: Gateway, **kwargs: Any) -> list[asyncio.Task[None]]:
    """Spawn discovery or execution tasks based on provided CLI keyword arguments.

    :param gateway: The main gateway instance handling transport and device
        indexing.
    :param kwargs: CLI configuration dictionary containing execution flags.
    :return: A list of the generated asyncio tasks running the specified scripts.
    """
    tasks: list[asyncio.Task[None]] = []

    if kwargs.get(EXEC_CMD):
        tasks.append(asyncio.create_task(exec_cmd(gateway, **kwargs)))

    if kwargs.get(GET_FAULTS):
        tasks.append(
            asyncio.create_task(get_faults(gateway, kwargs[GET_FAULTS]))
        )

    elif kwargs.get(GET_SCHED) and kwargs[GET_SCHED][0]:
        tasks.append(
            asyncio.create_task(get_schedule(gateway, *kwargs[GET_SCHED]))
        )

    elif kwargs.get(SET_SCHED) and kwargs[SET_SCHED][0]:
        tasks.append(
            asyncio.create_task(set_schedule(gateway, *kwargs[SET_SCHED]))
        )

    elif kwargs.get(EXEC_SCR):
        script = SCRIPTS.get(f"{kwargs[EXEC_SCR][0]}")
        if script is None:
            _LOGGER.warning(
                "Script: %s() - unknown script", kwargs[EXEC_SCR][0]
            )
        else:
            _LOGGER.info("Script: %s().- starts...", kwargs[EXEC_SCR][0])
            # script_poll_device returns a list of tasks, others return a coroutine
            result = script(gateway, kwargs[EXEC_SCR][1])
            if isinstance(result, list):
                tasks.extend(result)
            else:
                tasks.append(asyncio.create_task(result))

    gateway._engine._tasks.extend(tasks)
    return tasks


async def exec_cmd(gateway: Gateway, **kwargs: Any) -> None:
    """Execute a single raw command string from the CLI arguments.

    :param gateway: The gateway instance.
    :param kwargs: CLI parameters containing the 'EXEC_CMD' string.
    """
    command = CommandDTO.from_cli(kwargs[EXEC_CMD])
    await gateway._async_send_dto(command, priority=Priority.HIGH)


async def get_faults(
    gateway: Gateway,
    controller_id: DeviceIdT,
    start: int = 0,
    limit: int = 0x3F,
) -> None:
    """Retrieve the fault log from a target controller.

    :param gateway: The gateway instance.
    :param controller_id: The device ID of the controller to query.
    :param start: The index to start querying from.
    :param limit: The maximum number of fault entries to return.
    """
    controller = gateway.device_registry.get_device(
        controller_id, cls=Controller
    )

    try:
        if controller.tcs:
            await controller.tcs.get_faultlog(start=start, limit=limit)  # 0418
    except exc.ExpiredCallbackError as err:
        _LOGGER.error("get_faults(): Function timed out: %s", err)


async def get_schedule(
    gateway: Gateway, controller_id: DeviceIdT, zone_index: str
) -> None:
    """Retrieve the zone schedule for a specific zone under a controller.

    :param gateway: The gateway instance.
    :param controller_id: The device ID of the controller to query.
    :param zone_index: The zone index to fetch schedule for.
    """
    controller = gateway.device_registry.get_device(
        controller_id, cls=Controller
    )

    try:
        if zone_index == HW:
            if controller.tcs and controller.tcs.dhw:
                await controller.tcs.dhw.get_schedule()
        elif controller.tcs:
            zone = controller.tcs.get_htg_zone(zone_index)
            if zone:
                await zone.get_schedule()
    except exc.ExpiredCallbackError as err:
        _LOGGER.error("get_schedule(): Function timed out: %s", err)


async def set_schedule(
    gateway: Gateway, controller_id: DeviceIdT, schedule_input: str | Any
) -> None:
    """Set the zone schedule for a specific zone under a controller via JSON payload.

    :param gateway: The gateway instance.
    :param controller_id: The device ID of the controller to command.
    :param schedule_input: A JSON string, file-like object, or file path describing the schedule.
    """
    if hasattr(schedule_input, "read"):
        schedule_ = json.load(schedule_input)
    elif isinstance(schedule_input, str):
        try:
            schedule_ = json.loads(schedule_input)
        except json.JSONDecodeError:
            with open(schedule_input) as schedule_file:  # noqa: ASYNC230
                schedule_ = json.load(schedule_file)
    else:
        schedule_ = schedule_input

    zone_index = schedule_.get(
        SZ_ZONE_INDEX, schedule_.get("zone_index", "00")
    )
    schedule = schedule_.get(SZ_SCHEDULE, schedule_)

    controller = gateway.device_registry.get_device(
        controller_id, cls=Controller
    )

    try:
        if zone_index == HW:
            if controller.tcs and controller.tcs.dhw:
                await controller.tcs.dhw.set_schedule(schedule)
        elif controller.tcs:
            zone = controller.tcs.get_htg_zone(zone_index)
            if zone:
                await zone.set_schedule(schedule)

    except exc.ExpiredCallbackError as err:
        _LOGGER.error("set_schedule(): Function timed out: %s", err)


async def script_bind_device(
    gateway: Gateway,
    device_id: DeviceIdT,
    code: Code,
    zone_index: IndexT = "00",
) -> None:
    """Put a device into binding mode and wait for binding packets to exchange.

    :param gateway: The gateway instance.
    :param device_id: The device ID to transition to binding state.
    :param code: The expected bind code to accept.
    :param zone_index: The internal domain or zone index to map to.
    """
    device = gateway.device_registry.get_device(device_id)
    assert isinstance(device, Fakeable)  # mypy
    device._make_fake()
    await device._wait_for_binding_request([code], zone_index=zone_index)


def script_poll_device(
    gateway: Gateway, device_id: DeviceIdT
) -> list[asyncio.Task[None]]:
    """Generate tasks to periodically poll a device for vital status metrics.

    :param gateway: The gateway instance.
    :param device_id: The targeted device ID.
    :return: A list containing tasks executing the periodic polling.
    """

    async def periodic_send(
        gateway: Gateway,
        command: CommandDTO,
        count: int = 1,
        interval: float | None = None,
    ) -> None:
        async def periodic_(interval_: float) -> None:
            await asyncio.sleep(interval_)
            _send_probe_dto(gateway, command, priority=Priority.LOW)

        if interval is None:
            interval = 0 if count == 1 else 60

        if count <= 0:
            while True:
                await periodic_(interval)
        else:
            for _ in range(count):
                await periodic_(interval)

    _LOGGER.warning("poll_device() invoked...")

    tasks = []

    for code in (Code._0016, Code._1FC9):
        command = CommandDTO(
            verb=RQ,
            addr1=HGI_DEV_ADDR.id,
            addr2=device_id,
            addr3=NON_DEV_ADDR.id,
            code=code,
            payload="00",
        )
        tasks.append(
            asyncio.create_task(periodic_send(gateway, command, count=0))
        )

    gateway._engine._tasks.extend(tasks)
    return tasks


@script_decorator
async def script_scan_disc(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Trigger the target device's internal discovery poller routine.

    :param gateway: The gateway instance.
    :param device_id: The device ID to scan.
    """
    _LOGGER.warning("scan_disc() invoked...")

    device = gateway.device_registry.get_device(device_id)
    gateway.polling_manager.update_device_tasks(device)


@script_decorator
async def script_scan_full(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Execute a comprehensive probe of a target device across all recognized schema codes.

    :param gateway: The gateway instance.
    :param device_id: The device ID to scan.
    """
    _LOGGER.warning("scan_full() invoked - expect a lot of Warnings")

    _send_probe_dto(
        gateway,
        CommandDTO(
            verb=RQ,
            addr1=HGI_DEV_ADDR.id,
            addr2=device_id,
            addr3=NON_DEV_ADDR.id,
            code=Code._0016,
            payload="0000",
        ),
        num_repeats=3,
    )

    for code in sorted(CODE_NAME_LOOKUP):
        if code == Code._0005:
            for zone_type in range(20):  # known up to 18
                _send_probe_dto(
                    gateway,
                    CommandDTO(
                        verb=RQ,
                        addr1=HGI_DEV_ADDR.id,
                        addr2=device_id,
                        addr3=NON_DEV_ADDR.id,
                        code=code,
                        payload=f"00{zone_type:02X}",
                    ),
                )

        elif code == Code._000C:
            for zone_index in range(16):  # also: FA-FF?
                _send_probe_dto(
                    gateway,
                    CommandDTO(
                        verb=RQ,
                        addr1=HGI_DEV_ADDR.id,
                        addr2=device_id,
                        addr3=NON_DEV_ADDR.id,
                        code=code,
                        payload=f"{zone_index:02X}00",
                    ),
                )

        elif code == Code._0016:
            continue

        elif code in (Code._01D0, Code._01E9):
            for str_zone_index in ("00", "01", FC):
                _send_probe_dto(
                    gateway,
                    CommandDTO(
                        verb=W_,
                        addr1=HGI_DEV_ADDR.id,
                        addr2=device_id,
                        addr3=NON_DEV_ADDR.id,
                        code=code,
                        payload=f"{str_zone_index}00",
                    ),
                )
                _send_probe_dto(
                    gateway,
                    CommandDTO(
                        verb=W_,
                        addr1=HGI_DEV_ADDR.id,
                        addr2=device_id,
                        addr3=NON_DEV_ADDR.id,
                        code=code,
                        payload=f"{str_zone_index}03",
                    ),
                )

        elif code == Code._0404:  # FIXME
            intent1 = Intent(
                src=HGI_DEV_ADDR,
                dst=Address(device_id),
                action=Action.GET_SCHEDULE_FRAGMENT,
                data={
                    SZ_ZONE_INDEX: HW,
                    SZ_FRAGMENT_NUMBER: 1,
                    SZ_TOTAL_FRAGMENTS: 0,
                },
            )
            gateway.dispatcher.send_background(intent1)
            intent2 = Intent(
                src=HGI_DEV_ADDR,
                dst=Address(device_id),
                action=Action.GET_SCHEDULE_FRAGMENT,
                data={
                    SZ_ZONE_INDEX: "00",
                    SZ_FRAGMENT_NUMBER: 1,
                    SZ_TOTAL_FRAGMENTS: 0,
                },
            )
            gateway.dispatcher.send_background(intent2)

        elif code == Code._0418:
            for log_index in range(2):
                intent3 = Intent(
                    src=HGI_DEV_ADDR,
                    dst=Address(device_id),
                    action=Action.GET_FAULTLOG_ENTRY,
                    data={SZ_LOG_INDEX: log_index},
                )
                gateway.dispatcher.send_background(intent3)

        elif code == Code._1100:
            intent4 = Intent(
                src=HGI_DEV_ADDR,
                dst=Address(device_id),
                action=Action.GET_TPI_PARAMS,
                data={},
            )
            gateway.dispatcher.send_background(intent4)

        elif code == Code._2E04:
            intent_mode = Intent(
                src=HGI_DEV_ADDR,
                dst=Address(device_id),
                action=Action.GET_SYSTEM_MODE,
                data={},
            )
            gateway.dispatcher.send_background(intent_mode)

        elif code == Code._3220:
            for data_id in (0, 3):  # these are mandatory READ_DATA data_ids
                intent_ot = Intent(
                    src=HGI_DEV_ADDR,
                    dst=Address(device_id),
                    action=Action.GET_OPENTHERM_DATA,
                    data={SZ_MESSAGE_ID: data_id},
                )
                gateway.dispatcher.send_background(intent_ot)

        elif code == Code._PUZZ:
            continue

        elif code in RQ_NO_PAYLOAD:
            _send_probe_dto(
                gateway,
                CommandDTO(
                    verb=RQ,
                    addr1=HGI_DEV_ADDR.id,
                    addr2=device_id,
                    addr3=NON_DEV_ADDR.id,
                    code=code,
                    payload="00",
                ),
            )

        else:
            _send_probe_dto(
                gateway,
                CommandDTO(
                    verb=RQ,
                    addr1=HGI_DEV_ADDR.id,
                    addr2=device_id,
                    addr3=NON_DEV_ADDR.id,
                    code=code,
                    payload="0000",
                ),
            )

    # these are possible/difficult codes
    for code in (Code._0150, Code._2389):
        _send_probe_dto(
            gateway,
            CommandDTO(
                verb=RQ,
                addr1=HGI_DEV_ADDR.id,
                addr2=device_id,
                addr3=NON_DEV_ADDR.id,
                code=code,
                payload="0000",
            ),
        )


@script_decorator
async def script_scan_hard(
    gateway: Gateway, device_id: DeviceIdT, *, start_code: None | int = None
) -> None:
    """Execute a sequential numeric ping across the theoretical code space.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    :param start_code: Hex starting point for the iteration.
    """
    _LOGGER.warning("scan_hard() invoked - expect some Warnings")

    start_code = start_code or 0

    for code in range(start_code, 0x5000):
        await gateway._async_send_dto(
            CommandDTO(
                verb=RQ,
                addr1=HGI_DEV_ADDR.id,
                addr2=device_id,
                addr3=NON_DEV_ADDR.id,
                code=f"{code:04X}",
                payload="0000",
            ),
            priority=Priority.LOW,
        )


@script_decorator
async def script_scan_fan(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Probe an HVAC/Ventilator targeted device with standard parameters.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    """
    _LOGGER.warning("scan_fan() invoked - expect a lot of nonsense")

    from ramses_rf.protocol.ramses import _DEV_KLASSES_HVAC

    OUT_CODES = (
        Code._0016,
        Code._1470,
    )

    OLD_CODES = dict.fromkeys(
        c for k in _DEV_KLASSES_HVAC.values() for c in k if c not in OUT_CODES
    )
    for code in OLD_CODES:
        _send_probe_dto(
            gateway,
            CommandDTO(
                verb=RQ,
                addr1=HGI_DEV_ADDR.id,
                addr2=device_id,
                addr3=NON_DEV_ADDR.id,
                code=code,
                payload="00",
            ),
        )

    NEW_CODES = (
        Code._0150,
        Code._042F,
        Code._1030,
        Code._10D0,
        Code._10E1,
        Code._2210,
        Code._22B0,
        Code._22E0,
        Code._22E5,
        Code._22E9,
        Code._22F1,
        Code._22F2,
        Code._22F3,
        Code._22F4,
        Code._22F7,
        Code._22F8,
        Code._2400,
        Code._2410,
        Code._2420,
        Code._313E,
        Code._3221,
        Code._3222,
    )

    for code in NEW_CODES:
        if code not in OLD_CODES and code not in OUT_CODES:
            _send_probe_dto(
                gateway,
                CommandDTO(
                    verb=RQ,
                    addr1=HGI_DEV_ADDR.id,
                    addr2=device_id,
                    addr3=NON_DEV_ADDR.id,
                    code=code,
                    payload="00",
                ),
            )


@script_decorator
async def script_scan_otb(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Probe an OpenTherm Bridge targeted device across known data ID tables.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    """
    _LOGGER.warning("script_scan_otb_full invoked - expect a lot of nonsense")

    for msg_id in OPENTHERM_DATA_IDS:
        intent = Intent(
            src=HGI_DEV_ADDR,
            dst=Address(device_id),
            action=Action.GET_OPENTHERM_DATA,
            data={SZ_MESSAGE_ID: msg_id},
        )
        gateway.dispatcher.send_background(intent)


@script_decorator
async def script_scan_otb_hard(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Probe an OpenTherm Bridge target iteratively across numeric data ID space.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    """
    _LOGGER.warning("script_scan_otb_hard invoked - expect a lot of nonsense")

    for msg_id in range(0x80):
        intent = Intent(
            src=HGI_DEV_ADDR,
            dst=Address(device_id),
            action=Action.GET_OPENTHERM_DATA,
            data={SZ_MESSAGE_ID: msg_id},
        )
        gateway.dispatcher.send_background(intent, priority=Priority.LOW)


@script_decorator
async def script_scan_otb_map(gateway: Gateway, device_id: DeviceIdT) -> None:
    """Execute mapping verifications between native RAMSES codes and OpenTherm properties.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    """
    _LOGGER.warning("script_scan_otb_map invoked - expect a lot of nonsense")

    RAMSES_TO_OPENTHERM = {
        Code._22D9: "01",  # boiler setpoint         / ControlSetpoint
        Code._3EF1: "11",  # rel. modulation level   / RelativeModulationLevel
        Code._1300: "12",  # cv water pressure       / CHWaterPressure
        Code._12F0: "13",  # dhw_flow_rate           / DHWFlowRate
        Code._3200: "19",  # boiler output temp      / BoilerWaterTemperature
        Code._1260: "1A",  # dhw temp                / DHWTemperature
        Code._1290: "1B",  # outdoor temp            / OutsideTemperature
        Code._3210: "1C",  # boiler return temp      / ReturnWaterTemperature
        Code._10A0: "38",  # dhw params[SZ_SETPOINT] / DHWSetpoint
        Code._1081: "39",  # max ch setpoint         / MaxCHWaterSetpoint
    }

    for code, msg_id in RAMSES_TO_OPENTHERM.items():
        _send_probe_dto(
            gateway,
            CommandDTO(
                verb=RQ,
                addr1=HGI_DEV_ADDR.id,
                addr2=device_id,
                addr3=NON_DEV_ADDR.id,
                code=code,
                payload="00",
            ),
            priority=Priority.LOW,
        )
        intent = Intent(
            src=HGI_DEV_ADDR,
            dst=Address(device_id),
            action=Action.GET_OPENTHERM_DATA,
            data={SZ_MESSAGE_ID: msg_id},
        )
        gateway.dispatcher.send_background(intent, priority=Priority.LOW)


@script_decorator
async def script_scan_otb_ramses(
    gateway: Gateway, device_id: DeviceIdT
) -> None:
    """Probe an OpenTherm bridge exclusively for native RAMSES codes.

    :param gateway: The gateway instance.
    :param device_id: The device ID to probe.
    """
    _LOGGER.warning(
        "script_scan_otb_ramses invoked - expect a lot of nonsense"
    )

    _CODES = (
        Code._042F,
        Code._10E0,  # device_info
        Code._10E1,  # device_id
        Code._1FD0,
        Code._2400,
        Code._2401,
        Code._2410,
        Code._2420,
        Code._1300,  # cv water pressure      / CHWaterPressure
        Code._1081,  # max ch setpoint        / MaxCHWaterSetpoint
        Code._10A0,  # dhw params[SZ_SETPOINT] / DHWSetpoint
        Code._22D9,  # boiler setpoint        / ControlSetpoint
        Code._1260,  # dhw temp               / DHWTemperature
        Code._1290,  # outdoor temp           / OutsideTemperature
        Code._3200,  # boiler output temp     / BoilerWaterTemperature
        Code._3210,  # boiler return temp     / BoilerWaterTemperature
        Code._0150,
        Code._12F0,  # dhw flow rate          / DHWFlowRate
        Code._1098,
        Code._10B0,
        Code._3221,
        Code._3223,
        Code._3EF0,  # rel. modulation level  / RelativeModulationLevel (also, below)
        Code._3EF1,  # rel. modulation level  / RelativeModulationLevel
    )

    for code in _CODES:
        _send_probe_dto(
            gateway,
            CommandDTO(
                verb=RQ,
                addr1=HGI_DEV_ADDR.id,
                addr2=device_id,
                addr3=NON_DEV_ADDR.id,
                code=code,
                payload="00",
            ),
            priority=Priority.LOW,
        )


SCRIPTS = {
    k[7:]: v
    for k, v in locals().items()
    if callable(v) and k.startswith("script_")
}
