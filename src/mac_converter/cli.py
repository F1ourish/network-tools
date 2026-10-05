"""Optional source CLI using the exact same normalization as the GUI."""

import argparse

from . import __version__
from .mac import OUTPUT_FORMATS, InvalidMacAddress, format_mac


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a MAC-48 address locally.")
    parser.add_argument("value", help="MAC address; quote values containing spaces")
    parser.add_argument("--format", choices=OUTPUT_FORMATS, default="colon", dest="output_format")
    parser.add_argument("--upper", action="store_true", help="Use uppercase letters")
    parser.add_argument(
        "--version", action="version", version=f"MAC Address Converter {__version__}"
    )
    args = parser.parse_args(argv)
    try:
        result = format_mac(args.value, args.output_format, args.upper)
    except InvalidMacAddress as error:
        parser.error(str(error))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
