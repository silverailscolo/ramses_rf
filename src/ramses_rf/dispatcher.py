#!/usr/bin/env python3
"""RAMSES RF - Decode/process a message (payload into JSON)."""

# TODO:
# - fix dispatching - what devices (some are Addr) are sent packets, esp. 1FC9s

from __future__ import annotations

import contextlib
import dataclasses
import logging
import uuid
from datetime import timedelta as td
from typing import TYPE_CHECKING, Any, Final

from . import exceptions as exc, quirks
from .const import (
    I_,
    RQ,
    SZ_ACTIVE,
    SZ_AIR_QUALITY,
    SZ_AIR_QUALITY_BASIS,
    SZ_BYPASS_MODE,
    SZ_BYPASS_POSITION,
    SZ_BYPASS_STATE,
    SZ_CO2_LEVEL,
    SZ_DATETIME,
    SZ_DIFFERENTIAL,
    SZ_EXHAUST_FAN_SPEED,
    SZ_EXHAUST_FLOW,
    SZ_EXHAUST_TEMP,
    SZ_FAN_INFO,
    SZ_FAN_MODE,
    SZ_FAN_RATE,
    SZ_FILTER_DIRTY,
    SZ_FROST_CYCLE,
    SZ_HAS_FAULT,
    SZ_HEAT_DEMAND,
    SZ_INDOOR_HUMIDITY,
    SZ_INDOOR_TEMP,
    SZ_LANGUAGE,
    SZ_MINUTES,
    SZ_MODE,
    SZ_OUTDOOR_HUMIDITY,
    SZ_OUTDOOR_TEMP,
    SZ_OVERRUN,
    SZ_POST_HEAT,
    SZ_PRE_HEAT,
    SZ_PRESENCE_DETECTED,
    SZ_RELAY_DEMAND,
    SZ_REMAINING_DAYS,
    SZ_REMAINING_MINS,
    SZ_REMAINING_PERCENT,
    SZ_REQ_REASON,
    SZ_REQ_SPEED,
    SZ_SETPOINT,
    SZ_SPEED_CAPABILITIES,
    SZ_SUPPLY_FAN_SPEED,
    SZ_SUPPLY_FLOW,
    SZ_SUPPLY_TEMP,
    SZ_SYSTEM_MODE,
    SZ_TEMPERATURE,
    SZ_UNTIL,
    SZ_ZONE_MASK,
    ZON_ROLE_MAP,
    Code,
    DevType,
)
from .devices.hvac_ventilators import HvacVentilator
from .eavesdropper import EavesdropEngine
from .messages import Message
from .models import StateUpdatedEvent, SystemState
from .schemas import SZ_CLASS
from .systems.faultlog import FaultLogEntry
from .systems.zones import DhwZone
from .validators import instantiate_devices, validate_addresses, validate_slugs

if TYPE_CHECKING:
    from .gateway import Gateway

#
# NOTE: All debug flags should be False for deployment to end-users
_DBG_FORCE_LOG_MESSAGES: Final[bool] = False  # useful for dev/test
_DBG_INCREASE_LOG_LEVELS: Final[bool] = (
    False  # set True for developer-friendly log spam
)

_LOGGER = logging.getLogger(__name__)


__all__ = [
    "detect_array_fragment",
    "instantiate_devices",
    "process_msg",
    "validate_addresses",
    "validate_slugs",
]


MSG_FORMAT_18 = "|| {:18s} | {:18s} | {:2s} | {:16s} | {:^4s} || {}"

_TD_SECONDS_003 = td(seconds=3)


def _log_message(gwy: Gateway, msg: Message) -> None:
    """Log msg according to src, code, log.debug setting.

    :param gwy: The gateway handling the message.
    :type gwy: Gateway
    :param msg: the Message being processed.
    :type msg: Message
    """
    if _DBG_FORCE_LOG_MESSAGES:
        _LOGGER.warning(msg)
    elif msg.src != gwy.hgi or (msg.code != Code._PUZZ and msg.verb != RQ):
        _LOGGER.info(msg)
    elif msg.src != gwy.hgi or msg.verb != RQ:
        _LOGGER.info(msg)
    elif _LOGGER.getEffectiveLevel() == logging.DEBUG:
        _LOGGER.info(msg)


# DHW opcodes that carry no zone_idx/domain_id and need special routing.
_DHW_OPCODES: Final[frozenset[Code]] = frozenset({Code._1260, Code._10A0, Code._1F41})


