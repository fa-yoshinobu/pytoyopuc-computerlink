# TOYOPUC Computer Link Spec

Related documents:

- [../README.md](../README.md)
- [TESTING_GUIDE.md](TESTING_GUIDE.md)
- [../user/MODEL_RANGES.md](../user/MODEL_RANGES.md)
- [../../scripts/README.md](../../scripts/README.md)

This document is a working protocol summary for the 2ET Ethernet module.

It is not a verbatim manufacturer manual. It is a reorganized implementation note based on the current code and verified hardware behavior.

## Scope

This file is organized into three parts:

1. frame format
2. command groups
3. address and `Ex No.` tables

Testing and operational usage are documented in [TESTING_GUIDE.md](TESTING_GUIDE.md).

Status labels for this file:

- `verified`: behavior confirmed on current hardware
- `implementation rule`: behavior intentionally used by this project
- `summary`: reorganized description for easier implementation

## 1. Frame format

Common command frame:

```text
+------+------+------+------+------+-------------------+
| FT   | RC   | LL   | LH   | CMD  | DATA              |
+------+------+------+------+------+-------------------+
```

- `FT`: frame type
- `RC`: response code
- `LL/LH`: payload length, excluding the 5-byte header
- `CMD`: command code
- `DATA`: command payload

### FT / RC

- request: `FT=0x00`, `RC=0x00`
- response: `FT=0x80`, `RC=0x00` on success
- `RC != 0x00` means PLC-side error or rejection

### Error response codes

If the PLC returns a NAK response, the detailed error code may appear either:

- in the `CMD` byte, for example `80 10 01 00 40`
- or in the response data, depending on command path / module behavior

For this project, `rc=0x10` is treated as NAK and the client tries both forms when formatting the error.
- `RC=0x10` means NAK / anomaly response

Example:

- request rejected with out-of-range address:
  - response: `80 10 01 00 40`
  - interpretation:
    - `RC=0x10`: NAK
    - detailed error code: `0x40`
    - meaning: address out of range

Observed and documented error codes:

| Code | Meaning |
| --- | --- |
| `0x11` | CPU module hardware failure |
| `0x20` | Relay command ENQ fixed data is not `0x05` |
| `0x21` | Invalid transfer number in relay command |
| `0x23` | Invalid command code |
| `0x24` | Invalid subcommand code |
| `0x25` | Invalid command-format data byte |
| `0x26` | Invalid function-call operand count |
| `0x31` | Write or function call prohibited during sequence operation |
| `0x32` | Command not executable during stop continuity |
| `0x33` | Debug function called while not in debug mode |
| `0x34` | Access prohibited by configuration |
| `0x35` | Execution-priority limiting configuration prohibits execution |
| `0x36` | Execution-priority limiting by another device prohibits execution |
| `0x39` | Reset required after writing I/O parameters before scan start |
| `0x3C` | Command not executable during fatal failure |
| `0x3D` | Competing process prevents execution |
| `0x3E` | Command not executable because reset exists |
| `0x3F` | Command not executable because of stop duration |
| `0x40` | Address or address+count is out of range |
| `0x41` | Word/byte count is out of range |
| `0x42` | Undesignated data was sent |
| `0x43` | Invalid function-call operand |
| `0x52` | Timer/counter set/current value access mismatch |
| `0x66` | No reply from relay link module |
| `0x70` | Relay link module not executable |
| `0x72` | No reply from relay link module |
| `0x73` | Relay command collision on same link module; retry required |

Status: `summary` from manufacturer error code table

## 2. Command groups

### Base area access

- CPU status read: `CMD=32`, subcommand `11 00`
- CPU status read for flash/FR flow: `CMD=A0`, subcommand `01 10`
- clock read: `CMD=32`, subcommand `70 00`
- clock write: `CMD=32`, subcommand `71 00`
- word read: `CMD=1C`
- word write: `CMD=1D`
- byte read: `CMD=1E`
- byte write: `CMD=1F`
- bit read: `CMD=20`
- bit write: `CMD=21`
- multi-point word/byte/bit: `CMD=22-27`

