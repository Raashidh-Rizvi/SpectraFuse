import csv
from pathlib import Path


def main():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "sri-lanka-2000-2025"

    for dataset in ("modis", "viirs-jpss1"):
        files_by_header = {}
        for path in sorted((data_dir / dataset).rglob("*.csv")):
            with path.open(encoding="utf-8-sig", newline="") as csv_file:
                header = tuple(next(csv.reader(csv_file), []))
            files_by_header.setdefault(header, []).append(path)

        print(dataset)
        if not files_by_header:
            print("  No CSV files found")
        for header, paths in files_by_header.items():
            print(f"  {len(paths)} CSV file(s): {', '.join(header) or '(no header)'}")
            if len(files_by_header) > 1:
                for path in paths:
                    print(f"    {path.relative_to(data_dir / dataset)}")


if __name__ == "__main__":
    main()
