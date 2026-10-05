import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--require-gui", action="store_true", help="Fail instead of skipping without a Tk desktop"
    )


@pytest.fixture
def app(request):
    import tkinter as tk

    from mac_converter.gui import MacConverterApp

    try:
        root = tk.Tk()
    except tk.TclError as error:
        if request.config.getoption("--require-gui"):
            pytest.fail(f"A Tk desktop is required: {error}")
        pytest.skip("No Tk desktop; use Windows or Xvfb to run GUI checks")
    instance = MacConverterApp(root)
    root.update()
    yield instance
    root.destroy()