### Clock access

- clock read request: `00 00 03 00 32 70 00`
- clock read response:
  - `80 RC 0A 00 32 70 00 SS MM HH DD MM YY WW`
- clock write request:
  - `00 00 0A 00 32 71 00 SS MM HH DD MM YY WW`
- clock write response:
  - `80 RC 03 00 32 71 00`

Rules:

- 24-hour format
- year is the last two digits of AD
- BCD encoding
- weekday:
  - `0`: Sunday
  - `1`: Monday
  - ...

Observed on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`:

- the command itself is accepted
- time-of-day fields can be valid
- calendar fields can still contain `00`

Example observed response body:

```text
70 00 04 17 06 12 00 00 04
```

Meaning:

- `second=04`
- `minute=17`
- `hour=06`
- `day=12`
- `month=00`
- `year=00`
- `weekday=4`

Implementation note:

- this project exposes raw clock fields first
- `datetime` conversion is treated as best-effort only
- callers should expect `month=00` / `year=00` on some targets

### CPU status access

- CPU status read request:
  - `00 00 03 00 32 11 00`
- CPU status read response:
  - `80 RC 0B 00 32 11 00 D1 D2 D3 D4 D5 D6 D7 D8`

### CPU status access for flash/FR flow

- CPU status read request:
  - `00 00 03 00 A0 01 10`
- CPU status read response:
  - `80 RC 0B 00 A0 01 10 D1 D2 D3 D4 D5 D6 D7 D8`

Notes:

- this is a separate command path from `CMD=32 / 11 00`
- it is referenced in the flash-register write completion flow
- the 8 status bytes use the same `Data1-Data8` bit layout as the existing CPU-status table below
- in the current project, FR write completion is checked mainly with:
  - `Data7.bit4`: under writing flash register
  - `Data7.bit5`: abnormal write flash register
- practical completion rule:
  - wait until `Data7.bit4 == 0`
  - treat `Data7.bit5 == 1` as flash-write failure
- practical transport rule:
  - prefer `CMD=A0 / 01 10` when the target accepts it
  - if the target rejects `A0` with `0x23/0x24/0x25/0x26`, use normal CPU status `CMD=32 / 11 00` instead
  - on `Nano 10GX (TUC-1157)`, `A0` returned `0x24`, and `CMD=32 / 11 00` `Data7.bit4/bit5` was used successfully for FR commit waiting
  - on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` relay FR commit over `P1-L2:N2`, relay `A0` returned `0x26`, and the same `CMD=32 / 11 00` fallback path was used successfully

Data bytes:

- `Data1`
  - bit7: `RUN`
  - bit6: Under a stop
  - bit5: Under stop-request continuity
  - bit4: Under a pseudo-stop
  - bit3: Debug mode
  - bit2: I/O monitor user mode
  - bit1: PC3 mode
  - bit0: PC10 mode
- `Data2`
  - bit7: Fatal failure
  - bit6: Faint failure
  - bit5: Alarm
  - bit3: I/O allocation parameter altered
  - bit2: With a memory card
- `Data3`
  - bit7: Memory card operation
  - bit6: Write-protected program and supplementary information
- `Data4`
  - bit7: Read-protected system memory
  - bit6: Write-protected system memory
  - bit5: Read-protected system I/O
  - bit4: Write-protected system I/O
- `Data5`
  - bit7: Trace
  - bit6: Scan sampling trace
  - bit5: Periodic sampling trace
  - bit4: Enable detected
  - bit3: Trigger detected
  - bit2: One scan step
  - bit1: One block step
  - bit0: One instruction step
- `Data6`
  - bit7: I/O off-line
  - bit6: Remote RUN setting
  - bit5: Status latch setting
