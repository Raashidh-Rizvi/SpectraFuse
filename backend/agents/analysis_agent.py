"""Analysis Agent: Performs deterministic calculations, sensor comparisons, and seasonal anomalies."""

from datetime import datetime
from typing import Any
from backend.agents.schemas import (
    CalculationStep,
    CompareSensorsInput,
    EvidenceItem,
    GetCalibrationSummaryInput,
    GetSeasonalDepartureInput,
)
from backend.agents.tools import (
    compare_sensors,
    get_calibration_summary,
    get_seasonal_departure,
)


class AnalysisAgent:
    """Specialist agent responsible for statistical comparisons, anomalies, and calibration."""

    def analyze_seasonal_departure(self, region: str, year: int, month: int) -> dict[str, Any]:
        """Compute departure against historical expanding same-month medians."""
        params = GetSeasonalDepartureInput(region=region, year=year, month=month, sensor_basis="harmonized")
        result = get_seasonal_departure(params)

        if result.value is None or result.historical_median is None:
            answer = (
                f"Seasonal departure cannot be evaluated for {result.target_month} in {region} "
                "due to insufficient historical baseline (requires at least 2 earlier years of data for this calendar month)."
            )
            return {"answer": answer, "evidence": [], "calculations": [], "period": {"start": f"{result.target_month}-01", "end": f"{result.target_month}-28"}}

        val = result.value
        median = result.historical_median
        dep = result.departure_detections
        pct = result.departure_percent or 0.0

        diff_str = f"+{dep:,.1f}" if dep and dep > 0 else f"{dep:,.1f}" if dep else "0"
        pct_str = f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"

        evidence = EvidenceItem(
            source="historical_anomalies_analysis",
            product="harmonized",
            metric="seasonal_departure_percent",
            value=round(pct, 1),
            status="calculated",
            coverage="complete",
            metadata={"observed_value": val, "historical_median": median, "departure_detections": dep},
        )

        calc = CalculationStep(
            step="Seasonal departure percentage",
            formula=f"({val:.1f} - {median:.1f}) / {median:.1f} * 100",
            result=pct_str,
        )

        if pct > 25.0:
            assessment = "unusually elevated"
        elif pct < -25.0:
            assessment = "unusually low"
        else:
            assessment = "typical / near normal"

        try:
            dt = datetime.strptime(result.target_month, "%Y-%m")
            month_label = dt.strftime("%B %Y")
        except Exception:
            month_label = result.target_month

        answer = (
            f"{month_label} ({result.target_month}) was {assessment} compared with earlier same-month values in {region}. "
            f"The month recorded {val:,.1f} harmonized detections, representing a {pct_str} departure ({diff_str} detections) "
            f"relative to the historical median of {median:,.1f} detections (calculated across {result.prior_years_count} prior years). "
            "Detection counts describe observed hotspots, not burned area or unique wildfire events."
        )

        return {
            "answer": answer,
            "evidence": [evidence],
            "calculations": [calc],
            "period": {"start": f"{result.target_month}-01", "end": f"{result.target_month}-28"},
        }

    def compare_sensors_for_period(self, region: str, start_month: str, end_month: str) -> dict[str, Any]:
        """Compare MODIS and VIIRS S-NPP totals over matched months."""
        params = CompareSensorsInput(region=region, start_month=start_month, end_month=end_month)
        output = compare_sensors(params)

        matched = output.matched_months
        if matched == 0:
            answer = f"No matched paired months between MODIS and VIIRS were found for {start_month} to {end_month} in {region}."
            return {"answer": answer, "evidence": [], "calculations": [], "period": {"start": f"{start_month}-01", "end": f"{end_month}-28"}}

        modis_tot = output.summary.get("MODIS_SP", {}).get("total_detections", 0)
        viirs_tot = output.summary.get("VIIRS_SNPP_SP", {}).get("total_detections", 0)
        ratio = output.summary.get("ratio_viirs_to_modis")

        evidence = [
            EvidenceItem(
                source="paired_sensor_comparison",
                product="MODIS_SP",
                metric="total_detections",
                value=int(modis_tot),
                status="observed",
            ),
            EvidenceItem(
                source="paired_sensor_comparison",
                product="VIIRS_SNPP_SP",
                metric="total_detections",
                value=int(viirs_tot),
                status="observed",
            ),
        ]

        calculations = []
        if ratio is not None:
            calculations.append(
                CalculationStep(
                    step="VIIRS to MODIS detection ratio",
                    formula=f"{viirs_tot:,.0f} / {modis_tot:,.0f}",
                    result=round(ratio, 4),
                )
            )

        ratio_text = f" VIIRS detected approximately {ratio:.2f} times as many hotspots as MODIS." if ratio else ""
        answer = (
            f"Across {matched} matched months between {start_month} and {end_month} in {region}, "
            f"MODIS recorded {modis_tot:,.0f} total detections while VIIRS S-NPP recorded {viirs_tot:,.0f} detections.{ratio_text} "
            "VIIRS exhibits higher detection counts due to its finer 375 m pixel resolution compared to MODIS's 1 km resolution."
        )

        return {
            "answer": answer,
            "evidence": evidence,
            "calculations": calculations,
            "period": {"start": f"{start_month}-01", "end": f"{end_month}-28"},
        }

    def explain_calibration_factor(self, region: str) -> dict[str, Any]:
        """Explain the regional calibration multiplier and holdout validation error."""
        params = GetCalibrationSummaryInput(region=region)
        output = get_calibration_summary(params)

        factor = output.calibration_factor
        raw_mae = output.raw_mae
        adj_mae = output.adjusted_mae
        p90 = output.absolute_error_p90

        evidence = [
            EvidenceItem(
                source="regional_calibration_summary",
                product="MODIS_to_VIIRS",
                metric="calibration_factor",
                value=round(factor, 4) if factor else None,
                status="fitted",
                metadata={
                    "training_months": output.training_months,
                    "holdout_months": output.holdout_months,
                    "raw_mae": output.raw_mae,
                    "adjusted_mae": output.adjusted_mae,
                    "absolute_error_p90": output.absolute_error_p90,
                },
            )
        ]

        if factor is not None and adj_mae is not None and raw_mae is not None:
            answer = (
                f"The regional MODIS-to-VIIRS calibration factor for {region} is {factor:.4f}. "
                f"It was fitted over {output.training_months} earlier paired months and validated against a holdout of {output.holdout_months} later months. "
                f"Calibration reduced the regional holdout Mean Absolute Error from {raw_mae:.2f} to {adj_mae:.2f} detections per month, "
                f"with an empirical 90th percentile absolute error of {p90:.2f} detections. "
                "This multiplier scales complete MODIS months to the VIIRS scale when VIIRS observations are unavailable."
            )
        else:
            answer = f"Calibration factor details are unavailable for {region}."

        return {
            "answer": answer,
            "evidence": evidence,
            "calculations": [],
            "period": None,
        }
