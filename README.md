[![Linting](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-lint.yml/badge.svg?branch=eb-ventura-package)](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-lint.yml)
[![Typing](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-type.yml/badge.svg?branch=eb-ventura-package)](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-type.yml)
[![Testing](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-test.yml/badge.svg?branch=eb-ventura-package)](https://github.com/silverailscolo/ramses_rf/actions/workflows/check-test.yml)

# Cloned Beta
This is a beta release from a cloned repository to test the Vasco and ClimaRad PRs from @silverailscolo.

# New code owner wanted
As of spring 2025 @zxdavb is no longer able to work on this project and active development has ceased.

Please reach out to him if you feel able to take over. He promised to hand over the entire repo to the right person, and would be prepared to provide help during a transition period.

## Overview
**ramses_rf** is a client library/CLI utility used to interface with some Honeywell-compatible HVAC & CH/DHW systems that use 868MHz RF, such as:
 - (Heat) **evohome**, **Sundial**, **Hometronic**, **Chronotherm**
 - (HVAC) **Itho**, **Orcon**, **Nuaire**, **Vasco**, **ClimaRad**

It requires a USB-to-RF device, either a Honeywell HGI80 (somewhat rare, expensive) or something running the [evofw3](https://github.com/ghoti57/evofw3) firmware, such as the one from [here](https://indalo-tech.onlineweb.shop/) or your own ESP32-S3-WROOM-1 N16R8 with a CC1100 transponder.

It does three things:
 - decodes RAMSES II-compatible packets and converts them into useful JSON
 - builds a picture (schema, config & state) of evohome-compatible CH/DHW systems - either passively (by eavesdropping), or actively (probing)
 - allows you to send commands to CH/DHW and HVAC systems, or monitor for state changes
 - allows you to emulate some hardware devices

For CH/DHW, the simplest way to know if it will work with your system is to identify the box connected to your boiler/HVAC appliance as one of:
 - **R8810A**: OpenTherm Bridge
 - **BDR91A**: Wireless Relay (also BDR91T)
 - **HC60NG**: Wireless Relay (older hardware)

Other systems may well work, such as some Itho Daalderop HVAC systems, use this protocol; YMMV.

It includes a CLI and can be used as a standalone tool, but also is used as a client library by:
 - [ramses_cc](https://github.com/zxdavb/ramses_cc), a Home Assistant integration
 - [evohome-Listener](https://github.com/smar000/evohome-Listener), an MQTT gateway

## Installation

```
git clone https://github.com/zxdavb/ramses_rf
cd ramses_rf
pip install -r requirements.txt
```

## Ramses_rf CLI

The CLI is called ``client.py`` and is included in the code root.

To monitor your ramses stick, plugged in to a USB port on this computer, type:
```
python client.py monitor /dev/ttyUSB0 -o packet.log
```

To send a command to a device, type:
```
python client.py execute /dev/ttyUSB0 -x "_verb [seqn] addr0 [addr1 [addr2]] code payload"
```
Note: add whitespace before I verb: [PP]|[RQ]|[ I]; skip empty addresses; don't enter length. Example:
```
python3 client.py execute /dev/cu.usbmodemFD131 -x " I 29:091138 32:022222 22F1 000406"
```
