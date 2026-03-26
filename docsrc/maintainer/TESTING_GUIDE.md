# Testing Guide

Related documents:

- [../README.md](../README.md)
- [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md)
- [../user/MODEL_RANGES.md](../user/MODEL_RANGES.md)
- [../../scripts/README.md](../../scripts/README.md)
- [TODO.md](../../TODO.md)

## Scope

This document covers:

- `scripts/auto_rw_test.py`
- `scripts/clock_test.py`
- `scripts/cpu_status_test.py`
- `scripts/high_level_api_test.py`
- `scripts/interactive_cli.py`
- `scripts/manual_device_write_check.py`
- `scripts/recovery_write_loop.py`
- `scripts/find_last_writable.py`
- batch files under `scripts/`

Protocol details and address tables are kept in [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md).
Model-specific writable ranges are kept in [../user/MODEL_RANGES.md](../user/MODEL_RANGES.md).

Remaining open items are tracked in [TODO.md](../../TODO.md).

Historical evidence under `docsrc/validation/` may mention retired samples or
older helper-script names. Treat those files as snapshots, not as the current
test entry points. The current maintained entry points are the commands and
paths documented in this guide.

## Static analysis policy

The current CI split is intentional.

- `mypy`
  - target: `toyopuc/`
  - reason: this is the typed public runtime surface
- `ruff`
  - target: `toyopuc/`, `tests/`, `scripts/`, `samples/`
  - reason: style and obvious correctness checks should cover maintained entry points
- `py_compile`
  - target: `scripts/*.py`, `samples/*.py`
  - reason: helper scripts and user samples are supported workflows, but many of them are still runtime-oriented and are not yet practical `mypy` targets

Treat expanding `mypy` beyond `toyopuc/` as a separate maintenance task rather than an incidental CI tweak.

## Simulator

`scripts/sim_server.py` is a development helper, not a real-hardware substitute.

Currently supported in the simulator:

- basic single-point access
  - `CMD=1C/1D/1E/1F/20/21`
- basic multi-point access
  - `CMD=22/23/24/25`
- extended single/contiguous access
  - `CMD=94/95/96/97`
- extended multi-point access
  - `CMD=98/99`
- PC10 block/multi access
  - `CMD=C2/C3/C4/C5`
- relay command
  - `CMD=60` single-hop read verified on real hardware
- clock
  - `CMD=32 70 00` read
  - `CMD=32 71 00` write
- CPU status
  - `CMD=32 11 00`

Not modeled accurately enough to treat as hardware-equivalent:

- `FR`
- `CMD=CA`
- hardware-specific NAK/error behavior

## Relay hardware verification

Verified on `2026-03-10` against `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over UDP:

- single-hop relay path: `P1-L2:N2` (`Link=0x12`, `Exchange=0x0002`)
- successful inner commands:
  - `CMD=32 / 11 00` CPU status read
  - `CMD=32 / 70 00` clock read
  - `CMD=1C` word read (`D0000`, count `1`)
  - `CMD=C2` FR read (`FR000000`, count `1`)
  - `CMD=C3` FR write (`FR000000 = 0x55AA`) with immediate readback
  - `CMD=CA` FR commit on `FR000000` with completion wait
  - post-reset `CMD=C2` FR read confirming that the committed `FR000000 = 0x55AA` value persisted after CPU reset
- verified two-hop relay:
  - hops: `P1-L2:N2 -> P1-L2:N4`
  - inner command: `CMD=32 / 11 00` CPU status read
- verified three-hop relay:
  - hops: `P1-L2:N2 -> P1-L2:N4 -> P1-L2:N6`
  - verified inner commands:
    - `CMD=32 / 11 00` CPU status read
    - `CMD=32 / 70 00` clock read
    - `CMD=32 / 71 00` clock write with successful readback
    - `CMD=1C` word read (`D0000`, count `1`)
    - `CMD=1D` word write (`D0000 = 0x1234`) with successful readback
- verified three-hop contiguous relay word block path:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - inner commands:
    - `CMD=1D` contiguous word write on `D0000-D0007`
    - `CMD=1C` contiguous word read on `D0000-D0007`
  - checked with `count=8`, `loops=3`, patterns `0x1000-0x1007`, `0x1100-0x1107`, `0x1200-0x1207`
  - observed result: `summary = 3/3 loops passed`
- verified three-hop relay FR path:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - verified inner commands:
    - `CMD=C2` FR read (`FR000000`, count `1`)
    - `CMD=C3` FR write (`FR000000 = 0x0099`) with immediate readback
    - `CMD=CA` FR commit on `FR000000` with completion wait
    - post-commit `CMD=C2` FR read confirming `FR000000 = 0x0099`
- verified relay high-level API sweep:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - command:
    - `python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --include-pc10-word --log relay_high_level_api.log`
  - observed result:
    - `TOTAL: 24/24`
    - `ERROR CASES: 0`
  - verified categories:
    - basic bit / word / byte
    - prefixed bit / word
    - extended bit / word
    - PC10 word
    - contiguous basic word / byte / bit sequences
    - mixed `read_many()` / `write_many()` on `D/M/P1-R/ES/U`
- verified relay matrix expansion:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - command:
    - `python scripts\\relay_matrix_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --targets D0000,R0000,S0000,U08000 --counts 16,32 --loops 3 --value 0x1000 --step 1 --loop-step 0x0100 --clock-loops 3 --clock-start 2026-03-10T15:30:00`
  - observed result:
    - `D0000`: `count=16`, `count=32` both `3/3` loops passed
    - `R0000`: `count=16`, `count=32` both `3/3` loops passed
    - `U08000`: `count=16`, `count=32` both `3/3` loops passed
    - `S0000`: `count=16`, `count=32` both failed to retain written patterns (`0/3`)
    - word-only `write_many()` across `D/R/S/U`: passed
    - mixed `write_many()` case showed a byte mismatch on `D0000L` (`0x79 -> 0x68`)
    - repeated relay `clock-write` / readback / restore: `3/3` loops passed
- verified relay low-level sweep:
  - UDP path:
    - `python scripts\\relay_low_level_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --clock-value 2026-03-10T15:00:00`
    - passed: `cpu-status`, `clock-read`, `clock-write`, `CMD=20/21`, `CMD=1C/1D`, `CMD=24/25`, `CMD=94/95`, `CMD=96/97`, `CMD=98/99`, `CMD=C2/C3`
    - standalone relay `A0` returned relay NAK `0x15`
    - the `D0000L` single-byte case and `D0000/D0001` multi-word case did not hold the requested values on this path during the UDP sweep
  - TCP path:
    - `python scripts\\relay_low_level_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2"`
    - passed: `cpu-status`, `clock-read`, `CMD=20/21`, `CMD=1C/1D`, `CMD=1E/1F`, `CMD=22/23`, `CMD=24/25`, `CMD=94/95`, `CMD=96/97`, `CMD=98/99`, `CMD=C2/C3`
    - standalone relay `A0` returned relay NAK `0x15`
