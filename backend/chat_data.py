"""Read-only, typed lookups over the selected dashboard archive."""

import calendar
from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.analytics import evaluate_overlap, historical_anomalies
from backend.fire import PRODUCTS, workspace

Product = Literal["MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "harmonized"]
MONTH = r"^[0-9]{4}-(0[1-9]|1[0-2])$"
LABELS = dict(zip((*PRODUCTS, "harmonized"), ("MODIS", "VIIRS S-NPP", "VIIRS NOAA-20", "Harmonized")))


class Lookup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["coverage", "monthly", "comparison", "anomaly", "calibration", "frp"]
    products: list[Product] = Field(default_factory=list, max_length=4)
    start_month: str | None = Field(default=None, pattern=MONTH)
    end_month: str | None = Field(default=None, pattern=MONTH)

    @model_validator(mode="after")
    def validate_scope(self):
        if any(month and month.startswith("0000") for month in (self.start_month, self.end_month)):
            raise ValueError("Use a valid calendar year.")
        if self.start_month and self.end_month and self.start_month > self.end_month:
            raise ValueError("The start month must precede or equal the end month.")
        if self.kind == "calibration":
            if self.products or self.start_month or self.end_month:
                raise ValueError("Calibration uses the region's saved monthly series and fixed holdout.")
        elif len(set(self.products)) != len(self.products) or not self.products:
            raise ValueError("Select distinct products for the lookup.")
        if self.kind == "comparison" and (len(self.products) < 2 or "harmonized" in self.products):
            raise ValueError("Compare at least two observed products.")
        if self.kind in ("coverage", "frp") and "harmonized" in self.products:
            raise ValueError("Daily partitions belong to observed products.")
        if self.kind == "frp" and (
            not self.start_month or not self.end_month
            or month_count(self.start_month, self.end_month) > 12
        ):
            raise ValueError("Specify up to 12 months for an FRP lookup.")
        return self


def month_count(first, last):
    y1, m1 = map(int, first.split("-"))
    y2, m2 = map(int, last.split("-"))
    return (y2 - y1) * 12 + m2 - m1 + 1


def month_end(month):
    year, number = map(int, month.split("-"))
    return date(year, number, calendar.monthrange(year, number)[1]).isoformat()


def partition_paths(area, product, lookup):
    paths = []
    for path in (workspace(area) / "processed" / product).glob("????-??-??.parquet"):
        month = path.stem[:7]
        if (lookup.start_month and month < lookup.start_month) or (lookup.end_month and month > lookup.end_month):
            continue
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        paths.append((day.isoformat(), path))
    return sorted(paths)


def citation(product, basis, dates, lookup):
    first, last = (dates[0], dates[-1]) if len(dates) else (None, None)
    start = lookup.start_month or (first[:7] if first else None)
    end = lookup.end_month or (last[:7] if last else None)
    expected = None
    if start and end:
        if basis == "daily_partitions":
            # Unspecified bounds stop at the first or last downloaded day.
            first_day = lookup.start_month + "-01" if lookup.start_month else first
            last_day = month_end(lookup.end_month) if lookup.end_month else last
            expected = (date.fromisoformat(last_day) - date.fromisoformat(first_day)).days + 1
        else:
            expected = month_count(start, end)
    return {"product": product, "basis": basis, "first": first, "last": last,
            "available": len(dates), "expected": expected, "start_month": start, "end_month": end}


def frp_summary(paths):
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    count = 0
    total = 0.0
    minimum, maximum = float("inf"), -float("inf")
    for _, path in paths:
        with pq.ParquetFile(path) as partition:
            values = partition.read(columns=["frp"])["frp"]
        values = pc.filter(values, pc.is_finite(values))
        if len(values):
            bounds = pc.min_max(values).as_py()
            count += len(values)
            total += pc.sum(values).as_py()
            minimum = min(minimum, bounds["min"])
            maximum = max(maximum, bounds["max"])
    return {"detections_with_frp": count, "units": "MW per detection",
            "mean": total / count if count else None,
            "minimum": minimum if count else None, "maximum": maximum if count else None}


def monthly_summary(series, include_rows=True):
    if series.empty:
        return {"total": None, "mean": None, "median": None, "minimum": None, "maximum": None}
    result = {"total": float(series.sum()), "mean": float(series.mean()), "median": float(series.median()),
              "minimum": {"month": series.idxmin(), "value": float(series.min())},
              "maximum": {"month": series.idxmax(), "value": float(series.max())}}
    if include_rows and len(series) <= 36:
        result["monthly_values"] = series.to_dict()
    elif include_rows:
        yearly = series.groupby(series.index.str[:4]).agg(["size", "sum", "mean"])
        result["annual"] = yearly.rename(columns={"size": "months", "sum": "total"}).to_dict("index")
        result["largest_months"] = series.nlargest(5).to_dict()
        result["smallest_months"] = series.nsmallest(5).to_dict()
    return result


def retrieve(lookup, area, get_frame):
    if lookup.kind in ("coverage", "frp"):
        results = []
        for product in lookup.products:
            paths = partition_paths(area, product, lookup)
            result = {"citation": citation(product, "daily_partitions", [day for day, _ in paths], lookup)}
            if lookup.kind == "frp":
                result.update(frp_summary(paths))
            results.append(result)
        return results

    frame = get_frame(PRODUCTS[-1] in lookup.products)
    if lookup.kind == "calibration":
        holdout, metrics = evaluate_overlap(frame)
        return [{"citation": citation("MODIS_SP / VIIRS_SNPP_SP", "holdout_months", holdout.index, lookup),
                 "units": "detections per UTC month for errors and bias",
                 "metrics": metrics.astype(object).where(metrics.notna(), None).to_dict("index")}]

    products = lookup.products
    if lookup.kind == "comparison":
        matched = frame.loc[lookup.start_month:lookup.end_month, products].dropna()
        return [{"citation": citation(product, "matched_months", matched.index, lookup),
                 "units": "detections per UTC month", **monthly_summary(matched[product], include_rows=False)}
                for product in products]

    results = []
    for product in products:
        if lookup.kind == "anomaly":
            series = historical_anomalies(frame[product])["Departure (%)"]
            values = series.loc[lookup.start_month:lookup.end_month].dropna()
            largest = values.loc[values.abs().nlargest(5).index]
            results.append({"citation": citation(product, "anomaly_months", values.index, lookup),
                            "units": "percent departure from the earlier same-month median",
                            "largest_absolute_departures": largest.to_dict(),
                            "monthly_departures": values.to_dict() if len(values) <= 36 else None})
            continue
        values = frame.loc[lookup.start_month:lookup.end_month, product].dropna()
        result = {"citation": citation(product, "complete_months", values.index, lookup),
                  "units": "detections per UTC month", **monthly_summary(values)}
        if product == "harmonized":
            origins = frame.loc[values.index, "origin"]
            result["months_by_origin"] = origins.value_counts().to_dict()
            if len(origins) <= 36:
                result["origin_by_month"] = origins.to_dict()
        results.append(result)
    return results
