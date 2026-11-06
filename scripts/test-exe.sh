#!/usr/bin/env bash
# Runs the built exe for real and fails the job unless it exits 0 with some output.
# Env in: EXE, TEST_ARGS (e.g. "--help"), GUI, LOG (where to write the test log)
set -uo pipefail
: "${LOG:=test-log.txt}"
{
  echo "Repo-to-EXE smoke test"
  echo "Runner: $(uname -a) | $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "File: $(basename "$EXE")  size: $(stat -c %s "$EXE") bytes"
  echo "PE header: $(head -c 2 "$EXE")"
} > "$LOG"
if [ "$(head -c 2 "$EXE")" != "MZ" ]; then echo "FAIL: not a Windows executable" | tee -a "$LOG"; exit 1; fi
if [ "$GUI" = "true" ] && [ -z "${TEST_ARGS:-}" ]; then
  echo "GUI app and no test args given: checked it is a valid .exe but did not open a window." | tee -a "$LOG"
  exit 0
fi
echo "Command: $(basename "$EXE") ${TEST_ARGS:-}" >> "$LOG"
# GNU timeout is not in Git Bash, and Windows timeout.exe is a different command.
# Python is on every GitHub runner and can start a Windows .exe with a real timeout.
EXE_RUN="$EXE"
if command -v cygpath >/dev/null 2>&1; then
  EXE_RUN="$(cygpath -w "$EXE")"
fi
PY=python
command -v python >/dev/null 2>&1 || PY=python3
# shellcheck disable=SC2086
"$PY" - "$EXE_RUN" ${TEST_ARGS:-} <<'PY'
import subprocess, sys
exe, *args = sys.argv[1:]
try:
    proc = subprocess.run(
        [exe, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
except subprocess.TimeoutExpired as exc:
    with open("out.txt", "wb") as fh:
        fh.write(exc.stdout or b"")
    sys.exit(124)
with open("out.txt", "wb") as fh:
    fh.write(proc.stdout or b"")
sys.exit(proc.returncode)
PY
CODE=$?
echo "Exit code: $CODE" >> "$LOG"
echo "----- output -----" >> "$LOG"; cat out.txt >> "$LOG"
cat "$LOG"
if [ "$CODE" -ne 0 ]; then echo "FAIL: exit code $CODE"; exit 1; fi
if [ ! -s out.txt ]; then echo "FAIL: no output"; exit 1; fi
if grep -qiE "Traceback \(most recent call last\)|ModuleNotFoundError|Cannot find module|panic:" out.txt; then
  echo "FAIL: output contains a crash message"; exit 1
fi
echo "PASS"
