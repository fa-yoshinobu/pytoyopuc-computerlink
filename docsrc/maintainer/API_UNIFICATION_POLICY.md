# API Unification Policy

This document defines the planned public API rules for the TOYOPUC Python library.
It is a design policy document. It does not claim that every rule is implemented yet.

## Purpose

- Keep the user-facing API aligned with the TOYOPUC .NET library.
- Keep protocol-oriented access available for advanced use.
- Add asyncio support without inventing different method names.

## Public API Layers

The library must keep two explicit layers.

1. `ToyopucClient`
   Low-level API for numeric addresses, raw commands, relay frames, and FR details.
2. `ToyopucDeviceClient`
   High-level API for string device addresses.

Planned asyncio parity must use separate async classes.

1. `AsyncToyopucClient`
2. `AsyncToyopucDeviceClient`

Do not expose provisional top-level constructors such as `Toyopuc(...)`.

## Naming Rules

High-level generic device access must use these names.

- `read`
- `write`
- `read_many`
- `write_many`
- `read_dword`
- `write_dword`
- `read_dwords`
- `write_dwords`
- `read_float32`
- `write_float32`
- `read_float32s`
- `write_float32s`
- `read_fr`
- `write_fr`
- `commit_fr`
- `resolve_device`
- `relay_read`
- `relay_write`
- `relay_read_many`
- `relay_write_many`

Low-level typed access must keep explicit protocol-oriented names.

- `read_words`
- `write_words`
- `read_bytes`
- `write_bytes`
- `read_bit`
- `write_bit`
- `read_dwords`
- `write_dwords`
- `read_float32s`
- `write_float32s`
- `read_ext_words`
- `write_ext_words`
- `pc10_block_read`
- `pc10_block_write`
- `read_clock`
- `write_clock`
- `read_cpu_status`

Do not add a second high-level naming family such as `read_word`, `write_word`, or `read_device` when the input is already a string device address.

## 32-Bit Value Rules

The library should distinguish raw 32-bit integers from IEEE 754 floating-point values.

- `dword` means a raw 32-bit unsigned value stored across two PLC words.
- Signed 32-bit helpers, if added later, should be named `read_int32` and `write_int32`.
- Floating-point helpers should use `float32` in the public name, not plain `float`.

Default 32-bit word-pair interpretation:

- The default contract is protocol-native low-word-first ordering.
- If alternate word order must be supported, use an explicit keyword such as `word_order`.
- Avoid public names such as `read_float_swap`.

## Async Rules

Async method names must stay identical to sync method names.
The async boundary is expressed by the async class and `await`, not by `_async` suffixes.

Examples:

- `await client.connect()`
- `await client.read("P1-D0000")`
- `await client.write("P1-M0000", True)`
- `await client.read_many([...])`
- `await client.commit_fr("FR000000", wait=True)`

Async classes must also support:

- `async with AsyncToyopucClient(...) as client:`
- `async with AsyncToyopucDeviceClient(...) as client:`

Async methods must follow these rules.

- Keep argument names and order aligned with the sync method.
- Return the same logical result shape as the sync method.
- Keep the same exception classes where practical.

## Internal Naming Rules

Private helper names must describe the resolved object or protocol path they operate on.

Avoid vague names such as:

- `_read_one`
- `_write_one`
- `_relay_read_one`
- `_relay_write_one`
- `_offset`

Prefer names such as:

- `_read_resolved_device`
- `_write_resolved_device`
- `_relay_read_resolved_device`
- `_relay_write_resolved_device`
- `_offset_resolved_device`
- `_pack_uint32_low_word_first`
- `_unpack_uint32_low_word_first`
- `_pack_float32_low_word_first`
- `_unpack_float32_low_word_first`

When a helper is protocol-family specific, keep that family in the name.

- `_read_pc10_multi_words`
- `_pack_pc10_multi_word_payload`
- `_resolve_ext_bit`

## Documentation Rules

README and samples must prefer these canonical entry points.

- Sync quick start: `ToyopucDeviceClient`
- Async quick start: `AsyncToyopucDeviceClient`
- Advanced samples: `ToyopucClient` or `AsyncToyopucClient`

README must not use undocumented aliases as the primary form.

## Stability Rules

- Sync naming remains the base contract.
- Async support must be additive.
- Do not keep legacy public class aliases once the canonical class names are published.
