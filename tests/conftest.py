from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--require-gui", action="store_true", help="Fail instead of skipping without a Tk desktop"
    )


@pytest.fixture(scope="session")
def tk_runtime(request):
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as error:
        if request.config.getoption("--require-gui"):
            pytest.fail(f"A Tk desktop is required: {error}")
        pytest.skip("No Tk desktop; use Windows or Xvfb to run GUI checks")
    # Preload the actual Tk focus definitions rather than deferring their file I/O
    # to tk_focusNext after dozens of short-lived Windows test windows.
    # Python reads the same installed script; all focus-order assertions stay intact.
    focus_script = Path(root.tk.eval("set tk_library")) / "focus.tcl"
    root.tk.eval(focus_script.read_text(encoding="utf-8"))
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tk_runtime, tmp_path):
    import tkinter as tk

    from mac_converter.gui import MacConverterApp

    # Keep one Tcl/Tk interpreter; each test still gets a fresh application window.
    root = tk.Toplevel(tk_runtime)
    instance = MacConverterApp(root, settings_path=tmp_path / "settings.json")
    root.update()
    try:
        yield instance
    finally:
        root.destroy()
