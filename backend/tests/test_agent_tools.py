"""Unit tests for the SpectraFuse deterministic agent tool layer (Phase 2)."""

import pytest

from backend.agents.schemas import (
    CompareSensorsInput,
    GenerateExportReferenceInput,
    GetCalibrationSummaryInput,
    GetCoverageStatusInput,
    GetHoldoutMetricsInput,
    GetHotspotDetectionsInput,
    GetMapLayersActionInput,
    GetMonthlyActivityInput,
    GetSeasonalDepartureInput,
    ListRegionsInput,
)
from backend.agents.tools import (
    compare_sensors,
    execute_tool,
    generate_export_reference,
    get_calibration_summary,
    get_coverage_status,
    get_holdout_metrics,
    get_hotspot_detections,
    get_map_layers_action,
    get_monthly_activity,
    get_seasonal_departure,
    get_tool_definitions,
    list_regions,
)


def test_tc_t01_list_regions():
    """TC-T01: list_regions discovers valid regions including sri-lanka."""
    result = list_regions()
    region_ids = [r.id for r in result.regions]
    assert "sri-lanka" in region_ids
    sl = next(r for r in result.regions if r.id == "sri-lanka")
    assert sl.label == "Sri Lanka"
    assert sl.area == "79.5,5.8,82,10"


def test_tc_t02_get_monthly_activity_observed():
    """TC-T02: get_monthly_activity returns observed VIIRS for August 2021."""
    params = GetMonthlyActivityInput(
        region="sri-lanka",
        start_month="2021-08",
        end_month="2021-08",
    )
    result = get_monthly_activity(params)
    assert result.total_months == 1
    record = result.records[0]
    assert record.month == "2021-08"
    assert record.origin == "Observed by VIIRS"
    assert record.VIIRS_SNPP_SP is not None
    assert record.harmonized == record.VIIRS_SNPP_SP


def test_tc_t03_get_monthly_activity_estimated():
    """TC-T03: get_monthly_activity returns estimated MODIS when VIIRS unavailable."""
    params = GetMonthlyActivityInput(
        region="sri-lanka",
        start_month="2005-08",
        end_month="2005-08",
    )
    result = get_monthly_activity(params)
    assert result.total_months == 1
    record = result.records[0]
    assert record.month == "2005-08"
    assert record.origin == "Estimated from MODIS"
    assert record.MODIS_SP is not None
    assert record.VIIRS_SNPP_SP is None
    assert record.harmonized is not None


def test_tc_t04_get_monthly_activity_unavailable_period():
    """TC-T04: get_monthly_activity outside dataset returns 0 months, does not turn missing to 0."""
    params = GetMonthlyActivityInput(
        region="sri-lanka",
        start_month="1990-01",
        end_month="1990-02",
    )
    result = get_monthly_activity(params)
    assert result.total_months == 0
    assert result.records == []


def test_tc_t05_get_coverage_status_complete():
    """TC-T05: get_coverage_status verifies 100% complete daily partitions for 2021-08."""
    params = GetCoverageStatusInput(
        region="sri-lanka",
        product="VIIRS_SNPP_SP",
        start_date="2021-08-01",
        end_date="2021-08-31",
    )
    result = get_coverage_status(params)
    assert result.expected_days == 31
    assert result.present_days == 31
    assert result.missing_days == 0
    assert result.is_complete is True
    assert result.status == "Complete"


def test_tc_t06_get_seasonal_departure():
    """TC-T06: get_seasonal_departure computes departure from expanding historical median."""
    params = GetSeasonalDepartureInput(
        region="sri-lanka",
        year=2023,
        month=3,
        sensor_basis="harmonized",
    )
    result = get_seasonal_departure(params)
    assert result.target_month == "2023-03"
    assert result.value is not None
    assert result.historical_median is not None
    assert result.departure_detections is not None
    assert result.departure_percent is not None
    assert result.prior_years_count >= 2


def test_tc_t07_get_calibration_summary():
    """TC-T07: get_calibration_summary returns valid factor and holdout metrics."""
    params = GetCalibrationSummaryInput(region="sri-lanka")
    result = get_calibration_summary(params)
    assert result.calibration_factor is not None
    assert result.calibration_factor > 0
    assert result.training_months >= 3
    assert result.holdout_months >= 1
    assert result.raw_mae is not None
    assert result.adjusted_mae is not None
    assert result.adjusted_mae < result.raw_mae  # Calibration must improve MAE


