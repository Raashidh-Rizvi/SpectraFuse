"""Export Agent: Generates authenticated CSV download references."""

from typing import Any, Literal
from backend.agents.schemas import GenerateExportReferenceInput
from backend.agents.tools import generate_export_reference


class ExportAgent:
    """Specialist agent responsible for preparing dataset exports and download links."""

    def prepare_export(
        self,
        region: str,
        year: int | None = None,
        export_type: Literal["monthly", "detections"] = "monthly",
        month: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Generate download reference for the requested dataset slice."""
        params = GenerateExportReferenceInput(
            region=region,
            year=year,
            export_type=export_type,
            month=month,
            source=source,
        )
        output = generate_export_reference(params)

        year_text = f"for {year}" if year else "for all available years"
        answer = (
            f"Here is your download reference for {region.title()} {output.metadata['type']} data {year_text}. "
            "Click the download button below to retrieve the exact CSV data."
        )

        return {
            "answer": answer,
            "downloads": [output.download],
            "period": {"start": f"{year}-01-01", "end": f"{year}-12-31"} if year else None,
        }
