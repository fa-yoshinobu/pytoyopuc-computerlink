"""Device profiles and addressing options for TOYOPUC PLCs.

Mirrors the .NET ``ToyopucDeviceProfile`` / ``ToyopucDeviceProfiles`` /
``ToyopucAddressingOptions`` types.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Address range
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyopucAddressRange:
    """An inclusive integer range [start, end]."""

    start: int
    end: int

    def contains(self, index: int) -> bool:
        return self.start <= index <= self.end


# ---------------------------------------------------------------------------
# Area descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyopucAreaDescriptor:
    """Per-area metadata for a device profile.

    Attributes:
        area: Area name (e.g. ``"D"``, ``"EP"``, ``"FR"``).
        direct_ranges: Valid index ranges for direct (non-prefixed) access.
        prefixed_ranges: Valid index ranges for P1-/P2-/P3- prefixed access.
        supports_packed_word: True when bit-device packed-word (W/L/H suffix)
            access is allowed.
        address_width: Number of hex digits in the normal address field.
        suggested_start_step: Step between suggested start addresses for UI.
        packed_direct_ranges_override: If set, overrides the shifted direct
            ranges used for packed/derived access.
        packed_prefixed_ranges_override: Same, for prefixed access.
    """

    area: str
    direct_ranges: tuple[ToyopucAddressRange, ...]
    prefixed_ranges: tuple[ToyopucAddressRange, ...]
    supports_packed_word: bool
    address_width: int
    suggested_start_step: int
    packed_direct_ranges_override: tuple[ToyopucAddressRange, ...] | None = None
    packed_prefixed_ranges_override: tuple[ToyopucAddressRange, ...] | None = None

    @property
    def supports_direct(self) -> bool:
        return len(self.direct_ranges) > 0

    @property
    def supports_prefixed(self) -> bool:
        return len(self.prefixed_ranges) > 0

    @property
    def packed_address_width(self) -> int:
        return max(1, self.address_width - 1)

    def uses_derived_access(self, unit: str, packed: bool = False) -> bool:
        """True when ``unit``/``packed`` combination uses shifted (derived) ranges."""
        if not self.supports_packed_word:
            return False
        return unit == "byte" or (unit == "word" and packed)

    def get_address_width(self, unit: str, packed: bool = False) -> int:
        if self.uses_derived_access(unit, packed):
            return self.packed_address_width
        return self.address_width

    def get_ranges(self, prefixed: bool, packed: bool = False) -> tuple[ToyopucAddressRange, ...]:
        """Return the valid index ranges for the given access mode.

        Args:
            prefixed: True for P1-/P2-/P3- prefixed access, False for direct.
            packed: True when using derived/packed (shifted) ranges.

        Returns:
            Tuple of valid address ranges.
        """
        if not packed:
            return self.prefixed_ranges if prefixed else self.direct_ranges

        override = self.packed_prefixed_ranges_override if prefixed else self.packed_direct_ranges_override
        if override is not None:
            return override

        source = self.prefixed_ranges if prefixed else self.direct_ranges
        seen: set[tuple[int, int]] = set()
        result: list[ToyopucAddressRange] = []
        for r in source:
            shifted = ToyopucAddressRange(r.start >> 4, r.end >> 4)
            key = (shifted.start, shifted.end)
            if key not in seen:
                seen.add(key)
                result.append(shifted)
        return tuple(result)

    def get_ranges_for_unit(self, prefixed: bool, unit: str, packed: bool = False) -> tuple[ToyopucAddressRange, ...]:
        """Return ranges applying derived-access logic for the given unit."""
        return self.get_ranges(prefixed, self.uses_derived_access(unit, packed))


# ---------------------------------------------------------------------------
# Addressing options
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyopucAddressingOptions:
    """Flags that control how device addresses are routed to protocol commands.

    All flags default to ``True`` (Generic / PC10G mode behaviour).

    Attributes:
        use_upper_u_pc10: Route U-area indexes >= 0x08000 via PC10 block
            commands instead of ext-word commands.
        use_eb_pc10: Route EB-area via PC10 block commands.
        use_fr_pc10: Route FR-area via PC10 block commands.
        use_upper_bit_pc10: Route P/V/T/C/L-area bit indexes >= 0x1000
            (and derived word/byte >= 0x100) via PC10 block commands.
        use_upper_m_bit_pc10: Same as above but for M-area.
    """

    use_upper_u_pc10: bool = True
    use_eb_pc10: bool = True
    use_fr_pc10: bool = True
    use_upper_bit_pc10: bool = True
    use_upper_m_bit_pc10: bool = True

    @staticmethod
    def from_profile(profile: str | None) -> ToyopucAddressingOptions:
        return ToyopucDeviceProfiles.from_name(profile).addressing_options


# Pre-defined instances (mirrors C# static properties)
ToyopucAddressingOptions.Default = ToyopucAddressingOptions()
ToyopucAddressingOptions.Generic = ToyopucAddressingOptions()
ToyopucAddressingOptions.ToyopucPlusStandard = ToyopucAddressingOptions(
    use_upper_u_pc10=False,
    use_eb_pc10=False,
    use_fr_pc10=False,
    use_upper_bit_pc10=False,
    use_upper_m_bit_pc10=False,
)
ToyopucAddressingOptions.ToyopucPlusExtended = ToyopucAddressingOptions.ToyopucPlusStandard
ToyopucAddressingOptions.Nano10GxMode = ToyopucAddressingOptions()
ToyopucAddressingOptions.Nano10GxCompatible = ToyopucAddressingOptions()
ToyopucAddressingOptions.Pc10GStandardPc3Jg = ToyopucAddressingOptions(
    use_upper_u_pc10=False,
    use_eb_pc10=True,
    use_fr_pc10=False,
    use_upper_bit_pc10=False,
    use_upper_m_bit_pc10=False,
)
ToyopucAddressingOptions.Pc10GMode = ToyopucAddressingOptions()
ToyopucAddressingOptions.Pc3JxPc3Separate = ToyopucAddressingOptions(
    use_upper_u_pc10=False,
    use_eb_pc10=False,
    use_fr_pc10=False,
    use_upper_bit_pc10=False,
    use_upper_m_bit_pc10=False,
)
ToyopucAddressingOptions.Pc3JxPlusExpansion = ToyopucAddressingOptions.Pc3JxPc3Separate
ToyopucAddressingOptions.Pc3JgMode = ToyopucAddressingOptions.Pc10GStandardPc3Jg
ToyopucAddressingOptions.Pc3JgPc3Separate = ToyopucAddressingOptions.Pc3JxPc3Separate


# ---------------------------------------------------------------------------
# Device profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyopucDeviceProfile:
    """A named device model configuration with area descriptors and options."""

    name: str
    addressing_options: ToyopucAddressingOptions
    areas: tuple[ToyopucAreaDescriptor, ...]


# ---------------------------------------------------------------------------
# Area builder helpers (private)
# ---------------------------------------------------------------------------


def _r(start: int, end: int) -> ToyopucAddressRange:
    return ToyopucAddressRange(start, end)


def _area(
    area: str,
    direct_ranges: tuple[ToyopucAddressRange, ...],
    prefixed_ranges: tuple[ToyopucAddressRange, ...],
    *,
    supports_packed_word: bool,
    address_width: int,
    suggested_start_step: int,
    packed_direct_override: tuple[ToyopucAddressRange, ...] | None = None,
    packed_prefixed_override: tuple[ToyopucAddressRange, ...] | None = None,
) -> ToyopucAreaDescriptor:
    return ToyopucAreaDescriptor(
        area=area,
        direct_ranges=direct_ranges,
        prefixed_ranges=prefixed_ranges,
        supports_packed_word=supports_packed_word,
        address_width=address_width,
        suggested_start_step=suggested_start_step,
        packed_direct_ranges_override=packed_direct_override,
        packed_prefixed_ranges_override=packed_prefixed_override,
    )


def _bit_area(
    area: str,
    direct_ranges: tuple[ToyopucAddressRange, ...],
    prefixed_ranges: tuple[ToyopucAddressRange, ...],
) -> ToyopucAreaDescriptor:
    return _area(
        area,
        direct_ranges,
        prefixed_ranges,
        supports_packed_word=True,
        address_width=4,
        suggested_start_step=0x10,
    )


def _prefixed_bit_area(area: str, prefixed_end: int) -> ToyopucAreaDescriptor:
    return _bit_area(area, (), (_r(0x0000, prefixed_end),))


def _prefixed_split_bit_area(area: str, low_end: int, high_end: int) -> ToyopucAreaDescriptor:
    return _bit_area(area, (), (_r(0x0000, low_end), _r(0x1000, high_end)))


def _word_area(
    area: str,
    direct_ranges: tuple[ToyopucAddressRange, ...],
    prefixed_ranges: tuple[ToyopucAddressRange, ...],
) -> ToyopucAreaDescriptor:
    return _area(
        area,
        direct_ranges,
        prefixed_ranges,
        supports_packed_word=False,
        address_width=4,
        suggested_start_step=0x10,
    )


def _prefixed_word_area(area: str, prefixed_end: int) -> ToyopucAreaDescriptor:
    return _word_area(area, (), (_r(0x0000, prefixed_end),))


def _prefixed_split_word_area(area: str, low_end: int, high_end: int) -> ToyopucAreaDescriptor:
    return _word_area(area, (), (_r(0x0000, low_end), _r(0x1000, high_end)))


def _word_area_direct(area: str, direct_end: int) -> ToyopucAreaDescriptor:
    return _word_area(area, (_r(0x0000, direct_end),), ())


def _ext_bit_area(
    area: str,
    direct_end: int,
    packed_direct_end: int | None = None,
) -> ToyopucAreaDescriptor:
    packed_override = (_r(0x0000, packed_direct_end),) if packed_direct_end is not None else None
    return _area(
        area,
        (_r(0x0000, direct_end),),
        (),
        supports_packed_word=True,
        address_width=4,
        suggested_start_step=0x10,
        packed_direct_override=packed_override,
    )


def _ext_word_area(area: str, direct_end: int) -> ToyopucAreaDescriptor:
    return _area(
        area,
        (_r(0x0000, direct_end),),
        (),
        supports_packed_word=False,
        address_width=5,
        suggested_start_step=0x100,
    )


def _fr_area(direct_end: int) -> ToyopucAreaDescriptor:
    return _area(
        "FR",
        (_r(0x000000, direct_end),),
        (),
        supports_packed_word=False,
        address_width=6,
        suggested_start_step=0x1000,
    )


# ---------------------------------------------------------------------------
# Per-profile area lists (private)
# ---------------------------------------------------------------------------


def _generic_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_split_bit_area("P", low_end=0x01FF, high_end=0x17FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_split_bit_area("V", low_end=0x00FF, high_end=0x17FF),
        _prefixed_split_bit_area("T", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("C", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("L", low_end=0x07FF, high_end=0x2FFF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_split_bit_area("M", low_end=0x07FF, high_end=0x17FF),
        _prefixed_split_word_area("S", low_end=0x03FF, high_end=0x13FF),
        _prefixed_split_word_area("N", low_end=0x01FF, high_end=0x17FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x2FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x1FFFF),
        _ext_word_area("EB", 0x3FFFF),
        _fr_area(0x1FFFFF),
    )


def _toyopuc_plus_standard_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
    )


def _toyopuc_plus_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
    )


def _nano10gx_mode_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_split_bit_area("P", low_end=0x01FF, high_end=0x17FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_split_bit_area("V", low_end=0x00FF, high_end=0x17FF),
        _prefixed_split_bit_area("T", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("C", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("L", low_end=0x07FF, high_end=0x2FFF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_split_bit_area("M", low_end=0x07FF, high_end=0x17FF),
        _prefixed_split_word_area("S", low_end=0x03FF, high_end=0x13FF),
        _prefixed_split_word_area("N", low_end=0x01FF, high_end=0x17FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x2FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x1FFFF),
        _ext_word_area("EB", 0x3FFFF),
        _fr_area(0x1FFFFF),
    )


def _pc10_standard_pc3jg_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
        _ext_word_area("EB", 0x1FFFF),
    )


def _pc10_mode_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_split_bit_area("P", low_end=0x01FF, high_end=0x17FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_split_bit_area("V", low_end=0x00FF, high_end=0x17FF),
        _prefixed_split_bit_area("T", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("C", low_end=0x01FF, high_end=0x17FF),
        _prefixed_split_bit_area("L", low_end=0x07FF, high_end=0x2FFF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_split_bit_area("M", low_end=0x07FF, high_end=0x17FF),
        _prefixed_split_word_area("S", low_end=0x03FF, high_end=0x13FF),
        _prefixed_split_word_area("N", low_end=0x01FF, high_end=0x17FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x2FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF, packed_direct_end=0x0FFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x1FFFF),
        _ext_word_area("EB", 0x3FFFF),
        _fr_area(0x1FFFFF),
    )


def _pc3jx_pc3_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x2FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
    )


def _pc3jx_plus_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
    )


def _pc3jg_mode_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
        _ext_word_area("EB", 0x1FFFF),
    )


def _pc3jg_pc3_areas() -> tuple[ToyopucAreaDescriptor, ...]:
    return (
        _prefixed_bit_area("P", 0x01FF),
        _prefixed_bit_area("K", 0x02FF),
        _prefixed_bit_area("V", 0x00FF),
        _prefixed_bit_area("T", 0x01FF),
        _prefixed_bit_area("C", 0x01FF),
        _prefixed_bit_area("L", 0x07FF),
        _prefixed_bit_area("X", 0x07FF),
        _prefixed_bit_area("Y", 0x07FF),
        _prefixed_bit_area("M", 0x07FF),
        _prefixed_word_area("S", 0x03FF),
        _prefixed_word_area("N", 0x01FF),
        _prefixed_word_area("R", 0x07FF),
        _prefixed_word_area("D", 0x0FFF),
        _word_area_direct("B", 0x1FFF),
        _ext_bit_area("EP", 0x0FFF),
        _ext_bit_area("EK", 0x0FFF),
        _ext_bit_area("EV", 0x0FFF),
        _ext_bit_area("ET", 0x07FF),
        _ext_bit_area("EC", 0x07FF),
        _ext_bit_area("EL", 0x1FFF),
        _ext_bit_area("EX", 0x07FF),
        _ext_bit_area("EY", 0x07FF),
        _ext_bit_area("EM", 0x1FFF),
        _ext_bit_area("GM", 0xFFFF),
        _ext_bit_area("GX", 0xFFFF),
        _ext_bit_area("GY", 0xFFFF),
        _ext_word_area("ES", 0x07FF),
        _ext_word_area("EN", 0x07FF),
        _ext_word_area("H", 0x07FF),
        _ext_word_area("U", 0x07FFF),
        _ext_word_area("EB", 0x1FFFF),
    )


# ---------------------------------------------------------------------------
# Device profiles catalog
# ---------------------------------------------------------------------------


class ToyopucDeviceProfiles:
    """Catalog of all known TOYOPUC device profiles."""

    Generic: ToyopucDeviceProfile
    ToyopucPlusStandard: ToyopucDeviceProfile
    ToyopucPlusExtended: ToyopucDeviceProfile
    Nano10GxMode: ToyopucDeviceProfile
    Nano10GxCompatible: ToyopucDeviceProfile
    Pc10GStandardPc3Jg: ToyopucDeviceProfile
    Pc10GMode: ToyopucDeviceProfile
    Pc3JxPc3Separate: ToyopucDeviceProfile
    Pc3JxPlusExpansion: ToyopucDeviceProfile
    Pc3JgMode: ToyopucDeviceProfile
    Pc3JgPc3Separate: ToyopucDeviceProfile

    @classmethod
    def get_names(cls) -> list[str]:
        return [p.name for p in cls._all()]

    @classmethod
    def from_name(cls, profile: str | None) -> ToyopucDeviceProfile:
        if not profile or not profile.strip():
            return cls.Generic
        normalized = profile.strip()
        for p in cls._all():
            if p.name.lower() == normalized.lower():
                return p
        raise ValueError(f"Unknown device profile: {profile!r}")

    @classmethod
    def get_area_descriptor(cls, area: str, profile: str | None = None) -> ToyopucAreaDescriptor:
        normalized = area.strip().upper()
        device_profile = cls.from_name(profile)
        for descriptor in device_profile.areas:
            if descriptor.area == normalized:
                return descriptor
        profile_name = device_profile.name
        raise ValueError(f"Unknown area for profile {profile_name!r}: {area!r}")

    @classmethod
    def _all(cls) -> tuple[ToyopucDeviceProfile, ...]:
        return (
            cls.Generic,
            cls.ToyopucPlusStandard,
            cls.ToyopucPlusExtended,
            cls.Nano10GxMode,
            cls.Nano10GxCompatible,
            cls.Pc10GStandardPc3Jg,
            cls.Pc10GMode,
            cls.Pc3JxPc3Separate,
            cls.Pc3JxPlusExpansion,
            cls.Pc3JgMode,
            cls.Pc3JgPc3Separate,
        )


# Populate class-level profile instances
_OPT = ToyopucAddressingOptions
ToyopucDeviceProfiles.Generic = ToyopucDeviceProfile(
    "Generic",
    _OPT.Generic,
    _generic_areas(),
)
ToyopucDeviceProfiles.ToyopucPlusStandard = ToyopucDeviceProfile(
    "TOYOPUC-Plus:Plus Standard mode",
    _OPT.ToyopucPlusStandard,
    _toyopuc_plus_standard_areas(),
)
ToyopucDeviceProfiles.ToyopucPlusExtended = ToyopucDeviceProfile(
    "TOYOPUC-Plus:Plus Extended mode",
    _OPT.ToyopucPlusExtended,
    _toyopuc_plus_areas(),
)
ToyopucDeviceProfiles.Nano10GxMode = ToyopucDeviceProfile(
    "Nano 10GX:Nano 10GX mode",
    _OPT.Nano10GxMode,
    _nano10gx_mode_areas(),
)
ToyopucDeviceProfiles.Nano10GxCompatible = ToyopucDeviceProfile(
    "Nano 10GX:Compatible mode",
    _OPT.Nano10GxCompatible,
    _nano10gx_mode_areas(),
)
ToyopucDeviceProfiles.Pc10GStandardPc3Jg = ToyopucDeviceProfile(
    "PC10G:PC10 standard/PC3JG mode",
    _OPT.Pc10GStandardPc3Jg,
    _pc10_standard_pc3jg_areas(),
)
ToyopucDeviceProfiles.Pc10GMode = ToyopucDeviceProfile(
    "PC10G:PC10 mode",
    _OPT.Pc10GMode,
    _pc10_mode_areas(),
)
ToyopucDeviceProfiles.Pc3JxPc3Separate = ToyopucDeviceProfile(
    "PC3JX:PC3 separate mode",
    _OPT.Pc3JxPc3Separate,
    _pc3jx_pc3_areas(),
)
ToyopucDeviceProfiles.Pc3JxPlusExpansion = ToyopucDeviceProfile(
    "PC3JX:Plus expansion mode",
    _OPT.Pc3JxPlusExpansion,
    _pc3jx_plus_areas(),
)
ToyopucDeviceProfiles.Pc3JgMode = ToyopucDeviceProfile(
    "PC3JG:PC3JG mode",
    _OPT.Pc3JgMode,
    _pc3jg_mode_areas(),
)
ToyopucDeviceProfiles.Pc3JgPc3Separate = ToyopucDeviceProfile(
    "PC3JG:PC3 separate mode",
    _OPT.Pc3JgPc3Separate,
    _pc3jg_pc3_areas(),
)
