#!/usr/bin/env python
import argparse
import shlex
import sys
from typing import List

from toyopuc import (
    ToyopucClient,
    encode_bit_address,
    encode_byte_address,
    encode_exno_byte_u32,
    encode_fr_word_addr32,
    encode_ext_no_address,
    encode_program_bit_address,
    encode_program_word_address,
    encode_word_address,
    parse_address,
)
from toyopuc.protocol import (
    build_bit_read,
    build_bit_write,
    build_byte_read,
    build_byte_write,
    build_ext_byte_read,
    build_ext_byte_write,
    build_ext_multi_read,
    build_ext_multi_write,
    build_ext_word_read,
    build_ext_word_write,
    build_multi_byte_read,
    build_multi_byte_write,
    build_multi_word_read,
    build_multi_word_write,
    build_pc10_block_read,
    build_pc10_block_write,
    build_pc10_multi_read,
    build_pc10_multi_write,
    build_word_read,
    build_word_write,
)


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _parse_ints(tokens: List[str]) -> List[int]:
    out = []
    for t in tokens:
        t = t.strip()
        if t.lower().startswith("0x"):
            out.append(int(t, 16))
        else:
            out.append(int(t, 10))
    return out


def _prompt(prompt: str, default: str) -> str:
    v = input(f"{prompt} [{default}]: ").strip()
    return v if v else default