- verified relay abnormal-case sweep:
  - command:
    - `python scripts\\relay_error_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12021 --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --forbidden-write-device S0000 --out-of-range-word-index 0x3000`
  - observed result:
    - missing station: timeout, no reply
    - broken path: timeout, no reply
    - raw out-of-range basic word read (`D3000`): timeout, no reply
    - relay write to `S0000`: timeout, no reply

Observed notes:

- relay request must include the trailing fixed `00` byte after the inner command payload
- outer relay response layout is `Link, ExLo, ExHi, ACK, inner..., padding?`
- inner response may include one trailing padding byte
- relay `CMD=A0 / 01 10` on the verified Plus path returned relay NAK `0x26`, so FR commit wait fell back to normal CPU status `CMD=32 / 11 00`
- standalone relay `CMD=A0 / 01 10` also returned relay NAK `0x15` on the verified three-hop Plus path over both UDP and TCP
- only the above two-hop / three-hop relay paths are verified for multi-hop relay
- relay FR verification is currently limited to the above single-hop `P1-L2:N2` path and three-hop `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2` path
- unsupported-area behavior by model
- timing and cable recovery behavior
- exact real-hardware semantics of shared areas

Example:

```bash
python scripts\\sim_server.py --host 127.0.0.1 --port 15000
python scripts\\clock_test.py --host 127.0.0.1 --port 15000 --protocol tcp
python scripts\\cpu_status_test.py --host 127.0.0.1 --port 15000 --protocol tcp
```

Batch example:

```bat
scripts\\run_sim_tests.bat 127.0.0.1 15000 tcp
```

Verified simulator smoke result:

- `scripts\\run_sim_tests.bat 127.0.0.1 15000 tcp`
- result:
  - `high_level_api_test`: `TOTAL: 21/21`, `ERROR CASES: 0`
  - `whl_addressing_test` (`W/H/L` addressing): `TOTAL: 35/35`, `ERROR CASES: 0`
  - `clock_test`: passed
  - `cpu_status_test`: passed
- note:
  - this confirms development-time simulator consistency for the current low-level/high-level API paths
  - it does **not** upgrade the simulator to hardware-equivalent status

## TCC-6740 + TCU-6858 Batch

For `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`, the current broad validation batch is:

```bat
scripts\\run_validation_all.bat 192.168.250.100 1025 tcp 4 5 2 0x200 0 60
```

UDP example:

```bat
scripts\\run_validation_all.bat 192.168.250.100 1027 udp 4 5 2 0x200 12000 60
```

This batch covers:

- full device sweep
- mixed `CMD=98/99`
- block test
- boundary test
- recovery write/read
- last-writable probe

Additional focused checks that are still run separately:

- `python scripts\\whl_addressing_test.py ...`
- `python scripts\\high_level_api_test.py ...`
- `python scripts\\clock_test.py ...`
- `python scripts\\cpu_status_test.py ...`

Use `run_validation_all.bat` plus the focused helpers above. The batch is intentionally configured to continue past the known `full test` mismatches seen on `TCC-6740 + TCU-6858`, while the remaining steps are still treated as fatal on error.

## Status

- Current verified results in this file are based on hardware checks performed through `2026-03-10`.
- `V` bit mismatches are tolerated because the PLC can overwrite that area.
- `S` word mismatches are also treated as tolerated when they occur.

## CLI

Start with explicit connection parameters:

```bash
python scripts\\interactive_cli.py --host 192.168.250.100 --port 1025 --protocol tcp
```

Supported connection options:

- `--host`
- `--port`
- `--local-port`
- `--protocol tcp|udp`
- `--timeout`
- `--retries`
- `--log`

## Clock Test

Clock access is implemented in the library and has been verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`.

Dedicated command-line helper:

Read current PLC clock:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp
```

Set PLC clock explicitly:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp --set "2026-03-08 12:34:56"
```

Set PLC clock to current local time:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp --set-now
```

UDP example:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
```

Read test from Python with the low-level client:

```bash
python - <<'PY'
from toyopuc import ToyopucClient

with ToyopucClient("192.168.250.100", 1025, protocol="tcp") as plc:
    print(plc.read_clock())
PY
```

Read test from Python with the high-level client:

```bash
python - <<'PY'
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.250.100", 1025, protocol="tcp") as plc:
    print(plc.read_clock())
PY
```

Raw command check in `interactive_cli`:

```text
raw 32 70 00
```

Expected response shape:

```text
80 00 0A 00 32 70 00 SS MM HH DD MM YY WW
```

Notes:

- time fields are BCD
- year is the lower two digits
- weekday is `0=Sunday`
- some PLCs can return incomplete calendar fields such as `month=00`; `tools.clock_test.py` prints both raw fields and a best-effort `datetime`

## CPU Status Test

Dedicated command-line helper:

Read and decode CPU status:

```bash
python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1025 --protocol tcp
```

UDP example:

```bash
python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
```

The helper prints:

- raw 8-byte status payload
- decoded flags such as `run`, `alarm`, `pc10_mode`
- program-running flags for programs 1/2/3

Write test should be done only after confirming that clock writes are acceptable on the target PLC.

Raw `A0` check from Python:

```bash
python - <<'PY'
from toyopuc import ToyopucClient

with ToyopucClient("192.168.250.100", 1025, protocol="tcp") as plc:
    print(plc.read_cpu_status_a0_raw().hex(" ").upper())
