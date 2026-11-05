#!/usr/bin/env bash
# The daily DGII RNC load. `download` stops after the zips, for the workflow.
set -euo pipefail

importer="$(cd "$(dirname "$0")" && pwd)/dgii_rnc_import.py"
user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

fetch() {
  local code
  if ! curl -sS -L --max-time 180 \
    -A "$user_agent" \
    -H 'Accept: */*' \
    -H 'Accept-Language: es-DO' \
    -H 'Referer: https://dgii.gov.do/herramientas/consultas/Paginas/RNC.aspx' \
    -o "$2" \
    -w 'http_code=%{http_code}\ncontent_type=%{content_type}\nsize_download=%{size_download}\ntime_total=%{time_total}\n' \
    "$1" | tee download.txt; then
    echo "download failed: $2"
    return 1
  fi
  code="$(sed -n 's/^http_code=//p' download.txt)"
  if [ "$code" != "200" ]; then
    echo "download failed: $2"
    head -c 400 "$2" || true
    echo
    return 1
  fi
}

download() {
  fetch 'https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip' rnc-csv.zip
  if ! fetch 'https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip' rnc-txt.zip; then
    rm -f rnc-txt.zip
    echo "trade names unavailable: the load goes on and previous names stay"
  fi
}

if [ "${1:-}" = "download" ]; then
  download
  exit 0
fi

secret_present=false
if [ -n "${SUPABASE_STAGING_DB_URL:-}" ]; then
  secret_present=true
fi
decision="$(python3 "$importer" gate \
  --enabled "${DGII_RNC_LOAD_ENABLED:-}" \
  --dry-run false \
  --secret-present "$secret_present")"
echo "$decision"
if [ "$decision" != "load" ]; then
  exit 0
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
cd "$workdir"
download
python3 "$importer" load rnc-csv.zip rnc-txt.zip
