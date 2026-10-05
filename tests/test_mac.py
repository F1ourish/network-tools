import random
import string

import pytest

from mac_converter.mac import InvalidMacAddress, format_mac, normalize_mac


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0011.2233.aabb", "00112233aabb"),
        ("00:11:22:33:aa:bb", "00112233aabb"),
        ("00-11-22-33-aa-bb", "00112233aabb"),
        ("00112233aabb", "00112233aabb"),
        ("0011 2233 aabb", "00112233aabb"),
        ("AABB.CCDD.EEFF", "aabbccddeeff"),
        (" \t\n00:11:22:33:AA:BB\r\n ", "00112233aabb"),
        ("00:11-22.33 aa:bb", "00112233aabb"),
        ("00 11 22 33 aa bb", "00112233aabb"),
        ("::0011..2233--aabb::", "00112233aabb"),
        ("0000.0000.0000", "000000000000"),
        ("FF:FF:FF:FF:FF:FF", "ffffffffffff"),
        ("01:00:5e:00:00:01", "01005e000001"),
    ],
)
def test_normalization(value, expected):
    assert normalize_mac(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        "123",
        "0011.2233",
        "00112233445566",
        "hello",
        "00:11:22:ZZ:44:55",
        "GGGG.GGGG.GGGG",
        "00112233445G",
        "0011/2233/4455",
        "0x001122334455",
        "00:11:22:33:44:55:66:77",
        "0011\t22334455",
        "0011\n22334455",
        "0011\r22334455",
        "0011\u00a022334455",
        "0011\u200b22334455",
        "0011–2233–4455",
        "００１１２２３３４４５５",
        "0011223344еf",
        "00112233445\x00",
        "001122334455\n112233445566",
    ],
)
def test_invalid_mac(value):
    with pytest.raises(InvalidMacAddress):
        normalize_mac(value)


@pytest.mark.parametrize("value", [None, 123, b"001122334455", ["001122334455"]])
def test_non_string_input(value):
    with pytest.raises(TypeError):
        normalize_mac(value)


@pytest.mark.parametrize(
    ("output_format", "expected"),
    [
        ("colon", "00:11:22:33:aa:bb"),
        ("hyphen", "00-11-22-33-aa-bb"),
        ("plain", "00112233aabb"),
        ("cisco", "0011.2233.aabb"),
    ],
)
@pytest.mark.parametrize("uppercase", [False, True])
def test_all_output_formats_and_case(output_format, expected, uppercase):
    result = format_mac("0011.2233.aAbB", output_format, uppercase)
    assert result == (expected.upper() if uppercase else expected)


@pytest.mark.parametrize("output_format", ["colon", "hyphen", "plain", "cisco"])
def test_invalid_input_propagates_in_every_format(output_format):
    with pytest.raises(InvalidMacAddress):
        format_mac("invalid", output_format)


@pytest.mark.parametrize("output_format", ["", "Cisco", "other"])
def test_unsupported_format(output_format):
    with pytest.raises(ValueError, match="Unsupported output format"):
        format_mac("00112233aabb", output_format)


def test_default_is_lowercase_colon():
    assert format_mac("AABB.CCDD.EEFF") == "aa:bb:cc:dd:ee:ff"


def test_round_trip_and_idempotence_for_varied_values():
    generator = random.Random(20261005)
    for _ in range(100):
        value = "".join(generator.choice(string.hexdigits) for _ in range(12))
        normalized = normalize_mac(value)
        assert normalize_mac(normalized) == normalized
        for output_format in ("cisco", "colon", "hyphen", "plain"):
            for uppercase in (False, True):
                formatted = format_mac(value, output_format, uppercase)
                assert normalize_mac(formatted) == normalized