PY
```

Notes:

- normal decoded CPU status uses `CMD=32 / 11 00`
- flash/FR completion flow also references `CMD=A0 / 01 10`
- `CMD=A0 / 01 10` uses the same `Data1-Data8` bit layout as the normal CPU-status command
- the current library exposes both `read_cpu_status_a0_raw()` and decoded `read_cpu_status_a0()`
- on targets where `A0` is accepted, FR commit wait can use `Data7.bit4` / `Data7.bit5`
- on `Nano 10GX (TUC-1157)`, `A0` was rejected with `0x24`, so FR commit wait falls back to `CMD=32 / 11 00` and uses the same `Data7.bit4` / `Data7.bit5` flags

## FR Probe

Use this when `FR` is believed to exist on the target PLC but the normal `FR` mapping still fails.

The probe tries:

- legacy `CMD=94` FR mapping from `encode_ext_no_address("FR", ...)`
- PC10 block read (`CMD=C2`) using `encode_fr_word_addr32()`
- optional `CMD=CA` acceptance check for candidate FR block `Ex No.` values

Batch example:

```bat
scripts\\run_fr_probe.bat 192.168.250.100 1027 udp 12000 5 2 "0x0,0x8000" "0x40,0x41"
```

Direct Python example:

```bash
python scripts\\fr_probe.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --indexes "0x0,0x8000" --register-exnos "0x40,0x41"
```

Interpretation:

- `legacy-cmd94` failing with `0x40` while `pc10-c2` succeeds means the FR path is PC10-based as expected
- `CA` success means the registration command format was accepted; it does not by itself prove read-bank switching

## FR Full-Range Read Scan

Read-only FR scan helper:

```bat
scripts\\run_fr_read_scan.bat 192.168.250.100 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read_full.log
```

What it reports:

- chunked `CMD=C2` progress
- `ok_chunks` / `error_chunks`
- `0x0000` / `0xFFFF` / `other` word counts
- whole-range `crc32`
- `holes`

Interpretation:

- `holes: none` means the requested FR span was readable end to end
- matching `crc32` before and after CPU reset is the practical persistence check for full-range FR writes

## FR Full-Range Write Scan

Write/commit/verify helper:

```bat
scripts\\run_fr_write_scan.bat 192.168.250.100 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0xA500 fr_write_full.log
```

What it does:

- writes the requested FR range with a deterministic pattern through chunked `CMD=C3`
- performs one final commit phase after all writes finish
- issues `CMD=CA` once for each touched `64-kbyte` FR block
- waits for each block commit to complete before moving to the next block
- verifies the written pattern through chunked `CMD=C2` readback

Interpretation:

- `expected_crc32 == actual_crc32` with `mismatch_words=0` means the write path and immediate readback both succeeded
- reset, then run `run_fr_read_scan.bat` again to confirm persistence across CPU reset

Low-level FR example:

```bash
python - <<'PY'
from toyopuc import ToyopucClient

with ToyopucClient("192.168.250.100", 1025, protocol="tcp") as plc:
    print(plc.read_fr_words(0x000000, 1))
    plc.write_fr_words_committed(0x000000, [0x1234])
PY
```

Low-level write example:

```bash
python - <<'PY'
from datetime import datetime
from toyopuc import ToyopucClient

with ToyopucClient("192.168.250.100", 1025, protocol="tcp") as plc:
    plc.write_clock(datetime(2026, 3, 8, 12, 34, 56))
PY
```

High-level write example:

```bash
python - <<'PY'
from datetime import datetime
from toyopuc import ToyopucDeviceClient

with ToyopucDeviceClient("192.168.250.100", 1025, protocol="tcp") as plc:
    plc.write_clock(datetime(2026, 3, 8, 12, 34, 56))
PY
```

## High-level API test

Use this when you want to verify `ToyopucDeviceClient` and `resolve_device()` directly.

It covers:

- single bit/word/byte
- prefixed access
- extended access
- PC10 access
- contiguous `read()` / `write()`
- `read_many()` / `write_many()`
- FR generic-write guard behavior

Example:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1025 --protocol tcp --log high_level_api.log
```

If the target model supports PC10 upper-word areas such as `U08000+`, add:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1025 --protocol tcp --include-pc10-word --log high_level_api.log
```

UDP:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --skip-errors --log high_level_api_udp.log
```

Relay over UDP:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --include-pc10-word --log relay_high_level_api.log
```

Verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over TCP:

```text
TOTAL: 21/21
ERROR CASES: 0
```

Verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over UDP:

```text
TOTAL: 21/21
ERROR CASES: 0
```

Verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over UDP through relay hops `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`:

```text
TOTAL: 24/24
ERROR CASES: 0
```

Note:

- `--local-port` is mainly for UDP, when the PLC expects a fixed source port from the PC.

### Unit regression guard for sparse `pc10-word` `read_many`

Regression tests were added on `2026-03-12` to guard the `pc10-word` sparse
`read_many`/`relay_read_many` behavior against accidental `CMD=C4` usage.

- File:
  - `tests/_internal/test_relay.py`
- Added tests:
  - `test_high_level_read_many_pc10_word_sparse_uses_block_read_only`
  - `test_high_level_relay_read_many_pc10_word_sparse_uses_block_read_only`
- Assertions:
  - direct `read_many` on sparse `U` word devices uses only per-point PC10
    block reads (`CMD=C2`).
  - relay `relay_read_many` on sparse `U` word devices sends only inner frames
    built by `build_pc10_block_read(..., 2)` (`CMD=C2`).
  - no `CMD=C4` PC10 multi-read path is used in these sparse `pc10-word`
    cases.
- Latest local run:
  - command: `python -m pytest tests/_internal/test_relay.py -q`
  - result: `24 passed`

## W/H/L Addressing Test

Use this when you want to verify `W/H/L` addressing on bit-device families.

It covers:

- basic bit-device word/byte access
- prefixed bit-device word/byte access
- extended bit-device word/byte access
- `W -> L/H` relation checks
- `L/H -> bit` relation checks

Example:

```bash
python scripts\\whl_addressing_test.py --host 192.168.250.100 --port 1025 --protocol tcp --log whl_addressing.log
```

UDP:

```bash
python scripts\\whl_addressing_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --skip-errors --log whl_addressing_udp.log
```

Typical addresses used by the test:

- `M0010W`
- `X0010L`
- `X0010H`
- `P1-M0010W`
- `EX0010W`
- `GX0010H`

Interpretation:

- `...W`: 16-bit word access to a bit-device family
- `...L`: lower byte of that word
- `...H`: upper byte of that word

Verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over TCP:

```text
TOTAL: 35/35
ERROR CASES: 0
```

Verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over UDP:

```text
TOTAL: 35/35
ERROR CASES: 0
```

The verification includes:

- `W` write/read on bit-device families
- `L/H` write/read on bit-device families
- `W -> L/H` consistency
- `L/H -> bit` consistency
- basic / prefixed / extended / `GX` families

### Basic commands

```text
wr D0100 3
ww D0100 1 0x0203 0x0405
br D0100L 5
bw D0100L 0x01 0x02 0x03 0x04 0x05
bitr M0201
bitw M0201 1
wmr D0100 D0200 D0210
wmw D0100:0x1234 D0200:0x5678 D0210:0x9ABC
bmr D0800L D0802L
bmw D0800L:0x56 D0802L:0x12
```

### Extended Commands

```text
xwr U 0x0000 1
xww U 0x0000 0x1234
xbr U 0x0000 2
xbw U 0x0000 0x12 0x34

