#!/usr/bin/env python3
"""RAMSES RF - devices from the CH/DHW (heat) domain."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from ramses_rf import exceptions as exc
from ramses_rf.const import (
    DEV_ROLE_MAP,
    DEV_TYPE_MAP,
    DOMAIN_TYPE_MAP,
    SZ_DEVICES,
    SZ_DOMAIN_ID,
    SZ_HEAT_DEMAND,
    SZ_PRESSURE,
    SZ_RELAY_DEMAND,
    SZ_SETPOINT,
    SZ_TEMPERATURE,
    SZ_UFH_IDX,
    SZ_WINDOW_OPEN,
    SZ_ZONE_IDX,
    SZ_ZONE_MASK,
    SZ_ZONE_TYPE,
    ZON_ROLE_MAP,
    DevType,
)
from ramses_rf.device import Device
from ramses_rf.entity_base import Entity, class_by_attr
from ramses_rf.helpers import shrink
from ramses_rf.schemas import SCH_TCS, SZ_ACTUATORS, SZ_CIRCUITS
from ramses_rf.topology import Child, Parent
from ramses_tx import NON_DEV_ADDR, Command, Priority
from ramses_tx.const import SZ_NUM_REPEATS, SZ_PRIORITY, MsgId
from ramses_tx.opentherm import (
    PARAMS_DATA_IDS,
    SCHEMA_DATA_IDS,
    STATUS_DATA_IDS,
    SZ_MSG_ID,
    SZ_MSG_NAME,
    SZ_MSG_TYPE,
    SZ_VALUE,
    OtMsgType,
)
from ramses_tx.ramses import CODES_OF_HEAT_DOMAIN_ONLY, CODES_ONLY_FROM_CTL
from ramses_tx.typing import PayDictT, PayloadT

from .base import BatteryState, DeviceHeat, Fakeable

from ramses_rf.const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    F9,
    FA,
    FC,
    FF,
)

from ramses_rf.const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    Code,
)

from ramses_tx.const import (
    SZ_BOILER_OUTPUT_TEMP,
    SZ_BOILER_RETURN_TEMP,
    SZ_BOILER_SETPOINT,
    SZ_BURNER_FAILED_STARTS,
    SZ_BURNER_HOURS,
    SZ_BURNER_STARTS,
    SZ_CH_ACTIVE,
    SZ_CH_ENABLED,
    SZ_CH_MAX_SETPOINT,
    SZ_CH_PUMP_HOURS,
    SZ_CH_PUMP_STARTS,
    SZ_CH_SETPOINT,
    SZ_CH_WATER_PRESSURE,
    SZ_COOLING_ACTIVE,
    SZ_COOLING_ENABLED,
    SZ_DHW_ACTIVE,
    SZ_DHW_BLOCKING,
    SZ_DHW_BURNER_HOURS,
    SZ_DHW_BURNER_STARTS,
    SZ_DHW_ENABLED,
    SZ_DHW_FLOW_RATE,
    SZ_DHW_PUMP_HOURS,
    SZ_DHW_PUMP_STARTS,
    SZ_DHW_SETPOINT,
    SZ_DHW_TEMP,
    SZ_FAULT_PRESENT,
    SZ_FLAME_ACTIVE,
    SZ_FLAME_SIGNAL_LOW,
    SZ_MAX_REL_MODULATION,
    SZ_OEM_CODE,
    SZ_OTC_ACTIVE,
    SZ_OUTSIDE_TEMP,
    SZ_REL_MODULATION_LEVEL,
    SZ_SUMMER_MODE,
)

if TYPE_CHECKING:
    from ramses_rf.models import DeviceTraits
    from ramses_rf.system import Evohome, Zone
    from ramses_tx import Address, Message, Packet
    from ramses_tx.opentherm import OtDataId


QOS_LOW = {SZ_PRIORITY: Priority.LOW}  # FIXME:  deprecate QoS in kwargs
QOS_MID = {SZ_PRIORITY: Priority.HIGH}  # FIXME: deprecate QoS in kwargs
QOS_MAX = {SZ_PRIORITY: Priority.HIGH, SZ_NUM_REPEATS: 3}  # FIXME: deprecate QoS...

#
# NOTE: All debug flags should be False for deployment to end-users
_DBG_ENABLE_DEPRECATION: Final[bool] = False
_DBG_EXTRA_OTB_DISCOVERY: Final[bool] = False

_LOGGER = logging.getLogger(__name__)


class Actuator(DeviceHeat):  # 3EF0, 3EF1 (for 10:/13:)
    # .I --- 13:109598 --:------ 13:109598 3EF0 003 00C8FF                # event-driven, 00/C8
    # RP --- 13:109598 18:002563 --:------ 0008 002 00C8                  # 00/C8, as above
    # RP --- 13:109598 18:002563 --:------ 3EF1 007 0000BF-00BFC8FF       # 00/C8, as above

    # RP --- 10:048122 18:140805 --:------ 3EF1 007 007FFF-003C2A10       # 10:s only RP, always 7FFF
    # RP --- 13:109598 18:199952 --:------ 3EF1 007 0001B8-01B800FF       # 13:s only RP

    # RP --- 10:047707 18:199952 --:------ 3EF0 009 001110-0A00FF-033100  # 10:s only RP
    # RP --- 10:138926 34:010253 --:------ 3EF0 006 002E11-0000FF         # 10:s only RP
    # .I --- 13:209679 --:------ 13:209679 3EF0 003 00C8FF                # 13:s only  I

    ACTUATOR_CYCLE: Final = "actuator_cycle"
    ACTUATOR_ENABLED: Final = "actuator_enabled"  # boolean
    ACTUATOR_STATE: Final = "actuator_state"
    MODULATION_LEVEL: Final = "modulation_level"  # percentage (0.0-1.0)

    def _handle_msg(self, msg: Message) -> None:  # NOTE: active
        super()._handle_msg(msg)

        if isinstance(self, OtbGateway):
            return

        if self._gwy.config.disable_discovery:
            return

        # TODO: why are we doing this here? Should simply use discovery poller!
        if msg.code == Code._3EF0 and msg.verb == I_ and not self.is_faked:
            # lf._send_cmd(Command.get_relay_demand(self.id), qos=QOS_LOW)
            self._send_cmd(
                Command.from_attrs(RQ, self.id, Code._3EF1, PayloadT("00")), **QOS_LOW
            )  # actuator cycle

    async def actuator_cycle(self) -> dict | None:  # 3EF1
        return cast(dict | None, await self.state_store._msg_value(Code._3EF1))

    async def actuator_state(self) -> dict | None:  # 3EF0
        return cast(dict | None, await self.state_store._msg_value(Code._3EF0))

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.ACTUATOR_CYCLE: await self.actuator_cycle(),
            self.ACTUATOR_STATE: await self.actuator_state(),
        }


class HeatDemand(DeviceHeat):  # 3150
    HEAT_DEMAND: Final = SZ_HEAT_DEMAND  # percentage valve open (0.0-1.0)

    async def heat_demand(self) -> float | None:  # 3150
        return cast(
            float | None,
            await self.state_store._msg_value(Code._3150, key=self.HEAT_DEMAND),
        )

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.HEAT_DEMAND: await self.heat_demand(),
        }


class Setpoint(DeviceHeat):  # 2309
    SETPOINT: Final = SZ_SETPOINT  # degrees Celsius

    async def setpoint(self) -> float | None:  # 2309
        return cast(
            float | None,
            await self.state_store._msg_value(Code._2309, key=self.SETPOINT),
        )

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.SETPOINT: await self.setpoint(),
        }


class Weather(DeviceHeat):  # 0002
    TEMPERATURE: Final = SZ_TEMPERATURE  # TODO: deprecate

    async def temperature(self) -> float | None:  # 0002
        return cast(
            float | None,
            await self.state_store._msg_value(Code._0002, key=SZ_TEMPERATURE),
        )

    def set_temperature(self, value: float | None) -> None:
        """Fake the outdoor temperature of the sensor."""

        if not self.is_faked:
            raise exc.DeviceNotFaked(f"{self}: Faking is not enabled")

        cmd = Command.put_outdoor_temp(self.id, value)
        self._gwy.send_cmd(cmd, num_repeats=2, priority=Priority.HIGH)

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.TEMPERATURE: await self.temperature(),
        }


class RelayDemand(DeviceHeat):  # 0008
    # .I --- 01:054173 --:------ 01:054173 1FC9 018 03-0008-04D39D FC-3B00-04D39D 03-1FC9-04D39D
    # .W --- 13:123456 01:054173 --:------ 1FC9 006 00-3EF0-35E240
    # .I --- 01:054173 13:123456 --:------ 1FC9 006 00-FFFF-04D39D

    # Some either 00/C8, others 00-C8
    # .I --- 01:145038 --:------ 01:145038 0008 002 0314  # ZON valve zone (ELE too?)
    # .I --- 01:145038 --:------ 01:145038 0008 002 F914  # HTG valve
    # .I --- 01:054173 --:------ 01:054173 0008 002 FA00  # DHW valve
    # .I --- 01:145038 --:------ 01:145038 0008 002 FC14  # appliance_relay

    # RP --- 13:109598 18:199952 --:------ 0008 002 0000
    # RP --- 13:109598 18:199952 --:------ 0008 002 00C8

    RELAY_DEMAND: Final = SZ_RELAY_DEMAND  # percentage (0.0-1.0)

    def _setup_discovery_cmds(self) -> None:
        super()._setup_discovery_cmds()

        if not self.is_faked:  # discover_flag & Discover.STATUS and
            self.discovery.add_cmd(Command.get_relay_demand(self.id), 60 * 15)

    async def relay_demand(self) -> float | None:  # 0008
        return cast(
            float | None,
            await self.state_store._msg_value(Code._0008, key=self.RELAY_DEMAND),
        )

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.RELAY_DEMAND: await self.relay_demand(),
        }


class DhwTemperature(DeviceHeat):  # 1260
    TEMPERATURE: Final = SZ_TEMPERATURE  # TODO: deprecate

    async def temperature(self) -> float | None:  # 1260
        return cast(
            float | None,
            await self.state_store._msg_value(Code._1260, key=SZ_TEMPERATURE),
        )

    def set_temperature(self, value: float | None) -> None:
        """Fake the DHW temperature of the sensor."""

        if not self.is_faked:
            raise exc.DeviceNotFaked(f"{self}: Faking is not enabled")

        cmd = Command.put_dhw_temp(self.id, value)
        self._gwy.send_cmd(cmd, num_repeats=2, priority=Priority.HIGH)

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.TEMPERATURE: await self.temperature(),
        }


class Temperature(DeviceHeat):  # 30C9
    # .I --- 34:145039 --:------ 34:145039 1FC9 012 00-30C9-8A368F 00-1FC9-8A368F
    # .W --- 01:054173 34:145039 --:------ 1FC9 006 03-2309-04D39D  # real CTL
    # .I --- 34:145039 01:054173 --:------ 1FC9 006 00-30C9-8A368F
    async def temperature(self) -> float | None:  # 30C9
        return cast(
            float | None,
            await self.state_store._msg_value(Code._30C9, key=SZ_TEMPERATURE),
        )

    def set_temperature(self, value: float | None) -> None:
        """Fake the indoor temperature of the sensor."""

        if not self.is_faked:
            raise exc.DeviceNotFaked(f"{self}: Faking is not enabled")

        cmd = Command.put_sensor_temp(self.id, value)
        self._gwy.send_cmd(cmd, num_repeats=2, priority=Priority.HIGH)

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            SZ_TEMPERATURE: await self.temperature(),
        }


class RfgGateway(DeviceHeat):  # RFG (30:)
    """The RFG100 base class."""

    _SLUG = DevType.RFG
    _STATE_ATTR = None


class Controller(DeviceHeat):  # CTL (01):
    """The Controller base class."""

    HEAT_DEMAND: Final = SZ_HEAT_DEMAND

    _SLUG = DevType.CTL
    _STATE_ATTR = HEAT_DEMAND

    def __init__(
        self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, traits=traits, **kwargs)

        # self.ctl = None
        self.tcs = None  # TODO: = self?
        self._make_tcs_controller(**kwargs)  # NOTE: must create_from_schema first

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)

        self.tcs._handle_msg(msg)

    def _make_tcs_controller(
        self, *, msg: Message | None = None, **schema: Any
    ) -> None:  # CH/DHW
        """Attach a TCS (create/update as required) after passing it any msg."""

        def get_system(*, msg: Message | None = None, **schema: Any) -> Evohome:
            """Return a TCS (temperature control system), create it if required.

            Use the schema to create/update it, then pass it any msg to handle.

            TCSs are uniquely identified by a controller ID.
            If a TCS is created, attach it to this device (which should be a CTL).
            """

            from ramses_rf.system import system_factory

            schema = shrink(SCH_TCS(schema))

            if not self.tcs:
                self.tcs = system_factory(self, msg=msg, **schema)

            elif schema:
                self.tcs._update_schema(**schema)

            if msg:
                self.tcs._handle_msg(msg)
            return self.tcs

        super()._make_tcs_controller(msg=None, **schema)

        self.tcs = get_system(msg=msg, **schema)


class Programmer(Controller):  # PRG (23):
    """The Controller base class."""

    _SLUG = DevType.PRG


class UfhController(Parent, DeviceHeat):  # UFC (02):
    """The UFC class, the HCE80 that controls the UFH zones."""

    HEAT_DEMAND: Final = SZ_HEAT_DEMAND

    _SLUG = DevType.UFC
    _STATE_ATTR = HEAT_DEMAND

    _child_id = FA
    _iz_controller = True

    childs: list[UfhCircuit]  # TODO: check (code so complex, not sure if this is true)

    # 12:27:24.398 067  I --- 02:000921 --:------ 01:191718 3150 002 0360
    # 12:27:24.546 068  I --- 02:000921 --:------ 01:191718 3150 002 065A
    # 12:27:24.693 067  I --- 02:000921 --:------ 01:191718 3150 002 045C
    # 12:27:24.824 059  I --- 01:191718 --:------ 01:191718 3150 002 FC5C
    # 12:27:24.857 067  I --- 02:000921 --:------ 02:000921 3150 006 0060-015A-025C

    def __init__(
        self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, traits=traits, **kwargs)

        self.circuit_by_id = {f"{i:02X}": {} for i in range(8)}

        self._setpoints: Message | None = None
        self._heat_demand: Message | None = None
        self._heat_demands: Message | None = None
        self._relay_demand: Message | None = None
        self._relay_demand_fa: Message | None = None

    def _setup_discovery_cmds(self) -> None:
        super()._setup_discovery_cmds()

        # Only RPs are: 0001, 0005/000C, 10E0, 000A/2309 & 22D0

        cmd = Command.from_attrs(
            RQ, self.id, Code._0005, PayloadT(f"00{DEV_ROLE_MAP.UFH}")
        )
        self.discovery.add_cmd(cmd, 60 * 60 * 24)

        # TODO: this needs work
        # if discover_flag & Discover.PARAMS:  # only 2309 has any potential?
        for ufc_idx in self.circuit_by_id:
            cmd = Command.get_zone_config(self.id, ufc_idx)
            self.discovery.add_cmd(cmd, 60 * 60 * 6)

            cmd = Command.get_zone_setpoint(self.id, ufc_idx)
            self.discovery.add_cmd(cmd, 60 * 60 * 6)

        for ufc_idx in range(8):
            payload = PayloadT(f"{ufc_idx:02X}{DEV_ROLE_MAP.UFH}")
            cmd = Command.from_attrs(RQ, self.id, Code._000C, payload)
            self.discovery.add_cmd(cmd, 60 * 60 * 24)

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)

        # Several assumptions are made, regarding 000C pkts:
        # - UFC bound only to CTL (not, e.g. SEN)
        # - all circuits bound to the same controller

        if msg.code == Code._0005:  # system_zones
            # {'zone_type': '09', 'zone_mask': [1, 1, 1, 1, 1, 0, 0, 0], 'zone_class': 'underfloor_heating'}

            if msg.payload[SZ_ZONE_TYPE] not in (ZON_ROLE_MAP.ACT, ZON_ROLE_MAP.UFH):
                return  # ignoring ZON_ROLE_MAP.SEN for now

            for idx, flag in enumerate(msg.payload[SZ_ZONE_MASK]):
                ufh_idx = f"{idx:02X}"
                if not flag:
                    self.circuit_by_id[ufh_idx] = {SZ_ZONE_IDX: None}
                # FIXME: this causing tests to fail when read-only protocol
                # elif SZ_ZONE_IDX not in self.circuit_by_id[ufh_idx]:
                #     cmd = Command.from_attrs(
                #         RQ, self.ctl.id, Code._000C, f"{ufh_idx}{DEV_ROLE_MAP.UFH}"
                #     )
                #     self._send_cmd(cmd)

        elif msg.code == Code._0008:  # relay_demand
            if msg.payload.get(SZ_DOMAIN_ID) == FC:
                self._relay_demand = msg
            else:  # FA
                self._relay_demand_fa = msg

        elif msg.code == Code._000C:  # zone_devices
            # {'zone_type': '09', 'ufh_idx': '00', 'zone_idx': '09', 'device_role': 'ufh_actuator', 'devices': ['01:095421']}
            # {'zone_type': '09', 'ufh_idx': '07', 'zone_idx': None, 'device_role': 'ufh_actuator', 'devices': []}

            if msg.payload[SZ_ZONE_TYPE] not in (ZON_ROLE_MAP.ACT, ZON_ROLE_MAP.UFH):
                return  # ignoring ZON_ROLE_MAP.SEN for now

            ufh_idx = msg.payload[SZ_UFH_IDX]  # circuit idx
            self.circuit_by_id[ufh_idx] = {SZ_ZONE_IDX: msg.payload[SZ_ZONE_IDX]}
            if msg.payload[SZ_ZONE_IDX] is not None:  # [SZ_DEVICES][0] will be the CTL
                self.set_parent(
                    self._gwy.get_device(msg.payload[SZ_DEVICES][0]).tcs,
                    # child_id=msg.payload[SZ_ZONE_IDX],
                )

        elif msg.code == Code._22C9:  # setpoint_bounds
            # .I --- 02:017205 --:------ 02:017205 22C9 024 00076C0A280101076C0A28010...
            # .I --- 02:017205 --:------ 02:017205 22C9 006 04076C0A2801
            self._setpoints = msg

        elif msg.code == Code._3150:  # heat_demands
            if isinstance(msg.payload, list):  # the circuit demands
                self._heat_demands = msg
            elif msg.payload.get(SZ_DOMAIN_ID) == FC:
                self._heat_demand = msg
            elif (
                (zone_idx := msg.payload.get(SZ_ZONE_IDX))
                and isinstance(msg.dst, Device)
                and (tcs := msg.dst.tcs)
                and (zone := tcs.zone_by_idx.get(zone_idx))
            ):
                zone._handle_msg(msg)

        # elif msg.code not in (Code._10E0, Code._22D0):
        #     print("xxx")
        # "0008|FA/FC", "22C9|array", "22D0|none", "3150|ZZ/array(/FC?)"

    # TODO: should be a private method
    def get_circuit(
        self, cct_idx: str, *, msg: Message | None = None, **schema: Any
    ) -> Any:
        """Return a UFH circuit, create it if required.

        First, use the schema to create/update it, then pass it any msg to handle.

        Circuits are uniquely identified by a UFH controller ID|cct_idx pair.
        If a circuit is created, attach it to this UFC.
        """

        schema = {}  # shrink(SCH_CCT(schema))

        cct: UfhCircuit = self.child_by_id.get(cct_idx)
        if not cct:
            cct = UfhCircuit(self, cct_idx)
            self.child_by_id[cct_idx] = cct
            self.childs.append(cct)

        elif schema:
            cct._update_schema(**schema)

        if msg:
            cct._handle_msg(msg)
        return cct

    # @property
    # def circuits(self) -> dict:  # 000C
    #     return self.circuit_by_id

    async def heat_demand(self) -> float | None:  # 3150|FC (there is also 3150|FA)
        return cast(
            float | None,
            self.state_store._msg_value_msg(self._heat_demand, key=self.HEAT_DEMAND),
        )

    async def heat_demands(self) -> dict | None:  # 3150|ufh_idx array
        # return self._heat_demands.payload if self._heat_demands else None
        return cast(dict | None, self.state_store._msg_value_msg(self._heat_demands))

    async def relay_demand(self) -> dict | None:  # 0008|FC
        return cast(
            dict | None,
            self.state_store._msg_value_msg(self._relay_demand, key=SZ_RELAY_DEMAND),
        )

    async def relay_demand_fa(self) -> dict | None:  # 0008|FA
        return cast(
            dict | None,
            self.state_store._msg_value_msg(self._relay_demand_fa, key=SZ_RELAY_DEMAND),
        )

    async def setpoints(self) -> dict[str, Any] | None:  # 22C9|ufh_idx array
        if self._setpoints is None:
            return None

        payload = self._setpoints.payload

        # 22C9 payload can be a list, flat dict(if indexed by schema), or dict of dicts
        if isinstance(payload, list):
            items: list[dict[str, Any]] = payload
        elif isinstance(payload, dict):
            # It's a single circuit (flat dict) if SZ_UFH_IDX is present,
            # otherwise it's a map of circuits (dict of dicts).
            items = [payload] if SZ_UFH_IDX in payload else list(payload.values())
        else:
            return None

        return {
            c[SZ_UFH_IDX]: {
                k: v for k, v in c.items() if k in ("temp_low", "temp_high")
            }
            for c in items
            if isinstance(c, dict) and SZ_UFH_IDX in c
        }

    async def schema(self) -> dict[str, Any]:
        base_schema = await super().schema()
        return {
            **base_schema,
            SZ_CIRCUITS: self.circuit_by_id,
        }

    async def params(self) -> dict[str, Any]:
        base_params = await super().params()
        return {
            **base_params,
            SZ_CIRCUITS: await self.setpoints(),
        }

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            SZ_HEAT_DEMAND: await self.heat_demand(),
            SZ_RELAY_DEMAND: await self.relay_demand(),
            f"{SZ_RELAY_DEMAND}_fa": await self.relay_demand_fa(),
        }


class DhwSensor(DhwTemperature, BatteryState, Fakeable):  # DHW (07): 10A0, 1260
    """The DHW class, such as a CS92."""

    DHW_PARAMS: Final = "dhw_params"

    _SLUG: str = DevType.DHW
    _STATE_ATTR = DhwTemperature.TEMPERATURE

    def __init__(
        self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, traits=traits, **kwargs)

        self._child_id = FA  # NOTE: domain_id

    def _handle_msg(self, msg: Message) -> None:  # NOTE: active
        super()._handle_msg(msg)

        if self._gwy.config.disable_discovery:
            return

        # TODO: why are we doing this here? Should simply use dscovery poller!
        # The following is required, as CTLs don't send spontaneously
        if msg.code == Code._1260 and self.ctl:
            # update the controller DHW temp
            self._send_cmd(Command.get_dhw_temp(self.ctl.id))

    async def initiate_binding_process(self) -> Packet:
        return await super()._initiate_binding_process(Code._1260)

    async def dhw_params(self) -> PayDictT._10A0 | None:
        return cast(
            PayDictT._10A0 | None, await self.state_store._msg_value(Code._10A0)
        )

    async def params(self) -> dict[str, Any]:
        base_params = await super().params()
        return {
            **base_params,
            self.DHW_PARAMS: await self.dhw_params(),
        }


class OutSensor(Weather, Fakeable):  # OUT: 17
    """The OUT class (external sensor), such as a HB85/HB95."""

    # LUMINOSITY = "luminosity"  # lux
    # WINDSPEED = "windspeed"  # km/h

    _SLUG = DevType.OUT
    _STATE_ATTR = SZ_TEMPERATURE

    # async def initiate_binding_process(self) -> Packet:
    #     return await super()._initiate_binding_process(...)


def _to_msg_id(data_id: OtDataId) -> MsgId:
    return f"{data_id:02X}"


# NOTE: config.use_native_ot should enforce sends, but not reads from _msgz DB
class OtbGateway(Actuator, HeatDemand):  # OTB (10): 3220 (22D9, others)
    """The OTB class, specifically an OpenTherm Bridge (R8810A Bridge)."""

    # see: https://www.opentherm.eu/request-details/?post_ids=2944
    # see: https://www.automatedhome.co.uk/vbulletin/showthread.php?6400-(New)-cool-mode-in-Evohome

    _SLUG = DevType.OTB
    _STATE_ATTR = SZ_REL_MODULATION_LEVEL

    OT_TO_RAMSES: dict[MsgId, Code] = {  # TODO: move to opentherm.py
        MsgId._00: Code._3EF0,  # master/slave status (actuator_state)
        MsgId._01: Code._22D9,  # boiler_setpoint
        MsgId._0E: Code._3EF0,  # max_rel_modulation_level (is a PARAM?)
        MsgId._11: Code._3EF0,  # rel_modulation_level (actuator_state, also Code._3EF1)
        MsgId._12: Code._1300,  # ch_water_pressure
        MsgId._13: Code._12F0,  # dhw_flow_rate
        MsgId._19: Code._3200,  # boiler_output_temp
        MsgId._1A: Code._1260,  # dhw_temp
        MsgId._1B: Code._1290,  # outside_temp
        MsgId._1C: Code._3210,  # boiler_return_temp
        MsgId._38: Code._10A0,  # dhw_setpoint (is a PARAM)
        MsgId._39: Code._1081,  # ch_max_setpoint (is a PARAM)
    }
    RAMSES_TO_OT: dict[Code, MsgId] = {
        v: k for k, v in OT_TO_RAMSES.items() if v != Code._3EF0
    }  # also 10A0?

    def __init__(
        self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, traits=traits, **kwargs)

        self._child_id = FC  # NOTE: domain_id

        # TODO(eb): cleanup
        if not self._gwy.msg_db:
            # self._add_record(
            #     id=self.id, code=Code._3220, verb="RP", payload="00C0060101"
            # )  # is parsed but pollutes the client.py
            # adds a "sim" RP opentherm_msg to the SQLite MessageIndex with code _3220
            # causes exc when fetching ALL, when no "real" msg was added to _msgs_. We skip those.
            # else:
            self.state_store._msgz_[Code._3220] = {RP: {}}  # No ctx! (not None)

        # lf._use_ot = self._gwy.config.use_native_ot
        self._msgs_ot: dict[MsgId, Message] = {}
        # lf._msgs_ot_ctl_polled = {}

    def _setup_discovery_cmds(self) -> None:
        def which_cmd(
            use_native_ot: Literal["always", "prefer", "avoid", "never"] | None,
            msg_id: MsgId,
        ) -> Command | None:
            """Create a OT cmd, or its RAMSES equivalent, depending."""
            # we know RQ|3220 is an option, question is: use that, or RAMSES or nothing?
            if use_native_ot in ("always", "prefer"):
                return Command.get_opentherm_data(self.id, msg_id)
            if msg_id in self.OT_TO_RAMSES:  # is: in ("avoid", "never")
                return Command.from_attrs(
                    RQ, self.id, self.OT_TO_RAMSES[msg_id], PayloadT("00")
                )
            if use_native_ot == "avoid":
                return Command.get_opentherm_data(self.id, msg_id)
            return None  # use_native_ot == "never"

        super()._setup_discovery_cmds()

        # always send at least one of RQ|3EF0 or RQ|3220|00 (status)
        if self._gwy.config.use_native_ot != "never":
            self.discovery.add_cmd(Command.get_opentherm_data(self.id, MsgId._00), 60)

        if self._gwy.config.use_native_ot != "always":
            self.discovery.add_cmd(
                Command.from_attrs(RQ, self.id, Code._3EF0, PayloadT("00")), 60
            )
            self.discovery.add_cmd(  # NOTE: this code is a WIP
                Command.from_attrs(RQ, self.id, Code._2401, PayloadT("00")), 60
            )

        for data_id in SCHEMA_DATA_IDS:  # From OT v2.2: version numbers
            if cmd := which_cmd(self._gwy.config.use_native_ot, _to_msg_id(data_id)):
                self.discovery.add_cmd(cmd, 6 * 3600, delay=180)

        for data_id in PARAMS_DATA_IDS:  # params or L/T state
            if cmd := which_cmd(self._gwy.config.use_native_ot, _to_msg_id(data_id)):
                self.discovery.add_cmd(cmd, 3600, delay=90)

        for data_id in STATUS_DATA_IDS:  # except "00", see above
            if data_id == 0x00:
                continue
            if cmd := which_cmd(self._gwy.config.use_native_ot, _to_msg_id(data_id)):
                self.discovery.add_cmd(cmd, 300, delay=15)

        if _DBG_EXTRA_OTB_DISCOVERY:  # TODO: these are WIP, but do vary in payload
            for code in (
                Code._2401,  # WIP - modulation_level + flags?
                Code._3221,  # R8810A/20A
                Code._3223,  # R8810A/20A
            ):
                self.discovery.add_cmd(
                    Command.from_attrs(RQ, self.id, code, PayloadT("00")), 60
                )

        if _DBG_EXTRA_OTB_DISCOVERY:  # TODO: these are WIP, appear FIXED in payload
            for code in (
                Code._0150,  # payload always "000000", R8820A only?
                Code._1098,  # payload always "00C8",   R8820A only?
                Code._10B0,  # payload always "0000",   R8820A only?
                Code._1FD0,  # payload always "0000000000000000"
                Code._2400,  # payload always "0000000F"
                Code._2410,  # payload always "000000000000000000000000010000000100000C"
                Code._2420,  # payload always "0000001000000...
            ):  # TODO: to test against BDR91T
                self.discovery.add_cmd(
                    Command.from_attrs(RQ, self.id, code, PayloadT("00")), 300
                )

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)

        if msg.verb not in (I_, RP):
            return

        if msg.code == Code._3220:
            self._handle_3220(msg)
        elif msg.code in self.RAMSES_TO_OT:
            self._handle_code(msg)

    def _handle_3220(self, msg: Message) -> None:
        """Handle 3220-based messages."""

        # NOTE: Reserved msgs have null data, but that msg_id may later be OK!
        if msg.payload[SZ_MSG_TYPE] == OtMsgType.RESERVED:
            return

        # NOTE: Some msgs have invalid data, but that msg_id may later be OK!
        if msg.payload.get(SZ_VALUE) is None:
            return

        # msg_id is int in msg payload/opentherm.py, but MsgId (str) in this module
        msg_id = _to_msg_id(msg.payload[SZ_MSG_ID])
        self._msgs_ot[msg_id] = msg

        if not _DBG_ENABLE_DEPRECATION:  # FIXME: data gaps
            return

        reset = msg.payload[SZ_MSG_TYPE] not in (
            OtMsgType.DATA_INVALID,
            OtMsgType.UNKNOWN_DATAID,
            OtMsgType.RESERVED,  # but some are ?always reserved
        )
        self.discovery.deprecate_code_ctx(msg._pkt, ctx=msg_id, reset=reset)

    def _handle_code(self, msg: Message) -> None:
        """Handle non-3220-based messages."""

        if msg.code == Code._3EF0 and msg.verb == I_:
            # NOTE: this is development/discovery code  # chasing flags
            # self._send_cmd(
            #     Command.get_opentherm_data(self.id, MsgId._00), **QOS_MID
            # )  # FIXME: deprecate QoS in kwargs
            return

        if msg.code in (Code._10A0, Code._3EF1):
            return

        if not _DBG_ENABLE_DEPRECATION:  # FIXME: data gaps
            return

        # TODO: can be temporarily 7FFF?
        if msg._pkt.payload[2:] == "7FFF" or (
            msg.code == Code._1300 and msg._pkt.payload[2:] == "09F6"
        ):  # latter is CH water pressure
            self.discovery.deprecate_code_ctx(msg._pkt)
        else:
            self.discovery.deprecate_code_ctx(msg._pkt, reset=True)

    def _ot_msg_flag(self, msg_id: MsgId, flag_idx: int) -> bool | None:
        flags = cast(list, self._ot_msg_value(msg_id))
        return bool(flags[flag_idx]) if flags else None

    @staticmethod
    def _ot_msg_name(msg: Message) -> str:  # TODO: remove
        return (
            msg.payload[SZ_MSG_NAME]
            if isinstance(msg.payload[SZ_MSG_NAME], str)
            else f"{msg.payload[SZ_MSG_ID]:02X}"
        )

    def _ot_msg_value(self, msg_id: MsgId) -> int | float | list | None:
        # data_id = int(msg_id, 16)
        if (msg := self._msgs_ot.get(msg_id)) and not msg._expired:
            # TODO: value_hb/_lb
            return msg.payload.get(SZ_VALUE)  # type: ignore[no-any-return]
        return None

    def _result_by_callback(
        self, cbk_ot: Callable | None, cbk_ramses: Callable | None
    ) -> Any | None:
        """Return a value using OpenTherm or RAMSES as per `config.use_native_ot`."""

        if self._gwy.config.use_native_ot == "always":
            return cbk_ot() if cbk_ot else None
        if self._gwy.config.use_native_ot == "prefer":
            if cbk_ot and (result := cbk_ot()) is not None:
                return result

        result_ramses = cbk_ramses() if cbk_ramses is not None else None
        if self._gwy.config.use_native_ot == "avoid" and result_ramses is None:
            return cbk_ot() if cbk_ot else None
        return result_ramses  # incl. use_native_ot == "never"

    async def _result_by_lookup(
        self,
        code: Code,
        /,
        *,
        key: str,
    ) -> Any | None:
        """Return a value using OpenTherm or RAMSES as per `config.use_native_ot`."""
        # assert code in self.RAMSES_TO_OT and kwargs.get("key"):

        if self._gwy.config.use_native_ot == "always":
            return self._ot_msg_value(self.RAMSES_TO_OT[code])

        if self._gwy.config.use_native_ot == "prefer":
            if (result_ot := self._ot_msg_value(self.RAMSES_TO_OT[code])) is not None:
                return result_ot

        result_ramses = await self.state_store._msg_value(code, key=key)
        if self._gwy.config.use_native_ot == "avoid" and result_ramses is None:
            return self._ot_msg_value(self.RAMSES_TO_OT[code])

        return result_ramses  # incl. use_native_ot == "never"

    def _result_by_value(
        self, result_ot: Any | None, result_ramses: Any | None
    ) -> Any | None:
        """Return a value using OpenTherm or RAMSES as per `config.use_native_ot`."""
        #

        if self._gwy.config.use_native_ot == "always":
            return result_ot

        if self._gwy.config.use_native_ot == "prefer":
            if result_ot is not None:
                return result_ot

        #
        elif self._gwy.config.use_native_ot == "avoid" and result_ramses is None:
            return result_ot

        return result_ramses  # incl. use_native_ot == "never"

    async def bit_2_4(self) -> bool | None:  # 2401 - WIP
        return await self.state_store._msg_flag(Code._2401, "_flags_2", 4)

    async def bit_2_5(self) -> bool | None:  # 2401 - WIP
        return await self.state_store._msg_flag(Code._2401, "_flags_2", 5)

    async def bit_2_6(self) -> bool | None:  # 2401 - WIP
        return await self.state_store._msg_flag(Code._2401, "_flags_2", 6)

    async def bit_2_7(self) -> bool | None:  # 2401 - WIP
        return await self.state_store._msg_flag(Code._2401, "_flags_2", 7)

    async def bit_3_7(self) -> bool | None:  # 3EF0 (byte 3, only OTB)
        return await self.state_store._msg_flag(Code._3EF0, "_flags_3", 7)

    async def bit_6_6(self) -> bool | None:  # 3EF0 ?dhw_enabled (byte 3, only R8820A?)
        return await self.state_store._msg_flag(Code._3EF0, "_flags_6", 6)

    async def percent(self) -> float | None:  # 2401 - WIP (~3150|FC)
        return cast(
            float | None,
            await self.state_store._msg_value(Code._2401, key=SZ_HEAT_DEMAND),
        )

    async def value(self) -> int | None:  # 2401 - WIP
        return cast(
            int | None, await self.state_store._msg_value(Code._2401, key="_value_2")
        )

    async def boiler_output_temp(self) -> float | None:  # 3220|19, or 3200
        return cast(
            float | None, await self._result_by_lookup(Code._3200, key=SZ_TEMPERATURE)
        )

    async def boiler_return_temp(self) -> float | None:  # 3220|1C, or 3210
        return cast(
            float | None, await self._result_by_lookup(Code._3210, key=SZ_TEMPERATURE)
        )

    async def boiler_setpoint(self) -> float | None:  # 3220|01, or 22D9
        return cast(
            float | None, await self._result_by_lookup(Code._22D9, key=SZ_SETPOINT)
        )

    async def ch_max_setpoint(self) -> float | None:  # 3220|39, or 1081
        return cast(
            float | None, await self._result_by_lookup(Code._1081, key=SZ_SETPOINT)
        )

    async def ch_setpoint(self) -> float | None:  # 3EF0 (byte 7, only R8820A?)
        return cast(
            float | None,
            self._result_by_value(
                None, await self.state_store._msg_value(Code._3EF0, key=SZ_CH_SETPOINT)
            ),
        )

    async def ch_water_pressure(self) -> float | None:  # 3220|12, or 1300
        return cast(
            float | None, await self._result_by_lookup(Code._1300, key=SZ_PRESSURE)
        )

    async def dhw_flow_rate(self) -> float | None:  # 3220|13, or 12F0
        return cast(
            float | None, await self._result_by_lookup(Code._12F0, key=SZ_DHW_FLOW_RATE)
        )

    async def dhw_setpoint(self) -> float | None:  # 3220|38, or 10A0
        return cast(
            float | None, await self._result_by_lookup(Code._10A0, key=SZ_SETPOINT)
        )

    async def dhw_temp(self) -> float | None:  # 3220|1A, or 1260
        return cast(
            float | None, await self._result_by_lookup(Code._1260, key=SZ_TEMPERATURE)
        )

    async def max_rel_modulation(self) -> float | None:  # 3220|0E, or 3EF0 (byte 8)
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                float | None,
                await self.state_store._msg_value(
                    Code._3EF0, key=SZ_MAX_REL_MODULATION
                ),
            )
        return cast(
            float | None,
            self._result_by_value(
                self._ot_msg_value(MsgId._0E),  # NOTE: not reliable?
                await self.state_store._msg_value(
                    Code._3EF0, key=SZ_MAX_REL_MODULATION
                ),
            ),
        )

    async def oem_code(self) -> float | None:  # 3220|73, no known RAMSES equivalent
        return cast(float | None, self._ot_msg_value(MsgId._73))

    async def outside_temp(self) -> float | None:  # 3220|1B, 1290
        return cast(
            float | None, await self._result_by_lookup(Code._1290, key=SZ_TEMPERATURE)
        )

    async def rel_modulation_level(self) -> float | None:  # 3220|11, or 3EF0/3EF1
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                float | None,
                await self.state_store._msg_value(
                    (Code._3EF0, Code._3EF1), key=self.MODULATION_LEVEL
                ),
            )
        return cast(
            float | None,
            self._result_by_value(
                self._ot_msg_value(MsgId._11),  # NOTE: not reliable?
                await self.state_store._msg_value(
                    (Code._3EF0, Code._3EF1), key=self.MODULATION_LEVEL
                ),
            ),
        )

    async def ch_active(self) -> bool | None:  # 3220|00, or 3EF0 (byte 3)
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                bool | None,
                await self.state_store._msg_value(Code._3EF0, key=SZ_CH_ACTIVE),
            )
        return cast(
            bool | None,
            self._result_by_value(
                self._ot_msg_flag(MsgId._00, 8 + 1),  # NOTE: not reliable?
                await self.state_store._msg_value(Code._3EF0, key=SZ_CH_ACTIVE),
            ),
        )

    async def ch_enabled(self) -> bool | None:  # 3220|00, or 3EF0 (byte 6)
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                bool | None,
                await self.state_store._msg_value(Code._3EF0, key=SZ_CH_ENABLED),
            )
        return cast(
            bool | None,
            self._result_by_value(
                self._ot_msg_flag(MsgId._00, 0),  # NOTE: not reliable?
                await self.state_store._msg_value(Code._3EF0, key=SZ_CH_ENABLED),
            ),
        )

    async def cooling_active(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None,
            self._result_by_value(self._ot_msg_flag(MsgId._00, 8 + 4), None),
        )

    async def cooling_enabled(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 2), None)
        )

    async def dhw_active(self) -> bool | None:  # 3220|00, or 3EF0 (byte 3)
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                bool | None,
                await self.state_store._msg_value(Code._3EF0, key=SZ_DHW_ACTIVE),
            )
        return cast(
            bool | None,
            self._result_by_value(
                self._ot_msg_flag(MsgId._00, 8 + 2),  # NOTE: not reliable?
                await self.state_store._msg_value(Code._3EF0, key=SZ_DHW_ACTIVE),
            ),
        )

    async def dhw_blocking(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 6), None)
        )

    async def dhw_enabled(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 1), None)
        )

    async def fault_present(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 8), None)
        )

    async def flame_active(self) -> bool | None:  # 3220|00, or 3EF0 (byte 3)
        if self._gwy.config.use_native_ot == "prefer":  # HACK: there'll always be 3EF0
            return cast(
                bool | None,
                await self.state_store._msg_value(Code._3EF0, key="flame_on"),
            )
        return cast(
            bool | None,
            self._result_by_value(
                self._ot_msg_flag(MsgId._00, 8 + 3),  # NOTE: not reliable?
                await self.state_store._msg_value(Code._3EF0, key="flame_on"),
            ),
        )

    async def otc_active(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 3), None)
        )

    async def summer_mode(self) -> bool | None:  # 3220|00, TODO: no known RAMSES
        return cast(
            bool | None, self._result_by_value(self._ot_msg_flag(MsgId._00, 5), None)
        )

    async def opentherm_schema(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            self._ot_msg_name(v): v.payload
            for k, v in self._msgs_ot.items()
            if self.discovery._supported_cmds_ctx.get(k)
            and int(k, 16) in SCHEMA_DATA_IDS
        }
        return {
            m: {k: v for k, v in p.items() if k.startswith(SZ_VALUE)}
            for m, p in result.items()
        }

    async def opentherm_counters(self) -> dict[str, Any]:  # all are U16
        return {
            SZ_BURNER_HOURS: self._ot_msg_value(MsgId._78),
            SZ_BURNER_STARTS: self._ot_msg_value(MsgId._74),
            SZ_BURNER_FAILED_STARTS: self._ot_msg_value(MsgId._71),
            SZ_CH_PUMP_HOURS: self._ot_msg_value(MsgId._79),
            SZ_CH_PUMP_STARTS: self._ot_msg_value(MsgId._75),
            SZ_DHW_BURNER_HOURS: self._ot_msg_value(MsgId._7B),
            SZ_DHW_BURNER_STARTS: self._ot_msg_value(MsgId._77),
            SZ_DHW_PUMP_HOURS: self._ot_msg_value(MsgId._7A),
            SZ_DHW_PUMP_STARTS: self._ot_msg_value(MsgId._76),
            SZ_FLAME_SIGNAL_LOW: self._ot_msg_value(MsgId._72),
        }  # 0x73 is not a counter: is OEM diagnostic code...

    async def opentherm_params(
        self,
    ) -> dict[str, Any]:  # F8_8, U8, {"hb": S8, "lb": S8}
        result = {
            self._ot_msg_name(v): v.payload
            for k, v in self._msgs_ot.items()
            if self.discovery._supported_cmds_ctx.get(k)
            and int(k, 16) in PARAMS_DATA_IDS
        }
        return {
            m: {k: v for k, v in p.items() if k.startswith(SZ_VALUE)}
            for m, p in result.items()
        }

    async def opentherm_status(
        self,
    ) -> dict[str, Any]:  # F8_8, U16 (only OEM_CODE) or bool
        return {  # most these are in: STATUS_DATA_IDS
            SZ_BOILER_OUTPUT_TEMP: self._ot_msg_value(MsgId._19),
            SZ_BOILER_RETURN_TEMP: self._ot_msg_value(MsgId._1C),
            SZ_BOILER_SETPOINT: self._ot_msg_value(MsgId._01),
            # SZ_CH_MAX_SETPOINT: self._ot_msg_value(MsgId._39),  # in PARAMS_DATA_IDS
            SZ_CH_WATER_PRESSURE: self._ot_msg_value(MsgId._12),
            SZ_DHW_FLOW_RATE: self._ot_msg_value(MsgId._13),
            # SZ_DHW_SETPOINT: self._ot_msg_value(MsgId._38),  # in PARAMS_DATA_IDS
            SZ_DHW_TEMP: self._ot_msg_value(MsgId._1A),
            SZ_OEM_CODE: self._ot_msg_value(MsgId._73),
            SZ_OUTSIDE_TEMP: self._ot_msg_value(MsgId._1B),
            SZ_REL_MODULATION_LEVEL: self._ot_msg_value(MsgId._11),
            #
            # SZ...: self._ot_msg_value(MsgId._05),  # in STATUS_DATA_IDS
            # SZ...: self._ot_msg_value(MsgId._18),  # in STATUS_DATA_IDS
            #
            SZ_CH_ACTIVE: self._ot_msg_flag(MsgId._00, 8 + 1),
            SZ_CH_ENABLED: self._ot_msg_flag(MsgId._00, 0),
            SZ_COOLING_ACTIVE: self._ot_msg_flag(MsgId._00, 8 + 4),
            SZ_COOLING_ENABLED: self._ot_msg_flag(MsgId._00, 2),
            SZ_DHW_ACTIVE: self._ot_msg_flag(MsgId._00, 8 + 2),
            SZ_DHW_BLOCKING: self._ot_msg_flag(MsgId._00, 6),
            SZ_DHW_ENABLED: self._ot_msg_flag(MsgId._00, 1),
            SZ_FAULT_PRESENT: self._ot_msg_flag(MsgId._00, 8),
            SZ_FLAME_ACTIVE: self._ot_msg_flag(MsgId._00, 8 + 3),
            SZ_SUMMER_MODE: self._ot_msg_flag(MsgId._00, 5),
            SZ_OTC_ACTIVE: self._ot_msg_flag(MsgId._00, 3),
        }

    async def ramses_schema(self) -> PayDictT.EMPTY:
        return {}

    async def ramses_params(self) -> dict[str, float | None]:
        return {
            SZ_MAX_REL_MODULATION: await self.max_rel_modulation(),
        }

    async def ramses_status(self) -> dict[str, Any]:
        return {
            SZ_BOILER_OUTPUT_TEMP: await self.state_store._msg_value(
                Code._3200, key=SZ_TEMPERATURE
            ),
            SZ_BOILER_RETURN_TEMP: await self.state_store._msg_value(
                Code._3210, key=SZ_TEMPERATURE
            ),
            SZ_BOILER_SETPOINT: await self.state_store._msg_value(
                Code._22D9, key=SZ_SETPOINT
            ),
            SZ_CH_MAX_SETPOINT: await self.state_store._msg_value(
                Code._1081, key=SZ_SETPOINT
            ),
            SZ_CH_SETPOINT: await self.state_store._msg_value(
                Code._3EF0, key=SZ_CH_SETPOINT
            ),
            SZ_CH_WATER_PRESSURE: await self.state_store._msg_value(
                Code._1300, key=SZ_PRESSURE
            ),
            SZ_DHW_FLOW_RATE: await self.state_store._msg_value(
                Code._12F0, key=SZ_DHW_FLOW_RATE
            ),
            SZ_DHW_SETPOINT: await self.state_store._msg_value(
                Code._1300, key=SZ_SETPOINT
            ),
            SZ_DHW_TEMP: await self.state_store._msg_value(
                Code._1260, key=SZ_TEMPERATURE
            ),
            SZ_OUTSIDE_TEMP: await self.state_store._msg_value(
                Code._1290, key=SZ_TEMPERATURE
            ),
            SZ_REL_MODULATION_LEVEL: await self.state_store._msg_value(
                (Code._3EF0, Code._3EF1), key=self.MODULATION_LEVEL
            ),
            #
            SZ_CH_ACTIVE: await self.state_store._msg_value(
                Code._3EF0, key=SZ_CH_ACTIVE
            ),
            SZ_CH_ENABLED: await self.state_store._msg_value(
                Code._3EF0, key=SZ_CH_ENABLED
            ),
            SZ_DHW_ACTIVE: await self.state_store._msg_value(
                Code._3EF0, key=SZ_DHW_ACTIVE
            ),
            SZ_FLAME_ACTIVE: await self.state_store._msg_value(
                Code._3EF0, key=SZ_FLAME_ACTIVE
            ),
        }

    async def traits(self) -> dict[str, Any]:
        base_traits = await super().traits()
        return {
            **base_traits,
            "opentherm_traits": await self.discovery.supported_cmds_ot(),
            "ramses_ii_traits": await self.discovery.supported_cmds(),
        }

    async def schema(self) -> dict[str, Any]:
        base_schema = await super().schema()
        return {
            **base_schema,
            "opentherm_schema": await self.opentherm_schema(),
            "ramses_ii_schema": await self.ramses_schema(),
        }

    async def params(self) -> dict[str, Any]:
        base_params = await super().params()
        return {
            **base_params,
            "opentherm_params": await self.opentherm_params(),
            "ramses_ii_params": await self.ramses_params(),
        }

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,  # incl. actuator_cycle, actuator_state
            #
            SZ_BOILER_OUTPUT_TEMP: await self.boiler_output_temp(),
            SZ_BOILER_RETURN_TEMP: await self.boiler_return_temp(),
            SZ_BOILER_SETPOINT: await self.boiler_setpoint(),
            SZ_CH_SETPOINT: await self.ch_setpoint(),
            SZ_CH_MAX_SETPOINT: await self.ch_max_setpoint(),
            SZ_CH_WATER_PRESSURE: await self.ch_water_pressure(),
            SZ_DHW_FLOW_RATE: await self.dhw_flow_rate(),
            SZ_DHW_SETPOINT: await self.dhw_setpoint(),
            SZ_DHW_TEMP: await self.dhw_temp(),
            SZ_OEM_CODE: await self.oem_code(),
            SZ_OUTSIDE_TEMP: await self.outside_temp(),
            SZ_REL_MODULATION_LEVEL: await self.rel_modulation_level(),
            #
            SZ_CH_ACTIVE: await self.ch_active(),
            SZ_CH_ENABLED: await self.ch_enabled(),
            SZ_COOLING_ACTIVE: await self.cooling_active(),
            SZ_COOLING_ENABLED: await self.cooling_enabled(),
            SZ_DHW_ACTIVE: await self.dhw_active(),
            SZ_DHW_BLOCKING: await self.dhw_blocking(),
            SZ_DHW_ENABLED: await self.dhw_enabled(),
            SZ_FAULT_PRESENT: await self.fault_present(),
            SZ_FLAME_ACTIVE: await self.flame_active(),
            SZ_SUMMER_MODE: await self.summer_mode(),
            SZ_OTC_ACTIVE: await self.otc_active(),
            #
            # "status_opentherm": await self.opentherm_status(),
            # "status_ramses_ii": await self.ramses_status(),
        }


class Thermostat(BatteryState, Setpoint, Temperature, Fakeable):  # THM (..):
    """The THM/STA class, such as a TR87RF."""

    _SLUG = DevType.THM
    _STATE_ATTR = SZ_TEMPERATURE

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)

        if msg.verb != I_ or self._iz_controller is not None:
            return

        # NOTE: this has only been tested on a 12:, does it work for a 34: too?
        if all(
            (
                msg._addrs[0] is self.addr,
                msg._addrs[1] is NON_DEV_ADDR,
                msg._addrs[2] is self.addr,
            )
        ):
            if self._iz_controller is None:
                # _LOGGER.info(f"{msg!r} # IS_CONTROLLER (10): is FALSE")
                self._iz_controller = False
            elif self._iz_controller:
                raise exc.SystemInconsistent(
                    f"{msg!r} # IS_CONTROLLER (11): was TRUE, now False"
                )

            if msg.code in CODES_ONLY_FROM_CTL:
                raise exc.PacketInvalid(f"{msg!r} # IS_CONTROLLER (12); is CORRUPT PKT")

        elif all(
            (
                msg._addrs[0] is NON_DEV_ADDR,
                msg._addrs[1] is NON_DEV_ADDR,
                msg._addrs[2] is self.addr,
            )
        ):
            if self._iz_controller is None:
                # _LOGGER.info(f"{msg!r} # IS_CONTROLLER (20): is TRUE")
                self._iz_controller = msg
                self._make_tcs_controller(msg=msg)
            elif self._iz_controller is False:
                raise exc.SystemInconsistent(
                    f"{msg!r} # IS_CONTROLLER (21): was FALSE, now True"
                )

    async def initiate_binding_process(self) -> Packet:
        return await super()._initiate_binding_process(
            (Code._2309, Code._30C9, Code._0008)
        )


class BdrSwitch(Actuator, RelayDemand):  # BDR (13):
    """The BDR class, such as a BDR91.

    BDR91s can be used in six distinct modes, including:

    - x2 boiler controller (FC/TPI): either traditional, or newer heat pump-aware
    - x1 electric heat zones (0x/ELE)
    - x1 zone valve zones (0x/VAL)
    - x2 DHW thingys (F9/DHW, FA/DHW)
    """

    ACTIVE: Final = "active"
    TPI_PARAMS: Final = "tpi_params"

    _SLUG = DevType.BDR
    _STATE_ATTR = "active"

    # def __init__(self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any) -> None:
    #     super().__init__(*args, traits=traits, **kwargs)

    #     if kwargs.get(SZ_DOMAIN_ID) == FC:  # TODO: F9/FA/FC, zone_idx
    #         self.ctl._set_app_cntrl(self)

    def _setup_discovery_cmds(self) -> None:
        """Discover BDRs.

        The BDRs have one of six roles:
         - heater relay *or* a heat pump relay (alternative to an OTB)
         - DHW hot water valve *or* DHW heating valve
         - Zones: Electric relay *or* Zone valve relay

        They all seem to respond thus (TODO: heat pump/zone valve relay):
         - all BDR91As will (erractically) RP to these RQs
             0016, 1FC9 & 0008, 1100, 3EF1
         - all BDR91As will *not* RP to these RQs
             0009, 10E0, 3B00, 3EF0
         - a BDR91A will *periodically* send an I/3B00/00C8 if it is the heater relay
        """

        super()._setup_discovery_cmds()

        if self.is_faked:
            return

        self.discovery.add_cmd(Command.get_tpi_params(self.id), 6 * 3600)  # params
        self.discovery.add_cmd(
            Command.from_attrs(RQ, self.id, Code._3EF1, PayloadT("00")),
            60 if self._child_id in (F9, FA, FC) else 300,
        )  # status

    async def active(self) -> bool | None:  # 3EF0, 3EF1
        """Return the actuator's current state."""
        result = await self.state_store._msg_value(
            (Code._3EF0, Code._3EF1), key=self.MODULATION_LEVEL
        )
        return None if result is None else bool(result)

    async def role(self) -> str | None:
        """Return the role of the BDR91A (there are six possibilities)."""

        # TODO: use self._parent?
        if self._child_id in DOMAIN_TYPE_MAP:
            return DOMAIN_TYPE_MAP[self._child_id]
        elif self._parent and isinstance(self._parent, Zone):
            # TODO: remove need for isinstance
            return self._parent.heating_type

        # if Code._3B00 in _msgs and _msgs[Code._3B00].verb == I_:
        #     self._is_tpi = True
        # if Code._1FC9 in _msgs and _msgs[Code._1FC9].verb == RP:
        #     if Code._3B00 in _msgs[Code._1FC9].raw_payload:
        #         self._is_tpi = True

        return None

    async def tpi_params(self) -> PayDictT._10A0 | None:
        return cast(
            PayDictT._10A0 | None, await self.state_store._msg_value(Code._1100)
        )

    async def schema(self) -> dict[str, Any]:
        base_schema = await super().schema()
        return {
            **base_schema,
            "role": await self.role(),
        }

    async def params(self) -> dict[str, Any]:
        base_params = await super().params()
        return {
            **base_params,
            self.TPI_PARAMS: await self.tpi_params(),
        }

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.ACTIVE: await self.active(),
        }