def _pack_u16_le(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def _prefixed_word_addr(prefix: str, area: str, index: int):
    program_no = {"P1": 0x01, "P2": 0x02, "P3": 0x03}[prefix.upper()]
    parsed = parse_address(f"{area}{index:04X}", "word")
    return program_no, encode_program_word_address(parsed)


def _prefixed_bit_addr(prefix: str, area: str, index: int):
    program_no = {"P1": 0x01, "P2": 0x02, "P3": 0x03}[prefix.upper()]
    parsed = parse_address(f"{area}{index:04X}", "bit")
    bit_no, addr = encode_program_bit_address(parsed)
    return program_no, bit_no, addr


def _ext_bit_addr(area: str, index: int):
    specs = {
        "EP": (0x00, 0x0000),
        "EK": (0x00, 0x0200),
        "EV": (0x00, 0x0400),
        "ET": (0x00, 0x0600),
        "EC": (0x00, 0x0600),
        "EL": (0x00, 0x0700),
        "EX": (0x00, 0x0B00),
        "EY": (0x00, 0x0B00),
        "EM": (0x00, 0x0C00),
        "GX": (0x07, 0x0000),
        "GY": (0x07, 0x0000),
        "GM": (0x07, 0x2000),
    }
    no, byte_base = specs[area.upper()]
    return no, index & 0x07, byte_base + (index >> 3)


def _pc10_bit_payload(addr32: int, value=None) -> bytes:
    header = bytearray([0x01, 0x00, 0x00, 0x00])
    header.extend(addr32.to_bytes(4, "little"))
    if value is None:
        return build_pc10_multi_read(bytes(header))
    header.append(value & 0x01)
    return build_pc10_multi_write(bytes(header))


def _parse_ext_multi_read_specs(tokens: List[str]):
    bit_points = []
    byte_points = []
    word_points = []
    labels = []
    for token in tokens:
        parts = token.split(":")
        kind = parts[0].lower()
        if kind == "bit" and len(parts) == 3:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            no, bit, addr = _ext_bit_addr(area, index)
            bit_points.append((no, bit, addr))
            labels.append(("bit", f"{area}{index:04X}"))
        elif kind == "byte" and len(parts) == 3:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            ext = encode_ext_no_address(area, index, "byte")
            byte_points.append((ext.no, ext.addr))
            labels.append(("byte", f"{area}{index:04X}"))
        elif kind == "word" and len(parts) == 3:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            ext = encode_ext_no_address(area, index, "word")
            word_points.append((ext.no, ext.addr))
            labels.append(("word", f"{area}{index:04X}"))
        else:
            raise ValueError(f"Invalid ext multi read spec: {token}")
    return bit_points, byte_points, word_points, labels


def _parse_ext_multi_write_specs(tokens: List[str]):
    bit_points = []
    byte_points = []
    word_points = []
    labels = []
    for token in tokens:
        parts = token.split(":")
        kind = parts[0].lower()
        if kind == "bit" and len(parts) == 4:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            value = _parse_ints([parts[3]])[0]
            no, bit, addr = _ext_bit_addr(area, index)
            bit_points.append((no, bit, addr, value))
            labels.append(("bit", f"{area}{index:04X}", value & 0x01))
        elif kind == "byte" and len(parts) == 4:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            value = _parse_ints([parts[3]])[0]
            ext = encode_ext_no_address(area, index, "byte")
            byte_points.append((ext.no, ext.addr, value))
            labels.append(("byte", f"{area}{index:04X}", value & 0xFF))
        elif kind == "word" and len(parts) == 4:
            area = parts[1].upper()
            index = _parse_ints([parts[2]])[0]
            value = _parse_ints([parts[3]])[0]
            ext = encode_ext_no_address(area, index, "word")
            word_points.append((ext.no, ext.addr, value))
            labels.append(("word", f"{area}{index:04X}", value & 0xFFFF))
        else:
            raise ValueError(f"Invalid ext multi write spec: {token}")
    return bit_points, byte_points, word_points, labels


def _decode_ext_multi_read_data(data: bytes, bit_count: int, byte_count: int, word_count: int):
    bit_bytes = (bit_count + 7) // 8
    if len(data) < bit_bytes + byte_count + word_count * 2:
        raise ValueError("Response data too short for ext multi payload")
    offset = 0
    bits_raw = data[offset : offset + bit_bytes]
    offset += bit_bytes
    bytes_raw = data[offset : offset + byte_count]
    offset += byte_count
    words_raw = data[offset : offset + word_count * 2]

    bits = []
    for i in range(bit_count):
        bits.append((bits_raw[i // 8] >> (i % 8)) & 0x01)
    bytes_out = list(bytes_raw)
    words_out = []
    for i in range(0, len(words_raw), 2):
        words_out.append(words_raw[i] | (words_raw[i + 1] << 8))
    return bits, bytes_out, words_out


def _pc10_word_addr(area: str, index: int) -> int:
    area_u = area.upper()
    if area_u in ("L", "M"):
        parsed = parse_address(f"{area_u}{index:04X}", "bit")
        return encode_bit_address(parsed)
    if area_u == "U":
        block = index // 0x8000
        ex_no = 0x03 + block
        byte_addr = (index % 0x8000) * 2
        return encode_exno_byte_u32(ex_no, byte_addr)
    if area_u == "EB":
        block = index // 0x8000
        ex_no = 0x10 + block
        byte_addr = (index % 0x8000) * 2
        return encode_exno_byte_u32(ex_no, byte_addr)
    raise ValueError(f"Unsupported PC10 area: {area}")


def print_help() -> None:
    print(
        "\nCommands:\n"
        "  wr <ADDR> <COUNT>            word read (CMD=1C)\n"
        "  ww <ADDR> <V1 V2 ...>        word write (CMD=1D)\n"
        "  br <ADDR> <COUNT>            byte read (CMD=1E)\n"
        "  bw <ADDR> <B1 B2 ...>        byte write (CMD=1F)\n"
        "  bitr <ADDR>                  bit read (CMD=20)\n"
        "  bitw <ADDR> <0|1>            bit write (CMD=21)\n"
        "  wmr <ADDR...>                multi word read (CMD=22)\n"
        "  wmw <ADDR:VAL ...>           multi word write (CMD=23)\n"
        "  bmr <ADDR...>                multi byte read (CMD=24)\n"
        "  bmw <ADDR:VAL ...>           multi byte write (CMD=25)\n"
        "  xwr <AREA> <INDEX> <COUNT>   ext word read (CMD=94)\n"
        "  xww <AREA> <INDEX> <V...>    ext word write (CMD=95)\n"
        "  xbr <AREA> <INDEX> <COUNT>   ext byte read (CMD=96)\n"
        "  xbw <AREA> <INDEX> <B...>    ext byte write (CMD=97)\n"
        "  xbitr <AREA> <INDEX>         ext bit read (CMD=98)\n"
        "  xbitw <AREA> <INDEX> <0|1>   ext bit write (CMD=99)\n"
        "  xmr <SPEC...>                ext multi read (CMD=98)\n"
        "                              spec: bit:AREA:IDX byte:AREA:IDX word:AREA:IDX\n"
        "  xmw <SPEC...>                ext multi write (CMD=99)\n"
        "                              spec: bit:AREA:IDX:VAL byte:AREA:IDX:VAL word:AREA:IDX:VAL\n"
        "  pwr <P1|P2|P3> <AREA> <INDEX> <COUNT>    prefixed word read (CMD=94)\n"
        "  pww <P1|P2|P3> <AREA> <INDEX> <V...>     prefixed word write (CMD=95)\n"
        "  pbitr <P1|P2|P3> <AREA> <INDEX>          prefixed bit read (CMD=98)\n"
        "  pbitw <P1|P2|P3> <AREA> <INDEX> <0|1>    prefixed bit write (CMD=99)\n"
        "  pcbitr <AREA> <INDEX>        PC10 bit read (CMD=C4)\n"
        "  pcbitw <AREA> <INDEX> <0|1>  PC10 bit write (CMD=C5)\n"
        "  pcwr <AREA> <INDEX> <COUNT>  PC10 word read (CMD=C2)\n"
        "  pcww <AREA> <INDEX> <V...>   PC10 word write (CMD=C3)\n"
        "  help                         show this help\n"
        "  quit                         exit\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Toyopuc CLI")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--local-port", type=int, default=None)
    parser.add_argument("--protocol", choices=["tcp", "udp"], default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--retries", type=int, default=None)
    parser.add_argument("--log", default=None)
    cli_args = parser.parse_args()

    host = cli_args.host if cli_args.host is not None else _prompt("Host", "192.168.0.10")
    port = cli_args.port if cli_args.port is not None else int(_prompt("Port", "0"))
    protocol = (
        cli_args.protocol if cli_args.protocol is not None else _prompt("Protocol (tcp/udp)", "tcp").lower()
    )
    timeout = cli_args.timeout if cli_args.timeout is not None else float(_prompt("Timeout sec", "3.0"))
    retries = cli_args.retries if cli_args.retries is not None else int(_prompt("Retries", "0"))
    if cli_args.local_port is not None:
        local_port = cli_args.local_port
    elif protocol == "udp":
        local_port = int(_prompt("Local UDP port (0=auto)", "0"))
    else:
        local_port = 0
    log_path = cli_args.log if cli_args.log is not None else _prompt("Log file (empty to skip)", "")

    log_f = open(log_path, "a", encoding="utf-8") if log_path else None

    print_help()

    with ToyopucClient(
        host,
        port,
        local_port=local_port,
        protocol=protocol,
        timeout=timeout,
        retries=retries,
    ) as plc:
        while True:
            try:
                line = input("toyopuc> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue
            if line.lower() in ("quit", "exit"):
                break
            if line.lower() in ("help", "?"):
                print_help()
                continue

            try:
                parts = shlex.split(line)
                cmd = parts[0].lower()
                args = parts[1:]

                payload = None

                if cmd == "wr":
                    addr = encode_word_address(parse_address(args[0], "word"))
                    count = _parse_ints([args[1]])[0]
                    payload = build_word_read(addr, count)
                elif cmd == "ww":
                    addr = encode_word_address(parse_address(args[0], "word"))
                    values = _parse_ints(args[1:])
                    payload = build_word_write(addr, values)
                elif cmd == "br":
                    addr = encode_byte_address(parse_address(args[0], "byte"))
                    count = _parse_ints([args[1]])[0]
                    payload = build_byte_read(addr, count)
                elif cmd == "bw":
                    addr = encode_byte_address(parse_address(args[0], "byte"))
                    values = _parse_ints(args[1:])
                    payload = build_byte_write(addr, values)
                elif cmd == "bitr":
                    addr = encode_bit_address(parse_address(args[0], "bit"))
                    payload = build_bit_read(addr)
                elif cmd == "bitw":
                    addr = encode_bit_address(parse_address(args[0], "bit"))
                    value = _parse_ints([args[1]])[0]
                    payload = build_bit_write(addr, value)
                elif cmd == "wmr":
                    addrs = [encode_word_address(parse_address(a, "word")) for a in args]
                    payload = build_multi_word_read(addrs)
                elif cmd == "wmw":
                    pairs = []
                    for a in args:
                        addr_s, val_s = a.split(":")
                        addr = encode_word_address(parse_address(addr_s, "word"))
                        val = _parse_ints([val_s])[0]
                        pairs.append((addr, val))
                    payload = build_multi_word_write(pairs)
                elif cmd == "bmr":
                    addrs = [encode_byte_address(parse_address(a, "byte")) for a in args]
                    payload = build_multi_byte_read(addrs)
                elif cmd == "bmw":
                    pairs = []
                    for a in args:
                        addr_s, val_s = a.split(":")
                        addr = encode_byte_address(parse_address(addr_s, "byte"))
                        val = _parse_ints([val_s])[0]
                        pairs.append((addr, val))
                    payload = build_multi_byte_write(pairs)
                elif cmd == "xwr":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    count = _parse_ints([args[2]])[0]
                    if area.upper() == "FR":
                        payload = build_pc10_block_read(encode_fr_word_addr32(index), count * 2)
                    else:
                        ext = encode_ext_no_address(area, index, "word")
                        payload = build_ext_word_read(ext.no, ext.addr, count)
                elif cmd == "xww":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    values = _parse_ints(args[2:])
                    if area.upper() == "FR":
                        data = b"".join(_pack_u16_le(v) for v in values)
                        payload = build_pc10_block_write(encode_fr_word_addr32(index), data)
                    else:
                        ext = encode_ext_no_address(area, index, "word")
                        payload = build_ext_word_write(ext.no, ext.addr, values)
                elif cmd == "xbr":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    count = _parse_ints([args[2]])[0]
                    ext = encode_ext_no_address(area, index, "byte")
                    payload = build_ext_byte_read(ext.no, ext.addr, count)
                elif cmd == "xbw":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    values = _parse_ints(args[2:])
                    ext = encode_ext_no_address(area, index, "byte")
                    payload = build_ext_byte_write(ext.no, ext.addr, values)
                elif cmd == "xbitr":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    no, bit, addr = _ext_bit_addr(area, index)
                    payload = build_ext_multi_read([(no, bit, addr)], [], [])
                elif cmd == "xbitw":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    value = _parse_ints([args[2]])[0]
                    no, bit, addr = _ext_bit_addr(area, index)
                    payload = build_ext_multi_write([(no, bit, addr, value)], [], [])
                elif cmd == "xmr":
                    bit_points, byte_points, word_points, labels = _parse_ext_multi_read_specs(args)
                    payload = build_ext_multi_read(bit_points, byte_points, word_points)
                elif cmd == "pwr":
                    prefix = args[0]
                    area = args[1]
                    index = _parse_ints([args[2]])[0]
                    count = _parse_ints([args[3]])[0]
                    no, addr = _prefixed_word_addr(prefix, area, index)
                    payload = build_ext_word_read(no, addr, count)
                elif cmd == "pww":
                    prefix = args[0]
                    area = args[1]
                    index = _parse_ints([args[2]])[0]
                    values = _parse_ints(args[3:])
                    no, addr = _prefixed_word_addr(prefix, area, index)
                    payload = build_ext_word_write(no, addr, values)
                elif cmd == "pbitr":
                    prefix = args[0]
                    area = args[1]
                    index = _parse_ints([args[2]])[0]
                    no, bit, addr = _prefixed_bit_addr(prefix, area, index)
                    payload = build_ext_multi_read([(no, bit, addr)], [], [])
                elif cmd == "pbitw":
                    prefix = args[0]
                    area = args[1]
                    index = _parse_ints([args[2]])[0]
                    value = _parse_ints([args[3]])[0]
                    no, bit, addr = _prefixed_bit_addr(prefix, area, index)
                    payload = build_ext_multi_write([(no, bit, addr, value)], [], [])
                elif cmd == "xmw":
                    bit_points, byte_points, word_points, labels = _parse_ext_multi_write_specs(args)
                    payload = build_ext_multi_write(bit_points, byte_points, word_points)
                elif cmd == "pcbitr":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    payload = _pc10_bit_payload(_pc10_word_addr(area, index))
                elif cmd == "pcbitw":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    value = _parse_ints([args[2]])[0]
                    payload = _pc10_bit_payload(_pc10_word_addr(area, index), value)
                elif cmd == "pcwr":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    count = _parse_ints([args[2]])[0]
                    payload = build_pc10_block_read(_pc10_word_addr(area, index), count * 2)
                elif cmd == "pcww":
                    area = args[0]
                    index = _parse_ints([args[1]])[0]
                    values = _parse_ints(args[2:])
                    data = b"".join(_pack_u16_le(v) for v in values)
                    payload = build_pc10_block_write(_pc10_word_addr(area, index), data)
                else:
                    print("Unknown command. Type 'help'.")
                    continue

                tx_hex = _hex(payload)
                print(f"TX: {tx_hex}")
                resp = plc.send_payload(payload)
                length = len(resp.data) + 1
                ll = length & 0xFF
                lh = (length >> 8) & 0xFF
                raw = bytes([resp.ft, resp.rc, ll, lh, resp.cmd]) + resp.data
                rx_hex = _hex(raw)
                print(f"RX: {rx_hex}")
                print(f"RX data: {resp.data.hex()}")
                if cmd == "xmr":
                    bits, bytes_out, words_out = _decode_ext_multi_read_data(
                        resp.data, len(bit_points), len(byte_points), len(word_points)
                    )
                    bit_idx = byte_idx = word_idx = 0
                    for kind, label in labels:
                        if kind == "bit":
                            print(f"  {label} = {bits[bit_idx]}")
                            bit_idx += 1
                        elif kind == "byte":
                            print(f"  {label} = 0x{bytes_out[byte_idx]:02X}")
                            byte_idx += 1
                        else:
                            print(f"  {label} = 0x{words_out[word_idx]:04X}")
                            word_idx += 1
                elif cmd == "xmw":
                    for kind, label, value in labels:
                        width = 1 if kind == "bit" else (2 if kind == "byte" else 4)
                        print(f"  {label} <= 0x{value:0{width}X}")
                if log_f:
                    log_f.write(f"TX {tx_hex}\n")
                    log_f.write(f"RX {rx_hex}\n")
                    log_f.write(f"RX data {resp.data.hex()}\n")
                    log_f.flush()
            except Exception as e:
                if log_f and plc.last_tx:
                    log_f.write(f"ERR {e}\n")
                    log_f.write(f"LAST_TX {_hex(plc.last_tx)}\n")
                    if plc.last_rx:
                        log_f.write(f"LAST_RX {_hex(plc.last_rx)}\n")
                    log_f.flush()
                print(f"ERR: {e}")

    if log_f:
        log_f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
