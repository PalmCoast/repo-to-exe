#!/usr/bin/env bash
# Repo-to-EXE build step. Runs on windows-latest under Git Bash.
# Env in: SRC (checked-out repo), OUT (output dir), LANG_ID, ENTRY, NAME, GUI (true/false), EXTRA (extra builder flags)
# Result: $OUT/$NAME.exe
set -euo pipefail
SRC="$(cd "$SRC" && pwd)"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
EXE="$OUT/$NAME.exe"
WORK="$(mktemp -d)"
echo "Building '$NAME' ($LANG_ID) from entry '$ENTRY' -> $EXE"
cd "$SRC"

case "$LANG_ID" in
python)
  python -m pip install --upgrade pip >/dev/null
  python -m pip install pyinstaller
  if [ -f pyproject.toml ] || [ -f setup.py ]; then
    python -m pip install .
  fi
  if [ -f requirements.txt ]; then python -m pip install -r requirements.txt || true; fi
  ARGS=(--onefile --noconfirm --clean --name "$NAME" --distpath "$OUT" --workpath "$WORK/build" --specpath "$WORK")
  [ "$GUI" = "true" ] && ARGS+=(--windowed)
  if [[ "$ENTRY" == *:* ]]; then
    MOD="${ENTRY%%:*}"; FUNC="${ENTRY#*:}"
    LAUNCH="$WORK/r2e_launcher.py"
    printf 'import sys\nfrom %s import %s as _entry\nif __name__ == "__main__":\n    sys.exit(_entry())\n' "$MOD" "${FUNC%%.*}" > "$LAUNCH"
    TOP="${MOD%%.*}"
    ARGS+=(--hidden-import "$MOD" --collect-submodules "$TOP")
    # package metadata so importlib.metadata.version() works inside the exe
    DIST="$(python - <<PY
import importlib.metadata as m
try:
    print(m.packages_distributions().get("$TOP", [""])[0])
except Exception:
    print("")
PY
)"
    [ -n "$DIST" ] && ARGS+=(--copy-metadata "$DIST")
  else
    LAUNCH="$SRC/$ENTRY"
    ARGS+=(--paths "$SRC")
  fi
  # shellcheck disable=SC2086
  python -m PyInstaller "${ARGS[@]}" ${EXTRA:-} "$LAUNCH"
  ;;
node)
  if [ -f package-lock.json ]; then npm ci --omit=dev --ignore-scripts || npm install --omit=dev --ignore-scripts
  elif [ -f package.json ]; then npm install --omit=dev --ignore-scripts; fi
  # copy the entry next to itself with a .js name so relative requires still resolve and esbuild knows the loader
  ENTRY_DIR="$(dirname "$ENTRY")"; SHIM="$ENTRY_DIR/__r2e_entry.js"
  cp "$ENTRY" "$SHIM"
  # Bundle everything into one CommonJS file. Optional packages that aren't installed
  # (e.g. spdy, fsevents) are marked external and retried, so they fail only if actually used.
  EXTS=()
  for attempt in 1 2 3 4 5 6; do
    # shellcheck disable=SC2086
    if npx --yes esbuild@0.24.2 "$SHIM" --bundle --platform=node --format=cjs --target=node22 \
        --outfile="$WORK/bundle.cjs" --log-level=error "${EXTS[@]}" ${EXTRA:-} 2> "$WORK/esbuild.err"; then
      break
    fi
    cat "$WORK/esbuild.err"
    MISSING=$(grep -oE 'Could not resolve "[^"]+"' "$WORK/esbuild.err" | sed -E 's/Could not resolve "([^"]+)"/\1/' | sort -u)
    if [ -z "$MISSING" ] || [ "$attempt" = 6 ]; then echo "esbuild failed"; exit 1; fi
    for m in $MISSING; do echo "Marking optional module '$m' as external"; EXTS+=("--external:$m"); done
  done
  rm -f "$SHIM"
  cd "$WORK"
  printf '{"main":"bundle.cjs","output":"sea-prep.blob","disableExperimentalSEAWarning":true}' > sea-config.json
  node --experimental-sea-config sea-config.json
  # Git Bash cannot cp the path Node prints on Windows ("C:\Program Files\nodejs\node.exe").
  node -e "require('fs').copyFileSync(process.execPath, 'sea.exe')"
  # Injecting into a signed node.exe makes Windows reject the image. The Windows SDK
  # on GitHub-hosted runners provides signtool; other systems skip this.
  SIG=""
  if command -v signtool >/dev/null 2>&1; then
    SIG="$(command -v signtool)"
  elif [ -d "/c/Program Files (x86)/Windows Kits/10/bin" ]; then
    SIG="$(find "/c/Program Files (x86)/Windows Kits/10/bin" -path '*/x64/signtool.exe' 2>/dev/null | sort | tail -1 || true)"
  fi
  if [ -n "$SIG" ]; then
    echo "Removing Authenticode signature before injection"
    MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1 "$SIG" remove /s sea.exe || echo "signtool remove failed; continuing"
  fi
  npx --yes postject@1.0.0-alpha.6 sea.exe NODE_SEA_BLOB sea-prep.blob \
      --sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2 --overwrite
  # $EXE may be a Git Bash path (/d/a/...) which Windows Node cannot open.
  EXE_DEST="$EXE" node <<'NODE'
const fs = require("fs");
const { execFileSync } = require("child_process");
let dest = process.env.EXE_DEST;
if (process.platform === "win32" && dest.startsWith("/")) {
  dest = execFileSync("cygpath", ["-w", dest], { encoding: "utf8" }).trim();
}
fs.copyFileSync("sea.exe", dest);
NODE
  ;;
go)
  LDF="-s -w"; [ "$GUI" = "true" ] && LDF="$LDF -H windowsgui"
  # shellcheck disable=SC2086
  CGO_ENABLED=${CGO_ENABLED:-0} GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "$LDF" ${EXTRA:-} -o "$EXE" "$ENTRY"
  ;;
rust)
  BIN_ARGS=(); [ -n "$ENTRY" ] && BIN_ARGS=(--bin "$ENTRY")
  # shellcheck disable=SC2086
  cargo build --release --locked "${BIN_ARGS[@]}" ${EXTRA:-} || cargo build --release "${BIN_ARGS[@]}" ${EXTRA:-}
  BUILT="target/release/${ENTRY:-$NAME}.exe"
  [ -f "$BUILT" ] || BUILT="$(ls target/release/*.exe | head -1)"
  cp "$BUILT" "$EXE"
  ;;
dotnet)
  # shellcheck disable=SC2086
  dotnet publish "$ENTRY" -c Release -r win-x64 --self-contained true \
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None \
    -o "$WORK/publish" ${EXTRA:-}
  BUILT="$WORK/publish/$(basename "${ENTRY%.*}").exe"
  [ -f "$BUILT" ] || BUILT="$(ls "$WORK"/publish/*.exe | head -1)"
  cp "$BUILT" "$EXE"
  ;;
*) echo "Unknown language '$LANG_ID'"; exit 2 ;;
esac

ls -la "$EXE"
echo "Built $(du -h "$EXE" | cut -f1) exe."
