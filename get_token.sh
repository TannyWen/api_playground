#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://processdetraining.azurewebsites.net}"
USERNAME="${USERNAME:-student}"
PASSWORD="${PASSWORD:-student-pass-123}"

TOKEN=$(curl -sS -X POST "$BASE_URL/v1/auth/token" \
    -d "username=$USERNAME&password=$PASSWORD" \
    | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "$TOKEN"

echo
echo "Example:"
echo "  curl -H 'Authorization: Bearer $TOKEN' $BASE_URL/v1/master-data/suppliers"