def _get_dhw_zone_from_msg(msg: Message, src_dev: Any) -> DhwZone | None:
    """Resolve the DhwZone that should ingest a DHW opcode (1260/10A0/1F41).

    These payloads carry no ``zone_idx``/``domain_id``, so the standard
    routing in ``_resolve_logical_targets`` (and the equivalent block in
    ``StateProjector.process_message_state``) misses the DhwZone.

    ``1260`` is sent by the DhwSensor (or relayed by the Controller as an
    RP); ``10A0``/``1F41`` are sent by the Controller.  The
    appliance_control (OTB) also emits ``10A0``/``1260`` with different
    semantics (CH setpoint / null temp) and is excluded to avoid
    clobbering the DHW read-models.

    See: https://github.com/ramses-rf/ramses_cc/issues/843

    :param msg: The inbound message.
    :type msg: Message
    :param src_dev: The source device (DhwSensor or Controller).
    :return: The DhwZone to route to, or ``None`` if the message is not
        a DHW opcode or the source is not a DHW sender.
    :rtype: DhwZone | None
    """
    if msg.code not in _DHW_OPCODES or src_dev is None:
        return None

    src_slug = getattr(src_dev, "_SLUG", "")
    if msg.code == Code._1260:
        is_dhw_src = src_slug in ("DHW", "CTL")
    else:  # 10A0 / 1F41 are owned by the Controller
        is_dhw_src = src_slug == "CTL"

    if not is_dhw_src:
        return None

    tcs = getattr(src_dev, "tcs", None)
    if tcs is None:
        return None

    return getattr(tcs, "dhw", None)


def _resolve_logical_targets(
    gwy: Gateway, msg: Message, p: dict[str, Any]
) -> list[Any]:
    """Resolve all logical software twins that should ingest this payload."""
    targets = []
    src_dev = gwy.device_registry.device_by_id.get(msg.src.id)
    dst_dev = gwy.device_registry.device_by_id.get(msg.dst.id)
    tcs = getattr(src_dev, "tcs", None) if src_dev else None
    tcs = tcs or getattr(gwy, "tcs", None)
    if tcs is None and (registry := getattr(gwy, "device_registry", None)):
        for dev in registry.device_by_id.values():
            if str(dev.id).startswith("01:"):
                tcs = getattr(dev, "tcs", None) or dev
                break

    # 1. Fault logs strictly target the TCS (if it exists) or the source device
    if msg.code == Code._0418:
        if tcs:
            targets.append(getattr(tcs, "faultlog", src_dev))
        elif src_dev:
            targets.append(src_dev)
        return targets

    # 2. Hardware twin (Sender) always gets the update UNLESS it's a Controller/UFC
    # actively broadcasting an array of children's states (e.g., a 30C9 sync).
    src_type = getattr(src_dev, "type", None)
    has_arr = getattr(msg, "_has_array", False)
    if src_type not in ("01", "02") or not has_arr:
        if src_dev:
            targets.append(src_dev)

    # 3. Hardware twin (Destination) gets the update.
    # Legacy routes packets to the destination device's cache. To maintain
    # strict parity, we mirror this.
    # HVAC packets (e.g. 22F1 fan_mode from REM→FAN) target the destination
    # device's hvac_state directly, so we also accept devices that have
    # hvac_state even if they lack apply_state_update.
    if msg.dst.id != msg.src.id and getattr(msg.dst, "id", "") != "63:262142":
        if (
            dst_dev
            and (
                getattr(dst_dev, "apply_state_update", None) is not None
                or getattr(dst_dev, "hvac_state", None) is not None
            )
            and dst_dev not in targets
        ):
            targets.append(dst_dev)

    # 4. Virtual twins (Zones) get updates if explicitly addressed by idx.
    if "zone_idx" in p and tcs:
        if zone := tcs.zone_by_idx.get(p["zone_idx"]):
            if zone not in targets:
                targets.append(zone)

    # 5. Domain twins (TCS, DHW) get updates.
    if "domain_id" in p and tcs:
        domain_id = p["domain_id"]
        if domain_id == "FC" and tcs not in targets:
            targets.append(tcs)
        elif domain_id in ("FA", "F9") and getattr(tcs, "dhw", None) is not None:
            if tcs.dhw not in targets:
                targets.append(tcs.dhw)

    # 6. System-level opcodes (2E04/0100/313F) target the TCS directly.
    #    These packets have no domain_id/zone_idx, so steps 4/5 miss them.
    if msg.code in (Code._2E04, Code._0100, Code._313F) and tcs and tcs not in targets:
        targets.append(tcs)

    # 7. DHW opcodes (1260/10A0/1F41) carry no domain_id/zone_idx, so steps
    #    4/5 miss the DhwZone.  Route them via the shared helper.
    #    See: https://github.com/ramses-rf/ramses_cc/issues/843
    dhw = _get_dhw_zone_from_msg(msg, src_dev)
    if dhw is not None and dhw not in targets:
        targets.append(dhw)

    return targets


