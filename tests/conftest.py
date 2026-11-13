from pathlib import Path

import pandas as pd
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "firms"


def read_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURE_DIR / name, dtype=str)


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR
