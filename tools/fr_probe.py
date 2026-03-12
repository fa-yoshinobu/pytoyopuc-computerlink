import argparse
from dataclasses import dataclass
from typing import Iterable, Optional

from toyopuc import ToyopucClient, encode_ext_no_address, encode_fr_word_addr32, fr_block_ex_no


def parse_int_auto(value: str) -> int:
    return int(value, 0)


def parse_csv_ints(value: str) -> list[int]:
    return [parse_int_auto(part.strip()) for part in value.split(",") if part.strip()]


def fmt_words(values: Iterable[int]) -> str:
    return "[" + ", ".join(f"0x{value:04X}" for value in values) + "]"


def hex_or_none(data: Optional[bytes]) -> str:
    if data is None:
        return "-"
    return data.hex(" ").upper()


@dataclass
class ProbeResult:
    label: str
    ok: bool
    detail: str
    tx_register: Optional[bytes] = None
    rx_register: Optional[bytes] = None
    tx_read: Optional[bytes] = None
    rx_read: Optional[bytes] = None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Probe FR access paths and print raw TX/RX for each attempt."
    )
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument(
        "--indexes",
        default="0x0,0x8000",
        help="Comma-separated FR word indexes to probe, e.g. 0x0,0x8000",
    )
    p.add_argument(
        "--register-exnos",
        default="0x40,0x41",
        help="Comma-separated candidate Ex No. values for CMD=CA probing",
    )
    p.add_argument(
        "--log",
        help="Optional text log path",
    )
    return p


def _print_and_log(line: str, log_f) -> None:
    print(line)
    if log_f is not None:
        log_f.write(line + "\n")
        log_f.flush()


def _print_result(result: ProbeResult, log_f) -> None:
    _print_and_log(f"{result.label}: {'OK' if result.ok else 'ERR'} {result.detail}", log_f)
    if result.tx_register is not None or result.rx_register is not None:
        _print_and_log(f"  CA TX {hex_or_none(result.tx_register)}", log_f)
        _print_and_log(f"  CA RX {hex_or_none(result.rx_register)}", log_f)
        if result.tx_read is not None or result.rx_read is not None:
            _print_and_log(f"  RD TX {hex_or_none(result.tx_read)}", log_f)
            _print_and_log(f"  RD RX {hex_or_none(result.rx_read)}", log_f)
        return
    _print_and_log(f"  TX {hex_or_none(result.tx_read)}", log_f)
    _print_and_log(f"  RX {hex_or_none(result.rx_read)}", log_f)


def probe_legacy_fr(plc: ToyopucClient, index: int) -> ProbeResult:
    ext = encode_ext_no_address("FR", index, "word")
    label = f"legacy-cmd94 index=0x{index:06X} no=0x{ext.no:02X} addr=0x{ext.addr:04X}"
    try:
        values = plc.read_ext_words(ext.no, ext.addr, 1)
        return ProbeResult(
            label=label,
            ok=True,
            detail=f"read={fmt_words(values)}",
            tx_read=plc.last_tx,
            rx_read=plc.last_rx,
        )
    except Exception as e:
        return ProbeResult(
            label=label,
            ok=False,
            detail=str(e),
            tx_read=plc.last_tx,
            rx_read=plc.last_rx,
        )


def probe_pc10_fr(plc: ToyopucClient, index: int, *, label_prefix: str = "pc10-c2") -> ProbeResult:
    addr32 = encode_fr_word_addr32(index)
    ex_no = fr_block_ex_no(index)
    label = f"{label_prefix} index=0x{index:06X} ex_no=0x{ex_no:02X} addr32=0x{addr32:08X}"
    try:
        values = plc.read_fr_words(index, 1)
        return ProbeResult(
            label=label,
            ok=True,
            detail=f"read={fmt_words(values)}",
            tx_read=plc.last_tx,
            rx_read=plc.last_rx,
        )
    except Exception as e:
        return ProbeResult(
            label=label,
            ok=False,
            detail=str(e),
            tx_read=plc.last_tx,
            rx_read=plc.last_rx,
        )


def probe_ca_only(plc: ToyopucClient, ex_no: int) -> ProbeResult:
    masked_ex_no = ex_no & 0xFF
    label = f"ca=0x{masked_ex_no:02X} (arg=0x{ex_no:X})"
    try:
        plc.fr_register(ex_no)
        return ProbeResult(
            label=label,
            ok=True,
            detail="accepted",
            tx_register=plc.last_tx,
            rx_register=plc.last_rx,
        )
    except Exception as e:
        return ProbeResult(
            label=label,
            ok=False,
            detail=f"CA failed: {e}",
            tx_register=plc.last_tx,
            rx_register=plc.last_rx,
        )


def main() -> int:
    args = build_parser().parse_args()
    indexes = parse_csv_ints(args.indexes)
    register_exnos = parse_csv_ints(args.register_exnos)
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    try:
        with ToyopucClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            success_count = 0
            total_count = 0
            for index in indexes:
                _print_and_log(
                    f"=== FR index 0x{index:06X} (expected block ex_no=0x{fr_block_ex_no(index):02X}) ===",
                    log_f,
                )

                legacy = probe_legacy_fr(plc, index)
                total_count += 1
                if legacy.ok:
                    success_count += 1
                _print_result(legacy, log_f)

                proper = probe_pc10_fr(plc, index)
                total_count += 1
                if proper.ok:
                    success_count += 1
                _print_result(proper, log_f)

                for ex_no in register_exnos:
                    ca_result = probe_ca_only(plc, ex_no)
                    total_count += 1
                    if ca_result.ok:
                        success_count += 1
                    _print_result(ca_result, log_f)
                    if not ca_result.ok:
                        continue

                    after = probe_pc10_fr(plc, index, label_prefix=f"after-ca=0x{ex_no & 0xFF:02X}")
                    after.tx_register = ca_result.tx_register
                    after.rx_register = ca_result.rx_register
                    total_count += 1
                    if after.ok:
                        success_count += 1
                    _print_result(after, log_f)
                _print_and_log("", log_f)

            _print_and_log(f"SUMMARY: {success_count}/{total_count} probes succeeded", log_f)
            return 0 if success_count > 0 else 1
    finally:
        if log_f is not None:
            log_f.close()


if __name__ == "__main__":
    raise SystemExit(main())
