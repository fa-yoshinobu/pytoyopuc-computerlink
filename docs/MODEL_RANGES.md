# Model-Specific Writable Ranges

Related documents:

- [../README.md](../README.md)
- [TESTING.md](TESTING.md)
- [COMPUTER_LINK_SPEC.md](COMPUTER_LINK_SPEC.md)
- [RELEASE_NOTES.md](RELEASE_NOTES.md)

This document records writable device ranges confirmed per hardware model.

The intent is practical:
- where writes are accepted
- where writes are rejected
- whether there are holes inside the accepted span

Evidence types used in this file:

- `exhaustive scan`
  Confirmed by `tools/exhaustive_writable_scan.py`.
- `runtime tests`
  Confirmed by the normal runtime test set in [TESTING.md](TESTING.md).

These ranges are based primarily on `tools/exhaustive_writable_scan.py`.

## TOYOPUC-Plus CPU (TCC-6740) + Plus EX2 (TCU-6858)

Source command:

```bash
python -m tools.exhaustive_writable_scan --host <HOST> --port <PORT> --protocol tcp --targets all --log exhaustive.log
```

Evidence:

- exhaustive scan
- runtime tests also agree with the supported/unsupported split for the tested paths

### Basic Bit

| Device | Writable range |
| --- | --- |
| `P` | `P0000-P17FF` |
| `K` | `K0000-K02FF` |
| `V` | `V0000-V17FF` |
| `T` | `T0000-T17FF` |
| `C` | `C0000-C17FF` |
| `L` | `L0000-L2FFF` |
| `X` | `X0000-X07FF` |
| `Y` | `Y0000-Y07FF` |
| `M` | `M0000-M17FF` |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

### Basic Word

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S13FF` |
| `N` | `N0000-N17FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D0FFF` |
| `B` | unsupported |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

### Prefixed Bit (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `P` | `P000-P1FF` |
| `K` | `K000-K2FF` |
| `V` | `V000-V0FF` |
| `T` | `T000-T1FF` |
| `C` | `C000-C1FF` |
| `L` | `L000-L7FF` |
| `X` | `X000-X7FF` |
| `Y` | `Y000-Y7FF` |
| `M` | `M000-M7FF` |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

Not writable on this model:
- `P1000-P17FF`
- `V1000-V17FF`
- `T1000-T17FF`
- `C1000-C17FF`
- `L1000-L2FFF`
- `M1000-M17FF`

### Prefixed Word (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S03FF` |
| `N` | `N0000-N01FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D0FFF` |
| `B` | unsupported |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

Not writable on this model:
- `S1000-S13FF`
- `N1000-N17FF`
- `D1000-D2FFF`

### Extension Bit

| Device | Writable range |
| --- | --- |
| `EP` | `EP0000-EP0FFF` |
| `EK` | `EK0000-EK0FFF` |
| `EV` | `EV0000-EV0FFF` |
| `ET` | `ET0000-ET07FF` |
| `EC` | `EC0000-EC07FF` |
| `EL` | `EL0000-EL1FFF` |
| `EX` | `EX0000-EX07FF` |
| `EY` | `EY0000-EY07FF` |
| `EM` | `EM0000-EM1FFF` |
| `GX` | `GX0000-GXFFFF` |
| `GY` | `GY0000-GYFFFF` |
| `GM` | `GM0000-GMFFFF` |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

### Extension Word

| Device | Writable range |
| --- | --- |
| `ES` | `ES0000-ES07FF` |
| `EN` | `EN0000-EN07FF` |
| `H` | `H0000-H07FF` |
| `U` | `U00000-U07FFF` |
| `EB` | not present on this model |

Evidence:

| Scope | Source |
| --- | --- |
| final range | exhaustive scan |
| supported behavior | runtime tests |

### FR

| Device | Range | Notes |
| --- | --- | --- |
| `FR` | *(not exposed on this CPU)* | `CMD=C2/C3/CA` always returns `0x40`. |

Does not exist on this model:
- `U08000-U1FFFF`

### Notes

- No holes were observed inside the writable spans above.
- Unsupported spans were contiguous in the observed scan.
- This is a write-acceptance result. It does not imply readback validation.
- For this model, the exhaustive scan is the primary source for final upper bounds such as `D0000-D0FFF` and `U00000-U07FFF`.

## Nano 10GX (TUC-1157)

Source commands:

