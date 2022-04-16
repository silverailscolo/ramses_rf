#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - The evohome-compatible system."""

# TODO: refactor packet routing (filter *before* routing)

import logging
from asyncio import Task
from datetime import datetime as dt
from datetime import timedelta as td
from symtable import Class
from threading import Lock
from types import SimpleNamespace
from typing import Optional

from .const import (
    SYS_MODE_MAP,
    SZ_DATETIME,
    SZ_DEVICE_ROLE,
    SZ_DEVICES,
    SZ_DOMAIN_ID,
    SZ_HEAT_DEMAND,
    SZ_LANGUAGE,
    SZ_SYSTEM_MODE,
    SZ_TEMPERATURE,
    SZ_ZONE_IDX,
    Discover,
    __dev_mode__,
)
from .devices import BdrSwitch, Device, OtbGateway, Temperature, UfhController
from .entity_base import Entity, class_by_attr, discover_decorator
from .helpers import shrink
from .protocol import (
    Address,
    Command,
    CorruptStateError,
    ExpiredCallbackError,
    Message,
    Priority,
)
from .protocol.transport import PacketProtocolPort
from .schema import (
    SCHEMA_DHW,
    SCHEMA_SYS,
    SCHEMA_ZON,
    SZ_APP_CNTRL,
    SZ_CLASS,
    SZ_CONTROLLER,
    SZ_DHW_SYSTEM,
    SZ_ORPHANS,
    SZ_SENSOR,
    SZ_TCS_SYSTEM,
    SZ_UFH_SYSTEM,
    SZ_ZONE_TYPE,
    SZ_ZONES,
)
from .zones import DhwZone, Zone

# skipcq: PY-W2000
from .protocol import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    DEV_ROLE_MAP,
    DEV_TYPE_MAP,
    ZON_CLASS_MAP,
)

# skipcq: PY-W2000
from .protocol import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    _0001,
    _0002,
    _0004,
    _0005,
    _0006,
    _0008,
    _0009,
    _000A,
    _000C,
    _000E,
    _0016,
    _0100,
    _0150,
    _01D0,
    _01E9,
    _0404,
    _0418,
    _042F,
    _0B04,
    _1030,
    _1060,
    _1081,
    _1090,
    _1098,
    _10A0,
    _10B0,
    _10E0,
    _10E1,
    _1100,
    _11F0,
    _1260,
    _1280,
    _1290,
    _1298,
    _12A0,
    _12B0,
    _12C0,
    _12C8,
    _12F0,
    _1300,
    _1F09,
    _1F41,
    _1FC9,
    _1FCA,
    _1FD0,
    _1FD4,
    _2249,
    _22C9,
    _22D0,
    _22D9,
    _22F1,
    _22F3,
    _2309,
    _2349,
    _2389,
    _2400,
    _2401,
    _2410,
    _2420,
    _2D49,
    _2E04,
    _2E10,
    _30C9,
    _3110,
    _3120,
    _313F,
    _3150,
    _31D9,
    _31DA,
    _31E0,
    _3200,
    _3210,
    _3220,
    _3221,
    _3223,
    _3B00,
    _3EF0,
    _3EF1,
    _PUZZ,
)

DEV_MODE = __dev_mode__

_LOGGER = logging.getLogger(__name__)
if DEV_MODE:
    _LOGGER.setLevel(logging.DEBUG)


SYS_KLASS = SimpleNamespace(
    SYS="system",  # Generic (promotable?) system
    TCS="evohome",
    PRG="programmer",
)


