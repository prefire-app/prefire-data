#!/usr/bin/env python3
"""Download Census county boundaries, pickle them, and upload to S3.

Builds the index consumed by ``src/datasets/county.py`` for point-in-polygon
county lookups. Uses the Census ``cb_*_us_county_500k`` cartographic boundary
file (pre-simplified, ~3 MB) which is the same authoritative geometry as the
full TIGER/Line shapefile but suitable for general-purpose mapping and county
membership tests.

Refresh annually when Census publishes a new vintage.

Usage:
    ./prepare_county_index.py s3://prefire-data/counties/
    ./prepare_county_index.py s3://prefire-data/counties/ --vintage 2024
    ./prepare_county_index.py s3://prefire-data/counties/ --skip-upload --workdir ./out
"""

from __future__ import annotations

import argparse
import pickle
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

try:
    import shapefile  # type: ignore[import-untyped]  # pyshp
    from shapely.geometry import shape
except ImportError:
    sys.exit("missing deps. Run: pip install pyshp shapely")

CENSUS_URL_TEMPLATE = (
    "https://www2.census.gov/geo/tiger/GENZ{vintage}/shp/cb_{vintage}_us_county_500k.zip"
)


def main() -> int:
    args = _parse_args()
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="counties_"))
    workdir.mkdir(parents=True, exist_ok=True)

    url = CENSUS_URL_TEMPLATE.format(vintage=args.vintage)
    zip_path = workdir / f"cb_{args.vintage}_us_county_500k.zip"
    out_path = workdir / f"cb_{args.vintage}_us_county_500k.pkl"

    print(f"Downloading {url} ...")
    _download(url, zip_path)

    print("Extracting + serializing ...")
    rows = _build_rows(zip_path, workdir)
    with open(out_path, "wb") as fh:
        pickle.dump(rows, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Wrote {len(rows)} counties to {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    if not args.skip_upload:
        s3_dest = args.s3_dest.rstrip("/") + "/" + out_path.name
        print(f"Uploading to {s3_dest} ...")
        subprocess.run(["aws", "s3", "cp", str(out_path), s3_dest], check=True)
        print(f"Done. Set COUNTY_INDEX_URI={s3_dest} on the Lambda if it differs from default.")
    else:
        print(f"Skipping upload. Pickle at {out_path}")

    if not args.workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


def _download(url: str, dest: Path) -> None:
    """Download url to dest, replacing any existing file."""
    req = urllib.request.Request(url, headers={"User-Agent": "prefire-data/1.0"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as fh:  # noqa: S310 — hardcoded census URL
        shutil.copyfileobj(resp, fh)


def _build_rows(zip_path: Path, workdir: Path) -> list[tuple[str, str, str, bytes]]:
    """Extract the shapefile and return (statefp, countyfp, name, wkb) tuples.

    Preconditions:
        - zip_path is a Census cb_*_us_county_500k.zip archive.

    Postconditions:
        - Returns one tuple per county; geometries are well-known-binary.
    """
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(workdir)
    shp = next(workdir.glob("cb_*_us_county_500k.shp"))

    rows: list[tuple[str, str, str, bytes]] = []
    with shapefile.Reader(str(shp)) as reader:
        field_names = [f[0] for f in reader.fields[1:]]
        statefp_idx = field_names.index("STATEFP")
        countyfp_idx = field_names.index("COUNTYFP")
        name_idx = field_names.index("NAME")
        for sr in reader.iterShapeRecords():
            geom = shape(sr.shape.__geo_interface__)
            rec = sr.record
            rows.append(
                (
                    str(rec[statefp_idx]),
                    str(rec[countyfp_idx]),
                    str(rec[name_idx]),
                    geom.wkb,
                )
            )
    return rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("s3_dest", help="S3 prefix, e.g. s3://prefire-data/counties/")
    p.add_argument("--vintage", default="2024", help="Census vintage year (default: 2024)")
    p.add_argument(
        "--workdir", help="Keep extracted files in this directory (default: temp dir, deleted)"
    )
    p.add_argument("--skip-upload", action="store_true", help="Build locally, do not upload to S3")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