def _update_temperature_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate temperature data into a frozen StateUpdatedEvent."""
    temp_state = getattr(target, "temp_state", None)
    if temp_state is None or not dataclasses.is_dataclass(temp_state):
        return

    updates: dict[str, Any] = {}

    if SZ_TEMPERATURE in p:
        # Legacy Parity: Physical sensors only track their own local sensor readings.
        # We must ignore Zone temperature syncs sent TO them by the Controller.
        # Keep same as src/ramses_rf/pipeline/ingestion.py#_update_temperature_state
        target_id = getattr(target, "id", str(target))
        src_id = getattr(msg.src, "id", str(msg.src))

        if getattr(target, "_SLUG", "") in ("TRV", "THM") and src_id != target_id:
            pass
        else:
            updates[SZ_TEMPERATURE] = p[SZ_TEMPERATURE]

    if "setpoint" in p:
        updates[SZ_SETPOINT] = p[SZ_SETPOINT]

    if not updates:
        return

    new_state = dataclasses.replace(target.temp_state, **updates)
    event = StateUpdatedEvent(
        entity_id=getattr(target, "id", "unknown"),
        state=new_state,
        correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
        causation_id=getattr(msg, "message_id", uuid.uuid4()),
    )
    target.apply_state_update(event)


def _update_demand_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate demand data into a frozen StateUpdatedEvent."""
    demand_state = getattr(target, "demand_state", None)
    if demand_state is None or not dataclasses.is_dataclass(demand_state):
        return

    updates: dict[str, Any] = {}
    if SZ_HEAT_DEMAND in p:
        updates[SZ_HEAT_DEMAND] = p[SZ_HEAT_DEMAND]
    if SZ_RELAY_DEMAND in p:
        updates[SZ_RELAY_DEMAND] = p[SZ_RELAY_DEMAND]
        updates["relay_active"] = float(p[SZ_RELAY_DEMAND]) > 0.0
    if msg.code == Code._0009 and "failsafe_enabled" in p:
        updates["relay_failsafe"] = p["failsafe_enabled"]

    if not updates:
        return

    new_state = dataclasses.replace(target.demand_state, **updates)
    event = StateUpdatedEvent(
        entity_id=getattr(target, "id", "unknown"),
        state=new_state,
        correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
        causation_id=getattr(msg, "message_id", uuid.uuid4()),
    )
    target.apply_state_update(event)


def _update_faultlog_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate 0418 fault log data into a frozen StateUpdatedEvent.

    This handles the immutable tuple appending tracking required by the
    CQRS FaultLogState read-model container.

    :param target: The target entity software twin to update.
    :type target: Any
    :param p: The parsed message payload dictionary.
    :type p: dict[str, Any]
    :param msg: The immutable Message L7 envelope.
    :type msg: Message
    :return: None
    :rtype: None
    """
    if msg.code != Code._0418 or getattr(target, "state", None) is None:
        return
    if type(target.state).__name__ != "FaultLogState":
        return

    # Guard: Ensure the entry index exists in the parsed payload
    if "log_idx" not in p:
        return

    try:
        entry = FaultLogEntry.from_msg(msg)

        # Append to the immutable tuple, safely removing stale matching timestamps
        current_entries = getattr(target.state, "entries", ())
        filtered = [e for e in current_entries if e.timestamp != entry.timestamp]
        new_entries = tuple(filtered) + (entry,)

        new_state = dataclasses.replace(target.state, entries=new_entries)

        event = StateUpdatedEvent(
            entity_id=getattr(target, "id", "unknown"),
            state=new_state,
            correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
            causation_id=getattr(msg, "message_id", uuid.uuid4()),
        )
        target.apply_state_update(event)
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        _LOGGER.warning("Failed to process fault log entry from msg %s: %s", msg, err)


def _update_system_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate system configuration opcodes into SystemState.

    Handles 2E04 (system_mode), 0100 (language), and 313F (datetime).

    :param target: The target entity (TCS/Evohome) to update.
    :param p: The parsed message payload dictionary.
    :param msg: The immutable Message L7 envelope.
    """
    system_state = getattr(target, "system_state", None)
    if system_state is None or not dataclasses.is_dataclass(system_state):
        return

    updates: dict[str, Any] = {}
    if msg.code == Code._0100:
        if SZ_LANGUAGE in p:
            updates[SZ_LANGUAGE] = p[SZ_LANGUAGE]
    elif msg.code == Code._2E04:
        if SZ_SYSTEM_MODE in p:
            updates[SZ_SYSTEM_MODE] = p[SZ_SYSTEM_MODE]
        if SZ_UNTIL in p:
            updates[SZ_UNTIL] = p[SZ_UNTIL]
    elif msg.code == Code._313F:
        if SZ_DATETIME in p:
            updates[SZ_DATETIME] = p[SZ_DATETIME]
    else:
        return

    if not updates:
        return

    dtm = getattr(msg, "dtm", getattr(msg, "timestamp", None))
    if dtm:
        updates["last_updated"] = dtm

    current_state = target.system_state or SystemState()
    new_state = dataclasses.replace(current_state, **updates)
    target.system_state = new_state

    event = StateUpdatedEvent(
        entity_id=getattr(target, "id", "unknown"),
        state=new_state,
        correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
        causation_id=getattr(msg, "message_id", uuid.uuid4()),
    )
    if hasattr(target, "apply_state_update"):
        target.apply_state_update(event)