class SystemBase(Entity):  # 3B00 (multi-relay)
    """The Controllers base class (good for a generic controller)."""

    def __init__(self, ctl) -> None:
        _LOGGER.debug("Creating a TCS for CTL: %s (%s)", ctl, self.__class__)

        if ctl.id in ctl._gwy.system_by_id:
            raise LookupError(f"Duplicate TCS for CTL: {ctl}")

        super().__init__(ctl._gwy)

        self.id = ctl.id
        self._ctl = ctl
        self._tcs = self
        self._domain_id = "FF"

        # schema attrs
        self._app_cntrl = None

        # state attrs
        self._heat_demand = None

    def _zx_update_schema(self, **schema):
        """Update a CH/DHW system with new schema attrs.

        Raise an exception if the new schema is not a superset of the existing schema.
        """

        def set_app_cntrl(device: Device) -> None:  # self._app_cntrl
            """Set the TCS relay for this system (BDR or OTB)."""

            if self._app_cntrl is device:
                return
            if self._app_cntrl is not None:
                raise CorruptStateError(
                    f"{self} changed {SZ_APP_CNTRL}: {self._app_cntrl} to {device}"
                )

            if not isinstance(device, (BdrSwitch, OtbGateway)):
                raise TypeError(f"{self}: {SZ_APP_CNTRL} can't be {device}")

            self._app_cntrl = device
            device._set_parent(self, domain="FC")  # TODO: _set_domain()

        schema = shrink(SCHEMA_SYS(schema))

        if schema.get(SZ_TCS_SYSTEM) and (
            dev_id := schema[SZ_TCS_SYSTEM].get(SZ_APP_CNTRL)
        ):
            set_app_cntrl(self._gwy._zx_get_device(Address(dev_id)))  # self._app_cntrl

        if _schema := (schema.get(SZ_DHW_SYSTEM)):
            self.zx_get_dhw_zone(**_schema)  # self._dhw

        if _schema := (schema.get(SZ_ZONES)):
            [self.zx_get_htg_zone(idx, **s) for idx, s in _schema.items()]

    @classmethod
    def zx_create_from_schema(cls, ctl: Device, **schema):
        """Create a CH/DHW system for a CTL and set its schema attrs.

        The appropriate System class should have been determined by a factory.
        Schema attrs include: class (klass) & others.
        """

        tcs = cls(ctl)
        tcs._zx_update_schema(**schema)
        return tcs

    def __repr__(self) -> str:
        return f"{self._ctl.id} (sys_base)"

    # def __str__(self) -> str:  # TODO: WIP
    #     return json.dumps({self._ctl.id: self.schema})

    def _start_discovery(self) -> None:

        self._gwy.add_task(  # 0005/000C pkts
            self._discover, discover_flag=Discover.SCHEMA, delay=0, period=3600 * 24
        )
        self._gwy.add_task(
            self._discover, discover_flag=Discover.PARAMS, delay=2, period=3600 * 6
        )
        self._gwy.add_task(  # 2E04
            self._discover, discover_flag=Discover.STATUS, delay=2, period=60
        )
        self._gwy.add_task(
            self._discover, discover_flag=Discover.FAULTS, delay=60, period=60
        )
        self._gwy.add_task(
            self._discover, discover_flag=Discover.SCHEDS, delay=300, period=60
        )

    @discover_decorator
    def _discover(self, discover_flag=Discover.ALL) -> None:
        # super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.SCHEMA:
            try:
                _ = self._msgz[_000C][RP][f"00{DEV_ROLE_MAP.HTG}"]
            except KeyError:
                self._make_cmd(_000C, payload=f"00{DEV_ROLE_MAP.HTG}")

        if discover_flag & Discover.PARAMS:
            self._send_cmd(Command.get_tpi_params(self.id))

        # if discover_flag & Discover.PARAMS:
        #     for domain_id in range(0xF8, 0x100):
        #         self._make_cmd(_0009, payload=f"{domain_id:02X}00")

        # if discover_flag & Discover.STATUS:
        #     for domain_id in range(0xF8, 0x100):
        #         self._make_cmd(_0008, payload=f"{domain_id:02X}00")

    def _handle_msg(self, msg) -> None:
        def eavesdrop_app_cntrl(this, prev=None) -> None:
            """Discover the heat relay (10: or 13:) for this system.

            There's' 3 ways to find a controller's heat relay (in order of reliability):
            1.  The 3220 RQ/RP *to/from a 10:* (1x/5min)
            2a. The 3EF0 RQ/RP *to/from a 10:* (1x/1min)
            2b. The 3EF0 RQ (no RP) *to a 13:* (3x/60min)
            3.  The 3B00 I/I exchange between a CTL & a 13: (TPI cycle rate, usu. 6x/hr)

            Data from the CTL is considered 'authorative'. The 1FC9 RQ/RP exchange
            to/from a CTL is too rare to be useful.
            """

            # 18:14:14.025 066 RQ --- 01:078710 10:067219 --:------ 3220 005 0000050000
            # 18:14:14.446 065 RP --- 10:067219 01:078710 --:------ 3220 005 00C00500FF
            # 14:41:46.599 064 RQ --- 01:078710 10:067219 --:------ 3EF0 001 00
            # 14:41:46.631 063 RP --- 10:067219 01:078710 --:------ 3EF0 006 0000100000FF

            # 06:49:03.465 045 RQ --- 01:145038 13:237335 --:------ 3EF0 001 00
            # 06:49:05.467 045 RQ --- 01:145038 13:237335 --:------ 3EF0 001 00
            # 06:49:07.468 045 RQ --- 01:145038 13:237335 --:------ 3EF0 001 00
            # 09:03:59.693 051  I --- 13:237335 --:------ 13:237335 3B00 002 00C8
            # 09:04:02.667 045  I --- 01:145038 --:------ 01:145038 3B00 002 FCC8

            assert self._gwy.config.enable_eavesdrop, "Coding error"

            if this.code not in (_3220, _3B00, _3EF0):
                return

            # note the order: most to least reliable
            heater = None

            if this.code == _3220 and this.verb == RQ:
                if this.src is self._ctl and isinstance(this.dst, OtbGateway):
                    heater = this.dst

            elif this.code == _3EF0 and this.verb == RQ:
                if this.src is self._ctl and isinstance(
                    this.dst, (BdrSwitch, OtbGateway)
                ):
                    heater = this.dst

            elif this.code == _3B00 and this.verb == I_ and prev is not None:
                if this.src is self._ctl and isinstance(prev.src, BdrSwitch):
                    if prev.code == this.code and prev.verb == this.verb:
                        heater = prev.src

            if heater is not None:
                self._set_app_cntrl(heater)

        assert msg.src is self._ctl, f"msg inappropriately routed to {self}"

        super()._handle_msg(msg)

        if msg.code == _0008:
            if (domain_id := msg.payload.get(SZ_DOMAIN_ID)) and msg.verb in (I_, RP):
                self._relay_demands[domain_id] = msg
                if domain_id == "F9":
                    device = self.dhw.heating_valve if self.dhw else None
                elif domain_id == "FkA":  # TODO, FIXME
                    device = self.dhw.hotwater_valve if self.dhw else None
                elif domain_id == "FC":
                    device = self.appliance_control
                else:
                    device = None

                if False and device is not None:  # TODO: FIXME
                    qos = {"priority": Priority.LOW, "retries": 2}
                    for code in (_0008, _3EF1):
                        device._make_cmd(code, qos)

        elif msg.code == _000C and msg.payload[SZ_DEVICES]:
            if (dev_role := msg.payload[SZ_DEVICE_ROLE]) == DEV_ROLE_MAP["APP"]:
                self._zx_update_schema(
                    **{SZ_TCS_SYSTEM: {dev_role: msg.payload[SZ_DEVICES][0]}}
                )
            return

        elif msg.code == _3150:
            if msg.payload.get(SZ_DOMAIN_ID) == "FC" and msg.verb in (I_, RP):
                self._heat_demand = msg.payload

        if self._gwy.config.enable_eavesdrop and not self.appliance_control:
            eavesdrop_app_cntrl(msg)

    def _make_cmd(self, code, payload="00", **kwargs) -> None:  # skipcq: PYL-W0221
        super()._make_cmd(code, self._ctl.id, payload=payload, **kwargs)

    @property
    def devices(self) -> list[Device]:
        return self._ctl.devices + [self._ctl]  # TODO: to sort out

    @property
    def appliance_control(self) -> Device:
        """The TCS relay, aka 'appliance control' (BDR or OTB)."""
        if self._app_cntrl:
            return self._app_cntrl
        app_cntrl = [d for d in self._ctl.devices if d._domain_id == "FC"]
        return app_cntrl[0] if len(app_cntrl) == 1 else None  # HACK for 10:

    @property
    def tpi_params(self) -> Optional[dict]:  # 1100
        return self._msg_value(_1100)

    @property
    def heat_demand(self) -> Optional[float]:  # 3150/FC
        return self._msg_value(_3150, domain_id="FC", key=SZ_HEAT_DEMAND)

    @property
    def is_calling_for_heat(self) -> Optional[bool]:
        """Return True is the system is currently calling for heat."""
        return self._app_cntrl and self._app_cntrl.actuator_state

    @property
    def schema(self) -> dict:
        """Return the system's schema."""

        schema = {SZ_TCS_SYSTEM: {}}
        # hema = {SZ_CONTROLLER: self._ctl.id, SZ_TCS_SYSTEM: {}}

        schema[SZ_TCS_SYSTEM][SZ_APP_CNTRL] = (
            self.appliance_control.id if self.appliance_control else None
        )

        schema[SZ_ORPHANS] = sorted(
            [
                d.id
                for d in self._ctl.devices  # HACK: UFC
                if not d._domain_id and d._is_present
            ]  # and not isinstance(d, UfhController)
        )  # devices without a parent zone, NB: CTL can be a sensor for a zone

        return schema

    @property
    def _schema_min(self) -> dict:
        """Return the global schema."""

        schema = self.schema
        result = {SZ_CONTROLLER: self.id}

        try:
            if schema[SZ_TCS_SYSTEM][SZ_APP_CNTRL][:2] == DEV_TYPE_MAP.OTB:  # DEX
                result[SZ_TCS_SYSTEM] = {
                    SZ_APP_CNTRL: schema[SZ_TCS_SYSTEM][SZ_APP_CNTRL]
                }
        except (IndexError, TypeError):
            result[SZ_TCS_SYSTEM] = {SZ_APP_CNTRL: None}

        zones = {}
        for idx, zone in schema[SZ_ZONES].items():
            _zone = {}
            if zone[SZ_SENSOR] and zone[SZ_SENSOR][:2] == DEV_TYPE_MAP.CTL:  # DEX
                _zone = {SZ_SENSOR: zone[SZ_SENSOR]}
            if devices := [
                d for d in zone[SZ_DEVICES] if d[:2] == DEV_TYPE_MAP.TR0
            ]:  # DEX
                _zone.update({SZ_DEVICES: devices})
            if _zone:
                zones[idx] = _zone
        if zones:
            result[SZ_ZONES] = zones

        return result

    @property
    def params(self) -> dict:
        """Return the system's configuration."""

        params = {SZ_TCS_SYSTEM: {}}
        params[SZ_TCS_SYSTEM]["tpi_params"] = self._msg_value(_1100)
        return params

    @property
    def status(self) -> dict:
        """Return the system's current state."""

        status = {SZ_TCS_SYSTEM: {}}
        status[SZ_TCS_SYSTEM]["heat_demand"] = self.heat_demand

        status[SZ_DEVICES] = {d.id: d.status for d in sorted(self._ctl.devices)}

        return status


