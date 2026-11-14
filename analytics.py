import pandas as pd

from fire import SOURCES


def historical_anomalies(series):
    """Compare each month with earlier observations from the same calendar month."""
    history = series.groupby(series.index.str[5:]).transform(
        lambda values: values.shift().expanding(min_periods=2).median())
    difference = series - history
    return pd.DataFrame({"Historical median": history,
                         "Departure (detections)": difference,
                         "Departure (%)": difference.div(history.where(history.ne(0))) * 100})


def evaluate_overlap(table):
    modis, viirs = SOURCES
    paired = table[list(SOURCES)].dropna()
    size = max(1, len(paired) // 4)
    train, test = paired.iloc[:-size], paired.iloc[-size:]
    if len(train) < 3 or min(train.sum()) <= 0:
        return pd.DataFrame(), pd.DataFrame()
    factor = train[viirs].sum() / train[modis].sum()
    comparison = test.rename(columns={modis: "Raw MODIS", viirs: "VIIRS reference"})
    comparison["Calibrated MODIS"] = comparison["Raw MODIS"] * factor
    reference = comparison["VIIRS reference"]
    rows = []
    for name in ("Raw MODIS", "Calibrated MODIS"):
        prediction = comparison[name]
        error = prediction - reference
        seasonal = pd.DataFrame({"prediction": prediction, "reference": reference}).groupby(
            prediction.index.str[5:]).mean()
        rows.append({"Method": name, "MAE": error.abs().mean(), "Bias": error.mean(),
                     "Correlation": prediction.corr(reference) if prediction.nunique() > 1
                     and reference.nunique() > 1 else None,
                     "Seasonal correlation": seasonal.prediction.corr(seasonal.reference)
                     if seasonal.prediction.nunique() > 1 and seasonal.reference.nunique() > 1 else None,
                     "Absolute error 90th percentile": error.abs().quantile(.90)})
    return comparison, pd.DataFrame(rows).set_index("Method")
