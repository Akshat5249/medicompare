#!/usr/bin/env bash
# Runs all scanners. Writes one report per tool to verification/security/.
# Exit status is non-zero if any tool reports an unjustified high or critical finding.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT="verification/security"; mkdir -p "$OUT"
status=0
TEST_RUN="docker compose --profile test run --rm -T backend-test"
echo "== bandit (medium and above)"
$TEST_RUN sh -c "bandit -q -r app -c pyproject.toml -ll -f txt" | tee "$OUT/bandit.txt" || status=1
echo "== pip-audit"
$TEST_RUN sh -c "uv export --frozen --no-dev --no-emit-project -o /tmp/req.txt >/dev/null && uvx pip-audit -r /tmp/req.txt --disable-pip --no-deps" | tee "$OUT/pip-audit.txt"
[[ ${PIPESTATUS[0]} -eq 0 ]] || status=1
echo "== npm audit (runtime dependencies, high and above)"
(cd frontend && npm audit --omit=dev --audit-level=high) | tee "$OUT/npm-audit.txt"
[[ ${PIPESTATUS[0]} -eq 0 ]] || status=1
echo "== gitleaks"
docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:v8.28.0 dir /repo \
  --config /repo/.gitleaks.toml --redact --no-banner --exit-code 1 \
  --report-format json --report-path /dev/stdout 2>&1 | tee "$OUT/gitleaks.txt"
[[ ${PIPESTATUS[0]} -eq 0 ]] || status=1
echo "== trivy (fixed high and critical vulnerabilities, and secrets, in built images; see .trivyignore and trivy-secret.yaml)"
mkdir -p "$HOME/.cache/trivy"
TRIVY=(docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$HOME/.cache/trivy:/root/.cache/trivy" -v "$PWD/.trivyignore:/.trivyignore:ro" -v "$PWD/trivy-secret.yaml:/trivy-secret.yaml:ro" aquasec/trivy:0.67.2)
: > "$OUT/trivy.txt"
for image in medicompare-backend medicompare-worker medicompare-frontend; do
  echo "-- $image" | tee -a "$OUT/trivy.txt"
  "${TRIVY[@]}" image --quiet --scanners vuln,secret --secret-config /trivy-secret.yaml --severity HIGH,CRITICAL --ignore-unfixed --ignorefile /.trivyignore --exit-code 1 --format table "$image" 2>&1 | tee -a "$OUT/trivy.txt"
  [[ ${PIPESTATUS[0]} -eq 0 ]] || status=1
done
exit $status
