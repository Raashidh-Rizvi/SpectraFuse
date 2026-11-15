"""Stage the React dashboard, FastAPI service, and processed data for Vercel."""

import json
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / ".vercel-stage"
# Packages the deployed API imports at runtime. The agent layer calls Gemini, Groq and
# OpenAI over plain HTTPS with `requests`, so no provider SDK is needed on the server.
RUNTIME = {"fastapi", "pydantic", "pandas", "numpy", "pyarrow", "python-dotenv", "requests"}


def requirement_name(line):
    """Return the normalized package name of a requirements line, for any version operator."""
    return re.split(r"[<>=!~\[;\s]", line.strip(), maxsplit=1)[0].lower()


def copy_tree(source, target):
    """Copy a source folder, replacing stale files and skipping caches and bytecode."""
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))


def main():
    pilot = ROOT / "data" / "d73f2ecaea43efef"
    if not (pilot / "area.txt").is_file() or not any(pilot.glob("processed/*/*.parquet")):
        sys.exit("Build or restore the Sri Lanka dataset before staging the deployment.")

    STAGE.mkdir(exist_ok=True)
    (STAGE / "backend").mkdir(exist_ok=True)
    for name in ("backend/__init__.py", "backend/main.py", "backend/analytics.py", "backend/fire.py",
                 "backend/grid.py", "backend/chat.py"):
        shutil.copyfile(ROOT / name, STAGE / name)
    # The multi-agent chat system: orchestrator, specialist agents, memory, providers.
    copy_tree(ROOT / "backend" / "agents", STAGE / "backend" / "agents")

    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    runtime = [line.strip() for line in requirements if requirement_name(line) in RUNTIME]
    missing = RUNTIME - {requirement_name(line) for line in runtime}
    if missing:
        sys.exit(f"requirements.txt is missing runtime packages: {sorted(missing)}")
    (STAGE / "requirements.txt").write_text("\n".join(runtime) + "\n")
    (STAGE / ".python-version").write_text("3.13\n")
    (STAGE / "pyproject.toml").write_text(
        '[project]\nname = "firescope"\nversion = "0.1.0"\nrequires-python = "==3.13.*"\n'
        f'dependencies = {json.dumps(runtime)}\n\n[tool.vercel]\nentrypoint = "backend.main:app"\n'
    )
    (STAGE / "package.json").write_text(json.dumps({"private": True, "engines": {"node": "22.x"}}))

    frontend = STAGE / "frontend"
    frontend.mkdir(exist_ok=True)
    for name in (".env.production", "package.json", "package-lock.json", "index.html",
                 "src.jsx", "DatasetChat.jsx", "style.css", "vite.config.js"):
        shutil.copyfile(ROOT / "frontend" / name, frontend / name)
    # Chatbot UI imported by src.jsx.
    for folder in ("components", "context"):
        copy_tree(ROOT / "frontend" / folder, frontend / folder)

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
            "backend/main.py": {
                "includeFiles": "{data/**,frontend/dist/**}",
                "excludeFiles": "{frontend/node_modules/**,processed-data.zip}",
            },
        },
    }
    (STAGE / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"Vercel project staged at {STAGE}")


if __name__ == "__main__":
    main()