class MultiZone(SystemBase):  # 0005 (+/- 000C?)
    def zx_get_htg_zone(self, zone_idx, msg=None, **schema) -> Zone:
        """Return a heating zone (create/update it as required).

        Heating zones are uniquely identified by a controller ID|zone_idx pair.
        If a zone is created, attach it to this TCS.
        Raise an error if the zone exists and a schema was provided.
        """

        from .zones import zx_zone_factory

        schema = shrink(SCHEMA_ZON(schema))  # TODO: add shrink? do earlier?

        # Step 0: Return the object if it exists
        if zon := self.zone_by_idx.get(zone_idx):
            if schema:
                raise TypeError("a schema was provided, but the zone exists!")
            return zon

        # Step 1: Create the object (__init__ checks for unique ID)
        zon = zx_zone_factory(self, zone_idx, msg=msg, **schema)
        self.zone_by_idx[zon.idx] = zon
        self.zones.append(zon)

        # Step 2: If enabled/possible, start discovery (TODO: is messy)
        if not self._gwy.config.disable_discovery and isinstance(
            self._gwy.pkt_protocol, PacketProtocolPort
        ):
            zon._start_discovery()

        return zon

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.zones = []
        self.zone_by_idx = {}
        self.max_zones = self._gwy.config.max_zones

        self.zone_lock = Lock()
        self.zone_lock_idx = None

        self._prev_30c9 = None  # used to eavesdrop zone sensors

    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.SCHEMA:
            for zone_type in ZON_CLASS_MAP.HEAT_ZONES:
                try:
                    _ = self._msgz[_0005][RP][f"00{zone_type}"]
                except KeyError:
                    self._make_cmd(_0005, payload=f"00{zone_type}")

    def _handle_msg(self, msg) -> None:
        def eavesdrop_zone_sensors(this, prev=None) -> None:
            """Determine each zone's sensor by matching zone/sensor temperatures.

            The temperature of each zone is reliably known (30C9 array), but the sensor
            for each zone is not. In particular, the controller may be a sensor for a
            zone, but unfortunately it does not announce its sensor temperatures.

            In addition, there may be 'orphan' (e.g. from a neighbour) sensors
            announcing temperatures with the same value.

            This leaves only a process of exclusion as a means to determine which zone
            uses the controller as a sensor.
            """

            def match_sensors(testable_sensors, zone_idx, zone_temp) -> list:
                return [
                    s
                    for s in testable_sensors
                    if s.temperature == zone_temp
                    and (s.zone is None or s.zone.idx == zone_idx)
                ]

            def _testable_zones(changed_zones) -> dict:
                return {
                    z: t
                    for z, t in changed_zones.items()
                    if self.zone_by_idx[z].sensor is None
                    # and t is not None  # done in changed_zones = {}
                    and t not in [t2 for z2, t2 in changed_zones.items() if z2 != z]
                }  # zones with unique (non-null) temps, and no sensor

            assert self._gwy.config.enable_eavesdrop, "Coding error"

            if this.code != _30C9 or not isinstance(this.payload, list):
                return

            if self._prev_30c9 is None:
                self._prev_30c9 = this
                return

            self._prev_30c9, prev = this, self._prev_30c9

            if len([z for z in self.zones if z.sensor is None]) == 0:
                return  # (currently) no zone without a sensor

            # TODO: use msgz/I, not RP
            secs = self._msg_value(_1F09, key="remaining_seconds")
            if secs is None or this.dtm > prev.dtm + td(seconds=secs + 5):
                return  # can only compare against 30C9 pkt from the last cycle

            _LOGGER.debug("System state (before): %s", self.schema)

            changed_zones = {
                z[SZ_ZONE_IDX]: z[SZ_TEMPERATURE]
                for z in this.payload
                if z not in prev.payload and z[SZ_TEMPERATURE] is not None
            }  # zones with changed temps
            _LOGGER.debug("Changed zones (from 30C9): %s", changed_zones)
            if not changed_zones:
                return  # ctl's 30C9 says no zones have changed temps during this cycle

            testable_zones = _testable_zones(changed_zones)
            _LOGGER.debug(
                " - has unique/non-null temps (from 30C9) & no sensor (from state): %s",
                testable_zones,
            )
            if not testable_zones:
                return  # no testable zones

            testable_sensors = [
                d
                for d in self._gwy.devices  # NOTE: *not* self._ctl.devices
                if d._ctl in (self._ctl, None)
                and isinstance(d, Temperature)  # d.addr.type in DEVICE_HAS_ZONE_SENSOR
                and d.temperature is not None
                and d._msgs[_30C9].dtm > prev.dtm  # changed during last cycle
            ]

            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "Testable zones: %s (unique/non-null temps & sensorless)",
                    testable_zones,
                )
                _LOGGER.debug(
                    "Testable sensors: %s (non-null temps & orphans or zoneless)",
                    {d.id: d.temperature for d in testable_sensors},
                )

            if testable_sensors:  # the main matching algorithm...
                for zone_idx, temp in testable_zones.items():
                    # TODO: when sensors announce temp, ?also includes it's parent zone
                    matching_sensors = match_sensors(testable_sensors, zone_idx, temp)
                    _LOGGER.debug("Testing zone %s, temp: %s", zone_idx, temp)
                    _LOGGER.debug(
                        " - matching sensor(s): %s (same temp & not from another zone)",
                        [s.id for s in matching_sensors],
                    )

                    if len(matching_sensors) == 1:
                        _LOGGER.debug("   - matched sensor: %s", matching_sensors[0].id)
                        zone = self.zone_by_idx[zone_idx]
                        zone._set_sensor(matching_sensors[0])
                        zone.sensor._set_ctl(self._ctl)
                    elif len(matching_sensors) == 0:
                        _LOGGER.debug("   - no matching sensor (uses CTL?)")
                    else:
                        _LOGGER.debug("   - multiple sensors: %s", matching_sensors)

                _LOGGER.debug("System state (after): %s", self.schema)

            # now see if we can allocate the controller as a sensor...
            if any(z for z in self.zones if z.sensor is self._ctl):
                return  # the controller is already a sensor
            if len([z for z in self.zones if z.sensor is None]) != 1:
                return  # no single zone without a sensor

            remaining_zones = _testable_zones(changed_zones)
            if not remaining_zones:
                return  # no testable zones

            zone_idx, temp = list(remaining_zones.items())[0]
            _LOGGER.debug("Testing (sole remaining) zone %s, temp: %s", zone_idx, temp)
            # want to avoid complexity of z._temp
            # zone = self.zone_by_idx[zone_idx]
            # if zone._temp is None:
            #     return  # TODO: should have a (not-None) temperature

            matching_sensors = match_sensors(testable_sensors, zone_idx, temp)
            _LOGGER.debug(
                " - matching sensor(s): %s (excl. controller)",
                [s.id for s in matching_sensors],
            )

            # can safely(?) assume this zone is using the CTL as a sensor...
            if len(matching_sensors) == 0:
                _LOGGER.debug("   - assumed sensor: %s (by exclusion)", self._ctl.id)
                zone = self.zone_by_idx[zone_idx]
                zone._set_sensor(self._ctl)
                zone.sensor._set_ctl(self._ctl)

            _LOGGER.debug("System state (finally): %s", self.schema)

        def handle_msg_by_zone_idx(zone_idx: str, msg):
            if zone_idx is None:
                pass
            elif zone := self.zone_by_idx.get(zone_idx):
                zone._handle_msg(msg)
            # elif self._gwy.config.enable_eavesdrop:
            #     self.zx_get_htg_zone(zone_idx)._handle_msg(msg)

        super()._handle_msg(msg)

        # TODO: a I/0005 may have changed zones & may need a restart (del) or not (add)
        if msg.code == _0005:  # RP, and also I
            if msg.payload.get(SZ_ZONE_TYPE) in ZON_CLASS_MAP.HEAT_ZONES:
                [
                    self.zx_get_htg_zone(f"{idx:02X}")._zx_update_schema(
                        **{SZ_CLASS: ZON_CLASS_MAP[msg.payload[SZ_ZONE_TYPE]]}
                    )
                    for idx, flag in enumerate(msg.payload["zone_mask"])
                    if flag == 1
                ]
                return

        elif msg.code == _000C:  # RP, and also I
            if msg.payload.get(SZ_ZONE_TYPE) in ZON_CLASS_MAP:
                # NOTE: _zx_update_schema is later, below
                self.zx_get_htg_zone(msg.payload[SZ_ZONE_IDX])

        # Route all messages to their zones, incl. 000C, others
        if isinstance(msg.payload, dict):
            if zone_idx := msg.payload.get(SZ_ZONE_IDX):
                handle_msg_by_zone_idx(zone_idx, msg)
            # TODO: elif msg.payload.get(SZ_DOMAIN_ID) == "FA":  # DHW

        elif isinstance(msg.payload, list) and len(msg.payload):
            if isinstance(msg.payload[0], dict):  # e.g. 1FC9 is a list of lists:
                [handle_msg_by_zone_idx(z.get(SZ_ZONE_IDX), msg) for z in msg.payload]
            # TODO: elif msg.payload.get(SZ_DOMAIN_ID) == "FA":  # DHW

        # # If some zones still don't have a sensor, maybe eavesdrop?
        # if self._gwy.config.enable_eavesdrop and not all(z.sensor for z in self.zones):
        #     eavesdrop_zone_sensors(msg)

    @property
    def schema(self) -> dict:
        return {
            **super().schema,
            SZ_ZONES: {z.idx: z.schema for z in sorted(self.zones)},
        }

    @property
    def params(self) -> dict:
        return {
            **super().params,
            SZ_ZONES: {z.idx: z.params for z in sorted(self.zones)},
        }

    @property
    def status(self) -> dict:
        return {
            **super().status,
            SZ_ZONES: {z.idx: z.status for z in sorted(self.zones)},
        }