- `Data7`
  - bit6: Write-priority limited program and supplementary information
  - bit5: Abnormal write flash register
  - bit4: Under writing flash register
  - bit3: Abnormal write of equipment info.
  - bit2: abnormal writing of equipment info
  - bit1: abnormal write during RUN
  - bit0: under writing during RUN
- `Data8`
  - bit3: under program 3 running
  - bit2: under program 2 running
  - bit1: under program 1 running

Status: `summary`

### Relay command

Status: `verified` for selected relay read flows on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` over UDP on `2026-03-10`

- command code: `CMD=60`
- purpose: tunnel any CPU command (`CMD=01-42`) through a chain of FL-net / HPC Link modules
- maximum payload: **< 550 bytes** for both request and response (manufacturer caution)

#### Single-hop format

```
Request:
00 00 LL LH 60 LinkNo ExNo 00 05 LL' LH' <inner command...>

Response (success):
80 RC LL LH 60 LinkNo ExNo 00 06 LL' LH' <inner response...> [padding]

Response (error):
80 00 .. .. 60 LinkNo ExNo 00 15 .. .. <error payload> [padding]
```

- `LinkNo`: target FL-net link number (8-bit)
- `ExNo`: target exchange number (8-bit)
- `00`: reserved byte
- `05` / `06` / `15`: fixed bytes representing `ENQ` / `ACK` / `NAK`
- `LL/LH`: outer transfer byte count (excluding 5-byte frame header)
- `LL'/LH'`: inner command byte count (excluding the relay wrapper)
- `<inner command...>`: literal frame payload for the command destined to the remote CPU (e.g., word read `CMD=1C`)
- `<inner response...>`: literal response payload produced by the remote CPU
- `<error payload>`: manufacturer error format (`EC` + details); refer to the response-data error code table.
If the downstream CPU rejects the command, the relay wrapper still uses `NAK=0x15` and propagates the CPU-side error payload.
If the downstream PLC is unreachable, no reply may arrive for up to **5 seconds**; retries must wait more than 5 seconds between attempts.
Repeated relays toward an unreachable address can raise hardware fault **H9** on the relay PLC; recovery requires CPU reset.

#### Example: read `D0100-D0102` on Link No.2 / Exchange No.3

```
Request:
00 00 0D 00 60 02 03 00 05 05 00 1C 00 11 03 00 00

Response (values 0100/0302/0504):
80 00 0F 00 60 02 03 00 06 07 00 1C 00 01 02 03 04 05 XX
```

`XX` indicates undefined trailing padding.

#### Hierarchical relay (multi-hop)

CMD=60 wrappers can be nested up to **four stages**. Each hop prepends its own `(LinkNo, ExNo, ENQ, length)` tuple in front of the downstream relay block.

Example: three-hop relay reaching `III CPU` (partial bytes):

```
00 00 15 00
  60 02 01 00 05 0D 00   ; outer hop (I)
    60 02 01 00 05 05 00 ; middle hop (II)
      1C 00 11 03 00 00  ; inner command to III CPU