def test_tc_t08_get_hotspot_detections():
    """TC-T08: get_hotspot_detections retrieves paginated records for a day."""
    # Test day with positive detections (2020-01-16 has 2 detections in Sri Lanka)
    params = GetHotspotDetectionsInput(
        region="sri-lanka",
        day="2020-01-16",
        product="MODIS_SP",
        limit=10,
    )
    result = get_hotspot_detections(params)
    assert result.day == "2020-01-16"
    assert result.product == "MODIS_SP"
    assert result.total == 2
    assert len(result.detections) == 2
    first = result.detections[0]
    assert 5.0 <= first.latitude <= 10.5
    assert 79.0 <= first.longitude <= 82.5
    assert first.satellite in ("Terra", "Aqua")

    # Test day with 0 detections (successful partition, 0 hotspots - distinct from missing data)
    zero_day_params = GetHotspotDetectionsInput(
        region="sri-lanka",
        day="2020-01-01",
        product="MODIS_SP",
        limit=10,
    )
    zero_result = get_hotspot_detections(zero_day_params)
    assert zero_result.total == 0
    assert len(zero_result.detections) == 0


def test_tc_t09_get_map_layers_action_valid():
    """TC-T09: get_map_layers_action validates parameters and returns UIAction payload."""
    params = GetMapLayersActionInput(
        region="sri-lanka",
        start_date="2022-03-01",
        end_date="2022-03-10",
        bbox="79.6,6.0,81.8,9.5",
    )
    result = get_map_layers_action(params)
    assert result.expected_days == 10
    assert result.ui_action.type == "show_on_map"
    assert result.ui_action.payload["region"] == "sri-lanka"
    assert result.ui_action.payload["start"] == "2022-03-01"
    assert result.ui_action.payload["end"] == "2022-03-10"


def test_tc_t10_get_map_layers_action_outside_extent():
    """TC-T10: get_map_layers_action rejects bounding boxes outside downloaded region."""
    params = GetMapLayersActionInput(
        region="sri-lanka",
        start_date="2022-03-01",
        end_date="2022-03-10",
        bbox="10,10,20,20",
    )
    with pytest.raises(ValueError, match="Bounds must lie within the downloaded extent"):
        get_map_layers_action(params)


def test_tc_t11_get_map_layers_action_date_range_limit():
    """TC-T11: get_map_layers_action rejects date spans exceeding 31 days."""
    params = GetMapLayersActionInput(
        region="sri-lanka",
        start_date="2022-01-01",
        end_date="2022-02-15",
    )
    with pytest.raises(ValueError, match="Select 1 to 31 inclusive UTC dates"):
        get_map_layers_action(params)


def test_tc_t12_generate_export_reference():
    """TC-T12: generate_export_reference creates valid download URLs."""
    monthly_ref = generate_export_reference(
        GenerateExportReferenceInput(region="sri-lanka", year=2022, export_type="monthly")
    )
    assert monthly_ref.download.url == "/api/fire/download?region=sri-lanka&year=2022"
    assert monthly_ref.download.format == "csv"

    detections_ref = generate_export_reference(
        GenerateExportReferenceInput(
            region="sri-lanka",
            export_type="detections",
            month="2022-03",
            source="MODIS_SP",
        )
    )
    assert "month=2022-03" in detections_ref.download.url
    assert "source=MODIS_SP" in detections_ref.download.url


def test_tool_registry_and_dynamic_execution():
    """Test dynamic tool dispatching via execute_tool and schema generation."""
    definitions = get_tool_definitions()
    assert len(definitions) == 10
    names = [d["function"]["name"] for d in definitions]
    assert "get_monthly_activity" in names
    assert "get_seasonal_departure" in names

    # Dynamic execution test
    result = execute_tool(
        "get_monthly_activity",
        {"region": "sri-lanka", "start_month": "2021-08", "end_month": "2021-08"},
    )
    assert isinstance(result, dict)
    assert result["total_months"] == 1
    assert result["records"][0]["origin"] == "Observed by VIIRS"
