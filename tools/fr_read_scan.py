#!/usr/bin/env python
import argparse
import time
import zlib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from toyopuc import ToyopucClient, ToyopucError, encode_fr_word_addr32


FR_MAX_INDEX = 0x1FFFFF
FR_BLOCK_WORDS = 0x8000


Range = Tuple[int, int]


@dataclass
class ScanSummary:
    ok_chunks: int = 0
    error_chunks: int = 0
    ok_words: int = 0
    error_words: int = 0
    zero_words: int = 0
    ffff_words: int = 0
    other_words: int = 0
    crc32: int = 0
    first_ok: Optional[int] = None
    last_ok: Optional[int] = None


def parse_int_auto(value: str) -> int:
    return int(value, 0)


def format_fr_word(index: int) -> str:
    return f"FR{index:06X}"


def format_fr_range(start: int, end: int) -> str:
    return f"{format_fr_word(start)}-{format_fr_word(end)}"


def write_log(log_f, line: str) -> None:
    if log_f:
        log_f.write(line + "\n")
        log_f.flush()


def iter_fr_chunks(start: int, end: int, chunk_words: int):
    index = start
    while index <= end:
        block_end = (((index // FR_BLOCK_WORDS) + 1) * FR_BLOCK_WORDS) - 1
        count = min(chunk_words, end - index + 1, block_end - index + 1)
        yield index, count
        index += count


def compress_ranges(ranges: Sequence[Range]) -> List[Range]:
    if not ranges:
        return []
    merged: List[Range] = []
    cur_start, cur_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= cur_end + 1:
            cur_end = max(cur_end, end)
            continue
        merged.append((cur_start, cur_end))
        cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


def count_words(data: bytes) -> Tuple[int, int, int]:
    zero_words = 0
    ffff_words = 0
    other_words = 0
    for i in range(0, len(data), 2):
        word = data[i] | (data[i + 1] << 8)
        if word == 0x0000:
            zero_words += 1
        elif word == 0xFFFF:
            ffff_words += 1
        else:
            other_words += 1
    return zero_words, ffff_words, other_words


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only FR range scan using PC10 block read (CMD=C2).")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--start", type=parse_int_auto, default=0x000000, help="FR start word index")
    p.add_argument("--end", type=parse_int_auto, default=FR_MAX_INDEX, help="FR end word index (inclusive)")
    p.add_argument("--chunk-words", type=parse_int_auto, default=0x200, help="words per C2 read (default: 0x200)")
    p.add_argument("--progress-every", type=int, default=64, help="print progress every N successful chunks (0=disable)")
    p.add_argument("--stop-after-ng", type=int, default=0, help="stop after this many consecutive read errors (0=disabled)")
    p.add_argument("--log", default="", help="optional log path")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.log:
        args.log = args.log.strip().strip('"')
    if args.chunk_words <= 0:
        raise SystemExit("--chunk-words must be >= 1")
    if args.progress_every < 0:
        raise SystemExit("--progress-every must be >= 0")
    if not 0 <= args.start <= FR_MAX_INDEX:
        raise SystemExit(f"--start must be in 0x000000-0x{FR_MAX_INDEX:06X}")
    if not 0 <= args.end <= FR_MAX_INDEX:
        raise SystemExit(f"--end must be in 0x000000-0x{FR_MAX_INDEX:06X}")
    if args.start > args.end:
        raise SystemExit("--start must be <= --end")

    total_words = args.end - args.start + 1
    total_chunks = sum(1 for _ in iter_fr_chunks(args.start, args.end, args.chunk_words))
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    summary = ScanSummary()
    error_ranges: List[Range] = []
    start_time = time.monotonic()
    scanned_chunks = 0
    consecutive_ng = 0

    header = (
        f"range={format_fr_range(args.start, args.end)} "
        f"chunk_words=0x{args.chunk_words:X} total_words=0x{total_words:X} total_chunks={total_chunks}"
    )
    print(header)
    write_log(log_f, header)

    plc: Optional[ToyopucClient] = None
    try:
        with ToyopucClient(
            args.host,
            args.port,
            protocol=args.protocol,
            local_port=args.local_port,
            timeout=args.timeout,
            retries=args.retries,
        ) as plc:
            for index, chunk_words in iter_fr_chunks(args.start, args.end, args.chunk_words):
                scanned_chunks += 1
                try:
                    data = plc.pc10_block_read(encode_fr_word_addr32(index), chunk_words * 2)
                    zero_words, ffff_words, other_words = count_words(data)
                    summary.ok_chunks += 1
                    summary.ok_words += chunk_words
                    summary.zero_words += zero_words
                    summary.ffff_words += ffff_words
                    summary.other_words += other_words
                    summary.crc32 = zlib.crc32(data, summary.crc32)
                    if summary.first_ok is None:
                        summary.first_ok = index
                    summary.last_ok = index + chunk_words - 1
                    consecutive_ng = 0

                    if args.progress_every and summary.ok_chunks % args.progress_every == 0:
                        elapsed = max(time.monotonic() - start_time, 1e-9)
                        progress = (summary.ok_words + summary.error_words) / total_words * 100.0
                        rate = (summary.ok_words + summary.error_words) / elapsed
                        line = (
                            f"progress={progress:6.2f}% "
                            f"last_ok={format_fr_range(index, index + chunk_words - 1)} "
                            f"words={summary.ok_words + summary.error_words}/{total_words} "
                            f"rate={rate:.1f} words/s"
                        )
                        print(line)
                        write_log(log_f, line)
                except (ToyopucError, ValueError) as e:
                    chunk_start = index
                    chunk_end = index + chunk_words - 1
                    summary.error_chunks += 1
                    summary.error_words += chunk_words
                    error_ranges.append((chunk_start, chunk_end))
                    consecutive_ng += 1
                    line = f"ERR {format_fr_range(chunk_start, chunk_end)}: {e}"
                    print(line)
                    write_log(log_f, line)
                    if plc.last_tx is not None:
                        write_log(log_f, f"LAST_TX {plc.last_tx.hex(' ').upper()}")
                    if plc.last_rx is not None:
                        write_log(log_f, f"LAST_RX {plc.last_rx.hex(' ').upper()}")
                    if args.stop_after_ng > 0 and consecutive_ng >= args.stop_after_ng:
                        line = f"stopped early after {consecutive_ng} consecutive read errors"
                        print(line)
                        write_log(log_f, line)
                        break
    except Exception as e:
        print(f"ERR: {e}")
        write_log(log_f, f"ERR: {e}")
        if plc is not None and plc.last_tx is not None:
            print(f"LAST_TX {plc.last_tx.hex(' ').upper()}")
            write_log(log_f, f"LAST_TX {plc.last_tx.hex(' ').upper()}")
        if plc is not None and plc.last_rx is not None:
            print(f"LAST_RX {plc.last_rx.hex(' ').upper()}")
            write_log(log_f, f"LAST_RX {plc.last_rx.hex(' ').upper()}")
        if log_f:
            log_f.close()
        return 1

    elapsed = time.monotonic() - start_time
    merged_errors = compress_ranges(error_ranges)

    print(f"elapsed_sec={elapsed:.2f}")
    print(f"ok_chunks={summary.ok_chunks} error_chunks={summary.error_chunks}")
    print(f"ok_words={summary.ok_words} error_words={summary.error_words}")
    print(f"value_words 0x0000={summary.zero_words} 0xFFFF={summary.ffff_words} other={summary.other_words}")
    print(f"crc32=0x{summary.crc32:08X}")
    if summary.first_ok is None:
        print("first_ok=none")
        print("last_ok=none")
    else:
        print(f"first_ok={format_fr_word(summary.first_ok)}")
        print(f"last_ok={format_fr_word(summary.last_ok)}")

    if merged_errors:
        print("holes:")
        for start, end in merged_errors:
            print(f"  {format_fr_range(start, end)}")
    else:
        print("holes: none")

    write_log(log_f, f"elapsed_sec={elapsed:.2f}")
    write_log(log_f, f"ok_chunks={summary.ok_chunks} error_chunks={summary.error_chunks}")
    write_log(log_f, f"ok_words={summary.ok_words} error_words={summary.error_words}")
    write_log(log_f, f"value_words 0x0000={summary.zero_words} 0xFFFF={summary.ffff_words} other={summary.other_words}")
    write_log(log_f, f"crc32=0x{summary.crc32:08X}")
    if summary.first_ok is None:
        write_log(log_f, "first_ok=none")
        write_log(log_f, "last_ok=none")
    else:
        write_log(log_f, f"first_ok={format_fr_word(summary.first_ok)}")
        write_log(log_f, f"last_ok={format_fr_word(summary.last_ok)}")
    if merged_errors:
        write_log(log_f, "holes:")
        for start, end in merged_errors:
            write_log(log_f, f"  {format_fr_range(start, end)}")
    else:
        write_log(log_f, "holes: none")

    if log_f:
        log_f.close()
    return 0 if summary.error_chunks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
