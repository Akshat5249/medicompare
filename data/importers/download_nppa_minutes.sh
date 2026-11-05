#!/usr/bin/env bash
# Downloads NPPA Authority minutes into data/downloads/minutes/.
# NPPA's copyright policy permits free reproduction when accurate and acknowledged:
# https://nppa.gov.in/en/copyrightpolicy (verified 2026-11-05)
set -euo pipefail
cd "$(dirname "$0")/../downloads"
mkdir -p minutes
cd minutes
agent="Mozilla/5.0 (compatible; MediCompare-source-audit/0.1)"
for year in 2026-2027 2025-2026 2024-2025; do
  curl --fail --silent --show-error --location --max-time 60 --user-agent "$agent" --output "$year.html" "https://nppa.gov.in/en/year$year"
done
python3 - "$agent" <<'PY'
import html
import re
import subprocess
import sys

agent = sys.argv[1]
for year in ("2026-2027", "2025-2026", "2024-2025"):
    page = open(f"{year}.html", errors="ignore").read()
    for row in re.findall(r"(?s)<tr.*?</tr>", page):
        link = re.search(r'href="([^"]+\.pdf)"', row, re.I)
        meeting = re.search(r"(\d+)\s*(?:st|nd|rd|th)\s*\(overall\)", html.unescape(re.sub(r"<[^>]+>", " ", row)))
        if not link or not meeting:
            continue
        url = link[1] if link[1].startswith("http") else f"https://nppa.gov.in{link[1]}"
        done = subprocess.run(["curl", "-sfL", "-A", agent, "-m", "90", "-o", f"minutes-{meeting[1]}.pdf", url])
        print(f"minutes-{meeting[1]}.pdf", "ok" if done.returncode == 0 else "FAILED")
PY
