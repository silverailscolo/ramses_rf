ramses_rf/src/
===

.. toctree::
   :maxdepth: 4

   ramses_cli
   ramses_rf
   ramses_tx

.. {mermaid}::

    ---
    title: ramses-rf packages
    ---
    classDiagram
        namespace ramses_rf.dispatcher{
            class Dispatcher{
                + create_device()
                + ..
                + process_msg()
            }
        }
        namespace ramses_rf.database{
            class Database {
                - add(msg)
                - ..
                - qry(msg)
                - ..
                - rem(msg)
            }
        }
        namespace ramses_rf.device{
            class heat
            class hvac
        }
        namespace ramses_rf.gateway{
            class hgi
        }
        namespace ramses_tx.message{
            class Message {
                - parse_message()
                - ..
                - parse_payload()
                - ..
                - validate_msg()
            }
        }
        namespace ramses_tx.command{
            class Command{
                - _from_attrs
                - ..
                - set_zone_config
            }
        }
        namespace ramses_tx.gateway-engine{
            class Engine {
                - add_msg_handler()
                - ..
                - create_cmd()
                - ..
                - async_send_cmd()
            }
        }
        namespace ramses_tx.transport{
            class Transport {
                - MqttTransport
                - ..
                - PortTransport
            }
        }
        namespace ramses_ESP{
            class RF
            class Serial
        }

        Transport <|--|> Serial
        Transport <|--|> RF
        Transport <|--|> Engine
        Engine <|--|> hgi
        Database <|--|> hgi
        Message <|--|> hgi
        heat <|--|> hgi
        hvac <|--|> hgi
        Dispatcher <|--|> hvac
        Dispatcher <|--|> heat
        Dispatcher <|--|> Message
