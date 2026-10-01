#!/usr/bin/env bash
# Optioneel: serveer het dashboard lokaal via http (file:// werkt ook gewoon).
# Gebruik: ./serve.sh [poort]   — zonder poort wordt een vrije poort gekozen.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')}"
echo "Dashboard: http://127.0.0.1:${PORT}/index.html   (Ctrl+C om te stoppen)"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
