import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
app = AppTest.from_file(str(root / 'app.py'), default_timeout=60).run()
assert not app.exception, [item.message for item in app.exception]
assert len(app.get("plotly_chart")) == 4
assert len(app.metric) == 6
app.sidebar.selectbox[2].select("Departure (%)").run()
assert not app.exception, [item.message for item in app.exception]
assert len(app.get("plotly_chart")) == 4
print("Dashboard smoke test passed: calendar, trend, map, metrics, and anomaly toggle.")
