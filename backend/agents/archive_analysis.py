"""Deterministic period comparisons over the dashboard archive."""

import re

import pandas as pd

from backend.analytics import historical_anomalies
from backend.agents.schemas import EvidenceItem


def archive_analysis(region, question, selected_year, month_names):
    from backend.main import dashboard_frame

    frame = dashboard_frame(region).sort_index()
    years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", question)))
    span = re.search(r"\b((?:19|20)\d{2})\s*(?:to|through|[–-])\s*((?:19|20)\d{2})\b", question)
    if span:
        years = sorted(set(years) | {str(y) for y in range(int(span[1]), int(span[2]) + 1)})
    dates = []
    names = "|".join(month_names)
    for match in re.finditer(
        rf"\b(?:(?P<iso>(?:19|20)\d{{2}}-(?:0[1-9]|1[0-2]))|(?P<name>{names})(?:\s+(?P<year>(?:19|20)\d{{2}}))?)\b",
        question,
    ):
        if match["iso"]:
            dates.append(match["iso"])
        else:
            targets = [match["year"]] if match["year"] else years or [selected_year]
            if not all(y and y.isdigit() for y in targets):
                return {"answer": "Which year should I use for the named month?"}
            dates.extend(f"{y}-{month_names[match['name']]:02d}" for y in targets)

    if re.search(r"year.by.year|all years|whole archive", question):
        selected_year = None
    periods = list(dict.fromkeys(dates or years or (
        [selected_year] if selected_year and selected_year.isdigit() else list(frame.index.str[:4].unique())
    )))
    before_after = "harmoniz" in question and any(w in question for w in ("before", "after", "raw"))
    products = []
    if "modis" in question or before_after:
        products.append("MODIS_SP")
    if ("viirs" in question and "noaa" not in question) or "npp" in question:
        products.append("VIIRS_SNPP_SP")
    if "noaa" in question:
        products.append("VIIRS_NOAA20_SP")
    if not products or "harmoniz" in question:
        products.append("harmonized")
    observed_only = re.search(r"observed.only|only observed|without estimates|exclude estimates", question)
    if observed_only:
        products = [p for p in products if p != "harmonized"]
        if not products:
            products = ["VIIRS_SNPP_SP"]
    lines, evidence = [], []
    if observed_only:
        lines.append("Observed satellite counts only. MODIS-derived estimates are excluded.")
    for product in products:
        lines.append(f"**{product} — detections in {region}**")
        totals = []
        for period in periods:
            months = [period] if len(period) == 7 else [f"{period}-{m:02d}" for m in range(1, 13)]
            paired = frame.reindex(months)[products].dropna() if len(products) > 1 else None
            series = paired[product] if paired is not None else frame[product].reindex(months).dropna()
            total = float(series.sum()) if len(series) else None
            origins = frame.loc[series.index, "origin"].value_counts().to_dict() if product == "harmonized" else {}
            coverage = f"{len(series)}/{len(months)} months"
            if total is None:
                lines.append(f"- {period}: unavailable ({coverage}).")
            else:
                provenance = "; " + ", ".join(f"{v} {k.lower()}" for k, v in origins.items()) if origins else ""
                lines.append(f"- {period}: {total:,.1f} ({coverage}{provenance}); peak {series.idxmax()}.")
            totals.append((period, total, tuple(m[5:] for m in series.index)))
            evidence.append(EvidenceItem(source="local_parquet_archive", product=product,
                metric="period_total_detections", value=total, status="calculated" if total is not None else "unavailable",
                metadata={"period": period, "months": list(series.index), "origin_counts": origins}))
        for (a, old, ma), (b, new, mb) in zip(totals, totals[1:]):
            if old is None or new is None:
                continue
            if len(a) != len(b) or (len(a) == 4 and ma != mb):
                lines.append(f"- {a} to {b}: coverage differs; totals are not directly comparable.")
                continue
            pct = f" ({(new-old)/old:+.1%})" if old else " (percent change undefined from zero)"
            lines.append(f"- {a} to {b}: {new-old:+,.1f} detections{pct}.")
        if re.search(r"anomal|unusual|departure|pattern|season", question):
            series = frame[product].dropna()
            chosen = [m for m in series.index if m in periods or m[:4] in periods]
            if re.search(r"pattern|season", question) and chosen:
                grouped = series.loc[chosen].groupby(lambda m: m[5:])
                ranking = grouped.median().sort_values(ascending=False).head(3)
                lines.append("Highest calendar-month medians: " + ", ".join(
                    f"{m}: {v:,.1f} ({grouped.size()[m]} values)" for m, v in ranking.items()) + ".")
            anomalies = historical_anomalies(series).loc[chosen, "Departure (%)"].dropna()
            largest = anomalies.loc[anomalies.abs().nlargest(3).index]
            lines.append("Largest seasonal departures from earlier same-month medians: " +
                         (", ".join(f"{m}: {v:+.1f}%" for m, v in largest.items())
                          if len(largest) else "unavailable with the available baseline") + ".")
    if len(products) > 1:
        for period in periods:
            matched = [item for item in evidence if item.metadata["period"] == period and item.value is not None]
            for item in matched[1:]:
                baseline = matched[0]
                delta = item.value - baseline.value
                pct = f" ({delta / baseline.value:+.1%})" if baseline.value else ""
                lines.append(f"{period}: {item.product} minus {baseline.product} = {delta:+,.1f} detections{pct}.")
        lines.append("Sensor totals use only months available for every requested series.")
    if before_after:
        lines.append("Harmonization keeps observed VIIRS S-NPP and fills eligible gaps with scaled MODIS. The raw and harmonized totals above use the same months.")
    lines.append("Counts represent satellite detections. Unavailable data is distinct from zero. Harmonized totals may include estimates." +
                 (" This archive is synthetic demo data." if region == "demo" else ""))
    return {"answer": "\n\n".join(lines), "evidence": evidence}
