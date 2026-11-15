"""Deterministic tool layer wrapping SpectraFuse domain functions and FastAPI services."""

import calendar as cal
from datetime import date, datetime
from typing import Any, Callable, cast

import pandas as pd
from fastapi import HTTPException

from backend.analytics import evaluate_overlap, historical_anomalies
from backend.fire import (
    PRODUCTS,
    SOURCES,
    area_value,
    calibration_factor,
    calibration_split,
    data_directory,
    workspace,
)
from backend.main import (
    calendar_table,
    dashboard_frame,
    map_layers,
    records,
    resolve,
)
from backend.agents.schemas import (
    CalibrationSummaryOutput,
    CompareSensorsInput,
    CoverageStatusOutput,
    DownloadItem,
    GenerateExportReferenceInput,
    GenerateExportReferenceOutput,
    GetCalibrationSummaryInput,
    GetCoverageStatusInput,
    GetHoldoutMetricsInput,
    GetHotspotDetectionsInput,
    GetHotspotDetectionsOutput,
    GetMapLayersActionInput,
    GetMonthlyActivityInput,
    GetMonthlyActivityOutput,
    GetSeasonalDepartureInput,
    HoldoutMetricsOutput,
    HotspotItem,
    ListRegionsInput,
    ListRegionsOutput,
    MapLayersActionOutput,
    MonthlyRecord,
    RegionItem,
    SeasonalDepartureOutput,
    SensorComparisonOutput,
    UIAction,
)


# ---------------------------------------------------------------------------
# Helper Casts & Formatting
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float:
    """Safely cast scalar/pandas value to native Python float."""
    return float(cast(Any, val))


def _to_optional_float(val: Any) -> float | None:
    """Safely cast scalar/pandas value or None/NaN to optional Python float."""
    if val is None or pd.isna(val):
        return None
    return float(cast(Any, val))


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def list_regions(params: ListRegionsInput | None = None) -> ListRegionsOutput:
    """Discover available geographic datasets in the local archive."""
    labels = {"79.5,5.8,82,10": "Sri Lanka", "101,14,102,15": "Central Thailand"}
    items: list[RegionItem] = []
    for marker in sorted(data_directory().glob("*/area.txt")):
        area = marker.read_text(encoding="utf-8").strip()
        if area != "demo":
            region_id = "sri-lanka" if area == "79.5,5.8,82,10" else area
            items.append(RegionItem(id=region_id, label=labels.get(area, area), area=area))
    return ListRegionsOutput(regions=items)


# Simple module-level cache for dashboard_frame to avoid rescanning 3,000+ NOAA-20 parquet files
_DASHBOARD_FRAME_CACHE: dict[str, pd.DataFrame] = {}


def get_cached_dashboard_frame(region: str) -> pd.DataFrame:
    """Retrieve or compute cached dashboard frame with all sensors and anomalies."""
    if region not in _DASHBOARD_FRAME_CACHE:
        _DASHBOARD_FRAME_CACHE[region] = dashboard_frame(region)
    return _DASHBOARD_FRAME_CACHE[region]


def get_monthly_activity(params: GetMonthlyActivityInput) -> GetMonthlyActivityOutput:
    """Retrieve monthly hotspot counts and provenance for a region and period."""
    # Fast path: use calendar_table directly unless NOAA20 is explicitly requested
    if params.sensor_basis == "VIIRS_NOAA20_SP":
        frame = get_cached_dashboard_frame(params.region)
    else:
        frame = calendar_table(params.region)

    if frame.empty:
        return GetMonthlyActivityOutput(region=params.region, records=[], total_months=0)

    if params.start_month:
        frame = frame[frame.index >= params.start_month]
    if params.end_month:
        frame = frame[frame.index <= params.end_month]

    monthly_records: list[MonthlyRecord] = []
    for month_str, row in frame.iterrows():
        modis = float(row["MODIS_SP"]) if pd.notna(row.get("MODIS_SP")) else None
        viirs = float(row["VIIRS_SNPP_SP"]) if pd.notna(row.get("VIIRS_SNPP_SP")) else None
        noaa = float(row["VIIRS_NOAA20_SP"]) if "VIIRS_NOAA20_SP" in row and pd.notna(row.get("VIIRS_NOAA20_SP")) else None
        harmonized = float(row["harmonized"]) if pd.notna(row.get("harmonized")) else None
        origin = str(row.get("origin", "Unavailable"))

        monthly_records.append(
            MonthlyRecord(
                month=str(month_str),
                MODIS_SP=modis,
                VIIRS_SNPP_SP=viirs,
                VIIRS_NOAA20_SP=noaa,
                harmonized=harmonized,
                origin=origin,
            )
        )

    return GetMonthlyActivityOutput(
        region=params.region,
        records=monthly_records,
        total_months=len(monthly_records),
    )