xbitr EX 0x0000
xbitw EX 0x0000 1

pwr P1 D 0x0000 1
pww P1 D 0x0000 0x1234
pbitr P1 M 0x0000
pbitw P1 M 0x0000 1
```

### Mixed `CMD=98/99`

```text
xmr bit:EX:0x0000 byte:U:0x0000 word:EN:0x0000
xmw bit:EX:0x0000:1 byte:U:0x0000:0x12 word:EN:0x0000:0x3456
```

### Manual write-and-check flow

This helper writes fixed values one device at a time and waits for a human check in the vendor tool before moving on.

Rules:

- bit devices: write `1`
- word devices: write `FFFF`
- each device family uses the first and last address of each supported range
- before each write, the tool prints the target device
- after each write, the operator confirms `y/n/q`

Example:

```bash
python scripts\\manual_device_write_check.py --host 192.168.250.100 --port 1025 --protocol tcp
```

UDP example:

```bash
python scripts\\manual_device_write_check.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2
```

Optional:

- `--include-fr` adds `FR` first/last points to the manual sequence
- `--log` writes operator actions and results to a text file

Observed on `TOYOPUC-Plus`:

- non-`B` device families were manually confirmed as broadly working
- `B` was treated as unsupported
- several tail-end points were rejected separately during earlier manual checks

### Find last writable address

This helper writes downward from a chosen end address and reports the last address that still accepts writes.

Example:

```bash
python scripts\\find_last_writable.py --host 192.168.250.100 --port 1025 --protocol tcp --start D2FFF --stop D2FF0 --log last_d.log
```

Automatic known-tail probe:

```bash
python scripts\\find_last_writable.py --host 192.168.250.100 --port 1025 --protocol tcp --auto-pending --log last_pending.log
```

UDP example:

```bash
python scripts\\find_last_writable.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --start U1FFFF --stop U1FFF0 --log last_u_udp.log
```

Notes:

- `--start` and `--stop` must be in the same device family
- the tool moves downward by `--step` (default `1`)
- it reports `last_ok` and the first rejected point
- `--auto-pending` runs the current known tail candidates automatically:
  - `D2FFF`
  - `P1-D2FFF`
  - `P3-D2FFF`
  - `U1FFFF`

### Cable unplug/replug recovery loop

This helper writes to one target repeatedly at a fixed interval and logs timeout/error/recovery behavior while the cable is unplugged and reconnected.

Rules:

- default interval: `200 ms`
- default bit value: `1`
- default word value: `FFFF`
- on write error, the client socket is closed and the next cycle tries again
- when writes start succeeding again after errors, the tool logs `RECOVERED`
- `--mode read` switches the loop to repeated reads instead of writes
- `--expect` can be used in read mode to log `OK` vs `MISMATCH`

Example:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1025 --protocol tcp --target M0000 --interval-ms 200
```

UDP example:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --target D0000 --interval-ms 200 --log recovery_udp.log
```

Read example:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1025 --protocol tcp --target M0000 --mode read --expect 1 --interval-ms 200 --log recovery_read.log
```

Supported targets:

- base bit/word: `M0000`, `D0000`
- prefixed: `P1-M0000`, `P1-D0000`
- extended bit/word: `EX0000`, `ES0000`
- PC10 word ranges: `U08000`, `EB00000`

## Auto Test

Basic example:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --count 4 --log auto_basic.log
```

UDP with fixed local port example:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --local-port 12000 --protocol udp --count 4 --timeout 5 --retries 2 --log auto_udp_basic.log
```

Full PC10G example:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --count 4 --pc10g-full --include-p123 --skip-errors --log auto_pc10g_p123.log
```

Block test:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --max-block-test --pc10-block-words 0x200 --skip-errors --log auto_block.log
```

Boundary test:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --boundary-test --skip-errors --log auto_boundary.log
```

Mixed multi-point test:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --ext-multi-test --skip-errors --log auto_ext_multi.log
```

## Rules

- Bit devices: write `0`, read back, then write `1`, read back on the same address.
- Word devices: write a random 16-bit value, read back, then write the bitwise-inverted value and read back on the same address.
- Byte devices: single write/read verification.
- `--skip-errors` logs access errors such as `rc=0x10` and continues.

## Options

```text
--include-io
--include-special
--include-extended
--include-all
--include-fr
--local-port
--pc10g-full
--include-p123
--skip-errors
--max-block-test
--pc10-block-words
--ext-multi-test
--boundary-test
```

## Cautions

- `FR` is not part of the normal safe test path.
- `V` bit mismatches are counted separately as tolerated.
- `S` word mismatches are tolerated when they occur.
- UDP may require `--local-port` because some PLC setups expect a fixed PC-side source port.
- `--pc10-block-words 0x200` is the current safe default.
- Values larger than `0x200` can be rejected by the PLC or destabilize later checks.
- `--skip-errors` is recommended for broad real-hardware sweeps.

## Mapping

- Base bit areas: `CMD=20/21`
- Base word areas: `CMD=1C/1D`
- Extended word/byte areas: `CMD=94/95/96/97`
- Extended bit areas `EP/EK/EV/ET/EC/EL/EX/EY/EM/GX/GY/GM`: `CMD=98/99`
- Prefixed devices `P1/P2/P3` use program numbers `01/02/03`
- Prefixed word areas: `CMD=94/95`
- Prefixed bit areas: `CMD=98/99`
- For `CMD=98/99`, the current program-number mapping is:
- `00`: `EP/EK/EV/ET/EC/EL/EX/EY/EM`
- `07`: `GX/GY/GM`
- `01/02/03`: `P1/P2/P3`
- `Nano 10GX (TUC-1157)` candidate-`no` probe on `2026-03-10` showed no alias across `00/01/02/03/07` for `EX/GX/P1/P2/P3`
- `L1000-L2FFF` and `M1000-M17FF` use PC10 multi access `CMD=C4/C5` in the current implementation
- `Nano 10GX (TUC-1157)` probe on `2026-03-10` also showed that `CMD=C4/C5` reaches the same points for the `U00000-U1FFFF` and `EB00000-EB3FFFF` spans
- `U00000-U07FFF` stays on `CMD=94/95`
- `U08000-U1FFFF` and `EB00000-EB3FFFF` currently use `CMD=C2/C3` for normal word/byte single-point and block access
- `EB40000-EB7FFFF` stays on `CMD=94/95`

