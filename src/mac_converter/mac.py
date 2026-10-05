"""MAC-48 normalization and formatting, independent of any user interface."""

from typing import Literal

OutputFormat = Literal["cisco", "colon", "hyphen", "plain"]
OUTPUT_FORMATS: tuple[OutputFormat, ...] = ("cisco", "colon", "hyphen", "plain")
_SEPARATORS = str.maketrans("", "", ".:- ")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class InvalidMacAddress(ValueError):
    """The input does not contain exactly twelve ASCII hexadecimal digits."""


def normalize_mac(value: str) -> str:
    """Strip surrounding whitespace and the permitted separators.

    Separator placement is intentionally permissive, as specified: mixed
    separators are accepted, but tabs/newlines *inside* a MAC are rejected.
    This validates syntax only; zero, multicast and broadcast values are valid.
    """
    if not isinstance(value, str):
        raise TypeError("MAC address must be a string")
    normalized = value.strip().translate(_SEPARATORS)
    if len(normalized) != 12:
        raise InvalidMacAddress("Expected 12 hexadecimal characters")
    if any(character not in _HEX_DIGITS for character in normalized):
        raise InvalidMacAddress("Invalid MAC address: use hexadecimal digits 0-9 and A-F")
    return normalized.lower()


def format_mac(
    value: str, output_format: OutputFormat | str = "colon", uppercase: bool = False
) -> str:
    """Normalize input and return one of the four supported representations."""
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    normalized = normalize_mac(value)
    if uppercase:
        normalized = normalized.upper()
    if output_format == "plain":
        return normalized
    group_size = 4 if output_format == "cisco" else 2
    separator = {"cisco": ".", "colon": ":", "hyphen": "-"}[output_format]
    return separator.join(
        normalized[index : index + group_size] for index in range(0, 12, group_size)
    )
