# Project Architecture and Design Goals

This document outlines the core design philosophy and technical structure of the TOYOPUC Computer Link Python library.

## 1. Project Background

The library provides a Python interface to TOYOPUC PLCs over the 2ET Ethernet module using the proprietary Computer Link protocol. It is designed for industrial monitoring and automation tasks requiring reliable, high-throughput device access.

## 2. Core Design Principles

- **Sync and Async Parity**: All public operations are available in both synchronous (`ToyopucClient`) and asynchronous (`AsyncToyopucClient`) forms with identical signatures.
- **Protocol Fidelity**: Low-level access mirrors the raw command structure so advanced users can inspect and debug frame-level behavior.
- **High-Level Abstraction**: `ToyopucDeviceClient` and `AsyncToyopucDeviceClient` accept human-readable device strings (e.g., `"P1-D0000"`, `"FR000000"`) and handle address validation and range checking automatically.

## 3. Layer Structure

```
AsyncToyopucDeviceClient / ToyopucDeviceClient   ← high-level string-address API
        │
AsyncToyopucClient / ToyopucClient               ← low-level numeric-address API
        │
ToyopucProtocol (protocol.py)                    ← frame builders / parsers
        │
Transport (TCP/UDP socket)
```

### Low-Level Client (`ToyopucClient`)

- Accepts numeric addresses and byte/word counts.
- Exposes all supported command groups: basic, extended, PC10, relay, FR, clock, CPU status.
- `send_raw` and `send_payload` allow arbitrary frame injection for protocol investigation.

### High-Level Client (`ToyopucDeviceClient`)

- Accepts device strings such as `"P1-D0000"`, `"L3-M0100"`, `"FR000000"`.
- Resolves device strings to numeric addresses via `resolve_device`.
- Wraps `ToyopucClient` internally.

### Protocol Layer (`protocol.py`)

- Stateless frame builder and parser functions.
- `build_command(cmd, data)` constructs the 5-byte header + payload frame.
- Individual `build_*` helpers for each command type.

### Async Wrapper (`async_client.py`)

- `AsyncToyopucClient` and `AsyncToyopucDeviceClient` delegate to their sync counterparts via `asyncio.get_event_loop().run_in_executor`.
- Method list is declared in `_CLIENT_ASYNC_METHODS` and `_HIGH_LEVEL_ASYNC_METHODS` for automatic generation.

## 4. Relay Support

Relay commands (`CMD=60`) wrap an inner command frame with a routing header.
Nested relay is supported for multi-hop topologies.
The library resolves hop specifications from string notation (e.g., `"P1-L2:N2"`) or list-of-tuples form.

## 5. FR Area

FR (File Register) access uses PC10 block commands (`CMD=C2/C3`) with `Ex No. = 0x40–0x7F`.
Write + commit is a two-step operation: write with `CMD=C3`, then commit with `CMD=CA`.
`write_fr_words_committed` combines both steps with optional completion polling.

## 6. Error Handling

All protocol errors raise `ToyopucProtocolError`.
Timeout and connection failures raise `ToyopucTimeoutError` (subclass of `ToyopucProtocolError`).
