[![Documentation](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://fa-yoshinobu.github.io/samples/)

This page is the user-facing guide to the high-level Python samples.
Open the file that matches the task you want to perform.

Related documents:

- [../README.md](../README.md)
- [../docsrc/user/USER_GUIDE.md](../docsrc/user/USER_GUIDE.md)
- [../scripts/README.md](../scripts/README.md)

Run them from the repository root or after installing the package.

## Start here

If you want the shortest path, use one of these:

- first read / write: `samples/high_level_minimal.py`
- common daily tasks: `samples/high_level_basic.py`
- full sync cookbook: `samples/high_level_all_sync.py`
- full async cookbook: `samples/high_level_all_async.py`
- UDP with local port: `samples/high_level_udp.py`
- FR storage: `samples/fr_basic.py`
- relay access: `samples/relay_basic.py`
- clock and CPU status: `samples/clock_and_status.py`

Quick copy/paste commands:

```powershell
python samples/high_level_minimal.py --host 192.168.250.100 --port 1025
python samples/high_level_basic.py --host 192.168.250.100 --port 1025
python samples/high_level_all_sync.py --host 192.168.250.100 --port 1025
python samples/high_level_all_async.py --host 192.168.250.100 --port 1025 --poll-count 2
python samples/high_level_udp.py --host 192.168.250.100 --port 1027 --local-port 12000
python samples/fr_basic.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --target FR000000 --value 0x1234
python samples/relay_basic.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode cpu-status
python samples/clock_and_status.py --host 192.168.250.100 --port 1025
```

Address note:

- `P/K/V/T/C/L/X/Y/M/S/N/R/D` families require `P1-`, `P2-`, or `P3-` prefix when a profile is in use

## Choose a sample by task

- Read and write one word or bit
  - `samples/high_level_minimal.py`
- Read several devices together, including `W/H/L` packed access
  - `samples/high_level_basic.py`
- Learn the whole sync API surface
  - `samples/high_level_all_sync.py`
- Learn the whole async helper surface
  - `samples/high_level_all_async.py`
- Connect over UDP
  - `samples/high_level_udp.py`
- Read or persist FR values
  - `samples/fr_basic.py`
- Use relay hops
  - `samples/relay_basic.py`
- Read PLC clock and CPU status
  - `samples/clock_and_status.py`

## Sample summary

- `samples/high_level_all_sync.py`
  Full synchronous cookbook for `ToyopucDeviceClient`
- `samples/high_level_all_async.py`
  Full asynchronous cookbook for `open_and_connect`, `read_typed`, `read_named`, `poll`, and related helpers
- `samples/high_level_minimal.py`
  Smallest possible read / write workflow
- `samples/high_level_basic.py`
  Broader read / write example, including `read_many` and `W/H/L` addressing
- `samples/high_level_udp.py`
  High-level read / write over UDP with a fixed local port
- `samples/fr_basic.py`
  FR read / write example with optional flash commit
- `samples/relay_basic.py`
  Relay sample for CPU status, clock, word I/O, and FR operations
- `samples/clock_and_status.py`
  CPU clock read and full CPU status decode

## More usage examples

Read one word and one bit:

```powershell
python samples/high_level_minimal.py --host 192.168.250.100 --port 1025
```

Read packed `W/H/L` values and mixed snapshots:

```powershell
python samples/high_level_basic.py --host 192.168.250.100 --port 1025
```

Run the full synchronous cookbook:

```powershell
python samples/high_level_all_sync.py --host 192.168.250.100 --port 1025
```

Run the full asynchronous cookbook:

```powershell
python samples/high_level_all_async.py --host 192.168.250.100 --port 1025 --poll-count 2
```

Read and optionally commit FR values:

```powershell
python samples/fr_basic.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --target FR000000 --value 0x1234 --commit
```

Use one or two relay hops:

```powershell
python samples/relay_basic.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2" --mode cpu-status
python samples/relay_basic.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --hops "P1-L2:N2,P1-L2:N4" --mode word-read --device P1-D0000 --count 4
```

Low-level protocol examples are intentionally omitted from this user guide.
