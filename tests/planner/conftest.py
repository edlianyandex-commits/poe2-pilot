import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for planner_helpers


@pytest.fixture(scope="session")
def tree():
    from pilot.planner.tree import PassiveTree
    return PassiveTree.load()
