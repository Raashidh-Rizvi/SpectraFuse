from datetime import date

import pandas as pd
import pytest

import fire

DAY = date(2020, 1, 1)
HEADER = ",".join(fire.COLUMNS) + "\n"
ROW = "7,80,2020-01-01,345,Terra,85,12,D\n"


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(fire, "ROOT", tmp_path)


def test_normalizes_and_deduplicates():
    table = fire.normalize((HEADER + ROW * 2).encode(), fire.SOURCES[0], DAY, "world")
    assert len(table) == 1
    assert table.acquired_utc.iloc[0].isoformat() == "2020-01-01T03:45:00+00:00"
    assert table.confidence_class.iloc[0] == "high"


@pytest.mark.parametrize("payload", [b"Invalid MAP_KEY", (HEADER + ROW.replace(",345,", ",2500,")).encode()])
def test_rejected_response_never_checkpointed(payload):
    with pytest.raises(ValueError):
        fire.partition("world", fire.SOURCES[0], DAY, payload)
    assert not list(fire.workspace("world").rglob("*.csv"))


def test_resumes_raw_and_preserves_completed_partition():
    source = fire.SOURCES[0]
    fire.partition("world", source, DAY, (HEADER + ROW).encode())
    path = fire.workspace("world") / "processed" / source / f"{DAY}.parquet"
    before = path.read_bytes()
    fire.partition("world", source, DAY, b"invalid")
    assert path.read_bytes() == before
    path.unlink()
    fire.partition("world", source, DAY)
    assert len(pd.read_parquet(path)) == 1
    assert fire.monthly("world")[0].empty


def test_holdout_calibration_and_zero_days():
    fire.demo()
    table, metrics = fire.monthly("demo")
    assert len(table) == 24
    assert metrics["training_months"] == 9
    assert metrics["holdout_months"] == 3
    assert metrics["factor"] == 2
    assert metrics["adjusted_mae"] == 0
    assert table.loc["2019-01", "origin"] == "Estimated from MODIS"
    assert table.loc["2020-01", "origin"] == "Observed by VIIRS"
    subset, _ = fire.monthly("demo", (-10, -10, 10, 10))
    assert subset.loc["2020-01", fire.SOURCES[1]] == 0


def test_canonical_area():
    assert fire.area_value(" 79.0,5.5,82,10 ") == "79,5.5,82,10"
    with pytest.raises(ValueError):
        fire.area_value("82,5.5,79,10")



def test_sync_clips_to_availability_and_resumes(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "mock-key")
    calls = []

    def reply(session, path):
        if path.startswith("/data_availability/"):
            return (b"data_id,min_date,max_date\n"
                    b"MODIS_SP,2020-01-01,2020-01-01\n"
                    b"VIIRS_SNPP_SP,2020-01-02,2020-01-02\n")
        calls.append(path)
        return HEADER.encode()

    monkeypatch.setattr(fire, "get", reply)
    for _ in range(2):
        fire.sync("world", date(2019, 12, 31), date(2020, 1, 3))
    assert calls == ["/area/csv/mock-key/MODIS_SP/world/1/2020-01-01",
                     "/area/csv/mock-key/VIIRS_SNPP_SP/world/1/2020-01-02"]
    assert len(list(fire.workspace("world").rglob("*.parquet"))) == 2

def test_history_uses_prior_months_and_handles_zero_baseline():
    from analytics import historical_anomalies
    sample = pd.Series([0., 0., 10., 15.],
                       index=['2018-01', '2019-01', '2020-01', '2021-01'])
    result = historical_anomalies(sample)
    assert pd.isna(result.loc['2019-01', 'Historical median'])
    assert result.loc['2020-01', 'Departure (detections)'] == 10
    assert pd.isna(result.loc['2020-01', 'Departure (%)'])


def test_grid_retains_unmatched_cells():
    from grid import daily_grid
    fire.partition('world', fire.SOURCES[0], DAY, (HEADER + ROW).encode())
    viirs = ROW.replace(',Terra,85,', ',N,h,')
    extra = viirs.replace('7,80,', '8,81,')
    fire.partition('world', fire.SOURCES[1], DAY, (HEADER + viirs + extra).encode())
    cells = daily_grid('world', str(DAY), str(DAY))
    assert list(cells[fire.SOURCES[0]]) == [1, 0]
    assert list(cells[fire.SOURCES[1]]) == [1, 1]

def test_sync_splits_batched_csv_and_preserves_empty_day(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "mock-key")

    def reply(session, path):
        if "/data_availability/" in path:
            return b"data_id,min_date,max_date\nMODIS_SP,2020-01-01,2020-01-03\n"
        assert path.endswith("/world/3/2020-01-01")
        return (HEADER + ROW + ROW.replace("2020-01-01", "2020-01-03")).encode()

    monkeypatch.setattr(fire, "get", reply)
    fire.sync("world", DAY, date(2020, 1, 3), (fire.SOURCES[0],))
    parts = sorted(fire.workspace("world").rglob("*.parquet"))
    assert [len(pd.read_parquet(path)) for path in parts] == [1, 0, 1]