def _update_hvac_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate HVAC ventilation payloads into a frozen HvacState.

    Handles 31D9/31DA/22F1/22F3/10D0/12A0/1298 and related opcodes,
    porting the logic from ``pipeline/ingestion.py`` into the dispatcher's
    CQRS ingestion engine.  See issue #649 / #547.
    """
    if getattr(target, "_SLUG", "") in ("CTL", "BDR", "TRV", "OTB", "UFC", "DHW"):
        return

    hvac_state = getattr(target, "hvac_state", None)
    if hvac_state is None or not dataclasses.is_dataclass(hvac_state):
        return

    p = quirks.apply_hvac_quirks(p, target.hvac_state, msg.code)

    fields = [
        SZ_CO2_LEVEL,
        SZ_AIR_QUALITY,
        SZ_AIR_QUALITY_BASIS,
        SZ_BYPASS_MODE,
        SZ_BYPASS_POSITION,
        SZ_BYPASS_STATE,
        SZ_EXHAUST_FAN_SPEED,
        SZ_EXHAUST_FLOW,
        SZ_EXHAUST_TEMP,
        SZ_FAN_RATE,
        SZ_FAN_MODE,
        SZ_FAN_INFO,
        SZ_INDOOR_HUMIDITY,
        SZ_INDOOR_TEMP,
        SZ_OUTDOOR_HUMIDITY,
        SZ_OUTDOOR_TEMP,
        SZ_POST_HEAT,
        SZ_PRE_HEAT,
        SZ_PRESENCE_DETECTED,
        SZ_REMAINING_MINS,
        SZ_SPEED_CAPABILITIES,
        SZ_SUPPLY_FAN_SPEED,
        SZ_SUPPLY_FLOW,
        SZ_SUPPLY_TEMP,
        SZ_TEMPERATURE,
        SZ_FILTER_DIRTY,
        SZ_FROST_CYCLE,
        SZ_HAS_FAULT,
        "dewpoint_temp",
    ]

    # Filter out null-marker values that 31DA/31D9 snapshots emit for
    # sensors the device does not have.  Without this, every polling cycle
    # (~10 min) overwrites good telemetry from 22F1/12A0/22F7 with null
    # markers, causing sensors to bounce to None/FF/0.  See issue #742.
    _NULL_HUMIDITY_FIELDS = frozenset({SZ_INDOOR_HUMIDITY, SZ_OUTDOOR_HUMIDITY})

    updates: dict[str, Any] = {}
    for f in fields:
        if f not in p:
            continue
        val = p[f]
        # None = "not implemented" (e.g. EF in bypass_position)
        if val is None:
            continue
        # Raw hex (e.g. "FF", "04") = non-semantic fan_mode from 31D9
        # long-payload devices; the quirk normalises these to None, but
        # filter here as belt-and-suspenders.  See ramses_cc issue 723.
        if f == SZ_FAN_MODE and isinstance(val, str) and len(val) == 2:
            try:
                int(val, 16)
                continue
            except ValueError:
                pass
        # 0.0 for humidity = "no sensor" (00 parses as 0%, physically impossible)
        if f in _NULL_HUMIDITY_FIELDS and val == 0:
            continue
        updates[f] = val

    # Handle non-standard names passed by the semantic parsers
    if SZ_REMAINING_DAYS in p and p[SZ_REMAINING_DAYS] is not None:
        updates["filter_remaining_days"] = p[SZ_REMAINING_DAYS]
    if SZ_REMAINING_PERCENT in p and p[SZ_REMAINING_PERCENT] is not None:
        updates["filter_remaining_percent"] = p[SZ_REMAINING_PERCENT]
    if SZ_MINUTES in p and msg.code == Code._22F3 and p[SZ_MINUTES] is not None:
        updates["boost_timer_mins"] = p[SZ_MINUTES]
    if SZ_REQ_SPEED in p and p[SZ_REQ_SPEED] is not None:
        updates["request_fan_speed"] = p[SZ_REQ_SPEED]
    if SZ_REQ_REASON in p and p[SZ_REQ_REASON] is not None:
        updates["request_reason"] = p[SZ_REQ_REASON]

    if not updates:
        return

    new_state = dataclasses.replace(target.hvac_state, **updates)
    target.hvac_state = new_state

    event = StateUpdatedEvent(
        entity_id=getattr(target, "id", "unknown"),
        state=new_state,
        correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
        causation_id=getattr(msg, "message_id", uuid.uuid4()),
    )
    if hasattr(target, "apply_state_update"):
        target.apply_state_update(event)


def _update_dhw_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Translate DHW opcodes (10A0/1260/1F41) into the frozen DhwState.

    Mirrors ``pipeline.ingestion.StateProjector._update_dhw_state`` so that
    the legacy dispatcher hydrates the DhwZone's ``dhw_state`` read-model
    (setpoint/overrun/differential from 10A0, mode/active/until from 1F41)
    in addition to ``temp_state``.
    """
    if not isinstance(target, DhwZone):
        return
    dhw_state = getattr(target, "dhw_state", None)
    if dhw_state is None or not dataclasses.is_dataclass(dhw_state):
        return

    updates: dict[str, Any] = {}
    if msg.code == Code._10A0:
        if SZ_SETPOINT in p:
            updates[SZ_SETPOINT] = p[SZ_SETPOINT]
        if SZ_OVERRUN in p:
            updates[SZ_OVERRUN] = p[SZ_OVERRUN]
        if SZ_DIFFERENTIAL in p:
            updates[SZ_DIFFERENTIAL] = p[SZ_DIFFERENTIAL]
    elif msg.code == Code._1F41:
        if SZ_MODE in p:
            updates[SZ_MODE] = p[SZ_MODE]
        if SZ_ACTIVE in p:
            updates[SZ_ACTIVE] = p[SZ_ACTIVE]
        if SZ_UNTIL in p:
            updates[SZ_UNTIL] = p[SZ_UNTIL]

    if not updates:
        return

    new_state = dataclasses.replace(target.dhw_state, **updates)
    target.dhw_state = new_state

    event = StateUpdatedEvent(
        entity_id=target.id,
        state=new_state,
        correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
        causation_id=getattr(msg, "message_id", uuid.uuid4()),
    )
    target.apply_state_update(event)