```

The response mirrors the nesting order, replacing each `05` with `06` and appending the inner CPU data (`D0100-D0102`).

Four-hop relays (`IV CPU`) follow the same pattern with another wrapper (`Transfer Byte No.(4)` etc.).

#### Practical guidance

- Always calculate `LL/LH` after the inner payload is assembled.
- Ensure every wrapper uses the correct `Link No.` / `Exchange No.` pair for its stage.
- Because latency compounds (each level can wait up to 5 seconds for timeouts), clients should set generous timeouts and back off aggressively when no response is seen.
- Verified on real hardware for these single-hop relay flows via `P1-L2:N2` (`Link=0x12`, `Exchange=0x0002`):
  - `CMD=32 / 11 00` CPU status read
  - `CMD=32 / 70 00` clock read
  - `CMD=1C` word read (`D0000`, count=`1`)
  - `CMD=C2` FR read (`FR000000`, count=`1`)
  - `CMD=C3` FR write (`FR000000 = 0x55AA`) with immediate readback
  - `CMD=CA` FR commit on `FR000000` with successful completion wait
  - post-reset `CMD=C2` FR read confirming that the committed `FR000000 = 0x55AA` value persisted after CPU reset
- Verified on real hardware for this two-hop read flow:
  - hops: `P1-L2:N2 -> P1-L2:N4`
  - inner command: `CMD=32 / 11 00` CPU status read
- Verified on real hardware for this three-hop read flow:
  - hops: `P1-L2:N2 -> P1-L2:N4 -> P1-L2:N6`
  - inner commands:
    - `CMD=32 / 11 00` CPU status read
    - `CMD=32 / 70 00` clock read
    - `CMD=32 / 71 00` clock write with successful readback
    - `CMD=1C` word read (`D0000`, count=`1`)
- Verified on real hardware for this three-hop write flow:
  - hops: `P1-L2:N2 -> P1-L2:N4 -> P1-L2:N6`
  - inner command:
    - `CMD=1D` basic word write (`D0000 = 0x1234`)
  - readback through the same relay path confirmed `D0000 = 0x1234`
- Verified on real hardware for this three-hop contiguous word block flow:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - inner commands:
    - `CMD=1D` contiguous word write on `D0000-D0007`
    - `CMD=1C` contiguous word read on `D0000-D0007`
  - checked with `count=8`, `loops=3`, patterns `0x1000-0x1007`, `0x1100-0x1107`, `0x1200-0x1207`
  - observed result: `summary = 3/3 loops passed`
- Verified on real hardware for this broader three-hop relay matrix:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - contiguous block results:
    - `D0000`, `R0000`, `U08000`: `count=16` and `count=32` both passed `3/3` loops
    - `S0000`: `count=16` and `count=32` did not retain the written patterns on this path
  - `write_many()` across `D0000/R0000/S0000/U08000`: passed
  - mixed `write_many()` case including `M0000`, `D0000L`, `P1-D0000`, `ES0000`, `U08000`: word/bit items passed, the `D0000L` byte readback did not hold the requested value on this path
  - repeated relay `clock-write` / readback / restore loop: passed
- Verified on real hardware for this three-hop relay FR flow:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - inner commands:
    - `CMD=C2` FR read (`FR000000`, count=`1`)
    - `CMD=C3` FR write (`FR000000 = 0x0099`) with immediate readback
    - `CMD=CA` FR commit on `FR000000` with completion wait
  - follow-up reads through the same relay path confirmed `FR000000 = 0x0099`
- Verified on real hardware for this three-hop relay high-level API sweep:
  - hops: `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`
  - command:
    - `python scripts\\high_level_api_test.py --host 192.168.250.100 --port 1027 --protocol udp --local-port 12000 --timeout 10 --retries 1 --hops "P1-L2:N4,P1-L2:N6,P1-L2:N2" --include-pc10-word`
  - observed result:
    - `TOTAL: 24/24`
    - `ERROR CASES: 0`
  - practical coverage:
    - basic bit / word / byte
    - prefixed bit / word
    - extended bit / word
    - PC10 word
    - contiguous basic sequences
    - mixed `read_many()` / `write_many()`
  - Observed response layout on that path:
    - outer response data: `Link, ExLo, ExHi, ACK, inner..., padding?`
    - inner response may contain one trailing padding byte after the valid relay payload
- Verified on real hardware for relay low-level sweeps on `P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`:
  - UDP:
    - passed: `CMD=32 / 11 00`, `CMD=32 / 70 00`, `CMD=32 / 71 00`, `CMD=20/21`, `CMD=1C/1D`, `CMD=24/25`, `CMD=94/95`, `CMD=96/97`, `CMD=98/99`, `CMD=C2/C3`
    - standalone relay `CMD=A0 / 01 10` returned relay NAK `0x15`
    - the `D0000L` single-byte and `D0000/D0001` multi-word checks did not hold the requested values on this UDP path
  - TCP:
    - passed: `CMD=32 / 11 00`, `CMD=32 / 70 00`, `CMD=20/21`, `CMD=1C/1D`, `CMD=1E/1F`, `CMD=22/23`, `CMD=24/25`, `CMD=94/95`, `CMD=96/97`, `CMD=98/99`, `CMD=C2/C3`
    - standalone relay `CMD=A0 / 01 10` returned relay NAK `0x15`
- Verified abnormal relay observations on the same three-hop path:
  - missing station: timeout / no reply
  - broken path: timeout / no reply
  - raw out-of-range basic word read (`D3000`): timeout / no reply
  - relay write to `S0000`: timeout / no reply

### Extended area access

- extended word read: `CMD=94`
- extended word write: `CMD=95`
- extended byte read: `CMD=96`
- extended byte write: `CMD=97`
- extended multi-point read: `CMD=98`
- extended multi-point write: `CMD=99`

Status: `verified` for `CMD=94-99` paths currently used by this project.

### PC10 access

- PC10 block read: `CMD=C2`
- PC10 block write: `CMD=C3`
- PC10 multi read: `CMD=C4`
- PC10 multi write: `CMD=C5`
- FR register: `CMD=CA`

Status:

- `CMD=C2-C5`: `verified` on the ranges used by this project
- `CMD=CA`: `verified` on `Nano 10GX (TUC-1157)` for direct FR block commit and on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)` for single-hop relay FR commit over `P1-L2:N2`