class TrvActuator(BatteryState, HeatDemand, Setpoint, Temperature):  # TRV (04):
    """The TRV class, such as a HR92."""

    WINDOW_OPEN: Final = SZ_WINDOW_OPEN

    _SLUG = DevType.TRV
    _STATE_ATTR = SZ_HEAT_DEMAND

    async def heat_demand(self) -> float | None:  # 3150
        if (heat_demand := await super().heat_demand()) is None:
            if (
                await self.state_store._msg_value(Code._3150) is None
                and await self.setpoint() is False
            ):
                return 0  # instead of None (no 3150s sent when setpoint is False)
        return heat_demand

    async def window_open(self) -> bool | None:  # 12B0
        return cast(
            bool | None,
            await self.state_store._msg_value(Code._12B0, key=self.WINDOW_OPEN),
        )

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.WINDOW_OPEN: await self.window_open(),
        }


class JimDevice(Actuator):  # BDR (08):
    _SLUG: str = DevType.JIM
    _STATE_ATTR = None


class JstDevice(RelayDemand):  # BDR (31):
    _SLUG: str = DevType.JST
    _STATE_ATTR = None


class UfhCircuit(Child, Entity):  # FIXME
    """The UFH circuit class (UFC:circuit is much like CTL/TCS:zone).

    NOTE: for circuits, there's a difference between :
     - `self.ctl`: the UFH controller, and
     - `self.tcs.ctl`: the Evohome controller
    """

    _SLUG: str = None
    _STATE_ATTR = None

    def __init__(self, ufc: UfhController, ufh_idx: str) -> None:
        super().__init__(ufc._gwy)

        # FIXME: gwy.msg_db entities must know their parent device ID and their own idx
        self._z_id = ufc.id
        self._z_idx = ufh_idx

        self.id: str = f"{ufc.id}_{ufh_idx}"

        self.ufc: UfhController = ufc
        self._child_id = ufh_idx

        # TODO: _ctl should be: .ufc? .ctl?
        self._ctl: Controller = None
        self._zone: Zone | None = None

    # def __str__(self) -> str:
    #     return f"{self.id} ({self._zone and self._zone._child_id})"

    def _update_schema(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)

        if msg.code != Code._000C or not msg.payload[SZ_DEVICES]:  # zone_devices
            return

        # FIXME: is messy
        if not (dev_ids := msg.payload[SZ_DEVICES]):
            return
        if len(dev_ids) != 1:
            raise exc.PacketPayloadInvalid("No devices")

        # ctl = self._gwy.device_by_id.get(dev_ids[0])
        ctl: Controller = self._gwy.get_device(dev_ids[0])
        if not ctl or (self._ctl and self._ctl is not ctl):
            raise exc.PacketPayloadInvalid("No CTL")
        self._ctl = ctl

        ctl._make_tcs_controller()
        # self.set_parent(ctl.tcs)

        zon = ctl.tcs.get_htg_zone(msg.payload[SZ_ZONE_IDX])
        if not zon:
            raise exc.PacketPayloadInvalid("No Zone")
        if self._zone and self._zone is not zon:
            raise exc.PacketPayloadInvalid("Wrong Zone")
        self._zone = zon

        if self.ufc not in self._zone.actuators:
            schema = {SZ_ACTUATORS: [self.ufc.id], SZ_CIRCUITS: [self.id]}
            self._zone._update_schema(**schema)

    @property
    def ufx_idx(self) -> str:
        return self._child_id

    @property
    def zone_idx(self) -> str | None:
        if self._zone:
            return self._zone._child_id
        return None