def _route_2411_to_fan(gwy: Gateway, msg: Message) -> None:
    """Route a 2411 parameter message to its HvacVentilator aggregate root.

    Phase 2.95 removed the ``HvacVentilator._handle_msg`` override that
    previously invoked ``_handle_2411_message`` (which sets
    ``_supports_2411`` and stores the parameter) and
    ``_handle_initialized_callback`` (which fires the ramses_cc entity
    creation callback).  Without this routing, FAN devices never advertise
    2411 support, so ramses_cc never creates the ~15 parameter ``number``
    entities (comfort temperature, etc.) — see ramses_cc issue 851.

    This re-wires the 2411 handling into the CQRS ingestion pipeline (where
    issue 639 wants domain logic to live) instead of restoring the leaky
    ``_handle_msg`` override.  ``_handle_2411_message`` reads
    ``msg.payload`` directly, so it is invoked once per FAN target, outside
    the per-payload loop in ``_cqrs_ingestion_engine``.
    """
    if getattr(msg, "verb", "") == "RQ":
        return

    registry = getattr(gwy, "device_registry", None)
    if registry is None:
        return

    candidates: list[Any] = []
    if msg.src is not None:
        src_dev = registry.device_by_id.get(msg.src.id)
        if src_dev is not None:
            candidates.append(src_dev)
    if msg.dst is not None:
        dst_dev = registry.device_by_id.get(msg.dst.id)
        if dst_dev is not None and dst_dev not in candidates:
            candidates.append(dst_dev)

    for dev in candidates:
        if not isinstance(dev, HvacVentilator):
            continue
        try:
            dev._handle_2411_message(msg)
            dev._handle_initialized_callback()
        except (exc.RamsesException, AttributeError, TypeError, ValueError) as err:
            _LOGGER.error(
                "Failed to route 2411 message to ventilator %s: %s",
                dev.id,
                err,
            )


def _update_schedule_state(target: Any, p: dict[str, Any], msg: Message) -> None:
    """Route 0006 version and 0404 fragment packets to Schedule read-models."""
    if msg.code not in (Code._0006, Code._0404):
        return

    sched = getattr(target, "schedule", None)
    if sched is not None and hasattr(sched, "process_schedule_msg"):
        sched.process_schedule_msg(msg)