## 3. Base address tables

### Word base addresses

- `K`: `0x0020`
- `V`: `0x0050`
- `T/C`: `0x0060`
- `L`: `0x0080`
- `X/Y`: `0x0100`
- `M`: `0x0180`
- `S`: `0x0200`
- `N`: `0x0600`
- `R`: `0x0800`
- `D`: `0x1000`
- `B`: `0x6000`

### Byte base addresses

- `K`: `0x0040`
- `V`: `0x00A0`
- `T/C`: `0x00C0`
- `L`: `0x0100`
- `X/Y`: `0x0200`
- `M`: `0x0300`
- `S`: `0x0400`
- `N`: `0x0C00`
- `R`: `0x1000`
- `D`: `0x2000`
- `B`: `0xC000`

### Bit base addresses

- `K`: `0x0200`
- `V`: `0x0500`
- `T/C`: `0x0600`
- `L`: `0x0800`
- `X/Y`: `0x1000`
- `M`: `0x1800`

## 3.5 W/H/L Addressing For Bit Devices

Bit devices can also be handled with `W/H/L` addressing as 16-bit or 8-bit values.

Rules:

- append `W` for 16-bit word access
- append `L` for the lower byte of that word
- append `H` for the upper byte of that word

Examples:

- `X0010W`
  - means 16 points `X0100-X010F`
- `M0003W`
  - means 16 points `M0030-M003F`
- `D1000L`
  - lower byte of `D1000`
- `X0010H`
  - upper byte of `X0010W`, i.e. `X0108-X010F`

Addressing notes:

- for 16-bit or 32-bit handling, use a word address
- the upper byte cannot be used as the starting point of a word or 32-bit value
- `X/Y` do not share the same address number
- `T/C` do not share the same address number

Implementation rule:

- this project accepts the following public `W/H/L` syntax:
  - basic bit families: `K/V/T/C/L/X/Y/M/P`
  - prefixed bit families: `P1-*`, `P2-*`, `P3-*`
  - extended bit families: `EP/EK/EV/ET/EC/EL/EX/EY/EM/GX/GY/GM`
- examples:
  - `M0010W`
  - `X0010L`
  - `P1-M0010W`
  - `EX0010H`
  - `GX0010L`

## 4. Shared-area naming

Shared-area aliases exist internally, but user-facing names in this project are:

- `X/Y`
- `T/C`
- `EX/EY`
- `ET/EC`
- `GX/GY`

Notes:

- internal aliases are implementation details only
- `GX/GY` also share one internal byte area

## 5. `CMD=98/99` layout

### Bit point

For bit points, one byte packs:

