from pathlib import Path

import pytest

from model_lab.scripts.data_cli import safe_member_name


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "a/../../escape", "C:\\escape.txt"])
def test_archive_paths_reject_traversal(name: str) -> None:
    with pytest.raises(ValueError):
        safe_member_name(name)


def test_archive_paths_accept_normal_member() -> None:
    assert safe_member_name("Battery-1/cycle_001.mat") == Path("Battery-1/cycle_001.mat")
