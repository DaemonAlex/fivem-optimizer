import os
import pytest

FIXTURES = os.environ.get("FIVEM_OPTIMIZER_FIXTURES", "")


def fixture(name):
    path = os.path.join(FIXTURES, name)
    if not FIXTURES or not os.path.isfile(path):
        pytest.skip(f"fixture {name} not available (set FIVEM_OPTIMIZER_FIXTURES)")
    return path