## Naming

- User-facing paired names are `X/Y`, `T/C`, `EX/EY`, `ET/EC`, and `GX/GY`.
- Internal aliases such as `GXY` remain implementation details only.

## Mixed Cases

- `EX0000 + U0000(byte) + EN0000(word)`
- `GX0000 + GX/GY byte(0001) + ES0000(word)`
- `P1-M0000 + P1-D0000(byte) + P1-D0000(word)`
- `GX0000 + GX/GY byte(0000)`
- `GX/GY byte(0000) + ES0000(word)`
- `GX0000 + ES0000(word)`

## Batch

Run all standard checks:

```bat
scripts\\run_auto_tests.bat 192.168.250.100 1025 tcp 4 3 0 0x200
```

UDP example with fixed local port:

```bat
scripts\\run_auto_tests.bat 192.168.250.100 1025 udp 4 5 2 0x200 12000
```

Meaning:

- `run_auto_tests.bat`: basic + mixed + full + block
- `run_quick_test.bat`: basic area only
- `run_full_test.bat`: broad `auto_rw_test --pc10g-full --include-p123` coverage
- `run_block_test.bat`: contiguous block-length checks only
- `run_validation_all.bat`: full + mixed + block + boundary + recovery write/read + last-writable probe
- `run_device_range_scan.bat`: two-pass coarse/fine range scan for all documented device families except `FR`; unsupported families are skipped automatically
- `run_fr_range_scan.bat`: two-pass coarse/fine range scan for `FR` only

Example `TCC-6740 + TCU-6858` range scan:

```bat
scripts\\run_device_range_scan.bat 192.168.250.100 1025 tcp 0 16 32
```

This runs:

- coarse forward scan with `step=16`
- fine forward scan with `step=1`
- the same target set for both passes
- default target set covers all documented device families except `FR`

`FR` only:

```bat
scripts\\run_fr_range_scan.bat 192.168.250.100 1025 tcp 0 16 32
```

Note:

- this batch is for broad range confirmation
- `FR` is excluded from the default target set and should be scanned explicitly with `run_fr_range_scan.bat`
- reverse scanning is still useful, but should be used only for tail-end discovery on a small target set such as `D,P1-D,P2-D,P3-D,U`

Split runners:

```bat
scripts\\run_quick_test.bat 192.168.250.100 1025
scripts\\run_full_test.bat 192.168.250.100 1025
scripts\\run_block_test.bat 192.168.250.100 1025 tcp 3 0 0x200
scripts\\run_validation_all.bat 192.168.250.100 1027 udp 4 5 2 0x200 12000 60
```

Generated outputs:

- `basic.log`
- `ext_multi.log`
- `pc10g_full.log`
- `block.log`
- `summary.txt`

## Verified Results

| Test | Result | Notes |
| --- | --- | --- |
| Full test | `TOTAL: 818/818` | checked on `2026-03-07`, `TOLERATED: 10`, `BIT:V: 10` |
| Full test over UDP | `TOTAL: 589/592` | checked on `2026-03-07`, `local_port=12000`, unsupported areas shown as skip |
| Mixed `CMD=98/99` over UDP | `TOTAL: 120/120` | checked on `2026-03-07`, `local_port=12000`, all current mixed cases passed |
| Block test over UDP | `TOTAL: 117/117` | checked on `2026-03-07`, `local_port=12000`, PC10 block ranges skipped on TOYOPUC-Plus |
| Boundary test over UDP | `TOTAL: 134/134` | checked on `2026-03-07`, `local_port=12000`, `U/L/M` boundaries passed and `EB` was skipped on `TOYOPUC-Plus` |
| TOYOPUC-Plus UDP final set | `full/mixed/block/boundary/recovery write/recovery read` | checked on `2026-03-07`, `local_port=12000`, supported areas verified |
| Recovery loop over TCP | `success: 102, error: 9, recoveries: 4` | checked on `2026-03-07`, `M0000`, `200 ms`, unplug/replug recovered |
| Recovery loop over UDP | `success: 43, error: 10, recoveries: 2` | checked on `2026-03-07`, `D0000`, `local_port=12000`, `200 ms`, `timeout=1`, `retries=0` |
| Recovery read loop over TCP | `success: 37, error: 4, recoveries: 2` | checked on `2026-03-07`, `M0000`, `expect=1`, unplug/replug recovered |
| Recovery read loop over UDP | `success: 43, error: 6, recoveries: 2` | checked on `2026-03-07`, `D0000`, `expect=0xFFFF`, `local_port=12000`, `timeout=1`, `retries=0` |
| Clock read on `TCC-6740 + TCU-6858` | `raw fields returned` | checked on `2026-03-08`, time fields were readable but calendar fields included `month=00`, `year=00` |
| Clock write/readback on `TCC-6740 + TCU-6858` | `successful` | checked on `2026-03-08`, write accepted and readback matched except for elapsed seconds |
| Clock read/write on `TCC-6740 + TCU-6858` over UDP | `successful after re-check` | checked on `2026-03-08`, read was stable and write converged correctly; first immediate readback could lag once |
| CPU status on `TCC-6740 + TCU-6858` | `decoded in RUN and STOP states` | checked on `2026-03-08`, decoded bits matched observed PLC state |
| Nano 10GX / `TUC-1157` full test over UDP | `TOTAL: 818/818` | checked on `2026-03-09`, `B`, prefixed upper ranges, `U08000+`, and `EB` were all supported in the runtime test set |
| Nano 10GX / `TUC-1157` `W/H/L` addressing over UDP | `TOTAL: 35/35` | checked on `2026-03-09`, word/byte relation and byte-to-bit relation both passed |
| Nano 10GX / `TUC-1157` high-level API over UDP | `TOTAL: 21/21` | checked on `2026-03-09`, high-level read/write and `read_many` / `write_many` passed |
| Nano 10GX / `TUC-1157` clock read/write over UDP | `successful` | checked on `2026-03-09`, write readback matched exactly |
| Nano 10GX / `TUC-1157` CPU status over UDP | `decoded in RUN state` | checked on `2026-03-09`, `RUN=True`, `PC10 mode=True`, `Alarm=False`, programs 1/2/3 running |
| Nano 10GX / `TUC-1157` FR read/write/commit over UDP | `successful` | checked on `2026-03-10`, `FR000000` read via `CMD=C2`, write via `CMD=C3`, commit via `CMD=CA`, and the written value persisted after CPU reset |
| Nano 10GX / `TUC-1157` `A0 01 10` during FR testing over UDP | `unsupported` | checked on `2026-03-10`, returned `0x24` (`Invalid subcommand code`) |
| Nano 10GX / `TUC-1157` FR full-range read scan over UDP | `successful` | checked on `2026-03-10`, `FR000000-FR1FFFFF` read with `holes: none`, `error_chunks=0`, and `crc32=0x00BF8BD1` before the full-range write test |
| Nano 10GX / `TUC-1157` FR full-range write/verify over UDP | `successful` | checked on `2026-03-10`, write pattern `seed=0xA500`, final commit phase across `64` FR blocks, `mismatch_words=0`, `expected_crc32=actual_crc32=0x6C5F5EB9` |
| Nano 10GX / `TUC-1157` FR full-range persistence after reset over UDP | `successful` | checked on `2026-03-10`, after CPU reset the full-range read scan still returned `holes: none` and `crc32=0x6C5F5EB9` |
| Nano 10GX / `TUC-1157` full test over TCP | `TOTAL: 818/818` | checked on `2026-03-09`, TCP `1025` matched the UDP full-test result |
| Nano 10GX / `TUC-1157` `W/H/L` addressing over TCP | `TOTAL: 35/35` | checked on `2026-03-09`, TCP `1025` matched the UDP `W/H/L` result |
| Nano 10GX / `TUC-1157` high-level API over TCP | `TOTAL: 21/21` | checked on `2026-03-09`, TCP `1025` matched the UDP high-level result |
| Nano 10GX / `TUC-1157` clock read over TCP | `successful` | checked on `2026-03-09`, valid calendar/time fields were returned over TCP `1025` |
| Nano 10GX / `TUC-1157` CPU status over TCP | `decoded in RUN state` | checked on `2026-03-09`, `RUN=True`, `PC10 mode=True`, `Alarm=False`, programs 1/2/3 running over TCP `1025` |
| Block test | `TOTAL: 198/198` | checked on `2026-03-07`, `TOLERATED: 12`, `BIT:V: 12` |
| Boundary test | `TOTAL: 220/220` | checked on `2026-03-07`, `U/EB/L/M` boundary transitions passed |
| Mixed `CMD=98/99` | `TOTAL: 198/198` | checked on `2026-03-07`, all current mixed cases passed |