```bash
tools\run_quick_test.bat 192.168.250.101 1025 tcp 4 5 0
tools\run_full_test.bat 192.168.250.101 1025 tcp 4 5 0
python -m tools.whl_addressing_test --host 192.168.250.101 --port 1025 --protocol tcp --timeout 5 --retries 0 --log whl_nano10gx_tcp.log
python -m tools.high_level_api_test --host 192.168.250.101 --port 1025 --protocol tcp --timeout 5 --retries 0 --log high_level_nano10gx_tcp.log
python -m tools.clock_test --host 192.168.250.101 --port 1025 --protocol tcp --timeout 5 --retries 0
python -m tools.cpu_status_test --host 192.168.250.101 --port 1025 --protocol tcp --timeout 5 --retries 0
tools\run_full_test.bat 192.168.250.101 1027 udp 4 5 2 12000
python -m tools.whl_addressing_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --skip-errors --log whl_nano10gx.log
python -m tools.high_level_api_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --skip-errors --log high_level_nano10gx.log
python -m tools.clock_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
python -m tools.clock_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2 --set "2026-03-09 20:00:10"
python -m tools.cpu_status_test --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --timeout 5 --retries 2
tools\run_device_range_scan.bat 192.168.250.101 1027 udp 12000 16 32
```

Evidence:

- runtime tests
- coarse device-range scan
- TCP and UDP runtime results agree on the tested families

### Basic Bit

| Device | Writable range |
| --- | --- |
| `P` | `P0000-P17FF` |
| `K` | `K0000-K02FF` |
| `V` | `V0000-V17FF` |
| `T` | `T0000-T17FF` |
| `C` | `C0000-C17FF` |
| `L` | `L0000-L2FFF` |
| `X` | `X0000-X07FF` |
| `Y` | `Y0000-Y07FF` |
| `M` | `M0000-M17FF` |

Evidence:

| Scope | Source |
| --- | --- |
| supported behavior | runtime tests |
| coarse upper-bound observation | device-range scan |

### Basic Word

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S13FF` |
| `N` | `N0000-N17FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D2FFF` |
| `B` | *(not present on this model)* |

Evidence:

| Scope | Source |
| --- | --- |
| supported behavior | runtime tests |
| coarse upper-bound observation | device-range scan |

### Prefixed Bit (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `P` | `P000-P17FF` |
| `K` | `K000-K2FF` |
| `V` | `V000-V17FF` |
| `T` | `T000-T17FF` |
| `C` | `C000-C17FF` |
| `L` | `L000-L2FFF` |
| `X` | `X000-X7FF` |
| `Y` | `Y000-Y7FF` |
| `M` | `M000-M17FF` |

Evidence:

| Scope | Source |
| --- | --- |
| supported behavior | runtime tests |
| coarse upper-bound observation | device-range scan |

### Prefixed Word (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S13FF` |
| `N` | `N0000-N17FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D2FFF` |

Upper prefixed ranges (`1000` series) are not implemented in either PC3 mode or Plus Expansion Mode.
### Extended Bit / Word

| Device | Writable range |
| --- | --- |
| `EP/EK/EV/ET/EC/EL/EX/EY/EM` | Standard ranges for this family (shared by PC3 mode and PC10 mode) |
| `GX/GY/GM` | `GX/GY/GM0000-GX/GY/GMFFFF` |
| `ES/EN/H` | `ES0000-ES07FF`, `EN0000-EN07FF`, `H0000-H07FF` |
| `U` | `U00000-U1FFFF` *(PC10 mode only)* |
| `EB` | *(not present)* |

### FR

| Device | Range | Notes |
| --- | --- | --- |
| `FR` | *(not exposed on this CPU)* | `CMD=C2/C3/CA` always returns `0x40`. |

## PC10G-CPU (TCC-6353)

Source commands (UDP unless noted):

```text
tools\run_device_full_scan.bat 192.168.250.101 1027 udp 12000 5 2 512 device_full
tools\run_device_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 S,N,R,D,P,K,V,T,C,L,X,Y,M,EP,EX,GX,GY,GM,U,EB,FR 512 device_read.log
tools\run_fr_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read.log
tools\run_fr_write_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0xA500 fr_write.log
tools\run_program_no_probe.bat 192.168.250.101 1027 udp 12000 5 2 ext00,gx07,p1,p2,p3 0x00,0x01,0x02,0x03,0x07 program_no_probe.log
tools\run_c4c5_range_probe.bat 192.168.250.101 1027 udp 12000 5 2 l1000,m1000,u00000,u08000,eb00000 c4c5_range.log
tools\run_sim_tests.bat 192.168.250.101 1027 udp 12000 5 2
python -m tools.auto_rw_test --host 192.168.250.101 --port 1025 --protocol tcp --ext-multi-test --skip-errors --log auto_ext_multi.log
python -m tools.auto_rw_test --host 192.168.250.101 --port 1025 --protocol tcp --boundary-test --skip-errors --log auto_boundary.log
python -m tools.auto_rw_test --host 192.168.250.101 --port 1025 --protocol tcp --max-block-test --pc10-block-words 0x200 --skip-errors --log auto_block.log
python -m tools.auto_rw_test --host 192.168.250.101 --port 1025 --protocol tcp --count 4 --pc10g-full --include-p123 --skip-errors --log auto_pc10g_p123.log
```

