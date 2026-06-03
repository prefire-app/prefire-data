#!/usr/bin/env python3
"""Build per-state building-footprint PMTiles from Overture Maps.

For each requested state FIPS:
  1. Fetch the state polygon from TIGERweb.
  2. Query Overture's buildings theme on S3 with DuckDB (bbox + polygon clip).
  3. Stream rows to GeoJSONSeq.
  4. Pack with tippecanoe into a single .pmtiles.
  5. Upload to s3://<bucket>/pmtiles/buildings-<fips>.pmtiles.

Requires: duckdb (pip), tippecanoe (>= 2.40), awscli, network access to S3
us-west-2 (Overture) and the destination bucket.

Typical usage:
  ./prepare_buildings_pmtiles.py --bucket prefire-data            # all 50 + DC
  ./prepare_buildings_pmtiles.py --bucket prefire-data --states 06,48,12
  ./prepare_buildings_pmtiles.py --bucket prefire-data --skip-upload --workdir ./out
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import duckdb

# Bump when a newer Overture release should be the default. Releases land
# monthly; only the last two are kept on the public bucket (60-day retention).
# Check the current tag at https://docs.overturemaps.org/release-calendar/
OVERTURE_RELEASE_DEFAULT = "2026-05-20.0"
OVERTURE_PARQUET_GLOB = (
    "s3://overturemaps-us-west-2/release/{release}"
    "/theme=buildings/type=building/*"
)
TIGER_STATES_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/State_County/MapServer/0/query"
)

# 50 states + DC. Territories (PR, VI, GU, AS, MP) intentionally omitted —
# add when needed; Overture covers them but the webapp currently does not.
STATE_FIPS: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}


def fetch_state_polygon(fips: str) -> dict:
    """Return a GeoJSON Polygon/MultiPolygon geometry for the given state FIPS."""
    params = {
        "where": f"STATE='{fips}'",
        "outFields": "STATE,NAME",
        "f": "geojson",
        "outSR": "4326",
        "geometryPrecision": "5",
    }
    url = f"{TIGER_STATES_URL}?{urlencode(params)}"
    with urlopen(url, timeout=60) as r:
        data = json.load(r)
    features = data.get("features") or []
    if not features:
        raise RuntimeError(f"TIGERweb returned no state for FIPS {fips}")
    return features[0]["geometry"]


def bbox_of(geom: dict) -> tuple[float, float, float, float]:
    def rings(g):
        if g["type"] == "Polygon":
            yield from g["coordinates"]
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                yield from poly
        else:
            raise ValueError(f"unsupported geometry: {g['type']}")
    xs: list[float] = []
    ys: list[float] = []
    for ring in rings(geom):
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def duckdb_connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")
    # Overture's bucket is public; no creds needed.
    con.execute("SET s3_use_ssl=true;")
    return con


def extract_state(
    con: duckdb.DuckDBPyConnection,
    fips: str,
    geom: dict,
    release: str,
    out_path: Path,
) -> int:
    """Extract Overture buildings for one state to GeoJSONSeq. Returns row count."""
    xmin, ymin, xmax, ymax = bbox_of(geom)
    src = OVERTURE_PARQUET_GLOB.format(release=release)
    geom_json = json.dumps(geom)

    # Two-stage filter: cheap bbox prune (uses Overture's bbox struct, no
    # geometry decode), then exact polygon clip via ST_Intersects.
    sql = f"""
    COPY (
      SELECT
        id,
        class,
        subtype,
        height,
        num_floors,
        geometry
      FROM read_parquet('{src}', hive_partitioning=1)
      WHERE bbox.xmin <= {xmax} AND bbox.xmax >= {xmin}
        AND bbox.ymin <= {ymax} AND bbox.ymax >= {ymin}
        AND ST_Intersects(geometry, ST_GeomFromGeoJSON(?))
    ) TO '{out_path.as_posix()}'
      WITH (FORMAT GDAL, DRIVER 'GeoJSONSeq', SRS 'EPSG:4326');
    """
    con.execute(sql, [geom_json])
    # Count for logging — cheap because we just wrote the file.
    with out_path.open("rb") as f:
        return sum(1 for _ in f)


def run_tippecanoe(geojsonseq: Path, pmtiles: Path) -> None:
    cmd = [
        "tippecanoe",
        "-o", str(pmtiles),
        "-l", "buildings",
        "-zg",
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
        "--no-tile-size-limit",
        "--force",
        str(geojsonseq),
    ]
    subprocess.run(cmd, check=True)


def upload(pmtiles: Path, bucket: str, fips: str) -> str:
    key = f"pmtiles/buildings-{fips}.pmtiles"
    dest = f"s3://{bucket}/{key}"
    subprocess.run(
        [
            "aws", "s3", "cp", str(pmtiles), dest,
            "--content-type", "application/vnd.pmtiles",
            "--cache-control", "public, max-age=86400",
        ],
        check=True,
    )
    return dest


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"required tool not on PATH: {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bucket", required=True, help="destination S3 bucket")
    ap.add_argument(
        "--states",
        default="",
        help="comma-separated state FIPS codes; default: all 50 + DC",
    )
    ap.add_argument(
        "--release",
        default=os.environ.get("OVERTURE_RELEASE", OVERTURE_RELEASE_DEFAULT),
        help=f"Overture release tag (default: {OVERTURE_RELEASE_DEFAULT})",
    )
    ap.add_argument(
        "--workdir",
        default="",
        help="keep intermediate files in this directory (default: temp dir)",
    )
    ap.add_argument(
        "--skip-upload",
        action="store_true",
        help="build .pmtiles locally but do not upload to S3",
    )
    args = ap.parse_args()

    require_tool("tippecanoe")
    if not args.skip_upload:
        require_tool("aws")

    if args.states:
        wanted = [s.strip() for s in args.states.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in STATE_FIPS]
        if unknown:
            sys.exit(f"unknown FIPS codes: {unknown}")
    else:
        wanted = list(STATE_FIPS)

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="buildings-"))
    workdir.mkdir(parents=True, exist_ok=True)

    con = duckdb_connect()

    failures: list[tuple[str, str]] = []
    for fips in wanted:
        postal = STATE_FIPS[fips]
        print(f"\n=== {fips} {postal} ===", flush=True)
        try:
            geom = fetch_state_polygon(fips)
            geojsonseq = workdir / f"buildings-{fips}.geojsonseq"
            pmtiles = workdir / f"buildings-{fips}.pmtiles"

            print(f"  extracting from Overture release {args.release} ...", flush=True)
            n = extract_state(con, fips, geom, args.release, geojsonseq)
            print(f"  {n:,} features", flush=True)

            print("  packing pmtiles ...", flush=True)
            run_tippecanoe(geojsonseq, pmtiles)
            size_mb = pmtiles.stat().st_size / 1e6
            print(f"  pmtiles {size_mb:,.1f} MB", flush=True)

            if not args.skip_upload:
                dest = upload(pmtiles, args.bucket, fips)
                print(f"  uploaded {dest}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}", flush=True)
            failures.append((fips, str(e)))

    if failures:
        print("\nFailures:")
        for fips, msg in failures:
            print(f"  {fips} {STATE_FIPS[fips]}: {msg}")
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