class ScheduleSync(SystemBase):  # 0006
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._active_0006 = None

    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.SCHEDS:  # check the latest schedule delta
            self._make_cmd(_0006)

    def _handle_msg(self, msg) -> None:  # NOTE: active
        super()._handle_msg(msg)

        if msg.code == _0006:
            # change counter checked every 60s, but updated only every 180s
            if self.schedule_outdated and (
                not self._active_0006
                or dt.now() - self._active_0006.dtm > td(minutes=3)
            ):
                self._active_0006 = msg  # TODO: what happens if the following fails?
                # if not self._gwy.config.disable_sending:  # TODO
                #     self._get_schedules()

    def _get_schedules(self) -> None:
        if self._gwy.config.disable_sending:
            raise RuntimeError("Sending is disabled")

        # schedules based upon 'active' (not most recent) 0006 pkt
        for zone in getattr(self, "zones", []):
            self._gwy._loop.create_task(zone.get_schedule(force_refresh=True))
        if dhw := getattr(self, "dhw", None):
            self._gwy._loop.create_task(dhw.get_schedule(force_refresh=True))

    @property
    def schedule_outdated(self) -> bool:
        return not self._active_0006 or (
            self._msg_value(self._active_0006, key="change_counter")
            != self._msg_value(_0006, key="change_counter")
        )  # TODO: also check if any zone/dhw has no schedule?

    @property
    def status(self) -> dict:
        return {
            **super().status,
            "schedule_outdated": self.schedule_outdated,
        }