Evidence:

- `run_device_full_scan` + `run_device_read_scan` reported zero errors across the accepted spans listed below and cleanly identified the first failing chunk at each upper boundary.
- `auto_rw_test --pc10g-full` sampled every documented basic/prefixed/extended range (bits, words, bytes) plus PC10 block access without mismatches (`TOTAL: 768/768`, only tolerated V-bit transient warnings).
- Prefixed-device numbers for `EX/ES` (`0x00`), `GX` (`0x07`), and `P1/P2/P3` (`0x01/0x02/0x03`) were reconfirmed via `run_program_no_probe`.
- `run_c4c5_range_probe` showed that `U00000`, `U08000`, and `EB00000` via PC10 block addressing alias the same storage as the normal `CMD=C4/C5` helpers; `L1000` / `M1000` rely on higher-level guards rather than direct `CMD=20/21`.
- Full-range FR read/write/commit scans (`fr_read.log`, `fr_write.log`) completed with perfect CRC agreement (`0x6C5F5EB9`) and verified that `CMD=A0` remains unavailable (`0x24`).

### Basic Bit

| Device | Writable range |
| --- | --- |
| `P` | `P0000-P17FF` |
| `K` | `K0000-K02FF` |
| `V` | `V0000-V17FF` |
| `T` | `T0000-T17FF` |
| `C` | `C0000-C17FF` |
| `L` | `L0000-L2FFF` |
| `X` | `X0000-X07FF` |
| `Y` | `Y0000-Y07FF` |
| `M` | `M0000-M17FF` |

### Basic Word

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S13FF` |
| `N` | `N0000-N17FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D2FFF` |

### Prefixed Bit (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `P` | `P000-P17FF` |
| `K` | `K000-K2FF` |
| `V` | `V000-V17FF` |
| `T` | `T000-T17FF` |
| `C` | `C000-C17FF` |
| `L` | `L000-L2FFF` |
| `X` | `X000-X7FF` |
| `Y` | `Y000-Y7FF` |
| `M` | `M000-M17FF` |

Note: Prefixed addresses starting at `1000` (`P1-M1000` etc.) are valid on this CPU but are blocked on Nano 10GX; keep guards device-specific.

### Prefixed Word (`P1/P2/P3`)

| Device | Writable range |
| --- | --- |
| `S` | `S0000-S13FF` |
| `N` | `N0000-N17FF` |
| `R` | `R0000-R07FF` |
| `D` | `D0000-D2FFF` |

### Extension Bit

| Device | Writable range |
| --- | --- |
| `EP` | `EP0000-EP0FFF` |
| `EK` | `EK0000-EK0FFF` |
| `EV` | `EV0000-EV0FFF` |
| `ET` | `ET0000-ET07FF` |
| `EC` | `EC0000-EC07FF` |
| `EL` | `EL0000-EL1FFF` |
| `EX` | `EX0000-EX07FF` |
| `EY` | `EY0000-EY07FF` |
| `EM` | `EM0000-EM1FFF` |
| `GX` | `GX0000-GXFFFF` |
| `GY` | `GY0000-GYFFFF` |
| `GM` | `GM0000-GMFFFF` |

### Extension Word

| Device | Writable range |
| --- | --- |
| `ES` | `ES0000-ES07FF` |
| `EN` | `EN0000-EN07FF` |
| `H` | `H0000-H07FF` |
| `U` | `U00000-U1FFFF` |
| `EB` | `EB00000-EB3FFFF` (Ex No. `0x10-0x17`; higher codes such as `0x18` are rejected) |

### Notes

- `tools\run_device_full_scan.bat` + `tools\run_device_read_scan.bat` cover the full scan in less than a minute when using 512-word chunks; the combined output is stored in `device_full*` / `device_read.log`.
- `tools\run_device_full_scan.bat` already chains the FR scan and the prefixed program-number probe, so re-running that single batch file is enough for future regressions.
- `B` area is not implemented on the tested PC10G unit, so block/byte tests mark `B0000-B1FFF` as `SKIP (unsupported)`.
- PC10 multi (`CMD=C4/C5`) is still required for `L1000+`, `M1000+`, `U`, and `EB`; direct basic bit/word commands stay on `CMD=20/21` or `CMD=94/95`.
- EB access uses Ex No. `0x10-0x17` consistently; the helper rejects anything higher to avoid undefined ranges.
- FR (`CMD=C2/C3/CA`) is not exposed on the tested PC10G unit; all FR attempts returned `error_code=0x40`.
