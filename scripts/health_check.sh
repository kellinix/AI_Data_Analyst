#!/usr/bin/env bash
# ============================================================
# Health check script — verifies all services are responding
# ============================================================
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

check_service() {
  local name=$1
  local url=$2
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
  if [ "$status" = "200" ]; then
    echo "✅ $name ($url)"
    return 0
  else
    echo "❌ $name ($url) returned HTTP $status"
    return 1
  fi
}

FAILURES=0

check_service "Backend Health" "$BACKEND_URL/api/v1/health" || FAILURES=$((FAILURES+1))
check_service "Frontend Health" "$FRONTEND_URL/api/health" || FAILURES=$((FAILURES+1))

if [ "$FAILURES" -gt 0 ]; then
  echo ""
  echo "❌ $FAILURES service(s) failed"
  exit 1
else
  echo ""
  echo "✅ All services healthy"
fi
