import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import evaluate_overlap, historical_anomalies
from fire import ROOT, SOURCES, monthly, workspace

st.set_page_config(page_title="FireScope", page_icon="🛰️", layout="wide")
st.title("FireScope")
st.caption("MODIS and VIIRS · Monthly active-fire detections · UTC")
areas = sorted(path.read_text(encoding="utf-8") for path in (ROOT / "data").glob("*/area.txt"))
if not areas:
    st.info("Run the demo or sync a FIRMS region using the commands in README.md.")
    st.stop()

area = st.sidebar.selectbox("Dataset", areas, format_func=lambda name: "Synthetic demo" if name == "demo" else name)
if area != "demo":
    st.caption(f"Downloaded extent {area}")
if area == "demo":
    st.warning("Synthetic demo. Values are generated for testing.")
bounds = None
if st.sidebar.checkbox("Filter to a smaller bounding box"):
    limits = [-180., -90., 180., 90.] if area in ("world", "demo") else list(map(float, area.split(",")))
    west, east = st.sidebar.slider("Longitude", -180., 180., (limits[0], limits[2]), step=.01)
    south, north = st.sidebar.slider("Latitude", -90., 90., (limits[1], limits[3]), step=.01)
    bounds = (west, south, east, north)
table, metrics = monthly(area, bounds)
if table.empty:
    st.info("The calendar needs at least one complete downloaded month.")
    st.stop()

series = st.sidebar.selectbox("Calendar measure", ["harmonized", *SOURCES],
                              format_func=lambda name: {"harmonized": "VIIRS-scale detections",
                                                       "MODIS_SP": "MODIS", "VIIRS_SNPP_SP": "VIIRS S-NPP"}[name])
years = sorted({int(month[:4]) for month in table.index})
selection = st.sidebar.select_slider("Calendar years", options=years,
                                     value=(years[0], years[-1])) if len(years) > 1 else (years[0], years[0])
calendar_data = table.assign(year=table.index.str[:4].astype(int), month_of_year=table.index.str[5:].astype(int))
calendar_data = calendar_data.join(historical_anomalies(calendar_data[series]))
measure = st.sidebar.selectbox("Calendar view", [series, "Departure (%)", "Departure (detections)"])
anomaly = measure != series
visible = calendar_data[calendar_data.year.between(*selection)]
valid_activity = visible[series].dropna()
if len(valid_activity):
    seasonal = valid_activity.groupby(valid_activity.index.str[5:]).median()
    peak = pd.Timestamp(f"2000-{seasonal.idxmax()}-01").strftime("%B")
    cols = st.columns(3)
    cols[0].metric("Months with data", len(valid_activity))
    cols[1].metric("Peak seasonal month", peak)
    cols[2].metric("Highest activity month", valid_activity.idxmax())
grid = visible.pivot(index="year", columns="month_of_year", values=measure).reindex(columns=range(1, 13))
grid.columns = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
calendar_selection = st.plotly_chart(px.imshow(grid, y=grid.index.astype(str), aspect="auto",
                         color_continuous_scale="RdBu_r" if anomaly else "YlOrRd",
                         color_continuous_midpoint=0 if anomaly else None,
                         labels={"color": ("%" if measure == "Departure (%)" else "Detections"), "x": "Month", "y": "Year"}), on_select="rerun", selection_mode="points")
st.caption("Blank cells indicate unavailable values. Seasonal departures use the median of at least two earlier values for the same calendar month. When the median is zero, use the departure in detections.")
trend = visible[[*SOURCES, "harmonized"]].rename(columns={
    "MODIS_SP": "MODIS", "VIIRS_SNPP_SP": "VIIRS S-NPP", "harmonized": "VIIRS-scale detections"})
st.plotly_chart(px.line(trend, markers=True, labels={"value": "Detections", "variable": "Series"}))

if "factor" in metrics:
    columns = st.columns(3)
    columns[0].metric("MODIS scaling factor", f"{metrics['factor']:.2f}×")
    columns[1].metric("Raw MODIS holdout MAE", f"{metrics['raw_mae']:,.1f}")
    columns[2].metric("Scaled MODIS holdout MAE", f"{metrics['adjusted_mae']:,.1f}")
    st.caption(f"{metrics['training_months']} training months and {metrics['holdout_months']} later holdout months. MAE is measured in monthly detections.")
else:
    st.info("Calibration requires at least three training months with positive totals for both sensors and a later holdout month.")
comparison, validation = evaluate_overlap(table)
if not comparison.empty:
    with st.expander("Held-out sensor comparison"):
        st.plotly_chart(px.line(comparison, markers=True, labels={"value": "Monthly detections"}))
        st.dataframe(validation)
        st.caption("The 90th percentile describes historical absolute errors in the holdout period. It is an empirical error summary.")
with st.expander("Monthly counts and provenance"):
    st.dataframe(visible[[*SOURCES, "harmonized", "origin", "Historical median", "Departure (%)", "Departure (detections)"]])
st.download_button("Download selected months as CSV", visible.to_csv().encode(), "firescope-monthly.csv", "text/csv")
st.caption("Satellite detections can include repeat observations and non-fire thermal sources. Counts measure detection activity, and coverage can vary by sensor.")


with st.expander("Monthly detection map"):
    selected_month = visible.index[-1]
    if calendar_selection.selection.points:
        point = calendar_selection.selection.points[0]
        labels = list(grid.columns)
        candidate = f"{point.get('y')}-{labels.index(point['x']) + 1:02}" if point.get("x") in labels else ""
        if candidate in visible.index:
            selected_month = candidate
    map_month = st.selectbox("Map month", visible.index, index=visible.index.get_loc(selected_month),
                             key=f"map-month-{selected_month}")
    st.dataframe(visible.loc[[map_month], [*SOURCES, "harmonized", "origin",
                                           "Historical median", "Departure (%)"]])
    map_source = st.selectbox("Map sensor", SOURCES)
    parts = sorted((workspace(area) / "processed" / map_source).glob(f"{map_month}-*.parquet"))
    if parts:
        points = pd.concat((pd.read_parquet(part)
                            for part in parts), ignore_index=True)
        if bounds is not None:
            west, south, east, north = bounds
            points = points[points.latitude.between(south, north) & points.longitude.between(west, east)]
        cells = points.groupby(["grid_lat", "grid_lon"]).size().rename("Detections").reset_index()
        st.download_button("Download selected hotspots", points.to_csv(index=False),
                           f"{map_source}-{map_month}.csv", "text/csv")
        if len(cells):
            cells["Latitude"] = cells.grid_lat + 0.5
            cells["Longitude"] = cells.grid_lon + 0.5
            st.plotly_chart(px.scatter_geo(cells, lat="Latitude", lon="Longitude",
                                          size="Detections", color="Detections",
                                          color_continuous_scale="YlOrRd", fitbounds="locations"))
        else:
            st.info("No detections in the selected extent.")
        st.caption(f"{len(parts)} downloaded days. Markers show one-degree cell centers.")
    else:
        st.info("No downloaded days for this sensor and month.")


