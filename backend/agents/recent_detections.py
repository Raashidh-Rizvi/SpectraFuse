"""Recent satellite detections from stored daily partitions."""

from datetime import date, timedelta

import pandas as pd

from backend.agents.schemas import EvidenceItem
from backend.fire import PRODUCTS, workspace
from backend.grid import CELLS_PER_DEGREE, cell_indices


def recent_detections(region, question, start=None, end=None, bbox=None):
    from backend.main import resolve

    root = workspace(resolve(region)) / "processed"
    if start and end and (end < start or (end - start).days >= 31):
        return {"answer": "Choose a date range of up to 31 days."}
    lines, evidence = [], []
    recurring = any(word in question for word in ("repeat", "multiple days", "recurr", "same location"))
    for product in PRODUCTS:
        if "modis" in question and "viirs" not in question and product != "MODIS_SP":
            continue
        if "viirs" in question and "modis" not in question and not product.startswith("VIIRS"):
            continue
        partitions = sorted((root / product).glob("????-??-??.parquet"), reverse=True)
        if not partitions:
            lines.append(f"- {product}: no archived days.")
            continue
        latest = date.fromisoformat(partitions[0].stem)
        last = end or latest
        first = start or last - timedelta(days=30)
        count, covered, recent = 0, 0, []
        cell_days = {}
        for path in partitions:
            day = date.fromisoformat(path.stem)
            if day > last:
                continue
            if day < first:
                break
            frame = pd.read_parquet(path, columns=["acquired_utc", "latitude", "longitude"])
            covered += 1
            if bbox:
                west, south, east, north = bbox
                frame = frame[frame.longitude.between(west, east) & frame.latitude.between(south, north)]
            count += len(frame)
            if recurring and not frame.empty:
                for cell in set(zip(*cell_indices(frame))):
                    cell_days[cell] = cell_days.get(cell, 0) + 1
            if len(recent) < 3:
                recent.extend(frame.dropna(subset=["acquired_utc"]).sort_values(
                    "acquired_utc", ascending=False).head(3 - len(recent)).to_dict("records"))
        summary = f"- {product}: {count:,} detections" if covered else f"- {product}: data unavailable"
        lines.append(f"{summary} across {covered}/{(last-first).days+1} archived days "
                     f"({first} to {last}). Latest archived day: {latest}.")
        lines.extend(f"  - {row['acquired_utc'].isoformat()} UTC at "
                     f"{row['latitude']:.4f}, {row['longitude']:.4f}." for row in recent)
        if recurring:
            ranked = sorted(cell_days.items(), key=lambda item: (-item[1], item[0]))
            repeated = [
                {"latitude": (y + 0.5) / CELLS_PER_DEGREE - 90,
                 "longitude": (x + 0.5) / CELLS_PER_DEGREE - 180, "days": days}
                for (y, x), days in ranked[:3] if days > 1
            ]
            if repeated:
                lines.append("  - Repeated detections by approximate 5 km cell center: " + ", ".join(
                    f"{cell['latitude']:.3f}, {cell['longitude']:.3f} ({cell['days']} days)"
                    for cell in repeated) + ".")
            elif covered:
                lines.append("  - No grid cell had detections on multiple covered days.")
        else:
            repeated = []
        evidence.append(EvidenceItem(source="local_parquet_archive", product=product,
            metric="detections_in_covered_days", value=count if covered else None,
            status="observed" if covered else "unavailable",
            metadata={"latest_archived_day": str(latest), "covered_days": covered, "repeated_cells": repeated}))
    label = " within the requested coordinates" if bbox else ""
    return {"answer": f"**Archived hotspot detections for {region}{label}**\n\n" +
            "\n".join(lines) + "\n\nAcquisition time records when a satellite detected a hotspot. "
            "Current fire status requires incident or field confirmation.", "evidence": evidence}
