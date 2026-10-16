#!/bin/sh
set -eu

: "${S3_ENDPOINT_URL:?Set the source MinIO endpoint}"
: "${S3_ACCESS_KEY_ID:?Set the source S3 access key}"
: "${S3_SECRET_ACCESS_KEY:?Set the source S3 secret}"
: "${S3_BUCKET:?Set the source bucket}"
: "${MINIO_BACKUP_ENDPOINT_URL:?Set the external backup endpoint}"
: "${MINIO_BACKUP_BUCKET:?Set the external backup bucket}"
: "${MINIO_BACKUP_ACCESS_KEY_ID:?Set the external backup access key}"
: "${MINIO_BACKUP_SECRET_ACCESS_KEY:?Set the external backup secret}"

case "$S3_BUCKET:$MINIO_BACKUP_BUCKET" in
  *[!A-Za-z0-9._:-]*)
    echo "Bucket names contain unsupported characters." >&2
    exit 2
    ;;
esac
if [ "$S3_ENDPOINT_URL" = "$MINIO_BACKUP_ENDPOINT_URL" ] &&
   [ "$S3_BUCKET" = "$MINIO_BACKUP_BUCKET" ]; then
  echo "Source and destination must not be the same endpoint and bucket." >&2
  exit 2
fi

prefix="${MINIO_BACKUP_PREFIX:-arena/minio}"
case "$prefix" in
  ""|/*|*..*|*\\*)
    echo "Backup prefix must be a non-empty relative object prefix without '..'." >&2
    exit 2
    ;;
esac

mc alias set source "$S3_ENDPOINT_URL" "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY" >/dev/null
mc alias set external "$MINIO_BACKUP_ENDPOINT_URL" \
  "$MINIO_BACKUP_ACCESS_KEY_ID" "$MINIO_BACKUP_SECRET_ACCESS_KEY" >/dev/null
mc mirror --overwrite "source/$S3_BUCKET" \
  "external/$MINIO_BACKUP_BUCKET/$prefix"
echo "Mirror complete. No destination objects were removed."
