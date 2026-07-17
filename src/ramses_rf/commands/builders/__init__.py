"""RAMSES RF - Intent-to-DTO Translation Builders.

This package houses the pure L7-to-L3 payload translation logic.
"""

from collections.abc import Callable

from ramses_rf.commands.core import Command
from ramses_rf.enums import Action
from ramses_tx.dtos import CommandDTO

from . import dhw, heat, hvac, zones

# Maps an Action intent to the appropriate payload constructor.
BUILDERS: dict[Action, Callable[[Command], CommandDTO]] = {
    # DHW Commands
    Action.GET_DHW_PARAMS: dhw.build_get_dhw_params,
    Action.SET_DHW_PARAMS: dhw.build_set_dhw_params,
    Action.GET_DHW_TEMP: dhw.build_get_dhw_temp,
    Action.PUT_DHW_TEMP: dhw.build_put_dhw_temp,
    Action.GET_DHW_MODE: dhw.build_get_dhw_mode,
    Action.SET_DHW_MODE: dhw.build_set_dhw_mode,
    # HVAC Commands
    Action.PUT_CO2_LEVEL: hvac.build_put_co2_level,
    Action.PUT_INDOOR_HUMIDITY: hvac.build_put_indoor_humidity,
    Action.SET_FAN_MODE: hvac.build_set_fan_mode,
    Action.SET_BYPASS_POSITION: hvac.build_set_bypass_position,
    Action.SET_FAN_PARAM: hvac.build_set_fan_param,
    Action.GET_FAN_PARAM: hvac.build_get_fan_param,
    Action.GET_HVAC_FAN_31DA: hvac.build_get_hvac_fan_31da,
    # Heat Commands
    Action.PUT_OUTDOOR_TEMP: heat.build_put_outdoor_temp,
    Action.PUT_DHW_TEMP: heat.build_put_dhw_temp,
    Action.PUT_SENSOR_TEMP: heat.build_put_sensor_temp,
    # Zone Commands
    Action.SET_TEMPERATURE: zones.build_set_temperature,
    Action.SET_MODE: zones.build_set_mode,
    Action.SET_ZONE_NAME: zones.build_set_name,
    Action.SET_ZONE_CONFIG: zones.build_set_config,
}


def build_dto(intent: Command) -> CommandDTO:
    """Translate an L7 Command intent into a strict L3 CommandDTO.

    :param intent: The high-level domain intent.
    :return: The low-level modem instruction.
    :raises NotImplementedError: If no builder is mapped for the action.
    """
    builder = BUILDERS.get(intent.action)
    if not builder:
        raise NotImplementedError(
            f"No translation builder registered for intent action: {intent.action}"
        )
    return builder(intent)