- upper 4 bits: bit position `0-7`
- lower 4 bits: program number

### Program number mapping used by the current implementation

- `00`: `EP/EK/EV/ET/EC/EL/EX/EY/EM`
- `07`: `GX/GY/GM`
- `01`: `P1`
- `02`: `P2`
- `03`: `P3`

Status: `confirmed on Nano 10GX (TUC-1157)` against candidate `no` values `00/01/02/03/07` on `2026-03-10`

### Mixed multi-point limits

For `CMD=98/99`:

- address total: `<= 176` points
- data total: `<= 128` bytes

Status: `summary`

## 6. PC10 `CMD=C4/C5` usage

The current implementation uses PC10 multi access (`CMD=C4/C5`) for these ranges:

- `L1000-L2FFF`
- `M1000-M17FF`

Status: `confirmed on Nano 10GX (TUC-1157)` for current use on `2026-03-10`

For `U/EB`, the normal word/byte path in the current implementation is not `CMD=C4/C5`:

- `U00000-U07FFF`
- `U08000-U1FFFF`
- `EB00000-EB3FFFF`
- `EB40000-EB7FFFF`

Path summary:

- `U00000-U07FFF`: `CMD=94/95`
- `U08000-U1FFFF`: `CMD=C2/C3`
- `EB00000-EB3FFFF`: `CMD=C2/C3`
- `EB40000-EB7FFFF`: `CMD=94/95`

Additional Nano 10GX probe result on `2026-03-10`:

- `CMD=C4/C5` also reached the same points for `U00000-U1FFFF`
- `CMD=C4/C5` also reached the same points for `EB00000-EB3FFFF`
- `L1000-L2FFF` and `M1000-M17FF` did not alias to basic `CMD=20/21`, so those upper bit ranges should stay on `CMD=C4/C5`

## 7. Prefixed areas `P1/P2/P3`

### Basic area 2

`P1` uses `Ex No.=0D`, `P2` uses `Ex No.=0E`, `P3` uses `Ex No.=0F`.

PC3JG-compatible ranges:

| Name | Address | Byte Address |
| --- | --- | --- |
| Edge | `P000-P1FF` | `0000-003F` |
| Keep relay | `K000-K2FF` | `0040-009F` |
| Special relay | `V000-V0FF` | `00A0-00BF` |
| Timer / Counter | `T/C000-T/C1FF` | `00C0-00FF` |
| Link relay | `L000-L7FF` | `0100-01FF` |
| I/O | `X/Y000-X/Y7FF` | `0200-02FF` |
| Internal relay | `M000-M7FF` | `0300-03FF` |
| Special register | `S0000-S03FF` | `0400-0BFF` |
| Current value register | `N0000-N01FF` | `0C00-0FFF` |
| Link register | `R0000-R07FF` | `1000-1FFF` |
| Data register 1 | `D0000-D0FFF` | `2000-3FFF` |
| Data register 2 | `D1000-D2FFF` | `4000-7FFF` |

PC10-extended ranges:

| Name | Address | Byte Address |
| --- | --- | --- |
| Edge | `P1000-P17FF` | `C000-C0FF` |
| Special relay | `V1000-V17FF` | `C100-C1FF` |
| Timer / Counter | `T/C1000-T/C17FF` | `C200-C2FF` |
| Internal relay | `M1000-M17FF` | `C300-C3FF` |
| Link relay | `L1000-L2FFF` | `C400-C7FF` |
| Special register | `S1000-S13FF` | `C800-CFFF` |
| Current value register | `N1000-N17FF` | `D000-DFFF` |

## 8. Extended areas

### Extended Area 1

`Ex No.=01`

