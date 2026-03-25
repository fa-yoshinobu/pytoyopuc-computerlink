import argparse

from toyopuc import ToyopucClient

STATUS_FIELDS = [
    ("RUN", "run"),
    ("Under a stop", "under_stop"),
    ("Under stop-request continuity", "under_stop_request_continuity"),
    ("Under a pseudo-stop", "under_pseudo_stop"),
    ("Debug mode", "debug_mode"),
    ("I/O monitor user mode", "io_monitor_user_mode"),
    ("PC3 mode", "pc3_mode"),
    ("PC10 mode", "pc10_mode"),
    ("Fatal failure", "fatal_failure"),
    ("Faint failure", "faint_failure"),
    ("Alarm", "alarm"),
    ("I/O allocation parameter altered", "io_allocation_parameter_altered"),
    ("With a memory card", "with_memory_card"),
    ("Memory card operation", "memory_card_operation"),
    (
        "Write-protected program and supplementary information",
        "write_protected_program_info",
    ),
    ("Read-protected system memory", "read_protected_system_memory"),
    ("Write-protected system memory", "write_protected_system_memory"),
    ("Read-protected system I/O", "read_protected_system_io"),
    ("Write-protected system I/O", "write_protected_system_io"),
    ("Trace", "trace"),
    ("Scan sampling trace", "scan_sampling_trace"),
    ("Periodic sampling trace", "periodic_sampling_trace"),
    ('"Enable" detected', "enable_detected"),
    ("Trigger detected", "trigger_detected"),
    ("One scan step", "one_scan_step"),
    ("One block step", "one_block_step"),
    ("One instruction step", "one_instruction_step"),
    ("I/O off-line", "io_offline"),
    ("Remote RUN setting", "remote_run_setting"),
    ("Status latch setting", "status_latch_setting"),
    (
        "Write-priority limited program and supplementary information",
        "write_priority_limited_program_info",
    ),
    ("Abnormal write flash register", "abnormal_write_flash_register"),
    ("Under writing flash register", "under_writing_flash_register"),
    ("Abnormal write of equipment info.", "abnormal_write_equipment_info"),
    ("Abnormal writing of equipment info.", "abnormal_writing_equipment_info"),
    ("Abnormal write during RUN", "abnormal_write_during_run"),
    ("Under writing during RUN", "under_writing_during_run"),
    ("Under program 1 running", "program1_running"),
    ("Under program 2 running", "program2_running"),
    ("Under program 3 running", "program3_running"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read and decode PLC CPU status.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=0)
    return p


def main() -> int:
    args = build_parser().parse_args()
    with ToyopucClient(
        args.host,
        args.port,
        protocol=args.protocol,
        local_port=args.local_port,
        timeout=args.timeout,
        retries=args.retries,
    ) as plc:
        try:
            status = plc.read_cpu_status()
            print(f"raw: {status.raw_bytes.hex(' ').upper()}")
            for label, field in STATUS_FIELDS:
                print(f"{label}: {getattr(status, field)}")
        except Exception as e:
            print(f"ERR: {e}")
            if plc.last_tx is not None:
                print(f"LAST_TX {plc.last_tx.hex(' ').upper()}")
            if plc.last_rx is not None:
                print(f"LAST_RX {plc.last_rx.hex(' ').upper()}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
