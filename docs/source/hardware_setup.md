# Hardware & Network Serial Setup

This guide documents connecting RF hardware interfaces to `ramses_rf`, including network serial proxies and USB gateway firmware.

---

## Network Serial Proxy (`ser2net`)

When running `ramses_rf` in a container or on a separate host from your RF dongle (such as an evofw3 or HGI80 interface), `ser2net` can expose the serial device over RFC2217 (Telnet).

### Configuration

A template configuration is provided in `examples/ser2net.yaml`:

```yaml
connection: &con00
  accepter: telnet(rfc2217),ipv4,tcp,5001
  timeout: 0
  connector: serialdev,/dev/ttyACM0,115200n81,local
  options:
    max-connections: 3
```

### Running `ser2net`

Start `ser2net` with the configuration file:

```console
$ ser2net -c examples/ser2net.yaml
```

### Client Configuration

Configure `ramses_rf` (or Home Assistant `ramses_cc`) to connect via RFC2217:

```yaml
ramses_cc:
  serial_port:
    port_name: rfc2217://localhost:5001
```

---

## Honeywell HGI80 USB Gateway Setup (Linux)

Genuine Honeywell HGI80 USB gateway devices use the Texas Instruments 3410 (TI 3410) USB-serial converter chip.

### Kernel Driver & Firmware Requirements

The Linux kernel `ti_3410` driver requires a firmware image (`ti_3410.fw`) to initialize the hardware.

1. **Check Kernel Messages**:
   Inspect kernel logs after plugging in the HGI80 dongle:
   ```console
   $ dmesg | grep ti_3410
   ```

2. **Install Firmware via Package Manager**:
   On Debian/Ubuntu and derivative distributions, install the standard kernel firmware package:
   ```console
   $ sudo apt-get update
   $ sudo apt-get install linux-firmware
   ```

3. **Manual Firmware Installation (if missing)**:
   If the firmware is not included in your distribution, download `ti_3410.fw` from the upstream Linux firmware repository and place it in `/lib/firmware/`:
   ```console
   $ wget https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/ti_3410.fw
   $ sudo mv ti_3410.fw /lib/firmware/
   $ sudo chown root:root /lib/firmware/ti_3410.fw
   $ sudo chmod 644 /lib/firmware/ti_3410.fw
   ```

4. **Verify Device**:
   Re-plug the device or reboot and verify detection:
   ```console
   $ lsusb
   $ ls -l /dev/ttyUSB*
   ```