| Name | Address | Byte Address | Program No. |
| --- | --- | --- | --- |
| Extended edge | `EP000-EPFFF` | `0000-01FF` | `00` |
| Extended keep relay | `EK000-EKFFF` | `0200-03FF` | `00` |
| Extended special relay | `EV000-EVFFF` | `0400-05FF` | `00` |
| Extended timer / counter | `ET/EC000-ET/EC7FF` | `0600-06FF` | `00` |
| Extended link relay | `EL0000-EL1FFF` | `0700-0AFF` | `00` |
| Extended I/O | `EX/EY000-EX/EY7FF` | `0B00-0BFF` | `00` |
| Extended internal relay | `EM0000-EM1FFF` | `0C00-0FFF` | `00` |
| Extended special register | `ES0000-ES07FF` | `1000-1FFF` | `00` |
| Extended current value register | `EN0000-EN07FF` | `2000-2FFF` | `00` |
| Extended setting value register | `H0000-H07FF` | `3000-3FFF` | `00` |

### Extended Area 2

| Name | Address | Byte Address | Program No. |
| --- | --- | --- | --- |
| Extended I/O | `GX/GY0000-GX/GYFFFF` | `0000-1FFF` | `07` |
| Extended internal relay | `GM0000-GMFFFF` | `2000-3FFF` | `07` |

### Extended Area 3

| Ex No. | Address | Byte Address | Program No. |
| --- | --- | --- | --- |
| `03` | `U00000-U07FFF` | `0000-FFFF` | `08` |
| `04` | `U08000-U0FFFF` | `0000-FFFF` | `08` |
| `05` | `U10000-U17FFF` | `0000-FFFF` | `08` |
| `06` | `U18000-U1FFFF` | `0000-FFFF` | `08` |

### Extended Area 4

| Ex No. | Address | Byte Address |
| --- | --- | --- |
| `10` | `EB00000-EB07FFF` | `0000-FFFF` |
| `11` | `EB08000-EB0FFFF` | `0000-FFFF` |
| `12` | `EB10000-EB17FFF` | `0000-FFFF` |
| `13` | `EB18000-EB1FFFF` | `0000-FFFF` |
| `14` | `EB20000-EB27FFF` | `0000-FFFF` |
| `15` | `EB28000-EB2FFFF` | `0000-FFFF` |
| `16` | `EB30000-EB37FFF` | `0000-FFFF` |
| `17` | `EB38000-EB3FFFF` | `0000-FFFF` |

### Extended Area 5

Flash register `FR`:

- `Ex No. 40-7F`
- each block covers `0x8000` words
- read/write path: PC10 block read/write (`CMD=C2/C3`)
- commit path after write: FR register registration (`CMD=CA`)
- examples:
  - `40`: `FR000000-FR007FFF`
  - `41`: `FR008000-FR00FFFF`
  - `7F`: `FR1F8000-FR1FFFFF`

Implementation note:

- direct `CMD=94 no=40-7F` is not the real-hardware FR read path
- write flow is `C3 -> CA -> completion check`
- `CA` is a registration / commit step for the written FR block, not a read bank-select command
- each `CA` applies to one `64-kbyte` FR block
- when multiple FR blocks are written, `CA` must be issued once per affected block
- practical safe flow is:
  - write the block with `C3`
  - issue `CA` for that block
  - wait for completion before issuing `CA` for the next block
- on `Nano 10GX (TUC-1157)`, the completion wait used `CMD=32 / 11 00` `Data7.bit4/bit5` because `A0` was unsupported
- during initialization, flash-memory data is transferred into the FR area in RAM
- after initialization, normal direct access targets the FR work area in RAM, similar to `EB`
- writing the FR area with normal commands updates RAM only
- writing flash memory itself requires the special FR registration flow
- if `CA` is not issued, the original flash content is restored on power-off or CPU reset
- full-range `FR000000-FR1FFFFF` read/write/commit persistence was verified on `Nano 10GX (TUC-1157)` over UDP on `2026-03-10`

## 9. Examples

### Base word

`D0100` word address:

- word base for `D`: `0x1000`
- index: `0x0100`
- result: `0x1100`

### Base byte

`D0100L` byte address:

- byte base for `D`: `0x2000`
- byte offset: `0x0100 * 2`
- result: `0x2200`

### Prefixed bit 32-bit example