class Language(SystemBase):  # 0100
    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.PARAMS:
            self._send_cmd(Command.get_system_language(self.id))

    @property
    def language(self) -> Optional[str]:
        return self._msg_value(_0100, key=SZ_LANGUAGE)

    @property
    def params(self) -> dict:
        params = super().params
        params[SZ_TCS_SYSTEM][SZ_LANGUAGE] = self.language
        return params


class Logbook(SystemBase):  # 0418
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._prev_event = None
        self._this_event = None

        self._prev_fault = None
        self._this_fault = None

        self._faultlog = None  # FaultLog(self._ctl)
        self._faultlog_outdated = None  # should be True

    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.FAULTS:  # check the latest log entry
            self._send_cmd(Command.get_system_log_entry(self._ctl.id, 0))
            # self._gwy._tasks.append(self._loop.create_task(self.get_faultlog()))

    def _handle_msg(self, msg) -> None:  # NOTE: active
        super()._handle_msg(msg)

        if msg.code != _0418:
            return

        if msg.payload["log_idx"] == "00":
            if not self._this_event or (
                msg.payload["log_entry"] != self._this_event.payload["log_entry"]
            ):
                self._this_event, self._prev_event = msg, self._this_event
            # TODO: self._faultlog_outdated = msg.verb == I_ or self._prev_event and (
            #     msg.payload["log_entry"] != self._prev_event.payload["log_entry"]
            # )

        if msg.payload["log_entry"] and msg.payload["log_entry"][1] == "fault":
            if not self._this_fault or (
                msg.payload["log_entry"] != self._this_fault.payload["log_entry"]
            ):
                self._this_fault, self._prev_fault = msg, self._this_fault

        # if msg.payload["log_entry"][1] == "restore" and not self._this_fault:
        #     self._send_cmd(Command.get_system_log_entry(self._ctl.id, 1))

        # TODO: if self._faultlog_outdated:
        #     if not self._gwy.config.disable_sending:
        #         self._loop.create_task(self.get_faultlog(force_refresh=True))

    async def get_faultlog(self, start=None, limit=None, force_refresh=None) -> dict:
        if self._gwy.config.disable_sending:
            raise RuntimeError("Sending is disabled")

        try:
            return await self._faultlog.get_faultlog(
                start=start, limit=limit, force_refresh=force_refresh
            )
        except (ExpiredCallbackError, RuntimeError):
            return

    # @property
    # def faultlog_outdated(self) -> bool:
    #     return self._this_event.verb == I_ or self._prev_event and (
    #         self._this_event.payload != self._prev_event.payload
    #     )

    # @property
    # def faultlog(self) -> dict:
    #     return self._faultlog.faultlog

    @property
    def active_fault(self) -> Optional[tuple]:
        """Return the most recently logged event, but only if it is a fault."""
        if self.latest_fault == self.latest_event:
            return self.latest_fault

    @property
    def latest_event(self) -> Optional[tuple]:
        """Return the most recently logged event (fault or restore), if any."""
        return self._this_event and self._this_event.payload["log_entry"]

    @property
    def latest_fault(self) -> Optional[tuple]:
        """Return the most recently logged fault, if any."""
        return self._this_fault and self._this_fault.payload["log_entry"]

    @property
    def status(self) -> dict:
        return {
            **super().status,
            "latest_event": self.latest_event,
            "active_fault": self.active_fault,
            # "faultlog": self.faultlog,
        }


