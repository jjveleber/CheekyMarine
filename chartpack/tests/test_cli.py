from chartpack import __version__
from chartpack.cli import main


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"chartpack {__version__}"
