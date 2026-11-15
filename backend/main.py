import calendar as cal
from datetime import date
from typing import Any, cast

import pandas as pd
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.analytics import evaluate_overlap, historical_anomalies
from backend.chat import ChatRequest, answer, evidence
from backend.agents.schemas import ChatRequest as AgentChatRequest
from backend.fire import (ROOT, PRODUCTS, SOURCES, area_value, calibration_factor,
                          calibration_split, data_directory, monthly, workspace)

from backend.grid import CELLS_PER_DEGREE, cell_indices

app = FastAPI(title="SpectraFuse API")
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
    if source not in PRODUCTS:
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
def download(region: str = "sri-lanka", year: int | None = None):
    frame = dashboard_frame(region)
    if year is not None:
        frame = frame[frame.index.str.startswith(f"{year:04}-")]
    return Response(frame.to_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=firescope-monthly.csv"})


def dashboard_frame(region):
    frame = calendar_table(region)
    source = PRODUCTS[-1]
    files = (workspace(resolve(region)) / "processed" / source).glob("*.parquet")
    totals = {}
    for path in files:
        month = path.stem[:7]
        days, count = totals.get(month, (0, 0))
        totals[month] = days + 1, count + pq.ParquetFile(path).metadata.num_rows
    frame[source] = pd.Series({month: count for month, (days, count) in totals.items()
                               if days == cal.monthrange(*map(int, month.split("-")))[1]}, dtype=float)
    for name in (*PRODUCTS, "harmonized"):
        frame[name + "_anomaly"] = historical_anomalies(frame[name])["Departure (%)"]
    heldout, metrics = evaluate_overlap(frame)
    if not metrics.empty:
        radius = float(cast(Any, metrics.loc["Calibrated MODIS", "Absolute error 90th percentile"]))
        estimated = frame.harmonized.where(frame.origin.eq("Estimated from MODIS"))
        frame["estimate_low"] = (estimated - radius).clip(lower=0)
        frame["estimate_high"] = estimated + radius
    return frame


@app.get("/api/fire/dashboard")
def dashboard(region: str = "sri-lanka"):
    return records(dashboard_frame(region).reset_index())


@app.get("/api/fire/monthly-hotspots")
def monthly_hotspots(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                     source: str = SOURCES[1], region: str = "sri-lanka", csv: bool = False, polygon: str | None = Query(None, max_length=4000)):
    if source not in PRODUCTS or month.startswith("0000"):
        raise HTTPException(422, "Use a valid month and sensor product.")
    path = workspace(resolve(region)) / "processed" / source
    files = sorted(path.glob(f"{month}-*.parquet"))
    columns = ["latitude", "longitude", "acq_date", "satellite", "confidence", "frp", "acquired_utc"]
    points = pd.concat((pd.read_parquet(file, columns=columns) for file in files), ignore_index=True) if files else pd.DataFrame(columns=columns)
    points = within_polygon(points, polygon)
    if csv:
        return Response(points.to_csv(index=False), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={source}-{month}.csv"})
    cells = points[["latitude", "longitude"]].round(2).groupby(["latitude", "longitude"]).size().rename("count").reset_index()
    return {"total": len(points), "days": len(files),
            "expected_days": cal.monthrange(*map(int, month.split("-")))[1], "cells": records(cells)}


def within_polygon(points, polygon):
    if polygon:
        import math
        try:
            vertices = [tuple(map(float, pair.split(","))) for pair in polygon.split(";")]
            if not 3 <= len(vertices) <= 100 or not all(
                len(pair) == 2 and math.isfinite(pair[0]) and math.isfinite(pair[1])
                and -180 <= pair[0] <= 180 and -90 <= pair[1] <= 90 for pair in vertices
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Provide 3 to 100 longitude,latitude vertices.") from None
        x, y = points.longitude, points.latitude
        inside = pd.Series(False, index=points.index)
        for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1]):
            if y1 != y2:
                inside ^= ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        points = points[inside]
    return points


@app.get("/api/fire/map-layers")
def map_layers(start: date, end: date, region: str = "sri-lanka",
               bbox: str | None = None,
               polygon: str | None = Query(None, max_length=4000)):
    expected = (end - start).days + 1
    if not 1 <= expected <= 31:
        raise HTTPException(422, "Select 1 to 31 inclusive UTC dates.")
    area = resolve(region)
    try:
        extent = area_value(bbox) if bbox else area
    except ValueError:
        raise HTTPException(422, "Use west,south,east,north bounds.") from None
    world = (-180, -90, 180, 90)
    west, south, east, north = world if extent in ("world", "demo") else map(float, extent.split(","))
    if area not in ("world", "demo"):
        w, s, e, n = map(float, area.split(","))
        if not (w <= west < east <= e and s <= south < north <= n):
            raise HTTPException(422, "Bounds must lie within the downloaded extent.")

    layers, points_by_source = {}, {}
    columns = ["latitude", "longitude"]
    for source in PRODUCTS:
        root = workspace(area) / "processed" / source
        files = sorted(path for path in root.glob("*.parquet") if str(start) <= path.stem <= str(end))
        points = pd.concat([pd.read_parquet(path, columns=columns) for path in files],
                           ignore_index=True) if files else pd.DataFrame(columns=columns, dtype=float)
        points = within_polygon(points[points.latitude.between(south, north)
                                      & points.longitude.between(west, east)], polygon)
        points_by_source[source] = points
        locations = points.groupby(columns).size().rename("count").reset_index()
        layers[source] = {"source": source, "days": len(files), "total": len(points) if files else None,
                          "status": "Complete" if len(files) == expected else "Partial" if files else "Unavailable",
                          "features": records(locations)}

    modis, viirs = SOURCES
    grid: dict[str, Any] = {"features": [], "total": None, "source": None, "days": 0, "status": "Unavailable",
                            "factor": None, "monthly_error_p90": None}
    source, scale = viirs, 1
    if layers[viirs]["days"] != expected:
        source = modis
        if layers[modis]["days"] == expected:
            table = calendar_table(region)
            scale = calibration_factor(calibration_split(table)[0])
            if scale is not None:
                _, metrics = evaluate_overlap(table)
                grid["monthly_error_p90"] = float(
                    cast(Any, metrics.loc["Calibrated MODIS", "Absolute error 90th percentile"]))
        else:
            scale = None
    if scale is not None:
        points = points_by_source[source]
        step = 1 / CELLS_PER_DEGREE
        cells = points.groupby(list(cell_indices(points))).size()
        grid.update(source=source, days=expected, total=len(points) * scale,
                    factor=scale if source == modis else None,
                    status="Estimated from MODIS" if source == modis else "Observed by VIIRS",
                    features=[{"south": y * step - 90, "west": x * step - 180,
                               "north": min(90, (y + 1) * step - 90),
                               "east": min(180, (x + 1) * step - 180),
                               "count": count * scale} for (y, x), count in cells.items()])
    layers["harmonized"] = grid
    return {"expected_days": expected, "provenance": "Synthetic demo" if area == "demo"
            else "NASA FIRMS Standard Processing", "layers": layers}


@app.get("/api/fire/regions")
def regions():
    labels = {PILOT: "Sri Lanka", "101,14,102,15": "Central Thailand"}
    items = []
    for marker in sorted(data_directory().glob("*/area.txt")):
        area = marker.read_text(encoding="utf-8").strip()
        if area != "demo":
            items.append({"id": "sri-lanka" if area == PILOT else area,
                          "label": labels.get(area, area), "area": area})
    return items


@app.post("/api/fire/chat")
def chat(request: AgentChatRequest):
    # Support legacy test call signature if passed directly
    if type(request).__name__ == "ChatRequest" and type(request).__module__ == "backend.chat":
        frame = dashboard_frame(request.region)
        if frame.empty:
            raise HTTPException(404, "This dataset has no monthly records.")
        _, metrics = evaluate_overlap(frame)
        data = evidence(frame, metrics, request.region)
        return {"answer": answer(request, data), "source": data["source"],
                "first_month": frame.index.min(), "last_month": frame.index.max()}

    from backend.agents.service import get_agent_service
    service = get_agent_service()
    return service.process_chat(request)


@app.get("/api/fire/chat/health")
def chat_health():
    from backend.agents.model_provider import FallbackModelProvider
    from backend.agents.service import get_agent_service
    service = get_agent_service()
    provider = service.orchestrator.provider
    if isinstance(provider, FallbackModelProvider):
        primary_name = provider.primary.__class__.__name__.lower().replace("modelprovider", "")
        fallback_name = provider.fallback.__class__.__name__.lower().replace("modelprovider", "")
        provider_name = f"{primary_name} (fallback: {fallback_name})"
    else:
        provider_name = provider.__class__.__name__.lower().replace("modelprovider", "")
    return {
        "status": "healthy",
        "provider": provider_name,
        "active_sessions": service.session_store.active_session_count(),
        "active_regions": ["sri-lanka", "demo", "101,14,102,15"],
        "stm_max_pairs": 4,
    }


@app.get("/api/fire/chat/capabilities")
def chat_capabilities():
    return {
        "supported_intents": [
            "monthly_summary",
            "trend_analysis",
            "anomaly_explanation",
            "sensor_comparison",
            "calibration_explanation",
            "hotspot_request",
            "data_export",
            "methodology_question",
            "coverage_question",
            "followup_explanation",
            "greeting",
            "gratitude",
            "help",
            "farewell",
            "acknowledgment",
            "unsupported_request",
        ],
        "deterministic_tools": [
            "list_regions",
            "get_monthly_activity",
            "get_coverage_status",
            "compare_sensors",
            "get_seasonal_departure",
            "get_calibration_summary",
            "get_holdout_metrics",
            "get_hotspot_detections",
            "get_map_layers_action",
            "generate_export_reference",
        ],
        "sensors": ["MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "harmonized"],
        "memory": {
            "stm_max_pairs": 4,
            "max_turns": 8,
            "ttl_seconds": 7200,
            "reference_resolution": True,
        },
    }


@app.delete("/api/fire/chat/session/{session_id}")
def clear_session(session_id: str):
    from backend.agents.service import get_agent_service
    service = get_agent_service()
    deleted = service.session_store.delete(session_id)
    return {"session_id": session_id, "deleted": deleted}


frontend = ROOT / "frontend" / "dist"
if (frontend / "index.html").is_file():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
