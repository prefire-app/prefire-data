#!/usr/bin/env bash
# Download USFS WHP 2023 classified CONUS raster and convert to a COG.
#
# Requires: curl, unzip, gdal (>= 3.1, for COG driver), awscli.
# Usage:    ./prepare_whp_cog.sh s3://prefire-data/whp/

set -euo pipefail

S3_DEST="${1:?usage: prepare_whp_cog.sh s3://bucket/prefix/}"
WORK="$(mktemp -d)"
URL="https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip"

echo "Downloading $URL ..."
curl -L --fail -o "$WORK/whp.zip" "$URL"

echo "Extracting..."
unzip -q "$WORK/whp.zip" -d "$WORK"
SRC_TIF=$(find "$WORK" -iname 'whp2023_cls_conus.tif' | head -n1)
[ -n "$SRC_TIF" ] || { echo "classified raster not found in zip"; exit 1; }

echo "Converting to COG..."
gdal_translate -of COG \
  -co COMPRESS=DEFLATE \
  -co PREDICTOR=2 \
  -co BLOCKSIZE=512 \
  -co OVERVIEWS=IGNORE_EXISTING \
  -co BIGTIFF=IF_SAFER \
  "$SRC_TIF" "$WORK/whp2023_cls_conus_cog.tif"

echo "Uploading to ${S3_DEST}whp2023_cls_conus.tif ..."
aws s3 cp "$WORK/whp2023_cls_conus_cog.tif" \
  "${S3_DEST}whp2023_cls_conus.tif" \
  --content-type image/tiff

echo "Done. Set WHP_COG_URI=${S3_DEST}whp2023_cls_conus.tif on the Lambda."
rm -rf "$WORK"