# e.g. {"CTL": Controller}
HEAT_CLASS_BY_SLUG: dict[str, type[DeviceHeat]] = class_by_attr(__name__, "_SLUG")

_HEAT_VC_PAIR_BY_CLASS = {
    DevType.DHW: ((I_, Code._1260),),
    DevType.OTB: ((I_, Code._3220), (RP, Code._3220)),
}


def class_dev_heat(
    dev_addr: Address, *, msg: Message | None = None, eavesdrop: bool = False
) -> type[DeviceHeat]:
    """Return a device class, but only if the device must be from the CH/DHW group.

    May return a device class, DeviceHeat (which will need promotion).
    """

    if dev_addr.type in DEV_TYPE_MAP.THM_DEVICES:
        return HEAT_CLASS_BY_SLUG[DevType.THM]

    try:
        slug = DEV_TYPE_MAP.slug(dev_addr.type)
    except KeyError:
        pass
    else:
        return HEAT_CLASS_BY_SLUG[slug]

    if not eavesdrop:
        raise exc.DeviceNotRecognised(
            f"No CH/DHW class for: {dev_addr} (no eavesdropping)"
        )

    if msg and msg.code in CODES_OF_HEAT_DOMAIN_ONLY:
        return DeviceHeat

    raise exc.DeviceNotRecognised(
        f"No CH/DHW class for: {dev_addr} (unknown type: {dev_addr.type})"
    )
