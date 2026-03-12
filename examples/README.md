# Examples

These examples show practical usage of `toyopuc`.

Related documents:

- [../README.md](../README.md)
- [../docs/TESTING.md](../docs/TESTING.md)
- [../docs/COMPUTER_LINK_SPEC.md](../docs/COMPUTER_LINK_SPEC.md)
- [../tools/README.md](../tools/README.md)

Run them from the repository root or after installing the package.

## Start Here

If you want the shortest path:

- minimal basic read/write: `examples/high_level_minimal.py`
- broader high-level example: `examples/high_level_basic.py`
- UDP example: `examples/high_level_udp.py`
- FR example: `examples/fr_basic.py`
- relay example: `examples/relay_basic.py`
- clock/status: `examples/clock_and_status.py`
- GUI monitor: `examples/device_monitor_gui.py`

`examples/low_level_basic.py` is an advanced example.
It is for users who want to work directly with:

- `ToyopucClient`
- explicit numeric addresses
- parser/encoder aware low-level usage

High-level address note:

- `P/K/V/T/C/L/X/Y/M/S/N/R/D` families require `P1-`, `P2-`, or `P3-` prefix (for example `P1-D0000`)

Quick copy/paste commands:

```powershell
python examples/high_level_minimal.py --host 192.168.250.101 --port 1025
python examples/high_level_basic.py --host 192.168.250.101 --port 1025
python examples/high_level_udp.py --host 192.168.250.101 --port 1027 --local-port 12000
python examples/fr_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --target FR000000 --value 0x1234
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode cpu-status
python examples/clock_and_status.py --host 192.168.250.101 --port 1025
python examples/device_monitor_gui.py --host 192.168.250.101 --port 1025
```

## Files

- `examples/low_level_basic.py`
  Advanced low-level read/write example using `ToyopucClient`
- `examples/high_level_minimal.py`
  Shortest high-level example for a single word read/write
- `examples/high_level_basic.py`
  Broader high-level example, including `W/H/L` addressing on bit-device families
- `examples/high_level_udp.py`
  High-level read/write over UDP with a fixed local port
- `examples/fr_basic.py`
  High-level FR read/write example with optional flash commit
- `examples/relay_basic.py`
  Relay example for CPU status, CPU status A0, clock read/write, basic word read/write, and FR read/write/commit
- `examples/clock_and_status.py`
  CPU clock read and full CPU status decode
- `examples/device_monitor_gui.py`
  Tkinter GUI monitor with editable connection settings, optional relay hops, a live watch table, and single/list/range device add input across high-level device families
- [`examples/device_monitor_gui.md`](device_monitor_gui.md)
  Dedicated usage guide for the GUI monitor

GUI quick start:

```powershell
python examples/device_monitor_gui.py
```

GUI guide:

- [`examples/device_monitor_gui.md`](device_monitor_gui.md)

GUI over UDP:

```powershell
python examples/device_monitor_gui.py --protocol udp --local-port 12000
```

## FR Example

Read and write one FR word without flash commit:

```powershell
python examples/fr_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --target FR000000 --value 0x1234
```

Read and write one FR word with flash commit:

```powershell
python examples/fr_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --target FR000000 --value 0x1234 --commit
```

Notes:

- without `--commit`, the FR work area in RAM is updated but the value is not persisted to flash
- with `--commit`, the touched FR block is registered to flash
- FR commit is destructive to the target FR block; use a safe address and value on real hardware

## Relay Example

CPU status through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode cpu-status
```

Clock read through two relay hops:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2,P1-L2:N4" --mode clock-read
```

CPU status A0 through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode cpu-status-a0
```

Clock write through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode clock-write --clock-value 2026-03-10T15:00:00
```

Word read through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode word-read --device P1-D0000 --count 1
```

Word write through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode word-write --device P1-D0000 --value 0x1234
```

Repeated contiguous relay word write/readback test:

```powershell
python -m tools.relay_block_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2,P1-L2:N4,P1-L2:N6" --device P1-D0000 --count 8 --loops 3 --value 0x1000 --step 1 --loop-step 0x0100
```

FR write through relay (RAM update only):

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode fr-write --device FR000000 --value 0x1234
```

FR commit through relay:

```powershell
python examples/relay_basic.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode fr-commit --device FR000000 --wait
```
