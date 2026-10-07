"""Uniform OS-random passwords. No storage, clipboard access or network I/O."""

from dataclasses import dataclass
from math import log2
import secrets
import string

DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}:,.?"
AMBIGUOUS = "0O1Il|"
MIN_LENGTH = 8
MAX_LENGTH = 128


class InvalidPasswordOptions(ValueError):
    """An impossible or unsupported generation policy."""


@dataclass(frozen=True)
class PasswordOptions:
    length: int = 20
    lowercase: bool = True
    uppercase: bool = True
    digits: bool = True
    symbols: bool = True
    exclude_ambiguous: bool = True
    symbol_chars: str = DEFAULT_SYMBOLS

    def groups(self) -> tuple[str, ...]:
        if type(self.length) is not int or not MIN_LENGTH <= self.length <= MAX_LENGTH:
            raise InvalidPasswordOptions(f"Длина: целое число от {MIN_LENGTH} до {MAX_LENGTH}.")
        flags = (self.lowercase, self.uppercase, self.digits, self.symbols, self.exclude_ambiguous)
        if any(type(flag) is not bool for flag in flags):
            raise InvalidPasswordOptions("Группы символов должны быть включены или выключены.")
        if self.symbols:
            if not isinstance(self.symbol_chars, str) or not self.symbol_chars:
                raise InvalidPasswordOptions("Введите хотя бы один спецсимвол.")
            if len(self.symbol_chars) > 32 or any(
                c not in string.punctuation for c in self.symbol_chars
            ):
                raise InvalidPasswordOptions(
                    "Спецсимволы: до 32 знаков ASCII без букв, пробелов и цифр."
                )
        groups = []
        for enabled, chars in zip(
            flags[:4],
            (string.ascii_lowercase, string.ascii_uppercase, string.digits, self.symbol_chars),
            strict=True,
        ):
            if enabled:
                chars = "".join(dict.fromkeys(chars))
                if self.exclude_ambiguous:
                    chars = "".join(c for c in chars if c not in AMBIGUOUS)
                if not chars:
                    raise InvalidPasswordOptions("После исключений одна из групп стала пустой.")
                groups.append(chars)
        if not groups:
            raise InvalidPasswordOptions("Выберите хотя бы одну группу символов.")
        if sum(map(len, groups)) < 2:
            raise InvalidPasswordOptions("Для генерации нужны хотя бы два разных символа.")
        return tuple(groups)


def password_space_size(options: PasswordOptions) -> int:
    """Exact count with at least one character from every selected disjoint group."""
    groups = options.groups()
    total = sum(map(len, groups))
    count = 0
    for mask in range(1 << len(groups)):
        excluded = sum(len(group) for i, group in enumerate(groups) if mask & (1 << i))
        count += (-1 if mask.bit_count() % 2 else 1) * (total - excluded) ** options.length
    return count


def entropy_bits(options: PasswordOptions) -> float:
    """Uniform generation entropy, not a score for a human-chosen password."""
    return log2(password_space_size(options))


def generate_password(options: PasswordOptions = PasswordOptions()) -> str:
    groups = options.groups()
    alphabet = "".join(groups)
    # Rejection retains a uniform distribution over all strings meeting the policy.
    # CSPRNG failures propagate; there is deliberately no weaker fallback.
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(options.length))
        if all(any(c in group for c in candidate) for group in groups):
            return candidate
