from itertools import product
from math import log2
import string

import pytest

from mac_converter import passwords
from mac_converter.passwords import (
    AMBIGUOUS,
    InvalidPasswordOptions,
    PasswordOptions,
    entropy_bits,
    generate_password,
    password_space_size,
)


@pytest.mark.parametrize("flags", [f for f in product((False, True), repeat=4) if any(f)])
@pytest.mark.parametrize("length", [8, 20, 128])
def test_every_group_combination_obeys_policy(flags, length):
    options = PasswordOptions(length, *flags)
    groups = options.groups()
    result = generate_password(options)
    assert len(result) == length
    assert set(result) <= set("".join(groups))
    assert not set(result) & set(AMBIGUOUS)
    assert all(set(result) & set(group) for group in groups)


@pytest.mark.parametrize("length", [0, 7, 129, True, 20.0, "20", None])
def test_bad_length_is_rejected(length):
    with pytest.raises(InvalidPasswordOptions):
        generate_password(PasswordOptions(length=length))


@pytest.mark.parametrize("symbols", ["", "abc", "12", "! ", "\n", "✦", "!" * 33, None])
def test_bad_symbols_are_rejected(symbols):
    with pytest.raises(InvalidPasswordOptions):
        generate_password(PasswordOptions(symbol_chars=symbols))


def test_no_groups_and_degenerate_alphabet_rejected():
    with pytest.raises(InvalidPasswordOptions):
        generate_password(
            PasswordOptions(lowercase=False, uppercase=False, digits=False, symbols=False)
        )
    with pytest.raises(InvalidPasswordOptions):
        generate_password(
            PasswordOptions(lowercase=False, uppercase=False, digits=False, symbol_chars="!")
        )
    with pytest.raises(InvalidPasswordOptions):
        generate_password(
            PasswordOptions(lowercase=False, uppercase=False, digits=False, symbol_chars="|")
        )


def test_disabled_symbols_are_ignored_and_duplicates_have_no_weight():
    assert PasswordOptions(symbols=False, symbol_chars="garbage").groups()
    assert (
        PasswordOptions(symbol_chars="!!@@").groups() == PasswordOptions(symbol_chars="!@").groups()
    )


def test_ambiguity_can_be_disabled():
    groups = PasswordOptions(exclude_ambiguous=False, symbol_chars="!|").groups()
    assert set(AMBIGUOUS) <= set("".join(groups))


def test_rejection_uses_only_secrets_and_keeps_valid_candidate(monkeypatch):
    choices = iter("aaaaaaaa" + "aB2!abcd")
    alphabets = []

    def choice(alphabet):
        alphabets.append(alphabet)
        return next(choices)

    monkeypatch.setattr(passwords.secrets, "choice", choice)
    options = PasswordOptions(length=8)
    assert generate_password(options) == "aB2!abcd"
    assert len(alphabets) == 16
    assert len(set(alphabets)) == 1
    assert alphabets[0] == "".join(options.groups())


def test_csprng_failure_has_no_fallback(monkeypatch):
    def unavailable(_alphabet):
        raise OSError("no entropy")

    monkeypatch.setattr(passwords.secrets, "choice", unavailable)
    with pytest.raises(OSError):
        generate_password()


def test_entropy_matches_brute_force_count(monkeypatch):
    groups = ("a", "B", "2", "!")
    monkeypatch.setattr(PasswordOptions, "groups", lambda _options: groups)
    options = PasswordOptions(length=8)
    count = sum(all(c in value for c in "aB2!") for value in product("aB2!", repeat=8))
    assert password_space_size(options) == count
    assert entropy_bits(options) == pytest.approx(log2(count))


def test_entropy_of_single_group_and_default():
    options = PasswordOptions(
        lowercase=False, uppercase=False, symbols=False, exclude_ambiguous=False
    )
    assert password_space_size(options) == 10**options.length
    assert entropy_bits(options) == pytest.approx(options.length * log2(10))
    assert 120 < entropy_bits(PasswordOptions()) < 132


def test_custom_punctuation_respects_policy():
    options = PasswordOptions(symbol_chars=string.punctuation, exclude_ambiguous=False)
    value = generate_password(options)
    assert any(c in string.punctuation for c in value)
