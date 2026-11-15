"""Map Agent: Interprets geographic requests, validates spatial bounds, and emits UI actions."""

from typing import Any
from backend.agents.schemas import EvidenceItem, GetMapLayersActionInput, UIAction
from backend.agents.tools import get_map_layers_action


class MapAgent:
    """Specialist agent responsible for geospatial queries, extent validation, and map actions."""

    def prepare_map_view(
        self,
        region: str,
        start_date: str,
        end_date: str,
        bbox: str | None = None,
        polygon: str | None = None,
    ) -> dict[str, Any]:
        """Validate geographic bounds and generate show_on_map action for React."""
        try:
            params = GetMapLayersActionInput(
                region=region,
                start_date=start_date,
                end_date=end_date,
                bbox=bbox,
                polygon=polygon,
            )
            output = get_map_layers_action(params)
        except Exception as err:
            return {
                "answer": f"Cannot display map: {err}. Please select inclusive dates up to 31 days within the downloaded extent.",
                "evidence": [],
                "ui_actions": [],
                "period": {"start": start_date, "end": end_date},
            }

        evidence = [
            EvidenceItem(
                source="map_layers_service",
                product="all_active_sensors",
                metric="expected_days",
                value=output.expected_days,
                status="verified",
                metadata={"layers": output.layers_summary},
            )
        ]

        bbox_desc = f" for bounding box [{bbox}]" if bbox else ""
        answer = (
            f"Displaying hotspot map for {region}{bbox_desc} from {start_date} to {end_date} ({output.expected_days} days). "
            "The map layers have been updated to show recorded satellite coordinates and the ~5 km harmonized grid. "
            "Detection counts describe observed thermal hotspots, not burned area or unique wildfire events."
        )

        return {
            "answer": answer,
            "evidence": evidence,
            "ui_actions": [output.ui_action],
            "period": {"start": start_date, "end": end_date},
        }