def get_coverage_status(params: GetCoverageStatusInput) -> CoverageStatusOutput:
    """Check daily partition completeness for a sensor over a UTC date range."""
    start_dt = date.fromisoformat(params.start_date)
    end_dt = date.fromisoformat(params.end_date)
    if start_dt > end_dt:
        raise ValueError("start_date must be on or before end_date.")

    expected_days = (end_dt - start_dt).days + 1
    area = resolve(params.region)
    product_dir = workspace(area) / "processed" / params.product

    present_files = sorted(
        path
        for path in product_dir.glob("*.parquet")
        if params.start_date <= path.stem <= params.end_date
    ) if product_dir.exists() else []

    present_count = len(present_files)
    missing_count = expected_days - present_count
    is_complete = present_count == expected_days

    status = "Complete" if is_complete else "Partial" if present_count > 0 else "Unavailable"

    return CoverageStatusOutput(
        region=params.region,
        product=params.product,
        start_date=params.start_date,
        end_date=params.end_date,
        expected_days=expected_days,
        present_days=present_count,
        missing_days=missing_count,
        is_complete=is_complete,
        status=status,
    )


def compare_sensors(params: CompareSensorsInput) -> SensorComparisonOutput:
    """Compare multiple satellite sensors over matched months with complete coverage."""
    # Fast path if comparing standard sources (MODIS and VIIRS S-NPP)
    if set(params.sensors).issubset(set(SOURCES)):
        frame = calendar_table(params.region)
    else:
        frame = get_cached_dashboard_frame(params.region)
    if params.start_month:
        frame = frame[frame.index >= params.start_month]
    if params.end_month:
        frame = frame[frame.index <= params.end_month]

    valid_sensors = [s for s in params.sensors if s in frame.columns]
    matched = frame.dropna(subset=valid_sensors)

    summary: dict[str, Any] = {}
    for s in valid_sensors:
        summary[s] = {
            "total_detections": float(matched[s].sum()),
            "mean_monthly_detections": float(matched[s].mean()) if len(matched) else 0.0,
            "min": float(matched[s].min()) if len(matched) else 0.0,
            "max": float(matched[s].max()) if len(matched) else 0.0,
        }

    # If MODIS and VIIRS S-NPP are both compared, compute ratio
    if "MODIS_SP" in valid_sensors and "VIIRS_SNPP_SP" in valid_sensors and summary["MODIS_SP"]["total_detections"] > 0:
        ratio = summary["VIIRS_SNPP_SP"]["total_detections"] / summary["MODIS_SP"]["total_detections"]
        summary["ratio_viirs_to_modis"] = float(round(ratio, 4))

    heldout, metrics = evaluate_overlap(calendar_table(params.region))
    holdout_summary = None
    if not metrics.empty and "Calibrated MODIS" in metrics.index:
        holdout_summary = {
            "calibrated_modis_mae": _to_float(metrics.loc["Calibrated MODIS", "MAE"]),
            "raw_modis_mae": _to_float(metrics.loc["Raw MODIS", "MAE"]),
            "absolute_error_p90": _to_float(metrics.loc["Calibrated MODIS", "Absolute error 90th percentile"]),
        }

    return SensorComparisonOutput(
        region=params.region,
        matched_months=len(matched),
        summary=summary,
        holdout_mae=holdout_summary,
    )


