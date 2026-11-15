"""Controlled markdown documentation knowledge base for methodology explanations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOC_FILES = {
    "project_reference": ROOT / "docs" / "PROJECT_REFERENCE.md",
    "readme": ROOT / "README.md",
    "submission": ROOT / "SUBMISSION.md",
}


def read_doc_section(topic: str) -> str:
    """Retrieve verified documentation text for a methodology topic."""
    topic_clean = topic.lower().strip()

    # Load docs into memory safely
    content_map: dict[str, str] = {}
    for key, path in DOC_FILES.items():
        if path.exists():
            try:
                content_map[key] = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

    if any(k in topic_clean for k in ("sensor", "modis", "viirs", "noaa", "resolution", "terra", "aqua")):
        return (
            "MODIS operates on NASA's Terra (morning 10:30 AM descending) and Aqua (afternoon 1:30 PM ascending) satellites with a 1 km nominal nadir resolution. "
            "VIIRS operates on Suomi-NPP and NOAA-20 (afternoon 1:30 PM ascending) with a 375 m nadir resolution, maintaining smaller pixel footprint across the scan angle. "
            "NOAA-20 acts as an independent comparison series in SpectraFuse and does not enter the S-NPP calibration."
        )

    if any(k in topic_clean for k in ("calibration", "multiplier", "factor", "harmoniz")):
        return (
            "SpectraFuse fits a single regional multiplier using the ratio of total VIIRS detections to total "
            "MODIS detections over earlier paired months. It reserves the latest quarter (at least one month) "
            "as a temporal holdout to evaluate unscaled vs scaled Mean Absolute Error (MAE). "
            "The calendar uses observed VIIRS S-NPP where available, and scaled MODIS wherever MODIS has complete "
            "coverage and VIIRS is unavailable."
        )

    if any(k in topic_clean for k in ("detection", "burned area", "unique fire", "hotspot")):
        return (
            "Detection counts describe observed satellite thermal anomalies (hotspots) at acquisition time. "
            "They do not measure burned area, fire size, or the number of unique wildfire events. "
            "Multiple detections can record the same burning fire on consecutive satellite passes, "
            "and cloud cover or heavy smoke can obscure active fires."
        )

    if any(k in topic_clean for k in ("incomplete", "missing", "blank")):
        return (
            "A month contributes a sensor total only when every calendar day has a processed daily partition. "
            "A blank or missing cell means that daily satellite partitions are incomplete or unavailable for that month. "
            "Missing data is fundamentally distinct from zero observed detections."
        )

    # General reference overview excerpt
    ref = content_map.get("project_reference", "")
    if ref:
        lines = [line.strip() for line in ref.splitlines() if line.strip() and not line.startswith("#")]
        return " ".join(lines[:6])

    return "SpectraFuse harmonizes historical NASA FIRMS MODIS and VIIRS satellite active fire observations."
