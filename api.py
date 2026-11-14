from datetime import date

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from analytics import evaluate_overlap, historical_anomalies
from fire import SOURCES, area_value, monthly, workspace

app = FastAPI(title="FireScope API")
PILOT = "79.5,5.8,82,10"


def resolve(region):
    try:
        area = PILOT if region == "sri-lanka" else region if region == "demo" else area_value(region)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if not (workspace(area) / "area.txt").exists():
        raise HTTPException(404, "Dataset has not been built.")
    return area


def records(frame):
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def calendar_table(region, bounds=None):
    area = resolve(region)
    export = workspace(area) / "harmonized" / "monthly.parquet"
    frame = pd.read_parquet(export) if bounds is None and export.exists() else monthly(area, bounds)[0]
    frame.index = pd.Index(frame.index, dtype="str", name="month")
    return frame


@app.get("/api/fire/calendar")
def calendar(region: str = "sri-lanka", year: int | None = None):
    frame = calendar_table(region)
    if year is not None:
        frame = frame[frame.index.str.startswith(f"{year:04}-")]
    return {"region": region, "monthly_activity": records(frame.reset_index())}


@app.get("/api/fire/historical-trends")
def trends(region: str = "sri-lanka"):
    return calendar(region)


@app.get("/api/fire/anomalies")
def anomalies(region: str = "sri-lanka"):
    frame = calendar_table(region)
    return records(frame.join(historical_anomalies(frame.harmonized)).reset_index())


@app.get("/api/fire/sensor-comparison")
def comparison(region: str = "sri-lanka"):
    heldout, metrics = evaluate_overlap(calendar_table(region))
    return {"holdout": records(heldout.reset_index()), "metrics": records(metrics.reset_index())}


@app.get("/api/fire/hotspots")
def hotspots(day: date, region: str = "sri-lanka", source: str = SOURCES[0],
             limit: int = Query(1000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    if source not in SOURCES:
        raise HTTPException(422, "Unknown sensor product.")
    path = workspace(resolve(region)) / "processed" / source / f"{day}.parquet"
    if not path.exists():
        raise HTTPException(404, "Daily partition is unavailable.")
    frame = pd.read_parquet(path)
    return {"total": len(frame), "offset": offset, "detections": records(frame.iloc[offset:offset + limit])}


class Extent(BaseModel):
    region: str = "sri-lanka"
    bounds: str


@app.post("/api/fire/area-analysis")
def area_analysis(request: Extent):
    try:
        bounds = list(map(float, area_value(request.bounds).split(",")))
    except ValueError:
        raise HTTPException(422, "Use west,south,east,north bounds.") from None
    area = resolve(request.region)
    west, south, east, north = bounds
    if area not in ("world", "demo"):
        w, s, e, n = map(float, area.split(","))
        if not (w <= west < east <= e and s <= south < north <= n):
            raise HTTPException(422, "Bounds must lie within the downloaded extent.")
    return records(calendar_table(request.region, bounds).reset_index())


@app.get("/api/fire/download")
def download(region: str = "sri-lanka"):
    return Response(calendar_table(region).to_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=firescope-monthly.csv"})