def get_seasonal_departure(params: GetSeasonalDepartureInput) -> SeasonalDepartureOutput:
    """Compute seasonal departure from expanding historical same-month medians."""
    target_month_str = f"{params.year:04d}-{params.month:02d}"
    frame = calendar_table(params.region)

    basis = params.sensor_basis
    if basis not in frame.columns:
        basis = "harmonized"

    series = frame[basis].dropna()
    anomalies = historical_anomalies(series)

    if target_month_str not in series.index:
        return SeasonalDepartureOutput(
            region=params.region,
            target_month=target_month_str,
            value=None,
            historical_median=None,
            departure_detections=None,
            departure_percent=None,
            prior_years_count=0,
            status="Unavailable",
        )

    val = _to_float(series.loc[target_month_str])
    hist_median = anomalies.loc[target_month_str, "Historical median"]
    dep_det = anomalies.loc[target_month_str, "Departure (detections)"]
    dep_pct = anomalies.loc[target_month_str, "Departure (%)"]

    # Count earlier years for this calendar month
    month_suffix = f"-{params.month:02d}"
    prior_count = len(series[(series.index < target_month_str) & series.index.str.endswith(month_suffix)])

    return SeasonalDepartureOutput(
        region=params.region,
        target_month=target_month_str,
        value=val,
        historical_median=_to_optional_float(hist_median),
        departure_detections=_to_optional_float(dep_det),
        departure_percent=_to_optional_float(dep_pct),
        prior_years_count=prior_count,
        status="Complete" if prior_count >= 2 else "Insufficient History (< 2 prior years)",
    )


def get_calibration_summary(params: GetCalibrationSummaryInput) -> CalibrationSummaryOutput:
    """Retrieve regional MODIS-to-VIIRS calibration factor and holdout metrics."""
    table = calendar_table(params.region)
    train, heldout = calibration_split(table)
    factor = calibration_factor(train)
    _, metrics = evaluate_overlap(table)

    raw_mae = None
    adj_mae = None
    p90 = None
    if not metrics.empty and "Calibrated MODIS" in metrics.index:
        raw_mae = _to_float(metrics.loc["Raw MODIS", "MAE"])
        adj_mae = _to_float(metrics.loc["Calibrated MODIS", "MAE"])
        p90 = _to_float(metrics.loc["Calibrated MODIS", "Absolute error 90th percentile"])

    return CalibrationSummaryOutput(
        region=params.region,
        calibration_factor=factor,
        paired_months=len(train) + len(heldout),
        training_months=len(train),
        holdout_months=len(heldout),
        raw_mae=raw_mae,
        adjusted_mae=adj_mae,
        absolute_error_p90=p90,
    )


def get_holdout_metrics(params: GetHoldoutMetricsInput) -> HoldoutMetricsOutput:
    """Retrieve full holdout validation comparison metrics."""
    table = calendar_table(params.region)
    _, metrics = evaluate_overlap(table)
    return HoldoutMetricsOutput(
        region=params.region,
        metrics=records(metrics.reset_index()) if not metrics.empty else [],
    )


def get_hotspot_detections(params: GetHotspotDetectionsInput) -> GetHotspotDetectionsOutput:
    """Retrieve paginated individual satellite fire observations for a specific day."""
    if params.product not in PRODUCTS:
        raise ValueError(f"Unknown sensor product: {params.product}. Use one of {PRODUCTS}.")

    area = resolve(params.region)
    path = workspace(area) / "processed" / params.product / f"{params.day}.parquet"
    if not path.exists():
        raise ValueError(f"Daily partition {params.day} is unavailable for {params.product} in {params.region}.")

    frame = pd.read_parquet(path)
    if params.bbox:
        try:
            w, s, e, n = map(float, area_value(params.bbox).split(","))
            frame = frame[frame.latitude.between(s, n) & frame.longitude.between(w, e)]
        except ValueError as err:
            raise ValueError(f"Invalid bbox parameter: {err}") from None

    total = len(frame)
    sliced = frame.iloc[params.offset : params.offset + params.limit]

    items: list[HotspotItem] = []
    for _, row in sliced.iterrows():
        items.append(
            HotspotItem(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                acq_date=str(row["acq_date"]),
                satellite=str(row.get("satellite", "")),
                confidence=row.get("confidence_class") or row.get("confidence"),
                frp=float(row["frp"]) if pd.notna(row.get("frp")) else None,
                acquired_utc=row["acquired_utc"].isoformat() if pd.notna(row.get("acquired_utc")) else None,
            )
        )

    return GetHotspotDetectionsOutput(
        region=params.region,
        day=params.day,
        product=params.product,
        total=total,
        offset=params.offset,
        limit=params.limit,
        detections=items,
    )


