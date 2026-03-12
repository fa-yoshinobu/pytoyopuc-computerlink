# Tools

Use this file as a short index for the `tools/` directory.

Related documents:

- [../README.md](../README.md)
- [../docs/TESTING.md](../docs/TESTING.md)
- [../docs/MODEL_RANGES.md](../docs/MODEL_RANGES.md)
- [../docs/COMPUTER_LINK_SPEC.md](../docs/COMPUTER_LINK_SPEC.md)
- [../examples/README.md](../examples/README.md)

## Main scripts

- `tools/run_validation_all.bat`
  Recommended broad validation batch for regression sweeps across full, mixed, block, boundary, recovery, and last-writable checks.
- `tools/run_device_range_scan.bat`
  Two-pass coarse/fine writable-range scan batch for all documented device families except `FR`.
- `tools/run_fr_range_scan.bat`
  `FR`-only coarse/fine writable-range scan batch.
- `tools/run_fr_read_scan.bat`
  `FR`-only read-only full/range scan batch using `CMD=C2`.
- `tools/run_fr_write_scan.bat`
  `FR`-only write/verify scan batch using `CMD=C3`, with a final commit phase.
- `tools/run_fr_probe.bat`
  `FR` candidate access probe batch using `CMD=CA` and several read-path guesses.
- `tools/run_relay_test.bat`
  `CMD=60` relay-command hardware test batch with outer/inner frame dump.
- `tools/run_relay_block_test.bat`
  Simple contiguous relay word write/readback batch for repeated block verification.
- `tools/run_relay_matrix_test.bat`
  Default broader relay matrix batch for `D/R/S/U`, counts `8/16/32`, repeated loops, `write_many`, mixed writes, and optional clock long-run checks.
- `tools/relay_low_level_test.py`
  Relay low-level sweep for `CMD=20/21`, `1C/1D`, `1E/1F`, `22/23`, `24/25`, `94/95`, `96/97`, `98/99`, `C2/C3`, `32`, `A0`, and optional relay `clock-write`.
- `tools/relay_matrix_test.py`
  Broader relay write/read matrix for larger contiguous blocks, `write_many`, mixed writes, and repeated clock-write/restore checks.
- `tools/run_relay_error_test.bat`
  Default relay abnormal-case batch for missing station, broken path, and raw out-of-range word access.
- `tools/relay_error_test.py`
  Relay abnormal-case helper that captures timeout / NAK / inner error-code behavior and summarizes observed codes.
- `tools/run_fr_commit_test.bat`
  Simple `FR` read / write+commit batch for direct hardware confirmation.
- `tools/run_program_no_probe.bat`
  `CMD=98/99` program-number probe that compares current mapping against candidate `no` values.
- `tools/run_c4c5_range_probe.bat`
  Probe for current-vs-alternate `CMD=C4/C5` usage on selected `L/M/U/EB` ranges.
- `tools/run_device_full_scan.bat`
  Combined helper that first runs the fast word-oriented scan (`run_device_read_scan`) for basic/extended/PC10/FR areas and then runs the prefixed/program-number probe (`run_program_no_probe`) for `P1/P2/P3` cases.
- `tools/run_device_read_scan.bat`
  Read-only range scan that uses word-oriented access (bit areas are bundled through `...W` addressing). `targets` may mix basic word (`S/N/R/D`), basic bit (`P/K/V/T/C/L/X/Y/M`), extended bit (`EP/EK/EV/ET/EC/EL/EX/EY/EM/GX/GY/GM`), PC10 block (`U/EB/FR`), and prefixed program areas such as `P1-D`, `P2-M`, `P3-X`.
- `tools/auto_rw_test.py`
  Automated read/write test against a real PLC.
- `tools/high_level_api_test.py`
  Verification tool for `ToyopucHighLevelClient` and `resolve_device()`.
- `tools/whl_addressing_test.py`
  Verification tool for `W/H/L` addressing on bit-device families.
- `tools/final_whl_edge_test.py`
  Final-edge 16-point consistency test for bit-device families with selectable write flow: `bits` or `hl`.
- `tools/run_final_whl_edge_matrix.bat`
  Batch helper that runs `final_whl_edge_test.py` over `TCP/UDP x P1/P2/P3 x bits/hl` and stores per-case logs.
- `tools/clock_test.py`
  Dedicated command-line helper for PLC clock read/set tests.
- `tools/cpu_status_test.py`
  Dedicated command-line helper for CPU status read/decode tests.
- `tools/interactive_cli.py`
  Manual read/write CLI for spot checks and protocol inspection.
- `tools/manual_device_write_check.py`
  Stepwise helper for human verification: writes one fixed test value, waits for manual confirmation, then advances.