### Full test

Command:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --count 4 --pc10g-full --include-p123 --skip-errors --log auto_pc10g_p123.log
```

Observed:

- `TOTAL: 818/818`
- `TOLERATED: 10`
- `BIT:V: 10`

### Block test

Command:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --max-block-test --skip-errors --log auto_block.log
```

Observed:

- `TOTAL: 198/198`
- `TOLERATED: 12`
- `BIT:V: 12`

### Full test over UDP

Command:

```bash
scripts\\run_full_test.bat 192.168.250.100 1027 udp 4 5 2 12000
```

Observed:

- `TOTAL: 589/592`
- `TOLERATED: 5`
- unsupported areas displayed as `SKIP (unsupported)`
- this result was taken on `TOYOPUC-Plus`

Observed again later on the same date:

- `TOTAL: 588/592`
- `TOLERATED: 3`
- unsupported prefixed high ranges and `EB` were shown as `SKIP (unsupported)`

### Mixed `CMD=98/99` over UDP

Command:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --ext-multi-test --skip-errors --log auto_ext_multi_udp.log
```

### Clock read on `TCC-6740 + TCU-6858`

Command:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp
```

Observed:

```text
raw: second=04 minute=17 hour=06 day=12 month=00 year=00 weekday=4
datetime: unavailable (month must be in 1..12, not 0)
```

Interpretation:

- the clock read command itself is accepted and returns fields
- this `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` returned a valid time-of-day
- the calendar fields were not fully initialized on the target at the time of the test
- callers should treat `read_clock()` as raw clock-field access first and only use `as_datetime()` when the PLC returns a valid calendar date

### Clock write/readback on `TCC-6740 + TCU-6858`

Command:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp --set "2026-03-08 18:52:08"
```

Observed:

```text
setting: 2026-03-08 18:52:08
readback raw: second=36 minute=52 hour=18 day=08 month=03 year=26 weekday=0
readback datetime: 2026-03-08 18:52:36
```

Interpretation:

- the write command was accepted
- readback matched the written calendar and time fields
- seconds had advanced by the time readback was performed
- `write_clock()` and `read_clock()` are both verified on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`

### Clock read/write on `TCC-6740 + TCU-6858` over UDP

Read command:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
```

Observed stable read:

```text
raw: second=13 minute=00 hour=20 day=08 month=03 year=26 weekday=0
datetime: 2026-03-08 20:00:13
```

Write command:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --set "2026-03-08 20:00:10"
```

Observed after re-check:

```text
setting: 2026-03-08 20:00:10
readback raw: second=16 minute=00 hour=20 day=08 month=03 year=26 weekday=0
readback datetime: 2026-03-08 20:00:16
```

Interpretation:

- UDP clock read is working on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`
- UDP clock write also worked after re-check
- one early write/readback attempt returned an older time-of-day before later attempts converged
- treat immediate first readback after UDP clock write with caution on this target

### CPU status on `TCC-6740 + TCU-6858`

Command:

```bash
python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1025 --protocol tcp
```

Observed in RUN:

```text
raw: 81 20 00 00 00 00 00 0E
```

Decoded meaning:

- `run = True`
- `pc10_mode = True`
- `alarm = True`
- `Under program 1 running = True`
- `Under program 2 running = True`
- `Under program 3 running = True`

Observed in STOP:

```text
raw: 61 20 00 00 00 00 00 00
```

Decoded meaning:

- `run = False`
- `Under a stop = True`
- `Under stop-request continuity = True`
- `pc10_mode = True`
- `alarm = True`
- `Under program 1 running = False`
- `Under program 2 running = False`
- `Under program 3 running = False`

Interpretation:

- the CPU status command itself is working on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`
- the decoded flag mapping is consistent with both observed RUN and STOP states

### Nano 10GX / `TUC-1157` over UDP

Connection that worked:

```bash
192.168.250.100:1027/udp with local_port=12000
```

Full runtime sweep:

```bash
scripts\\run_full_test.bat 192.168.250.100 1027 udp 4 5 2 12000
```

Observed:

- `TOTAL: 818/818`
- `TOLERATED: 10`
- `BIT:V: 10`
- `B` worked
- prefixed upper ranges worked
- `U08000-U1FFFF` worked
- `EB` worked in the runtime test set

`W/H/L` addressing:

