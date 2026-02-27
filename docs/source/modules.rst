ramses_rf/src/
==============

.. mermaid::

    classDiagram
        direction RL

        namespace ramses_rf-dispatcher{
            class Dispatcher{
                + create_device()
                + ..
                + process_msg()
            }
        }
        namespace ramses_rf-database{
            class Database {
                - add(msg)
                - ..
                - qry(msg)
                - ..
                - rem(msg)
            }
        }
        namespace ramses_rf-device{
            class heat
            class hvac
        }
        namespace ramses_rf-gateway{
            class hgi
        }
        namespace ramses_tx-message{
            class Message {
                - parse_message()
                - ..
                - parse_payload()
                - ..
                - validate_msg()
            }
        }
        namespace ramses_tx-command{
            class Command{
                - _from_attrs
                - ..
                - set_zone_config
            }
        }
        namespace ramses_tx-gateway-engine{
            class Engine {
                - add_msg_handler()
                - ..
                - create_cmd()
                - ..
                - async_send_cmd()
            }
        }
        namespace ramses_tx-transport{
            class Transport {
                - factory
                - base
                - file
                - mqtt
                - port
                - ...
            }
        }
        namespace ramses_ESP{
            class RF:::esp
            class Serial:::esp
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

        click Transport href "ramses_tx.transport.html" "docs"
        click Engine href "ramses_tx.html#module-ramses_tx.gateway" "docs"
        click hgi href "ramses_rf.html#module-ramses_rf.gateway" "docs"
        click Database href "ramses_rf.html#module-ramses_rf.database" "docs"
        click Message href "ramses_tx.html#module-ramses_tx.message" "docs"
        click heat href "ramses_rf.device.html#module-ramses_rf.device.heat" "docs"
        click hvac href "ramses_rf.device.html#module-ramses_rf.device.hvac" "docs"
        click Dispatcher href "ramses_rf.html#module-ramses_rf.dispatcher" "docs"
        click Command href "ramses_tx.html#module-ramses_tx.command" "docs"

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   ramses_cli
   ramses_rf
   ramses_tx
