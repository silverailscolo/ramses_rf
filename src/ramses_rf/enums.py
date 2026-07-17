"""RAMSES RF - Cross-domain enumerations for the L7 event pipeline."""

from enum import StrEnum


class Topic(StrEnum):
    """Event Bus routing discriminators."""

    RAW_EVENT = "raw_event"
    STATE_UPDATE = "state_update"
    TOPOLOGY_DISCOVERY = "topology_discovery"


class Action(StrEnum):
    """Standardized intents for outbound commands."""

    GET_ZONE_NAME = "get_zone_name"
    SET_ZONE_NAME = "set_zone_name"
    GET_ZONE_CONFIG = "get_zone_config"
    SET_ZONE_CONFIG = "set_zone_config"
    GET_WINDOW_STATE = "get_window_state"
    GET_SETPOINT = "get_setpoint"
    SET_SETPOINT = "set_setpoint"
    GET_MODE = "get_mode"
    SET_MODE = "set_mode"
    GET_ZONE_TEMP = "get_zone_temp"
    SET_TEMPERATURE = "set_temperature"

    GET_DHW_PARAMS = "get_dhw_params"
    SET_DHW_PARAMS = "set_dhw_params"
    GET_DHW_TEMP = "get_dhw_temp"
    PUT_DHW_TEMP = "put_dhw_temp"
    GET_DHW_MODE = "get_dhw_mode"
    SET_DHW_MODE = "set_dhw_mode"

    PUT_CO2_LEVEL = "put_co2_level"
    PUT_INDOOR_HUMIDITY = "put_indoor_humidity"
    SET_FAN_MODE = "set_fan_mode"
    SET_BYPASS_POSITION = "set_bypass_position"
    SET_FAN_PARAM = "set_fan_param"
    GET_FAN_PARAM = "get_fan_param"
    GET_HVAC_FAN_31DA = "get_hvac_fan_31da"


class TopologyAction(StrEnum):
    """Structural graph mutation actions."""

    PROMOTE_CLASS = "promote_class"
    UPDATE_TRAITS = "update_traits"
    BIND_DEVICE = "bind_device"
    CREATE_CONTROLLER = "create_controller"
    CREATE_CIRCUIT = "create_circuit"