```bash
python scripts\\whl_addressing_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --skip-errors --log whl_nano10gx.log
```

Observed:

- `TOTAL: 35/35`
- `ERROR CASES: 0`

High-level API:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --skip-errors --log high_level_nano10gx.log
```

Observed:

- `TOTAL: 21/21`
- `ERROR CASES: 0`

Clock read:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
```

Observed:

```text
raw: second=16 minute=45 hour=19 day=09 month=03 year=26 weekday=1
datetime: 2026-03-09 19:45:16
```

Clock write/readback:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --set "2026-03-09 20:00:10"
```

Observed:

```text
setting: 2026-03-09 20:00:10
readback raw: second=10 minute=00 hour=20 day=09 month=03 year=26 weekday=1
readback datetime: 2026-03-09 20:00:10
```

CPU status:

```bash
python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
```

Observed:

```text
raw: 81 00 00 00 00 00 00 0F
RUN: True
PC10 mode: True
Alarm: False
Under program 1 running: True
Under program 2 running: True
Under program 3 running: True
```

Range-scan note:

- `scripts\\run_device_range_scan.bat 192.168.250.100 1027 udp 12000 16 32`
- coarse scan showed continuous acceptance for documented families with no holes
- `B` and prefixed upper ranges were confirmed in the coarse scan
- `U00000-U1FFFF` was confirmed in the coarse scan
- `EB` was observed continuously at least through `EB41FF0` before the helper stopped after repeated upper-range errors
- `FR` was intentionally removed from the default target set and moved to a dedicated scan
- `scripts\\run_fr_range_scan.bat 192.168.250.100 1027 udp 12000 16 32`
- dedicated FR scan reported `ok=0`, `holes: all unsupported`

FR full-range read scan:

```bash
scripts\\run_fr_read_scan.bat 192.168.250.100 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read_full.log
```

Observed before full-range write:

- `ok_chunks=4096`
- `error_chunks=0`
- `ok_words=2097152`
- `holes: none`
- `crc32=0x00BF8BD1`

FR full-range write/verify:

```bash
scripts\\run_fr_write_scan.bat 192.168.250.100 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0xA500 fr_write_full_wait2.log
```

Observed:

- `commit_phase blocks=64`
- `write_errors=0`
- `verify_error_chunks=0`
- `mismatch_words=0`
- `expected_crc32=0x6C5F5EB9`
- `actual_crc32=0x6C5F5EB9`

Persistence re-check after CPU reset:

```bash
scripts\\run_fr_read_scan.bat 192.168.250.100 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read_full_after_reset_wait2.log
```

Observed after reset:

- `ok_chunks=4096`
- `error_chunks=0`
- `holes: none`
- `crc32=0x6C5F5EB9`

Interpretation:

- full-range FR read/write/commit persistence is confirmed on this model over UDP
- `A0` is not part of the working path on this model
- `CA` must be followed by completion wait per FR block
- practical wait path on this model is `CMD=32 / 11 00`, checking `Data7.bit4` and `Data7.bit5`

### Nano 10GX / `TUC-1157` over TCP

Connection that worked:

```bash
192.168.250.100:1025/tcp
```

Full runtime sweep:

```bash
scripts\\run_full_test.bat 192.168.250.100 1025 tcp 4 5 0
```

Observed:

- `TOTAL: 818/818`
- `TOLERATED: 10`
- `BIT:V: 10`
- TCP `1025` matched the UDP runtime result on this model

`W/H/L` addressing:

```bash
python scripts\\whl_addressing_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0 --log whl_nano10gx_tcp.log
```

Observed:

- `TOTAL: 35/35`
- `ERROR CASES: 0`

High-level API:

```bash
python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0 --log high_level_nano10gx_tcp.log
```

Observed:

- `TOTAL: 21/21`
- `ERROR CASES: 0`

Clock read:

```bash
python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0
```

Observed:

```text
raw: second=54 minute=32 hour=20 day=09 month=03 year=26 weekday=1
datetime: 2026-03-09 20:32:54
```

CPU status:

```bash
python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0
```

Observed:

```text
raw: 81 00 00 00 00 00 00 0F
RUN: True
PC10 mode: True
Alarm: False
Under program 1 running: True
Under program 2 running: True
Under program 3 running: True
```

Interpretation:

- this model is verified on both UDP `1027` and TCP `1025`
- the same broad runtime coverage passed over both transports

Observed:

- `TOTAL: 120/120`
- `TOLERATED: 5`
- all current mixed cases passed
- `B` word/byte areas were shown as `SKIP (unsupported)` on `TOYOPUC-Plus`

Observed again later on the same date:

- `TOTAL: 120/120`
- `TOLERATED: 3`
- all current mixed cases passed

### Block test over UDP

Command:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --max-block-test --pc10-block-words 0x200 --skip-errors --log auto_block_udp.log
```

Observed:

- `TOTAL: 117/117`
- `TOLERATED: 3`
- standard `D/U` block tests passed
- `U08000-... via PC10` and `EB00000-... via PC10` were shown as `SKIP (unsupported)` on `TOYOPUC-Plus`

### Boundary test over UDP

Command:

```bash
python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 5 --retries 2 --boundary-test --skip-errors --log auto_boundary_udp.log
```

Observed:

- `[BOUNDARY] U07FFE-U08001 transition: 4/4`
- `[BOUNDARY] EB3FFFE-EB40001 transition: SKIP (unsupported)`
- `[BOUNDARY] L07FE-L1001 transition: 8/8`
- `[BOUNDARY] M07FE-M1001 transition: 8/8`
- `TOTAL: 134/134`
- `TOLERATED: 2`

Observed again later on the same date:

- `TOTAL: 134/134`
- `TOLERATED: 4`

### Recovery loop over TCP

Command:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1025 --protocol tcp --target M0000 --interval-ms 200
```

Observed:

- `success: 102`
- `error: 9`
- `recoveries: 4`
- cable unplug/replug produced `Socket error` and timeout paths, then automatic recovery

### Recovery loop over UDP

Command:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 1 --retries 0 --target D0000 --interval-ms 200 --log recovery_udp.log
```

Observed:

- `success: 43`
- `error: 10`
- `recoveries: 2`
- cable unplug/replug produced `ToyopucTimeoutError`, then automatic recovery after reconnect

Observed again later on the same date:

- `success: 34`
- `error: 2`
- `recoveries: 1`

### Recovery read loop over TCP