def get_map_layers_action(params: GetMapLayersActionInput) -> MapLayersActionOutput:
    """Validate spatial boundaries and generate map layer data with show_on_map action."""
    start_dt = date.fromisoformat(params.start_date)
    end_dt = date.fromisoformat(params.end_date)
    expected_days = (end_dt - start_dt).days + 1
    if not 1 <= expected_days <= 31:
        raise ValueError("Select 1 to 31 inclusive UTC dates.")

    area = resolve(params.region)
    try:
        extent = area_value(params.bbox) if params.bbox else area
    except ValueError as err:
        raise ValueError(f"Use west,south,east,north bounds: {err}") from None

    if area not in ("world", "demo"):
        w, s, e, n = map(float, area.split(","))
        west, south, east, north = map(float, extent.split(","))
        if not (w <= west < east <= e and s <= south < north <= n):
            raise ValueError("Bounds must lie within the downloaded extent.")

    layers_data = map_layers(
        start=start_dt,
        end=end_dt,
        region=params.region,
        bbox=params.bbox,
        polygon=params.polygon,
    )

    layers_summary = {
        k: {
            "source": v.get("source"),
            "status": v.get("status"),
            "days": v.get("days"),
            "total": v.get("total"),
        }
        for k, v in layers_data.get("layers", {}).items()
    }

    action = UIAction(
        type="show_on_map",
        payload={
            "region": params.region,
            "start": params.start_date,
            "end": params.end_date,
            "layers": params.enabled_layers,
            "bbox": params.bbox,
            "polygon": params.polygon,
        },
    )

    return MapLayersActionOutput(
        region=params.region,
        start_date=params.start_date,
        end_date=params.end_date,
        expected_days=expected_days,
        layers_summary=layers_summary,
        ui_action=action,
    )


def generate_export_reference(params: GenerateExportReferenceInput) -> GenerateExportReferenceOutput:
    """Generate authenticated download item for exact query CSV export."""
    if params.export_type == "monthly":
        url = f"/api/fire/download?region={params.region}"
        if params.year is not None:
            url += f"&year={params.year}"
        label = f"Download {params.region.title()} {params.year or 'All Years'} Monthly Summary (CSV)"
        metadata = {"region": params.region, "year": params.year, "type": "monthly"}
    else:
        if not params.month:
            raise ValueError("month is required when export_type is 'detections'.")
        source = params.source or "VIIRS_SNPP_SP"
        url = f"/api/fire/monthly-hotspots?region={params.region}&month={params.month}&source={source}&csv=true"
        label = f"Download {params.region.title()} {params.month} {source} Detections (CSV)"
        metadata = {"region": params.region, "month": params.month, "source": source, "type": "detections"}

    download = DownloadItem(label=label, url=url, format="csv")
    return GenerateExportReferenceOutput(download=download, metadata=metadata)


# ---------------------------------------------------------------------------
# Tool Registry & Dispatch
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, tuple[Callable[..., Any], type]] = {
    "list_regions": (list_regions, ListRegionsInput),
    "get_monthly_activity": (get_monthly_activity, GetMonthlyActivityInput),
    "get_coverage_status": (get_coverage_status, GetCoverageStatusInput),
    "compare_sensors": (compare_sensors, CompareSensorsInput),
    "get_seasonal_departure": (get_seasonal_departure, GetSeasonalDepartureInput),
    "get_calibration_summary": (get_calibration_summary, GetCalibrationSummaryInput),
    "get_holdout_metrics": (get_holdout_metrics, GetHoldoutMetricsInput),
    "get_hotspot_detections": (get_hotspot_detections, GetHotspotDetectionsInput),
    "get_map_layers_action": (get_map_layers_action, GetMapLayersActionInput),
    "generate_export_reference": (generate_export_reference, GenerateExportReferenceInput),
}


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return JSON schema definitions for function-calling models (Groq, OpenAI, Gemini)."""
    definitions = []
    for name, (_, input_model) in TOOL_REGISTRY.items():
        schema = input_model.model_json_schema()
        doc = input_model.__doc__ or name
        definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": doc.strip(),
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            },
        })
    return definitions


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool deterministically with argument validation."""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: '{name}'. Available: {list(TOOL_REGISTRY.keys())}")

    fn, input_model = TOOL_REGISTRY[name]
    parsed_input = input_model(**arguments)
    result = fn(parsed_input)

    # Convert Pydantic result to pure dict
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result
