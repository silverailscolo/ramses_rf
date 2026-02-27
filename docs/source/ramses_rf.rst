ramses\_rf package
==================

Subpackages
-----------

.. toctree::
   :maxdepth: 4

   ramses_rf.device
   ramses_rf.system

Submodules
----------

ramses\_rf.binding\_fsm module
------------------------------

.. automodule:: ramses_rf.binding_fsm
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.const module
-----------------------

.. automodule:: ramses_rf.const
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.database module
--------------------------

.. mermaid::
    erDiagram
        msg_db ||--o{ device : query

        msg_db {
            TEXT(26)* dtm
            TEXT(2) verb
            TEXT(9) src
            TEXT(9) dst
            TEXT(4) code
            TEXT() ctx
            TEXT() hdr
        }

.. automodule:: ramses_rf.database
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.dispatcher module
----------------------------

.. automodule:: ramses_rf.dispatcher
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.entity\_base module
------------------------------

.. automodule:: ramses_rf.entity_base
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.exceptions module
----------------------------

.. automodule:: ramses_rf.exceptions
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.gateway module
-------------------------

.. automodule:: ramses_rf.gateway
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.helpers module
-------------------------

.. automodule:: ramses_rf.helpers
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.interfaces module
----------------------------

.. automodule:: ramses_rf.interfaces
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.schemas module
-------------------------

.. automodule:: ramses_rf.schemas
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.storage module
-------------------------

.. automodule:: ramses_rf.storage
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.typing module
------------------------

.. automodule:: ramses_rf.typing
   :members:
   :show-inheritance:
   :undoc-members:

ramses\_rf.version module
-------------------------

.. automodule:: ramses_rf.version
   :members:
   :show-inheritance:
   :undoc-members:

Module contents
---------------

.. automodule:: ramses_rf
   :members:
   :show-inheritance:
   :undoc-members:
