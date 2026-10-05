import pytest

from mac_converter import __version__
from mac_converter.cli import main


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["0011.2233.aabb"], "00:11:22:33:aa:bb\n"),
        (["aabb.ccdd.eeff", "--format", "hyphen", "--upper"], "AA-BB-CC-DD-EE-FF\n"),
        (["00 11 22 33 AA BB", "--format", "plain"], "00112233aabb\n"),
        (["00:11:22:33:aa:bb", "--format", "cisco"], "0011.2233.aabb\n"),
    ],
)
def test_cli(arguments, expected, capsys):
    assert main(arguments) == 0
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


@pytest.mark.parametrize("arguments", [[], ["hello"], ["001122334455", "--format", "bad"]])
def test_cli_errors(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "error:" in output.err
    assert "Traceback" not in output.err


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert __version__ in capsys.readouterr().out