class StoredHw(SystemBase):  # 10A0, 1260, 1F41
    MIN_SETPOINT = 30.0  # NOTE: these may be removed
    MAX_SETPOINT = 85.0
    DEFAULT_SETPOINT = 50.0

    def zx_get_dhw_zone(self, msg=None, **schema) -> DhwZone:
        """Return a DHW zone (create/update it as required).

        DHW zones are uniquely identified by a controller ID.
        If the DHW zone is created, attach it to this TCS.
        Raise an error if the DHW zone exists and a schema was provided.
        """

        from .zones import zx_zone_factory

        schema = shrink(SCHEMA_DHW(schema))  # TODO: add shrink? do earlier?

        # Step 0: Return the object if it exists
        if self._dhw:
            if schema:
                raise TypeError("a schema was provided, but the DHW zone exists!")
            return self._dhw

        # Step 1: Create the object (__init__ checks for unique DHW)
        self._dhw = zx_zone_factory(self, "HW", msg=msg, **schema)
        #
        #

        # Step 2: If enabled/possible, start discovery (TODO: is messy)
        if not self._gwy.config.disable_discovery and isinstance(
            self._gwy.pkt_protocol, PacketProtocolPort
        ):
            self._dhw._start_discovery()

        return self._dhw

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dhw = None

    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.SCHEMA:
            try:
                _ = self._msgz[_000C][RP][f"00{DEV_ROLE_MAP.DHW}"]
            except KeyError:
                self._make_cmd(_000C, payload=f"00{DEV_ROLE_MAP.DHW}")

    def _handle_msg(self, msg) -> None:
        super()._handle_msg(msg)

        # TODO: a I/0005 may have changed zones & may need a restart (del) or not (add)
        if (
            msg.code == _000C
            and msg.payload[SZ_ZONE_TYPE]
            in (
                DEV_ROLE_MAP.DHW,
                DEV_ROLE_MAP.HTG,
            )
            and msg.payload[SZ_DEVICES]
        ):
            self.zx_get_dhw_zone()._handle_msg(msg)

        if msg.code not in (_10A0, _1260, _1F41):
            # and "dhw_id" not in msg.payload and msg.payload.get(SZ_DOMAIN_ID) != "FA":
            return

        # RQ --- 18:002563 01:078710 --:------ 10A0 001 00  # every 4h
        # RP --- 01:078710 18:002563 --:------ 10A0 006 00157C0003E8
        if not self._dhw:
            self.zx_get_dhw_zone()

        # Route any messages to the DHW (dhw_params, dhw_temp, dhw_mode)
        self._dhw._handle_msg(msg)

    @property
    def dhw(self) -> DhwZone:
        return self._dhw

    @property
    def dhw_sensor(self) -> Device:
        return self._dhw.sensor if self._dhw else None

    @property
    def hotwater_valve(self) -> Device:
        return self._dhw.hotwater_valve if self._dhw else None

    @property
    def heating_valve(self) -> Device:
        return self._dhw.heating_valve if self._dhw else None

    @property
    def schema(self) -> dict:
        return {
            **super().schema,
            SZ_DHW_SYSTEM: self._dhw.schema if self._dhw else {},
        }

    @property
    def params(self) -> dict:
        return {
            **super().params,
            SZ_DHW_SYSTEM: self._dhw.params if self._dhw else {},
        }

    @property
    def status(self) -> dict:
        return {
            **super().status,
            SZ_DHW_SYSTEM: self._dhw.status if self._dhw else {},
        }