async def _update_topology_schema_state(
    gwy: Gateway, p: dict[str, Any], msg: Message
) -> None:
    """Ingest topology and telemetry payloads into models."""
    registry = getattr(gwy, "device_registry", None)
    tcs = None
    if registry:
        if getattr(msg.src, "type", None) in ("01", DevType.CTL):
            ctl_id = str(msg.src.id)
            if ctl_dev := registry.device_by_id.get(ctl_id):
                tcs = getattr(ctl_dev, "tcs", None)
        elif getattr(msg.dst, "type", None) in ("01", DevType.CTL):
            ctl_id = str(msg.dst.id)
            if ctl_dev := registry.device_by_id.get(ctl_id):
                tcs = getattr(ctl_dev, "tcs", None)
        else:
            if (devices := p.get("devices")) and isinstance(devices, list):
                for d in devices:
                    if getattr(d, "type", str(d)[:2]) == "01":
                        ctl_id = str(d)
                        if ctl_dev := registry.device_by_id.get(ctl_id):
                            tcs = getattr(ctl_dev, "tcs", None)
                        break

            if tcs is None and hasattr(msg.src, "id"):
                if src_dev := registry.device_by_id.get(str(msg.src.id)):
                    tcs = getattr(src_dev, "tcs", None)
            if tcs is None and hasattr(msg.dst, "id"):
                if dst_dev := registry.device_by_id.get(str(msg.dst.id)):
                    tcs = getattr(dst_dev, "tcs", None)

    if tcs is None and registry:
        controllers = [
            d
            for d in list(registry.device_by_id.values())
            if (getattr(d, "_SLUG", "") == "CTL" or getattr(d, "type", None) == "01")
            and hasattr(d, "tcs")
            and d.tcs is not None
        ]
        if len(controllers) == 1:
            tcs = controllers[0].tcs

    # 1. Code 0005: System Zone Structure Discovery & Initialization
    if msg.code == Code._0005 and getattr(msg.src, "type", None) == "01":
        if tcs and hasattr(tcs, "get_htg_zone"):
            z_type = p.get("zone_type")
            if isinstance(z_type, str) and z_type in ZON_ROLE_MAP.HEAT_ZONES:
                schema: dict[str, Any] = {"class": ZON_ROLE_MAP[z_type]}
                if zone_mask := p.get("zone_mask"):
                    for idx, active in enumerate(zone_mask):
                        if active:
                            with contextlib.suppress(
                                exc.DeviceNotFoundError, exc.SchemaInconsistentError
                            ):
                                z_str = f"{idx:02X}"
                                ez = getattr(tcs, "zone_by_idx", {}).get(z_str)
                                if (
                                    ez is not None
                                    and getattr(ez, "_heating_type", None) is not None
                                ):
                                    tcs.get_htg_zone(z_str)
                                else:
                                    tcs.get_htg_zone(z_str, **schema)
                elif (zone_idx := (p.get("zone_idx") or p.get("child_id"))) is not None:
                    with contextlib.suppress(
                        exc.DeviceNotFoundError, exc.SchemaInconsistentError
                    ):
                        z_str = str(zone_idx)
                        ez = getattr(tcs, "zone_by_idx", {}).get(z_str)
                        if (
                            ez is not None
                            and getattr(ez, "_heating_type", None) is not None
                        ):
                            tcs.get_htg_zone(z_str)
                        else:
                            tcs.get_htg_zone(z_str, **schema)

    # 2. Code 000C: Device Role Bindings, Zone Types & UFH Circuit Mappings
    elif msg.code == Code._000C:
        zone_idx = p.get("zone_idx")
        domain_id = p.get("domain_id")
        devices = p.get("devices", [])
        if "device_id" in p and not devices:
            devices = [p["device_id"]]

        zone_type = p.get("zone_type")
        ufh_idx = p.get("ufh_idx") or p.get("circuit_idx") or p.get("cct_idx")

        # 1. Instantiate any 02: UFH Controller devices and link as children of TCS
        ufc_devs: list[Any] = []
        if registry and tcs:
            for d_id in devices:
                if getattr(d_id, "type", str(d_id)[:2]) in ("02", DevType.UFC):
                    with contextlib.suppress(exc.DeviceNotFoundError):
                        ufc = registry.get_device(str(d_id), parent=tcs)
                        if ufc not in ufc_devs:
                            ufc_devs.append(ufc)

        if not ufc_devs and registry:
            if getattr(msg.src, "type", None) in ("02", DevType.UFC):
                with contextlib.suppress(exc.DeviceNotFoundError):
                    ufc_devs.append(registry.get_device(str(msg.src.id)))
            elif getattr(msg.dst, "type", None) in ("02", DevType.UFC):
                with contextlib.suppress(exc.DeviceNotFoundError):
                    ufc_devs.append(registry.get_device(str(msg.dst.id)))

        if not ufc_devs and tcs:
            ufc_devs = [
                d
                for d in getattr(tcs, "childs", [])
                if getattr(d, "_SLUG", "") == "UFC" or getattr(d, "type", None) == "02"
            ]

        # Route UFH circuit mappings to UFH controllers
        if ufc_devs and ufh_idx is not None:
            ufh_z_str: str | None = str(zone_idx) if zone_idx is not None else None
            ufh_str = (
                f"{int(str(ufh_idx), 16):02X}"
                if isinstance(ufh_idx, (int, str)) and str(ufh_idx).isalnum()
                else str(ufh_idx)
            )
            for ufc in ufc_devs:
                if hasattr(ufc, "circuit_by_id"):
                    ufc.circuit_by_id[ufh_str] = {"zone_idx": ufh_z_str}

        # Map Zone Bindings & Classes
        if (
            zone_idx is not None
            and tcs
            and hasattr(tcs, "get_htg_zone")
            and getattr(msg.src, "type", None) not in ("02", DevType.UFC)
        ):
            _non_zone_prefixes = (
                f"{DevType.CTL}:",
                f"{DevType.UFC}:",
                f"{DevType.HGI}:",
                "7F:",
            )
            valid_devs = [
                d
                for d in devices
                if not str(d).startswith(_non_zone_prefixes) and str(d) != "7FFFFFFF"
            ]
            zone_cls: str | None = None
            if valid_devs and zone_type is not None and zone_type in ZON_ROLE_MAP:
                candidate_cls = ZON_ROLE_MAP[zone_type]
                if candidate_cls in (
                    "radiator_valve",
                    "underfloor_heating",
                    "zone_valve",
                    "electric_zone",
                    "mix_valve",
                ):
                    zone_cls = candidate_cls

            existing_zone = tcs.zone_by_idx.get(str(zone_idx))
            if (
                existing_zone
                and getattr(existing_zone, "_heating_type", None) is not None
            ):
                schema = {}
            else:
                schema = {"class": zone_cls} if zone_cls else {}

            zone = tcs.get_htg_zone(str(zone_idx), **schema)
            if zone and valid_devs:
                # If a TRV (04: device) is bound to the zone, ensure the zone class is radiator_valve
                has_trv = any(str(d).startswith(f"{DevType.TRV}:") for d in valid_devs)
                if has_trv and getattr(zone, "_heating_type", None) != "radiator_valve":
                    with contextlib.suppress(exc.RamsesException):
                        zone._update_schema(**{SZ_CLASS: "radiator_valve"})

            if zone and valid_devs and registry:
                dev_role = p.get("device_role")
                z_type_code = p.get("zone_type")
                is_sen = dev_role in ("zone_sensor", "dhw_sensor") or z_type_code in (
                    "04",
                    "07",
                    "0D",
                )
                _non_actuator_prefixes = (
                    f"{DevType.CTL}:",
                    f"{DevType.UFC}:",
                    f"{DevType.HGI}:",
                    "63:",
                )
                for d_id in valid_devs:
                    d_str = str(d_id)
                    if d_str.startswith(_non_actuator_prefixes):
                        continue
                    with contextlib.suppress(
                        exc.DeviceNotFoundError, exc.SchemaInconsistentError
                    ):
                        if is_sen:
                            registry.device_by_id.get(d_str)
                        else:
                            registry.device_by_id.get(d_str)

        # Map Domain Bindings (Appliance Control / DHW)
        elif domain_id == "FC" and devices and tcs and registry:
            for d_id in devices:
                with contextlib.suppress(
                    exc.DeviceNotFoundError, exc.SchemaInconsistentError
                ):
                    registry.device_by_id.get(str(d_id))

        elif (
            domain_id in ("FA", "F9")
            and devices
            and tcs
            and hasattr(tcs, "get_dhw_zone")
        ):
            dhw = tcs.get_dhw_zone()
            if dhw and registry:
                for d_id in devices:
                    is_sen = (
                        getattr(d_id, "type", str(d_id)[:2]) == "07"
                        or p.get("device_role") == "dhw_sensor"
                    )
                    with contextlib.suppress(
                        exc.DeviceNotFoundError, exc.SchemaInconsistentError
                    ):
                        registry.get_device(
                            str(d_id), parent=dhw, child_id=domain_id, is_sensor=is_sen
                        )

    # 3. Code 0004: Zone Naming & Creation
    elif msg.code == Code._0004 and tcs:
        zone_idx = p.get("zone_idx")
        name = p.get("name")
        if zone_idx is not None and name:
            zone = tcs.get_htg_zone(str(zone_idx))
            if zone:
                zone.zone_state = dataclasses.replace(zone.zone_state, name=name)

    # Code 0005: System Zones (Zone Mask)
    elif msg.code == Code._0005 and tcs:
        for idx, flag in enumerate(p.get(SZ_ZONE_MASK, [])):
            if flag == 1:
                z_id = f"{idx:02X}"
                if z_id not in tcs.zone_by_idx:
                    tcs.get_htg_zone(z_id)

    # 4. Code 0204: Underfloor Heating (UFH) Controller Circuits
    elif msg.code == Code._0204:
        ufc_list: list[Any] = []
        if registry:
            if getattr(msg.src, "type", None) in ("02", DevType.UFC):
                with contextlib.suppress(exc.DeviceNotFoundError):
                    ufc_list.append(registry.get_device(str(msg.src.id)))
            elif getattr(msg.dst, "type", None) in ("02", DevType.UFC):
                with contextlib.suppress(exc.DeviceNotFoundError):
                    ufc_list.append(registry.get_device(str(msg.dst.id)))
        if not ufc_list and tcs and hasattr(tcs, "ufh_controllers"):
            ufc_list = list(getattr(tcs, "ufh_controllers", {}).values())

        cct_idx = p.get("circuit_idx") or p.get("cct_idx") or p.get("ufx_idx")
        z_idx = p.get("zone_idx")
        if cct_idx is not None and ufc_list:
            cct_str = (
                f"{int(str(cct_idx), 16):02X}"
                if isinstance(cct_idx, (int, str)) and str(cct_idx).isalnum()
                else str(cct_idx)
            )
            for ufc in ufc_list:
                if hasattr(ufc, "circuit_by_id"):
                    ufc.circuit_by_id[cct_str] = {
                        "zone_idx": str(z_idx) if z_idx is not None else None
                    }

    # 5. Code 000A: Zone Parameters & Configuration
    elif msg.code == Code._000A and tcs and hasattr(tcs, "get_htg_zone"):
        zone_idx = p.get("zone_idx")

    if getattr(gwy.config, "enable_eavesdrop", False):
        engine = getattr(gwy, "_eavesdrop_engine", None)
        if engine is None:
            engine = EavesdropEngine(gwy)
            with contextlib.suppress(AttributeError):
                gwy._eavesdrop_engine = engine
        await engine.process_eavesdrop(msg)


