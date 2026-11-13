import pandas as pd
import pytest
from fastapi import HTTPException

from godseye.api.app import in_bbox, parse_bbox


def test_bbox_crossing_the_antimeridian():
    lat = pd.Series([0.0, 0.0, 0.0, 0.0])
    lon = pd.Series([179.9, -179.9, 0.0, 169.0])
    assert in_bbox(lat, lon, (170, -10, -170, 10)).tolist() == [True, True, False, False]


def test_plain_bbox():
    lat, lon = pd.Series([31.9, 10.0]), pd.Series([35.9, 35.9])
    assert in_bbox(lat, lon, parse_bbox("34,29,42.5,37.5")).tolist() == [True, False]


def test_bad_bbox_is_a_422():
    with pytest.raises(HTTPException) as e:
        parse_bbox("1,2,3")
    assert e.value.status_code == 422