class SysMode(SystemBase):  # 2E04
    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.STATUS:
            self._send_cmd(Command.get_system_mode(self.id))

    @property
    def system_mode(self) -> Optional[dict]:  # 2E04
        return self._msg_value(_2E04)

    def set_mode(self, system_mode=None, until=None) -> Task:
        """Set a system mode for a specified duration, or indefinitely."""
        return self._send_cmd(
            Command.set_system_mode(self.id, system_mode=system_mode, until=until)
        )

    def set_auto(self) -> Task:
        """Revert system to Auto, set non-PermanentOverride zones to FollowSchedule."""
        return self.set_mode(SYS_MODE_MAP.AUTO)

    def reset_mode(self) -> Task:
        """Revert system to Auto, force *all* zones to FollowSchedule."""
        return self.set_mode(SYS_MODE_MAP.AUTO_WITH_RESET)

    @property
    def params(self) -> dict:
        params = super().params
        params[SZ_TCS_SYSTEM][SZ_SYSTEM_MODE] = self.system_mode
        return params


class Datetime(SystemBase):  # 313F
    def _discover(self, discover_flag=Discover.ALL) -> None:
        super()._discover(discover_flag=discover_flag)

        if discover_flag & Discover.PARAMS:  # really .STATUS, but to decrease frequency
            self._send_cmd(Command.get_system_time(self.id))

        # NOTE: used for testing
        # run_coroutine_threadsafe(self.get_datetime(), self._gwy._loop)

    def _handle_msg(self, msg) -> None:
        super()._handle_msg(msg)

        if msg.code == _313F and msg.verb in (I_, RP):  # NOTE: beware I/W/I loop, below
            if self._gwy.serial_port and (diff := abs(self._datetime - dt.now())) > td(
                minutes=5
            ):
                _LOGGER.warning(f"{msg!r} < excessive datetime difference: {diff}")
                # if the above is corrected thus, you can get a I/W/I loop
                # self._gwy.send_cmd(Command.set_system_time(self.id, dt.now()))

    @property
    def _datetime(self) -> Optional[dt]:  # 313F
        """Return the last seen datetime (NB: the packet could be from hours ago)."""
        if dtm_str := self._msg_value(_313F, key=SZ_DATETIME):
            return dt.fromisoformat(dtm_str)

    async def get_datetime(self) -> Optional[dt]:
        msg = await self._gwy.async_send_cmd(Command.get_system_time(self.id))
        return dt.fromisoformat(msg.payload["datetime"])

    async def set_datetime(self, dtm: dt) -> None:
        await self._gwy.async_send_cmd(Command.set_system_time(self.id, dtm))


class UfHeating(SystemBase):
    def _ufh_ctls(self):
        return sorted([d for d in self._ctl.devices if isinstance(d, UfhController)])

    @property
    def schema(self) -> dict:
        return {
            **super().schema,
            SZ_UFH_SYSTEM: {d.id: d.schema for d in self._ufh_ctls()},
        }

    @property
    def params(self) -> dict:
        return {
            **super().params,
            SZ_UFH_SYSTEM: {d.id: d.params for d in self._ufh_ctls()},
        }

    @property
    def status(self) -> dict:
        return {
            **super().status,
            SZ_UFH_SYSTEM: {d.id: d.status for d in self._ufh_ctls()},
        }


