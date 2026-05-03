#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"

if ! command -v java >/dev/null 2>&1; then
  echo "Java is required but was not found on PATH."
  echo "Install Java 11 or newer, then run this script again."
  exit 1
fi

if ! command -v mvn >/dev/null 2>&1; then
  echo "Maven is required but was not found on PATH."
  echo "Install Maven 3.8 or newer, then run this script again."
  exit 1
fi

JAVA_VERSION_OUTPUT="$(java -version 2>&1 | sed -n '1p')"
JAVA_MAJOR="$(printf '%s\n' "${JAVA_VERSION_OUTPUT}" | sed -E 's/.*version "([0-9]+).*/\1/')"

if [ "${JAVA_MAJOR}" -lt 11 ] 2>/dev/null; then
  echo "Java 11 or newer is required. Found: ${JAVA_VERSION_OUTPUT}"
  exit 1
fi

LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

echo "Starting webapp-210401210447 with Jetty..."
echo
echo "Open this app on the same device:"
echo "  http://localhost:${PORT}/"
echo

if [ -n "${LOCAL_IP}" ]; then
  echo "Open this app from an iPad on the same Wi-Fi network:"
  echo "  http://${LOCAL_IP}:${PORT}/"
  echo
fi

echo "Press Ctrl+C to stop the server."
echo

exec mvn jetty:run -Djetty.http.port="${PORT}"
