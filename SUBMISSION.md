# SpectraFuse · NASA Space Apps

SpectraFuse compares historical NASA FIRMS hotspot activity across MODIS and VIIRS. Its monthly calendar preserves observed VIIRS S-NPP where available and uses calibrated MODIS for earlier months. The dashboard shows provenance and an empirical holdout error range for estimates.

## Demo sequence

1. Open the Sri Lanka region. Switch between raw MODIS and VIIRS-scale activity.
2. Compare an earlier MODIS estimate with a later VIIRS observation. Open the sensor comparison and inspect the estimate range.
3. Turn on seasonal anomalies and select a calendar month. Compare the products on the map and download the underlying observations.
4. Switch regions and show the second-region validation result. Toggle light and dark themes on a narrow screen.
5. Explain the holdout experiment. The pilot's regional error fell from 456.4 to 138.3 monthly detections. Grid-day error increased, which limits how the regional multiplier should be used.

## Sources and limitations

- [NASA challenge brief](https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/)
- [NASA FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area)
- [FIRMS product availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability/)
- [Known satellite data gaps](https://firms.modaps.eosdis.nasa.gov/api/missing_data/)

Hotspots are satellite detections. Counts can include repeated observations and non-fire thermal sources. Download completeness measures the presence of daily files. The error range summarizes observed monthly errors in a time holdout, with no coverage guarantee for historical periods or another region.