class System(StoredHw, Datetime, Logbook, SystemBase):
    """The Controller class."""

    _SLUG: str = SYS_KLASS.PRG

    def __init__(self, ctl, **kwargs) -> None:
        super().__init__(ctl, **kwargs)

        self._heat_demands = {}
        self._relay_demands = {}
        self._relay_failsafes = {}

    def __repr__(self) -> str:
        return f"{self._ctl.id} (system)"

    def _handle_msg(self, msg) -> None:
        super()._handle_msg(msg)

        if SZ_DOMAIN_ID in msg.payload:
            idx = msg.payload[SZ_DOMAIN_ID]
            if msg.code == _0008:
                self._relay_demands[idx] = msg
            elif msg.code == _0009:
                self._relay_failsafes[idx] = msg
            elif msg.code == _3150:
                self._heat_demands[idx] = msg
            elif msg.code not in (_0001, _000C, _0418, _1100, _3B00):
                assert False, msg.code

    @property
    def heat_demands(self) -> Optional[dict]:  # 3150
        # FC: 00-C8 (no F9, FA), TODO: deprecate as FC only?
        if self._heat_demands:
            return {k: v.payload["heat_demand"] for k, v in self._heat_demands.items()}

    @property
    def relay_demands(self) -> Optional[dict]:  # 0008
        # FC: 00-C8, F9: 00-C8, FA: 00 or C8 only (01: all 3, 02: FC/FA only)
        if self._relay_demands:
            return {
                k: v.payload["relay_demand"] for k, v in self._relay_demands.items()
            }

    @property
    def relay_failsafes(self) -> Optional[dict]:  # 0009
        if self._relay_failsafes:
            return {}  # TODO: failsafe_enabled

    @property
    def status(self) -> dict:
        """Return the system's current state."""

        status = super().status
        # assert SZ_TCS_SYSTEM in status  # TODO: removeme

        status[SZ_TCS_SYSTEM]["heat_demands"] = self.heat_demands
        status[SZ_TCS_SYSTEM]["relay_demands"] = self.relay_demands
        status[SZ_TCS_SYSTEM]["relay_failsafes"] = self.relay_failsafes

        return status


class Evohome(ScheduleSync, Language, SysMode, MultiZone, UfHeating, System):
    """The Evohome system - some controllers are evohome-compatible."""

    # older evohome don't have zone_type=ELE

    _SLUG: str = SYS_KLASS.TCS

    def __repr__(self) -> str:
        return f"{self._ctl.id} (evohome)"


class Chronotherm(Evohome):

    _SLUG: str = SYS_KLASS.SYS

    def __repr__(self) -> str:
        return f"{self._ctl.id} (chronotherm)"


class Hometronics(System):
    # These are only ever been seen from a Hometronics controller
    #  I --- 01:023389 --:------ 01:023389 2D49 003 00C800
    #  I --- 01:023389 --:------ 01:023389 2D49 003 01C800
    #  I --- 01:023389 --:------ 01:023389 2D49 003 880000
    #  I --- 01:023389 --:------ 01:023389 2D49 003 FD0000

    # Hometronic does not react to W/2349 but rather requies W/2309

    _SLUG: str = SYS_KLASS.SYS

    RQ_SUPPORTED = (_0004, _000C, _2E04, _313F)  # TODO: WIP
    RQ_UNSUPPORTED = ("xxxx",)  # 10E0?

    def __repr__(self) -> str:
        return f"{self._ctl.id} (hometronics)"

    #
    # def _discover(self, discover_flag=Discover.ALL) -> None:
    #     # super()._discover(discover_flag=discover_flag)

    #     # will RP to: 0005/configured_zones_alt, but not: configured_zones
    #     # will RP to: 0004

    #     if discover_flag & Discover.STATUS:
    #         self._make_cmd(_1F09)


class Programmer(Evohome):

    _SLUG: str = SYS_KLASS.PRG

    def __repr__(self) -> str:
        return f"{self._ctl.id} (programmer)"


class Sundial(Evohome):

    _SLUG: str = SYS_KLASS.SYS

    def __repr__(self) -> str:
        return f"{self._ctl.id} (sundial)"


SYS_CLASS_BY_SLUG = class_by_attr(__name__, "_SLUG")  # e.g. "evohome": Evohome


def zx_system_factory(ctl, msg: Message = None, **schema) -> Class:
    """Return the system class for a given controller/schema (defaults to evohome)."""

    def class_tcs(
        ctl_addr: Address,
        msg: Message = None,
        eavesdrop: bool = False,
        **schema,
    ) -> Class:
        """Return the system class for a given CTL/schema (defaults to evohome)."""

        # a specified system class always takes precidence (even if it is wrong)...
        if klass := SYS_CLASS_BY_SLUG.get(schema.get(SZ_CLASS)):
            _LOGGER.debug(f"Using configured system class for: {ctl_addr} ({klass})")
            return klass

        # otherwise, use the default system class...
        _LOGGER.warning(f"Using generic system class for: {ctl_addr} ({Evohome})")
        return Evohome

    return class_tcs(
        ctl.addr,
        msg=msg,
        eavesdrop=ctl._gwy.config.enable_eavesdrop,
        **schema,
    ).zx_create_from_schema(ctl, **schema)
