import argparse
import calendar
import hashlib
import os
import tempfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
COLUMNS = ["latitude", "longitude", "acq_date", "acq_time", "satellite",
           "confidence", "frp", "daynight"]
API = "https://firms.modaps.eosdis.nasa.gov/api"


def area_value(value):
    if value == "world":
        return value
    west, south, east, north = map(float, value.split(","))
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Use west,south,east,north within geographic bounds.")
    return ",".join(format(n or 0, ".15g") for n in (west, south, east, north))


def workspace(area):
    return ROOT / "data" / (area if area in ("demo", "world") else
                            hashlib.sha256(area.encode()).hexdigest()[:16])


def atomic(path, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        write(temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def normalize(payload, source, day, area):
    frame = pd.read_csv(BytesIO(payload), dtype="string")
    if set(COLUMNS) - set(frame):
        raise ValueError("FIRMS response is missing expected CSV columns.")
    data = frame[COLUMNS].copy()
    for column in ("latitude", "longitude", "frp"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    time = data.acq_time.str.fullmatch(r"[0-9]{1,4}").fillna(False)
    stamp = pd.to_datetime(data.acq_date + " " + data.acq_time.str.zfill(4),
                           format="%Y-%m-%d %H%M", errors="coerce", utc=True)
    if source == SOURCES[0]:
        score = pd.to_numeric(data.confidence, errors="coerce")
        confidence = pd.cut(score, [-1, 29, 79, 100], labels=["low", "nominal", "high"])
        valid_confidence = score.between(0, 100) & score.mod(1).eq(0)
    else:
        confidence = data.confidence.str.lower().map({"l": "low", "n": "nominal", "h": "high"})
        valid_confidence = confidence.notna()
    bounds = [-180, -90, 180, 90] if area in ("world", "demo") else list(map(float, area.split(",")))
    west, south, east, north = bounds
    valid = (data.latitude.between(south, north) & data.longitude.between(west, east)
             & data.frp.between(0, float("inf"), inclusive="left")
             & data.acq_date.eq(str(day)) & time & stamp.notna() & valid_confidence
             & data.satellite.str.strip().ne("") & data.daynight.isin(["D", "N"]))
    if not valid.fillna(False).all():
        raise ValueError(f"{source} {day}: {int((~valid.fillna(False)).sum())} invalid rows.")
    data["confidence_class"] = confidence.astype("string")
    data["acquired_utc"] = stamp
    data["source"] = source
    data["grid_lon"] = data.longitude.clip(upper=179.999999).floordiv(1).astype("int16")
    data["grid_lat"] = data.latitude.clip(upper=89.999999).floordiv(1).astype("int16")
    return data.drop(columns="acq_time").drop_duplicates(
        ["latitude", "longitude", "acquired_utc", "satellite"])


def partition(area, source, day, payload=None):
    root = workspace(area)
    raw = root / "raw" / source / f"{day}.csv"
    output = root / "processed" / source / f"{day}.parquet"
    if output.exists():
        return
    content = raw.read_bytes() if raw.exists() else payload
    if content is None:
        raise ValueError("Missing raw CSV.")
    clean = normalize(content, source, day, area)
    if not raw.exists():
        atomic(raw, lambda target: target.write_bytes(content))
    atomic(output, lambda target: clean.to_parquet(target, index=False))


def get(session, path):
    try:
        with session.get(API + path, timeout=(10, 90), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError(f"FIRMS returned HTTP {response.status_code}.")
            return response.content
    except requests.RequestException:
        raise ValueError("FIRMS connection failed after retries.") from None


def sync(area, start, end):
    load_dotenv(ROOT / ".env")
    key = os.getenv("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise ValueError("Set FIRMS_MAP_KEY in the project .env file.")
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
        key = quote(key, safe="")
        try:
            availability = pd.read_csv(BytesIO(get(session, f"/data_availability/csv/{key}/ALL")))
            coverage = availability.set_index("data_id")
            windows = [(source, date.fromisoformat(coverage.loc[source, "min_date"]),
                        date.fromisoformat(coverage.loc[source, "max_date"])) for source in SOURCES]
        except (KeyError, TypeError, pd.errors.ParserError) as error:
            raise ValueError("Unexpected FIRMS availability response. Check your MAP_KEY.") from None
        for source, first, last in windows:
            day = max(start, first)
            stop = min(end, last)
            print(f"{source}: available {first} through {last}", flush=True)
            while day <= stop:
                root = workspace(area)
                raw = root / "raw" / source / f"{day}.csv"
                output = root / "processed" / source / f"{day}.parquet"
                if not output.exists():
                    print(f"{source} {day}", flush=True)
                    payload = None if raw.exists() else get(session, f"/area/csv/{key}/{source}/{area}/1/{day}")
                    partition(area, source, day, payload)
                day += timedelta(days=1)


def monthly(area, bounds=None):
    root = workspace(area)
    records = []
    for source in SOURCES:
        counts = {}
        for path in sorted((root / "processed" / source).glob("*.parquet")):
            month = path.stem[:7]
            days, count = counts.get(month, (0, 0))
            if bounds is None:
                import pyarrow.parquet as pq
                size = pq.ParquetFile(path).metadata.num_rows
            else:
                west, south, east, north = bounds
                points = pd.read_parquet(path, columns=["latitude", "longitude"])
                size = int((points.latitude.between(south, north)
                            & points.longitude.between(west, east)).sum())
            counts[month] = days + 1, count + size
        for month, (days, count) in counts.items():
            year, number = map(int, month.split("-"))
            if days == calendar.monthrange(year, number)[1]:
                records.append((month, source, count))
    if not records:
        return pd.DataFrame(columns=[*SOURCES, "harmonized", "origin"]), {}
    table = pd.DataFrame(records, columns=["month", "source", "count"]).pivot(
        index="month", columns="source", values="count").reindex(columns=list(SOURCES))
    table = table.reindex(pd.period_range(table.index.min(), table.index.max(), freq="M").astype(str))
    table.index.name = "month"
    paired = table.dropna()
    heldout = paired.iloc[-max(1, len(paired) // 4):]
    training = paired.iloc[:len(paired) - len(heldout)]
    metrics = {"paired_months": len(paired), "training_months": len(training),
               "holdout_months": len(heldout)}
    modis, viirs = SOURCES
    if len(training) >= 3 and training[modis].sum() > 0 and training[viirs].sum() > 0:
        factor = training[viirs].sum() / training[modis].sum()
        metrics.update(factor=float(factor),
                       raw_mae=float((heldout[modis] - heldout[viirs]).abs().mean()),
                       adjusted_mae=float((heldout[modis] * factor - heldout[viirs]).abs().mean()))
        estimate = table[modis] * factor
    else:
        estimate = pd.Series(float("nan"), index=table.index)
    table["harmonized"] = table[viirs].combine_first(estimate)
    table["origin"] = "Unavailable"
    table.loc[estimate.notna(), "origin"] = "Estimated from MODIS"
    table.loc[table[viirs].notna(), "origin"] = "Observed by VIIRS"
    return table, metrics


def demo():
    for source in SOURCES:
        day = date(2019 if source == SOURCES[0] else 2020, 1, 1)
        while day < date(2021, 1, 1):
            count = ((day.month * 3 + day.day) % 7) * (1 if source == SOURCES[0] else 2)
            rows = [",".join(COLUMNS)]
            confidence = "85" if source == SOURCES[0] else "h"
            for index in range(count):
                rows.append(f"{7 + index / 20},{80 + index / 20},{day},0345,"
                            f"{'Terra' if source == SOURCES[0] else 'N'},{confidence},12,D")
            partition("demo", source, day, ("\n".join(rows) + "\n").encode())
            day += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo")
    for name in ("sync", "build"):
        command = commands.add_parser(name)
        command.add_argument("--area", required=True)
        if name == "sync":
            command.add_argument("--start", required=True, type=date.fromisoformat)
            command.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    try:
        area = "demo" if args.command == "demo" or args.area == "demo" and args.command == "build" else area_value(args.area)
        if args.command == "sync":
            if args.start > args.end:
                raise ValueError("Start must be on or before end.")
            sync(area, args.start, args.end)
        if args.command == "demo":
            demo()
        table, metrics = monthly(area)
        root = workspace(area)
        atomic(root / "area.txt", lambda target: target.write_text(area, encoding="utf-8"))
        atomic(root / "harmonized" / "monthly.parquet", lambda target: table.to_parquet(target))
        atomic(root / "harmonized" / "monthly.csv", lambda target: table.to_csv(target))
        print(f"{area} | {len(table)} calendar months | {metrics}")
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()


