#!/usr/bin/env bash
# Runs the built exe for real and fails the job unless it exits 0 with some output.
# Env in: EXE, TEST_ARGS (e.g. "--help"), GUI, LOG (where to write the test log)
set -uo pipefail
: "${LOG:=test-log.txt}"
mkdir -p outcome
REPORT="$(cd outcome && pwd)"
note_result() { printf '%s\n' "$1" > "$REPORT/result.txt"; printf '%s\n' "$2" > "$REPORT/result-detail.txt"; }
{
  echo "Repo-to-EXE smoke test"
  echo "Runner: $(uname -a) | $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "File: $(basename "$EXE")  size: $(stat -c %s "$EXE") bytes"
  echo "PE header: $(head -c 2 "$EXE")"
} > "$LOG"
if [ "$(head -c 2 "$EXE")" != "MZ" ]; then
  echo "FAIL: not a Windows executable" | tee -a "$LOG"
  note_result "not-exe" "The file that was built isn't a Windows program."
  exit 1
fi
if [ "$GUI" = "true" ] && [ -z "${TEST_ARGS:-}" ]; then
  echo "GUI app and no test args given: checked it is a valid .exe but did not open a window." | tee -a "$LOG"
  note_result "pass" ""
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
echo "----- output -----" >> "$LOG"
if [ -f out.txt ]; then cat out.txt >> "$LOG"; else printf '%s\n' "(no output file)" >> "$LOG"; fi
cat "$LOG"
if [ "$CODE" -eq 124 ]; then note_result "timeout" "I ran it on Windows and it didn't finish within 2 minutes."; echo "FAIL: timed out"; exit 1; fi
if [ "$CODE" -ne 0 ]; then note_result "exit-code" "I ran it on Windows and it stopped with an error (exit code $CODE) instead of printing help."; echo "FAIL: exit code $CODE"; exit 1; fi
if [ ! -s out.txt ]; then note_result "no-output" "I ran it on Windows and it didn't print anything, so I didn't publish it."; echo "FAIL: no output"; exit 1; fi
if grep -qiE "Traceback \(most recent call last\)|ModuleNotFoundError|Cannot find module|panic:" out.txt; then
  note_result "crash" "I ran it on Windows and it crashed when it started."
  echo "FAIL: output contains a crash message"; exit 1
fi
# One short line of what it actually printed, for the reply on the issue.
SNIP=$(head -n 1 out.txt | tr -d '\r' | tr -cd '\11\12\15\40-\176' | cut -c 1-160)
printf '%s\n' "$SNIP" > "$REPORT/result-snippet.txt"
note_result "pass" ""
echo "PASS"