`P1-M1000`

- bit address: `0x61800`
- `Ex No.=0x0D`
- combined 32-bit value: `0x006E1800`

### Prefixed byte 32-bit example

`P2-D2000L`

- byte address: `0x6000`
- `Ex No.=0x0E`
- combined 32-bit value: `0x000E6000`

## 10. Message examples

### `CMD=1C` word read

Read `D0100-D0102`:

```text
00 00 05 00 1C 00 11 03 00
```

Example response:

```text
80 00 07 00 1C 00 01 02 03 04 05
```

### `CMD=1D` word write

Write `0x1234` to `D0100`:

```text
00 00 05 00 1D 00 11 34 12
```

Example response:

```text
80 00 01 00 1D
```

### `CMD=94` extended word read

Read `U0000` 1 word:

```text
00 00 06 00 94 08 00 00 01 00
```

Example response when `U0000=1234H`:

```text
80 00 03 00 94 34 12
```

### `CMD=95` extended word write

Write `1234H` to `U0000`:

```text
00 00 06 00 95 08 00 00 34 12
```

Example response:

```text
80 00 01 00 95
```

### `CMD=96` extended byte read

Read 2 bytes from `EN0000`:

```text
00 00 06 00 96 00 00 20 02 00
```

Example response when `EN0000=1234H`:

```text
80 00 03 00 96 34 12
```

### `CMD=97` extended byte write

Write `12H 34H` to `EN0000L` and `EN0000H`:

```text
00 00 06 00 97 00 00 20 12 34
```

Example response:

```text
80 00 01 00 97
```

### `CMD=98` extended multi-point read

Read 1 bit from `EX0000`, 1 byte from `U0000`, 1 word from `EN0000`:

```text
00 00 0D 00 98 01 01 01 00 00 0B 08 00 00 00 00 10
```

Example response:

```text
80 00 05 00 98 00 E1 D3 3B
```

Interpretation:

- bit data: `00`
- byte data: `E1`
- word data: `3BD3H`

### `CMD=99` extended multi-point write

Write bit `EX0000=1`, byte `U0000=1EH`, word `EN0000=C42CH`:

```text
00 00 11 00 99 01 01 01 00 00 0B 01 08 00 00 1E 00 00 10 2C C4
```

Example response:

```text
80 00 01 00 99
```

### `CMD=C4` PC10 multi read

Read 1 point at `L1000`:

```text
00 00 09 00 C4 01 00 00 00 00 18 00 00
```

Example response:

```text
80 00 06 00 C4 01 00 00 00 00
```

Interpretation:

- counts: bit=`01`, byte=`00`, word=`00`, long=`00`
- bit data payload: `00`

### `CMD=C5` PC10 multi write

Write `L1000=1`:

```text
00 00 0A 00 C5 01 00 00 00 00 18 00 00 01
```

Example response:

```text
80 00 01 00 C5
```

## 11. Commands not used in normal project flow

These commands exist in the protocol, but are not part of the current normal test and usage path:

- `CMD=60` relay command outside the verified single-hop paths and selected verified multi-hop paths
- `CMD=CA` FR register outside FR-specific flows

Status:

- `CMD=60`: `verified` for single-hop read / write / FR commit on `P1-L2:N2`; selected two-hop / three-hop read paths; three-hop basic word write; three-hop contiguous 8-word relay write/readback on `D0000-D0007`; broader three-hop relay matrix checks on `D/R/S/U` with counts `16/32`; three-hop relay `FR000000` read / write / commit path (`P1-L2:N4 -> P1-L2:N6 -> P1-L2:N2`); a three-hop relay high-level API sweep (`TOTAL: 24/24`); and relay low-level sweeps on both UDP and TCP. Standalone relay `CMD=A0 / 01 10` still returned NAK on the verified Plus relay paths.
- `CMD=CA`: `verified` for `FR` commit on `Nano 10GX (TUC-1157)` and for single-hop relay `FR` commit on `TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)`
