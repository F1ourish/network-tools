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
