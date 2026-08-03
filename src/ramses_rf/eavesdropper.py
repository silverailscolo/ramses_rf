"""RAMSES RF - Eavesdropping Engine.

Isolated component for telemetry-driven heuristic topology inference.
Runs only when `gwy.config.enable_eavesdrop` is True.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta as td
from typing import TYPE_CHECKING, Any

import ramses_rf.exceptions as exc
from ramses_rf.const import SZ_TEMPERATURE, SZ_ZONE_IDX
from ramses_rf.devices import Device, Temperature
from ramses_tx import Code
from ramses_tx.address import HGI_DEV_ADDR
from ramses_tx.typing import DeviceIdT

if TYPE_CHECKING:
    from ramses_rf import Gateway
    from ramses_rf.messages import Message


class EavesdropEngine:
    """Heuristic eavesdropping engine for un-bound log replay."""

    def __init__(self, gwy: Gateway) -> None:
        """Initialize the eavesdropping engine.

        :param gwy: The Gateway instance.
        :type gwy: Gateway
        """
        self._gwy: Gateway = gwy
        self._prev_30c9_map: dict[str, Message] = {}

    def eavesdrop_referenced_devices(self, msg: Message) -> None:
        """Instantiate implicitly referenced header devices during eavesdropping.

        :param msg: The incoming message.
        :type msg: Message
        """
        if not getattr(self._gwy.config, "enable_eavesdrop", False):
            return

        registry = getattr(self._gwy, "device_registry", None)
        if not registry:
            return

        hgi_id = self._gwy.hgi.id if self._gwy.hgi else None
        dst_dev = registry.device_by_id.get(msg.dst.id)

        if dst_dev is None and msg.src.id != hgi_id:
            with contextlib.suppress(exc.DeviceNotFoundError):
                registry.get_device(msg.dst.id)

        addrs_to_check = [msg.src.id, msg.dst.id]
        if hasattr(msg, "_dto") and msg._dto:
            addrs_to_check.extend(
                [
                    DeviceIdT(msg._dto.addr1),
                    DeviceIdT(msg._dto.addr2),
                    DeviceIdT(msg._dto.addr3),
                ]
            )

        for addr_id in dict.fromkeys(addrs_to_check):
            if addr_id and addr_id not in ("--:------", "63:262142"):
                if (
                    self._gwy.config.engine.enforce_known_list
                    and addr_id[:2] == "18"
                    and addr_id != HGI_DEV_ADDR.id
                    and addr_id != hgi_id
                ):
                    continue
                with contextlib.suppress(exc.DeviceNotFoundError):
                    registry.get_device(addr_id)

    def _get_tcs(self, msg: Message) -> Any:
        """Find the active TCS read-model instance.

        :param msg: The incoming message.
        :type msg: Message
        :returns: The active TCS instance if found.
        :rtype: Any
        """
        if tcs := getattr(msg.src, "tcs", None):
            return tcs
        if tcs := getattr(msg.dst, "tcs", None):
            return tcs
        if ctl := getattr(msg.src, "ctl", None):
            if tcs := getattr(ctl, "tcs", None):
                return tcs
        if ctl := getattr(msg.dst, "ctl", None):
            if tcs := getattr(ctl, "tcs", None):
                return tcs
        if tcs := getattr(self._gwy, "tcs", None):
            return tcs

        registry = getattr(self._gwy, "device_registry", None)
        if registry:
            ctls = [
                d
                for d in list(registry.device_by_id.values())
                if (
                    getattr(d, "_SLUG", "") == "CTL" or getattr(d, "type", None) == "01"
                )
                and hasattr(d, "tcs")
                and d.tcs is not None
            ]
            if len(ctls) == 1:
                return ctls[0].tcs
        return None

    async def process_eavesdrop(self, msg: Message) -> None:
        """Process an incoming message for heuristic eavesdropping.

        :param msg: The incoming message.
        :type msg: Message
        """
        if not getattr(self._gwy.config, "enable_eavesdrop", False):
            return

        tcs = self._get_tcs(msg)

        # 1. Telemetry-driven Sensor/Actuator Linking
        # NOTE: Do NOT prematurely bind msg.src.id to zone based on telemetry,
        # as 000C binding packets and temperature correlation handle authoritative parenting.

        # 2. 30C9 Temperature Broadcast Correlation
        if msg.code == Code._30C9 and tcs:
            ctl_id = str(getattr(tcs.ctl, "id", ""))
            prev = self._prev_30c9_map.get(ctl_id)

            if msg._has_array:
                await self._eavesdrop_from_controller_broadcast(tcs, msg, prev)
                self._prev_30c9_map[ctl_id] = msg
            elif getattr(msg.src, "type", None) in ("03", "04", "12", "22", "34"):
                await self._eavesdrop_from_trv_broadcast(tcs, msg)

    async def _eavesdrop_from_controller_broadcast(
        self, tcs: Any, msg: Message, prev: Message | None
    ) -> None:
        """Correlate recently heard TRV temperatures against a new zone array.

        :param tcs: The target TCS read-model.
        :type tcs: Any
        :param msg: The incoming 30C9 array message from the controller.
        :type msg: Message
        :param prev: The previous 30C9 array message to check changes.
        :type prev: Message | None
        """
        if prev is None:
            return

        # TODO: use msgz/I, not RP
        secs = await tcs.entity_state.get_value(Code._1F09, key="remaining_seconds")
        if not isinstance(secs, (int, float)):
            secs = 300.0
        if msg.dtm > prev.dtm + td(seconds=secs + 5):
            # can only compare against 30C9 pkt from the last cycle
            return

        # zones with changed temps
        changed_zones: dict[str, float] = {
            z.get(SZ_ZONE_IDX): z.get(SZ_TEMPERATURE)
            for z in msg.payload
            if z not in prev.payload and z.get(SZ_TEMPERATURE) is not None
        }
        if not changed_zones:
            # ctl's 30C9 says no zones have changed temps during this cycle
            return

        def _testable_zones(chg_zones: dict[str, float]) -> dict[float, str]:
            res: dict[float, str] = {}
            for i1, t1 in chg_zones.items():
                zone = tcs.zone_by_idx.get(i1) or (
                    tcs.get_htg_zone(i1) if hasattr(tcs, "get_htg_zone") else None
                )
                if (
                    zone is not None
                    and zone.sensor is None
                    and t1 not in [t2 for i2, t2 in chg_zones.items() if i2 != i1]
                ):
                    res[t1] = i1
            return res

        testable_zones = _testable_zones(changed_zones)
        if not testable_zones:
            return  # no testable zones

        testable_sensors_map: dict[float, list[Device]] = {}
        for d in self._gwy.device_registry.devices:
            if isinstance(d, Temperature) and d.ctl in (tcs.ctl, None):
                d_temp = await d.temperature()
                if d_temp is not None:
                    if d_temp not in testable_sensors_map:
                        testable_sensors_map[d_temp] = []
                    testable_sensors_map[d_temp].append(d)

        # COLLISION ABSTENTION: Drop temperatures reported by multiple sensors unless one is dedicated
        unique_sensors: dict[float, Device] = {}
        for temp_val, devs in testable_sensors_map.items():
            if len(devs) == 1:
                unique_sensors[temp_val] = devs[0]
            else:
                dedicated = [
                    d for d in devs if not str(getattr(d, "id", "")).startswith("04:")
                ]
                if len(dedicated) == 1:
                    unique_sensors[temp_val] = dedicated[0]

        if not unique_sensors:
            return  # no unique testable sensors available, must abstain

        matched_pairs = {
            sensor: zone_idx
            for temp_z, zone_idx in testable_zones.items()
            for temp_s, sensor in unique_sensors.items()
            if temp_z == temp_s
        }

        for sensor, zone_idx in matched_pairs.items():
            zone = tcs.zone_by_idx[zone_idx]
            if getattr(sensor, "_parent", None) is not None and getattr(
                sensor._parent, "id", None
            ) != getattr(zone, "id", None):
                continue
            with contextlib.suppress(
                exc.DeviceNotFoundError,
                exc.SchemaInconsistentError,
                exc.SystemSchemaInconsistent,
            ):
                self._gwy.device_registry.get_device(
                    sensor.id, parent=zone, is_sensor=True
                )

        # now see if we can allocate the controller as a sensor...
        if any(z for z in tcs.zones if z.sensor is tcs.ctl):
            return  # the controller is already a sensor

        remaining_zones = _testable_zones(changed_zones)
        if len(remaining_zones) != 1:
            return  # no testable zones

        temp, zone_idx = tuple(remaining_zones.items())[0]

        # can safely(?) assume this zone is using the CTL as a sensor...
        if not [s for s in unique_sensors if s == temp]:
            zone = tcs.zone_by_idx[zone_idx]
            with contextlib.suppress(
                exc.DeviceNotFoundError,
                exc.SchemaInconsistentError,
                exc.SystemSchemaInconsistent,
            ):
                self._gwy.device_registry.get_device(
                    tcs.ctl.id, parent=zone, is_sensor=True
                )

    async def _eavesdrop_from_trv_broadcast(self, tcs: Any, msg: Message) -> None:
        """Correlate a new TRV temperature broadcast against known zones.

        :param tcs: The target TCS read-model.
        :type tcs: Any
        :param msg: The incoming 30C9 message from a TRV.
        :type msg: Message
        """
        if not isinstance(msg.payload, dict):
            return

        dev = self._gwy.device_registry.device_by_id.get(msg.src.id)
        if dev is not None and getattr(dev, "_parent", None) is not None:
            return

        trv_temp = msg.payload.get(SZ_TEMPERATURE)
        if trv_temp is None:
            return

        matching_zones = []
        for zone in tcs.zones:
            if zone._sensor is None:
                zone_temp = await zone.temperature()
                if zone_temp == trv_temp:
                    matching_zones.append(zone)

        # COLLISION ABSTENTION: Bind only if exactly one zone matches this temp
        if len(matching_zones) == 1:
            with contextlib.suppress(
                exc.DeviceNotFoundError,
                exc.SchemaInconsistentError,
                exc.SystemSchemaInconsistent,
            ):
                self._gwy.device_registry.get_device(
                    msg.src.id, parent=matching_zones[0], is_sensor=True
                )
