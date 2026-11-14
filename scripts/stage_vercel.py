"""Stage the React dashboard, FastAPI service, and processed data for Vercel."""

import json
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".vercel-stage"
RUNTIME = {"fastapi", "pandas", "pyarrow", "python-dotenv", "requests"}


def main():
    pilot = ROOT / "data" / "d73f2ecaea43efef"
    if not (pilot / "area.txt").is_file() or not any(pilot.glob("processed/*/*.parquet")):
        sys.exit("Build or restore the Sri Lanka dataset before staging the deployment.")

    STAGE.mkdir(exist_ok=True)
    for name in ("main.py", "analytics.py", "fire.py"):
        shutil.copyfile(ROOT / name, STAGE / name)

    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    runtime = [line for line in requirements if line.split("==")[0] in RUNTIME]
    (STAGE / "requirements.txt").write_text("\n".join(runtime) + "\n")
    (STAGE / ".python-version").write_text("3.13\n")
    (STAGE / "pyproject.toml").write_text(
        '[project]\nname = "firescope"\nversion = "0.1.0"\nrequires-python = "==3.13.*"\n'
        f'dependencies = {json.dumps(runtime)}\n\n[tool.vercel]\nentrypoint = "main:app"\n'
    )
    (STAGE / "package.json").write_text(json.dumps({"private": True, "engines": {"node": "22.x"}}))

    frontend = STAGE / "frontend"
    frontend.mkdir(exist_ok=True)
    for name in (".env.production", "package.json", "package-lock.json", "index.html", "src.jsx", "style.css", "vite.config.js"):
        shutil.copyfile(ROOT / "frontend" / name, frontend / name)

    with ZipFile(STAGE / "processed-data.zip", "w", compression=ZIP_DEFLATED) as archive:
        for marker in sorted((ROOT / "data").glob("*/area.txt")):
            region = marker.parent
            if region.name == "demo":
                continue
            for path in (marker, *region.glob("harmonized/monthly.parquet"), *region.glob("processed/*/*.parquet")):
                archive.write(path, path.relative_to(ROOT))

    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": "fastapi",
        "buildCommand": "npm --prefix frontend ci --include=dev && npm --prefix frontend run build && python -m zipfile -e processed-data.zip .",
        "functions": {
            "main.py": {
                "includeFiles": "{data/**,frontend/dist/**}",
                "excludeFiles": "{frontend/node_modules/**,processed-data.zip}",
            },
        },
    }
    (STAGE / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"Vercel project staged at {STAGE}")


if __name__ == "__main__":
    main()