async def _cqrs_ingestion_engine(gwy: Gateway, msg: Message) -> None:
    """Parallel ingestion engine to populate immutable CQRS read-models.

    This acts as a Strangler Fig, intercepting decoded payloads and mapping
    them directly into the new `StateUpdatedEvent` structures.
    """
    # Notify candidate devices of _last_msg_dtm and all binding devices of rcvd_msg
    if registry := getattr(gwy, "device_registry", None):
        for dev in list(registry.device_by_id.values()):
            if dev.id in (getattr(msg.src, "id", None), getattr(msg.dst, "id", None)):
                if hasattr(dev, "_last_msg_dtm"):
                    dev._last_msg_dtm = msg.dtm
            if (bm := getattr(dev, "_binding_manager", None)) and getattr(
                bm, "is_binding", False
            ):
                bm.rcvd_msg(msg)

    if not isinstance(msg.payload, (dict, list)):
        return

    # 2411 parameter messages are handled by the FAN aggregate root directly
    # (they set _supports_2411 and fire the initialized callback).  This runs
    # before the per-payload loop because _handle_2411_message reads
    # msg.payload as a whole.  See ramses_cc issue 851.
    if msg.code == Code._2411:
        _route_2411_to_fan(gwy, msg)

    payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]
    with contextlib.suppress(exc.DeviceNotFoundError, exc.SchemaInconsistentError):
        for p in payloads:
            if isinstance(p, dict):
                await _update_topology_schema_state(gwy, p, msg)

    # Legacy Parity: Request packets (RQ) do not contain state update telemetry.
    if getattr(msg, "verb", "") == "RQ":
        return

    for p in payloads:
        if not isinstance(p, dict):
            continue
        targets = _resolve_logical_targets(gwy, msg, p)
        for target in targets:
            _update_system_state(target, p, msg)
            _update_hvac_state(target, p, msg)
            _update_dhw_state(target, p, msg)
            _update_temperature_state(target, p, msg)
            _update_demand_state(target, p, msg)
            _update_faultlog_state(target, p, msg)


