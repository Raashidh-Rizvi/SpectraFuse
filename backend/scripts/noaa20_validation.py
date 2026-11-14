"""Compare untouched NOAA-20 observations with MODIS in the original pilot holdout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.analytics import evaluate_overlap
from backend.api import dashboard_frame
from backend.fire import SOURCES, workspace

frame = dashboard_frame("sri-lanka").loc["2018-01":"2023-12"]
holdout, _ = evaluate_overlap(frame)
if len(holdout) != 18:
    raise SystemExit("The original pilot requires 18 holdout months.")
result = holdout.join(frame["VIIRS_NOAA20_SP"]).dropna()
if len(result) != 18:
    raise SystemExit("NOAA-20 coverage is incomplete.")
reference = result["VIIRS_NOAA20_SP"]
for column in ("Raw MODIS", "Calibrated MODIS"):
    error = result[column] - reference
    print(f"{column}: MAE {error.abs().mean():.2f}; bias {error.mean():.2f}")
output = workspace("79.5,5.8,82,10") / "harmonized" / "pilot" / "noaa20-holdout.csv"
output.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(output)
print(output)