Command:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1025 --protocol tcp --target M0000 --mode read --expect 1 --interval-ms 200 --log recovery_read.log
```

Observed:

- `success: 37`
- `error: 4`
- `recoveries: 2`
- cable unplug/replug produced `Socket error` and timeout paths, then automatic recovery
- recovered reads matched `expect=1`

### Recovery read loop over UDP

Command:

```bash
python scripts\\recovery_write_loop.py --host 192.168.250.100 --port 1027 --local-port 12000 --protocol udp --timeout 1 --retries 0 --target D0000 --mode read --expect 0xFFFF --interval-ms 200 --log recovery_read_udp.log
```

Observed:

- `success: 43`
- `error: 6`
- `recoveries: 2`
- cable unplug/replug produced `ToyopucTimeoutError`, then automatic recovery after reconnect
- recovered reads matched `expect=0xFFFF`

Observed again later on the same date:

- `success: 18`
- `error: 3`
- `recoveries: 1`
- recovered reads matched `expect=0xFFFF`

### TOYOPUC-Plus UDP final set

Summary on `2026-03-07` with `local_port=12000`:

- `full`: supported areas verified, unsupported ranges shown as `SKIP (unsupported)`
- `mixed`: all current cases passed
- `block`: standard `D/U` block tests passed
- `boundary`: supported transitions passed
- `recovery write`: unplug/replug recovered
- `recovery read`: unplug/replug recovered

Practical conclusion:

- `TOYOPUC-Plus` over UDP is usable on supported device families
- unsupported areas should be interpreted as device limitations, not transport failure
- fixed PC-side UDP source port is required in this environment

### Boundary test

Observed:

- `[BOUNDARY] U07FFE-U08001 transition: 8/8`
- `[BOUNDARY] EB3FFFE-EB40001 transition: 4/4`
- `[BOUNDARY] L07FE-L1001 transition: 8/8`
- `[BOUNDARY] M07FE-M1001 transition: 8/8`
- `TOTAL: 220/220`

### Mixed `CMD=98/99`

Observed:

- `[EXT MULTI] EX0000 + U0000(byte) + EN0000(word): 1/1`
- `[EXT MULTI] GX0000 + GX/GY byte(0001) + ES0000(word): 1/1`
- `[EXT MULTI] P1-M0000 + P1-D0000(byte) + P1-D0000(word): 1/1`
- `[EXT MULTI] GX0000 + GX/GY byte(0000): 1/1`
- `[EXT MULTI] GX/GY byte(0000) + ES0000(word): 1/1`
- `[EXT MULTI] GX0000 + ES0000(word): 1/1`
- `TOTAL: 198/198`
- `TOLERATED: 10`

## Coverage

- Base bit: `P/K/V/T/C/L/X/Y/M`
- Base word: `S/N/R/D/B`
- Base byte: `D/B`
- Prefixed devices: `P1/P2/P3`
- Extended bit: `EP/EK/EV/ET/EC/EL/EX/EY/EM/GX/GY/GM`
- Extended word: `ES/EN/H/U/EB`
- Mixed `CMD=98/99`: bit + byte + word in one request
- Boundary transitions:
- `U07FFE-U08001`
- `EB3FFFE-EB40001`
- `L07FE-L1001`
- `M07FE-M1001`
- UDP boundary transitions on `TOYOPUC-Plus`:
- `U07FFE-U08001`
- `L07FE-L1001`
- `M07FE-M1001`
- `EB3FFFE-EB40001` as `SKIP (unsupported)`
- Contiguous block tests:
- `D` word `x0200`
- `D` byte `x0400`
- `U` word `x0200`
- `U` byte `x0400`
- `U` PC10 word `x0200`
- `EB` PC10 word `x0200`
- Recovery loop:
- `TCP` on `M0000`
- `UDP` on `D0000`
- Recovery read loop:
- `TCP` on `M0000`
- `UDP` on `D0000`

## PC3JX-D (TCC-6902) PC3 divisions mode note

- `python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0`
  - `pc3_mode=True`, `pc10_mode=False`, programs 1-3 were running, and all FR-related bits were clear.
- `python scripts\\clock_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0`
  - `datetime: 2026-03-10 08:00:57` was read successfully.
- `scripts\\run_full_test.bat 192.168.250.100 1025 tcp 4 5 0`
  - Basic ranges and lower prefixed ranges (`P1/P2/P3`) completed.
  - PC10 families (`U/EB/FR`) and upper prefixed ranges such as `P1-M1000` were `SKIP (unsupported)`.
  - `GX/GY/GM` may show partial sample counts such as `3/6` or `4/8` when random probes hit unsupported addresses; valid addresses were still writable.
- `python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --count 4 --pc10g-full --include-p123 --skip-errors --log auto_pc3jx.log`
  - The same coverage was recorded in the log (`TOTAL: 522/532`); only unsupported areas were skipped.
- `scripts\\run_quick_test.bat`
  - This helper can still hit upper `D` word addresses and return `error_code=0x40` on PC3JX-D.
  - Use `run_full_test` / `auto_rw_test` as the authoritative range evidence for this mode.

## PC3JX-D (TCC-6902) Plus Expansion Mode note

- `python scripts\\cpu_status_test.py --host 192.168.250.100 --port 1025 --protocol tcp --timeout 5 --retries 0`
  - `pc3_mode=False`, `pc10_mode=True`, programs 1-3 were running.
- `python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --count 4 --pc10g-full --include-p123 --skip-errors --log auto_pc10g_p123.log`
  - Basic ranges and `U00000-U1FFFF` completed.
  - `EB` remained `SKIP (unsupported)`.
- `python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --max-block-test --pc10-block-words 0x200 --skip-errors --log auto_block.log`
  - `U` block access (`x0200`) passed.
  - `EB` block access was skipped.
  - `B` does not exist on this model, so `B` byte/word tests were skipped.
- `python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --boundary-test --skip-errors --log auto_boundary.log`
  - PC10 boundary checks such as `U07FFE-U08001` passed.
  - `EB3FFFE-EB40001` remained skipped.
- `python scripts\\auto_rw_test.py --host 192.168.250.100 --port 1025 --protocol tcp --ext-multi-test --skip-errors --log auto_ext_multi.log`
  - Mixed extended access across `GX/GY`, `ES/EN`, and prefixed areas completed in PC10 mode.
- `scripts\\run_full_test.bat 192.168.250.100 1025 tcp 4 5 0`
  - `TOTAL: 544/544` with only `EB` skipped.
- `scripts\\run_fr_commit_test.bat` / `scripts\\run_fr_write_scan.bat`
  - Both returned `error_code=0x40`; PC3JX-D does not expose `FR` even in PC10 mode.
