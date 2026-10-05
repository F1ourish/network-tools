"""GUI entry point."""

import tkinter as tk

from .gui import MacConverterApp


def main() -> None:
    root = tk.Tk()
    MacConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
