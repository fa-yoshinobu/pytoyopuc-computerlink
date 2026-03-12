#!/usr/bin/env python
import argparse
import time
import zlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

from toyopuc import ToyopucClient, ToyopucError, encode_fr_word_addr32


FR_MAX_INDEX = 0x1FFFFF
FR_BLOCK_WORDS = 0x8000


Range = Tuple[int, int]


@dataclass
class VerifySummary:
    ok_chunks: int = 0
    error_chunks: int = 0
    mismatch_words: int = 0
    first_mismatch_index: Optional[int] = None
    crc32_expected: int = 0
    crc32_actual: int = 0


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


def affected_blocks(start: int, end: int) -> List[int]:
    blocks: List[int] = []
    current = start - (start % FR_BLOCK_WORDS)
    while current <= end:
        blocks.append(current)
        current += FR_BLOCK_WORDS
    return blocks


def build_pattern_words(start_index: int, count: int, seed: int) -> List[int]:
    return [((seed + start_index + offset) & 0xFFFF) for offset in range(count)]


def build_pattern_bytes(start_index: int, count: int, seed: int) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in build_pattern_words(start_index, count, seed))


def count_chunk_mismatches(actual: bytes, expected: bytes, start_index: int) -> Tuple[int, Optional[int]]:
    mismatch_words = 0
    first_mismatch_index: Optional[int] = None
    for offset in range(0, min(len(actual), len(expected)), 2):
        actual_word = actual[offset] | (actual[offset + 1] << 8)
        expected_word = expected[offset] | (expected[offset + 1] << 8)
        if actual_word != expected_word:
            mismatch_words += 1
            if first_mismatch_index is None:
                first_mismatch_index = start_index + (offset // 2)
    return mismatch_words, first_mismatch_index


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Write an FR range with a deterministic pattern, then commit at the end and verify by readback.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    p.add_argument("--local-port", type=int, default=0)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--start", type=parse_int_auto, required=True, help="FR start word index")
    p.add_argument("--end", type=parse_int_auto, required=True, help="FR end word index (inclusive)")
    p.add_argument("--chunk-words", type=parse_int_auto, default=0x200, help="words per C3/C2 transfer (default: 0x200)")
    p.add_argument("--progress-every", type=int, default=64, help="print progress every N successful chunks (0=disable)")
    p.add_argument("--seed", type=parse_int_auto, default=0xA500, help="pattern seed; word = (seed + index) & 0xFFFF")
    p.add_argument("--skip-commit", action="store_true", help="write and verify RAM work area only; do not issue CA")
    p.add_argument("--skip-verify", action="store_true", help="skip final readback verification")
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
    commit_blocks = affected_blocks(args.start, args.end)
    log_f = open(args.log, "w", encoding="utf-8") if args.log else None
    verify = VerifySummary()
    write_errors: List[Range] = []
    read_errors: List[Range] = []
    start_time = time.monotonic()

    header = (
        f"range={format_fr_range(args.start, args.end)} "
        f"chunk_words=0x{args.chunk_words:X} total_words=0x{total_words:X} total_chunks={total_chunks} "
        f"seed=0x{args.seed & 0xFFFF:04X} commit_phase={'off' if args.skip_commit else 'end'}"
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
            write_ok_chunks = 0
            for index, chunk_words in iter_fr_chunks(args.start, args.end, args.chunk_words):
                data = build_pattern_bytes(index, chunk_words, args.seed)
                try:
                    plc.pc10_block_write(encode_fr_word_addr32(index), data)
                    write_ok_chunks += 1
                    verify.crc32_expected = zlib.crc32(data, verify.crc32_expected)
                    if args.progress_every and write_ok_chunks % args.progress_every == 0:
                        elapsed = max(time.monotonic() - start_time, 1e-9)
                        words_done = min(write_ok_chunks * args.chunk_words, total_words)
                        progress = words_done / total_words * 100.0
                        rate = words_done / elapsed
                        line = (
                            f"write_progress={progress:6.2f}% "
                            f"last={format_fr_range(index, index + chunk_words - 1)} "
                            f"words={words_done}/{total_words} "
                            f"rate={rate:.1f} words/s"
                        )
                        print(line)
                        write_log(log_f, line)
                except (ToyopucError, ValueError) as e:
                    write_errors.append((index, index + chunk_words - 1))
                    line = f"WRITE_ERR {format_fr_range(index, index + chunk_words - 1)}: {e}"
                    print(line)
                    write_log(log_f, line)
                    if plc.last_tx is not None:
                        write_log(log_f, f"LAST_TX {plc.last_tx.hex(' ').upper()}")
                    if plc.last_rx is not None:
                        write_log(log_f, f"LAST_RX {plc.last_rx.hex(' ').upper()}")
                    break

            if not write_errors and not args.skip_commit:
                line = f"commit_phase blocks={len(commit_blocks)}"
                print(line)
                write_log(log_f, line)
                for block_index in commit_blocks:
                    plc.commit_fr_block(block_index, wait=True)
                line = "commit_phase done"
                print(line)
                write_log(log_f, line)

            if not write_errors and not args.skip_verify:
                verify_start = time.monotonic()
                for index, chunk_words in iter_fr_chunks(args.start, args.end, args.chunk_words):
                    expected = build_pattern_bytes(index, chunk_words, args.seed)
                    try:
                        actual = plc.pc10_block_read(encode_fr_word_addr32(index), chunk_words * 2)
                        verify.ok_chunks += 1
                        verify.crc32_actual = zlib.crc32(actual, verify.crc32_actual)
                        mismatch_words, first_mismatch = count_chunk_mismatches(actual, expected, index)
                        verify.mismatch_words += mismatch_words
                        if verify.first_mismatch_index is None and first_mismatch is not None:
                            verify.first_mismatch_index = first_mismatch
                        if args.progress_every and verify.ok_chunks % args.progress_every == 0:
                            elapsed = max(time.monotonic() - verify_start, 1e-9)
                            words_done = min(verify.ok_chunks * args.chunk_words, total_words)
                            progress = words_done / total_words * 100.0
                            rate = words_done / elapsed
                            line = (
                                f"verify_progress={progress:6.2f}% "
                                f"last={format_fr_range(index, index + chunk_words - 1)} "
                                f"words={words_done}/{total_words} "
                                f"rate={rate:.1f} words/s"
                            )
                            print(line)
                            write_log(log_f, line)
                    except (ToyopucError, ValueError) as e:
                        verify.error_chunks += 1
                        read_errors.append((index, index + chunk_words - 1))
                        line = f"VERIFY_ERR {format_fr_range(index, index + chunk_words - 1)}: {e}"
                        print(line)
                        write_log(log_f, line)
                        if plc.last_tx is not None:
                            write_log(log_f, f"LAST_TX {plc.last_tx.hex(' ').upper()}")
                        if plc.last_rx is not None:
                            write_log(log_f, f"LAST_RX {plc.last_rx.hex(' ').upper()}")
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
    print(f"elapsed_sec={elapsed:.2f}")
    print(f"write_errors={len(write_errors)} verify_error_chunks={verify.error_chunks}")
    print(f"verify_ok_chunks={verify.ok_chunks} mismatch_words={verify.mismatch_words}")
    print(f"expected_crc32=0x{verify.crc32_expected:08X}")
    print(f"actual_crc32=0x{verify.crc32_actual:08X}")
    if verify.first_mismatch_index is None:
        print("first_mismatch=none")
    else:
        print(f"first_mismatch={format_fr_word(verify.first_mismatch_index)}")

    if write_errors:
        print("write_holes:")
        for start, end in write_errors:
            print(f"  {format_fr_range(start, end)}")
    else:
        print("write_holes: none")

    if read_errors:
        print("verify_holes:")
        for start, end in read_errors:
            print(f"  {format_fr_range(start, end)}")
    else:
        print("verify_holes: none")

    write_log(log_f, f"elapsed_sec={elapsed:.2f}")
    write_log(log_f, f"write_errors={len(write_errors)} verify_error_chunks={verify.error_chunks}")
    write_log(log_f, f"verify_ok_chunks={verify.ok_chunks} mismatch_words={verify.mismatch_words}")
    write_log(log_f, f"expected_crc32=0x{verify.crc32_expected:08X}")
    write_log(log_f, f"actual_crc32=0x{verify.crc32_actual:08X}")
    if verify.first_mismatch_index is None:
        write_log(log_f, "first_mismatch=none")
    else:
        write_log(log_f, f"first_mismatch={format_fr_word(verify.first_mismatch_index)}")
    if write_errors:
        write_log(log_f, "write_holes:")
        for start, end in write_errors:
            write_log(log_f, f"  {format_fr_range(start, end)}")
    else:
        write_log(log_f, "write_holes: none")
    if read_errors:
        write_log(log_f, "verify_holes:")
        for start, end in read_errors:
            write_log(log_f, f"  {format_fr_range(start, end)}")
    else:
        write_log(log_f, "verify_holes: none")

    if log_f:
        log_f.close()
    return 0 if not write_errors and verify.error_chunks == 0 and verify.mismatch_words == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
