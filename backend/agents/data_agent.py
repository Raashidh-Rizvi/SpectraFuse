"""Data Query Agent: Retrieves verified observations and coverage from the Parquet datastore."""

from datetime import datetime
from typing import Any
from backend.agents.schemas import EvidenceItem, GetMonthlyActivityInput
from backend.agents.tools import get_monthly_activity


class DataQueryAgent:
    """Specialist agent responsible for querying monthly counts and raw partitions."""

    def query_monthly_summary(self, region: str, month: str) -> dict[str, Any]:
        """Fetch monthly record and return direct grounded summary with evidence."""
        params = GetMonthlyActivityInput(region=region, start_month=month, end_month=month)
        output = get_monthly_activity(params)

        if not output.records:
            evidence = EvidenceItem(
                source="local_parquet_archive",
                product=None,
                metric="hotspot_detections",
                value=None,
                status="unavailable",
                coverage="unavailable",
                calibration_applied=False,
            )
            answer = (
                f"Fire activity data for {month} is unavailable in the {region} dataset "
                "because daily satellite partitions are missing. Missing data is distinct "
                "from zero observed detections."
            )
            return {"answer": answer, "evidence": [evidence], "period": {"start": f"{month}-01", "end": f"{month}-28"}}

        rec = output.records[0]
        status = "observed" if rec.origin == "Observed by VIIRS" else "estimated" if "Estimated" in rec.origin else "unavailable"
        val = rec.harmonized

        if val is None:
            evidence = EvidenceItem(
                source="local_parquet_archive",
                product=None,
                metric="hotspot_detections",
                value=None,
                status="unavailable",
                coverage="unavailable",
                calibration_applied=False,
            )
            answer = (
                f"Active fire data for {month} is unavailable in {region}. "
                "Missing data represents missing daily observation partitions and is distinct from zero observed detections."
            )
            return {"answer": answer, "evidence": [evidence], "period": {"start": f"{month}-01", "end": f"{month}-28"}}

        # Format number with comma
        rounded = round(val)
        formatted_val = f"{rounded:,}" if val == rounded else f"{val:,.1f}"

        # Format month nicely (e.g., '2021-08' -> 'August 2021')
        try:
            dt = datetime.strptime(month, "%Y-%m")
            month_label = f"{dt.strftime('%B %Y')}"
        except Exception:
            month_label = month

        if status == "observed":
            evidence = EvidenceItem(
                source="local_parquet_archive",
                product="VIIRS_SNPP_SP",
                metric="hotspot_detections",
                value=rounded if val == rounded else round(val, 1),
                status="observed",
                coverage="complete",
                calibration_applied=False,
            )
            if val == 0:
                answer = (
                    f"{month_label} has an observed activity value of 0 detections on the VIIRS scale in {region}. "
                    "This month has complete processed coverage with zero recorded hotspots. "
                    "Detection counts describe observed hotspots, not burned area or unique wildfire events."
                )
            else:
                answer = (
                    f"{month_label} has a harmonized activity value of {formatted_val} detections on the VIIRS scale (Observed by VIIRS S-NPP). "
                    "This value is based on observed VIIRS S-NPP data and the month has complete processed coverage. "
                    "Detection counts describe observed hotspots, not burned area or unique wildfire events."
                )
        else:
            evidence = EvidenceItem(
                source="local_parquet_archive",
                product="MODIS_SP",
                metric="hotspot_detections",
                value=rounded if val == rounded else round(val, 1),
                status="estimated",
                coverage="complete",
                calibration_applied=True,
                metadata={"raw_modis": rec.MODIS_SP},
            )
            answer = (
                f"{month_label} has an estimated harmonized activity value of {formatted_val} detections on the VIIRS scale. "
                "VIIRS S-NPP was unavailable for this month, so SpectraFuse multiplied the complete MODIS total "
                "by the regional calibration factor. This estimate is subject to the historical holdout error."
            )

        return {
            "answer": answer,
            "evidence": [evidence],
            "period": {"start": f"{month}-01", "end": f"{month}-28"},
        }

    def query_peak_months(self, region: str, top_n: int = 5) -> dict[str, Any]:
        """Fetch and rank the highest harmonized active-fire months across the archive."""
        from backend.main import calendar_table

        table = calendar_table(region)
        if table.empty or "harmonized" not in table.columns:
            return {
                "answer": f"Historical fire activity records are unavailable for {region}.",
                "evidence": [],
                "period": None,
            }

        valid = table["harmonized"].dropna().astype(float).sort_values(ascending=False).head(top_n)
        if valid.empty:
            return {
                "answer": f"No valid fire activity months recorded for {region}.",
                "evidence": [],
                "period": None,
            }

        evidence_items: list[EvidenceItem] = []
        lines: list[str] = []
        for rank, (month_str, val) in enumerate(valid.items(), start=1):
            m_key = str(month_str)
            origin = table.loc[m_key, "origin"] if "origin" in table.columns else "Unknown"
            status = "observed" if origin == "Observed by VIIRS" else "estimated" if "Estimated" in str(origin) else "calculated"
            rounded = round(float(val))
            formatted_val = f"{rounded:,}"

            try:
                dt = datetime.strptime(str(month_str), "%Y-%m")
                month_label = dt.strftime("%B %Y")
            except Exception:
                month_label = str(month_str)

            lines.append(f"{rank}. {month_label} ({formatted_val} detections, {origin})")
            evidence_items.append(
                EvidenceItem(
                    source="local_parquet_archive",
                    product="harmonized",
                    metric="peak_month_detections",
                    value=rounded,
                    status=status,
                    coverage="complete",
                    metadata={"month": str(month_str), "rank": rank, "origin": str(origin)},
                )
            )

        answer = (
            f"The top {len(lines)} months with the highest harmonized fire activity in {region} across the 25-year archive are:\n\n"
            + "\n".join(lines)
            + "\n\nDetection counts describe observed hotspots, not burned area or unique wildfire events."
        )

        first_month = str(valid.index[0])
        return {
            "answer": answer,
            "evidence": evidence_items,
            "period": {"start": f"{first_month}-01", "end": f"{first_month}-28"},
        }