async def process_msg(gwy: Gateway, msg: Message) -> None:
    """Decode the packet payload and route it through the message pipeline.

    This executor acts as a Chain of Responsibility, routing the message
    through sequential, mathematically isolated validation and dispatch stages.

    :param gwy: The gateway instance handling the routing.
    :type gwy: Gateway
    :param msg: The processed message to route.
    :type msg: Message
    """
    # All methods require msg with a valid payload, except instantiate_devices(),
    # which requires a valid payload only for 000C.
    try:
        if cm := getattr(gwy, "conversation_manager", None):
            cm.process_msg(msg)

        if not validate_addresses(gwy, msg):
            _log_message(gwy, msg)
            return

        if not instantiate_devices(gwy, msg):
            return

        if not validate_slugs(gwy, msg):
            _log_message(gwy, msg)
            return

        await _cqrs_ingestion_engine(gwy, msg)

    except (AssertionError, exc.RamsesException, NotImplementedError) as err:
        (_LOGGER.error if _DBG_INCREASE_LOG_LEVELS else _LOGGER.warning)(
            "%s < %s(%s)", msg, err.__class__.__name__, err
        )

    except (AttributeError, LookupError, TypeError, ValueError) as err:
        if getattr(gwy.config, "enforce_strict_handling", False):
            raise
        _LOGGER.warning("%s < %s(%s)", msg, err.__class__.__name__, err, exc_info=True)

    else:
        _log_message(gwy, msg)
        if gwy.message_store:
            gwy.message_store.add(msg)
            # why add it? enable for evohome


# TODO: this needs cleaning up (e.g. handle intervening packet)
def detect_array_fragment(this: Message, prev: Message) -> bool:  # _PayloadT
    """Return True if this pkt is the latter half of an array.

    :param this: The current message being evaluated.
    :type this: Message
    :param prev: The previously received message.
    :type prev: Message
    :return: True if the packet is part of a merged array, False otherwise.
    :rtype: bool
    """
    # This will work, even if the 2nd pkt._is_array == False as 1st == True
    # .I --- 01:158182 --:------ 01:158182 000A 048 001201F409C4011101F409C40...
    # .I --- 01:158182 --:------ 01:158182 000A 006 081001F409C4

    return bool(
        prev._has_array
        and this.code in (Code._000A, Code._22C9)  # TODO: not a complete list
        and this.code == prev.code
        and this.verb == prev.verb == I_
        and this.src == prev.src
        and this.dtm < prev.dtm + _TD_SECONDS_003
    )
