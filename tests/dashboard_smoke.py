from streamlit.testing.v1 import AppTest

app = AppTest.from_file("app.py", default_timeout=60).run()
assert not app.exception, [item.message for item in app.exception]
assert len(app.get("plotly_chart")) == 3
assert len(app.metric) == 3
app.sidebar.checkbox[1].check().run()
assert not app.exception, [item.message for item in app.exception]
assert len(app.get("plotly_chart")) == 3
print("Dashboard smoke test passed: calendar, trend, map, metrics, and anomaly toggle.")