- `tools/recovery_write_loop.py`
  Repeated write/read loop for unplug/replug recovery checks with interval logging.
- `tools/find_last_writable.py`
  Downward write probe to find the last writable address near a range end.
- `tools/exhaustive_writable_scan.py`
  Exhaustive full-range write scan that reports the true last writable address and any holes.
- `tools/run_auto_tests.bat`
  Runs the standard automated test sequence and writes logs plus `summary.txt`.
- `tools/run_quick_test.bat`
  Runs the basic-area test only.
- `tools/run_full_test.bat`
  Runs the broad `auto_rw_test --pc10g-full --include-p123` coverage set.
- `tools/run_block_test.bat`
  Runs the block-length test.
- `tools/run_validation_all.bat`
  Runs full + mixed + block + boundary + recovery write/read + last-writable probe in one batch.
- `tools/run_sim_tests.bat`
  Runs a small simulator-oriented smoke test set against `tools.sim_server`.
- `tools/build_api_docs.bat`
  Generates API HTML documentation with `pdoc` into `docs/api`.
- `tools/build_device_monitor_gui.bat`
  Builds `examples/device_monitor_gui.py` into a Windows GUI executable with PyInstaller.
- `tools/sim_server.py`
  Local simulator for protocol testing without hardware.

## Documents

- Project overview: [../README.md](../README.md)
- Test usage and verified results: [../docs/TESTING.md](../docs/TESTING.md)
- Model-specific writable ranges: [../docs/MODEL_RANGES.md](../docs/MODEL_RANGES.md)
- Communication protocol and address tables: [../docs/COMPUTER_LINK_SPEC.md](../docs/COMPUTER_LINK_SPEC.md)
- Remaining open items: [../docs/PENDING.md](../docs/PENDING.md)

## Batch usage summary

Use this section as a quick picker:

- `run_device_full_scan.bat`: fast all-in-one device check (basic/extended/PC10/FR + prefixed probes)
- `run_device_read_scan.bat`: single-run word scan for basic/extended/PC10/FR ranges
- `run_device_range_scan.bat`: coarse-to-fine writable range exploration (use when bringing up a new model)
- `run_fr_read_scan.bat`: `FR`-only read-only range scan with chunked `CMD=C2` reads
- `run_fr_write_scan.bat`: `FR`-only write/readback range scan with chunked `CMD=C3/C2` and end-of-range commit phase
- `run_program_no_probe.bat`: targeted `CMD=98/99` mapping probe for `EX/GX/P1/P2/P3`
- `run_c4c5_range_probe.bat`: targeted `CMD=C4/C5` range probe for `L/M/U/EB`
- `run_relay_block_test.bat`: repeated contiguous relay word write/readback verification
- `run_relay_matrix_test.bat`: broader relay matrix for `D/R/S/U` block counts `8/16/32`, `write_many`, mixed writes, and optional clock loops
- `run_relay_error_test.bat`: relay abnormal-case probe for missing station, broken path, and out-of-range raw word access
- `relay_low_level_test.py`: relay low-level command sweep, usable on both UDP and TCP paths
- `final_whl_edge_test.py`: final-edge bit-family consistency test with `--write-mode bits|hl`
- `run_final_whl_edge_matrix.bat`: one-shot matrix runner for `TCP/UDP x P1/P2/P3 x bits/hl`
- `run_sim_tests.bat`: simulator smoke test for high-level API, `W/H/L` addressing, clock, and CPU status

### Nano 10GX UDP quick commands

```bat
tools\run_device_full_scan.bat 192.168.250.101 1027 udp 12000 5 2 512 device_full
tools\run_device_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 S,N,R,D,P,K,V,T,C,L,X,Y,M,EP,EX,GX,GY,GM,U,EB,FR 512 device_read.log
tools\run_device_range_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 16 device_range.log
tools\run_fr_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read.log
tools\run_fr_write_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0xA500 fr_write.log
tools\run_program_no_probe.bat 192.168.250.101 1027 udp 12000 5 2 ext00,gx07,p1,p2,p3 0x00,0x01,0x02,0x03,0x07 program_no_probe.log
tools\run_c4c5_range_probe.bat 192.168.250.101 1027 udp 12000 5 2 l1000,m1000,u00000,u08000,eb00000 c4c5_range.log
python tools\final_whl_edge_test.py --host 192.168.250.101 --port 1027 --protocol udp --local-port 12000 --program-prefix P1 --write-mode bits --timeout 5 --retries 1 --log final_whl_edge_udp_bits.log
tools\run_final_whl_edge_matrix.bat 192.168.250.101 1025 1027 12000 5 1 final_whl_edge_matrix_logs
tools\run_sim_tests.bat 192.168.250.101 1027 udp 12000 5 2
```
