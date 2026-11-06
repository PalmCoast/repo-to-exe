---
name: repo-to-exe
description: Turn any public GitHub repo into a tested, downloadable Windows .exe with free GitHub Actions, and explain it to a non-technical person.
---

# Repo to EXE: bot instructions

Central repo: https://github.com/PalmCoast/repo-to-exe (owner: PalmCoast, Daniel Graham).
Workflow: `.github/workflows/build-exe.yml` ("Build EXE from a GitHub repo"). Public path: a "Make me an .exe" issue (`.github/ISSUE_TEMPLATE/build-exe.yml` and `.github/workflows/issue-build.yml`). Scripts: `scripts/detect.py`, `scripts/build.sh`, `scripts/test-exe.sh`.

People with no setup use the issue form: https://github.com/PalmCoast/repo-to-exe/issues/new?template=build-exe.yml . That workflow checks the link, runs one build, and comments in plain English. One build per issue. 20 minute cap. It turns down private repos, non-GitHub links, projects over about 80 MB, and programs over 200 MB. Don't open that issue on someone else's repo.

## Inputs
- **repo** (required): `owner/name` of a public repo. Private repos need a token with access, so don't promise them.
- **ref**: branch, tag or SHA. Leave blank for the default branch. Prefer the latest release tag if the default branch is unstable.
- **test_args**: what the smoke test passes to the exe. Defaults to `--help`. Use `--version` or `-v` if `--help` exits non-zero. `rakyll/hey` defines `-h` as a header flag, so `hey -h` exits 2; `--help` exits 0 and prints usage.
- **lang / entry / name / extra**: overrides, used only when auto-detect is wrong (see edge cases).
- Always confirm the license is permissive (MIT, Apache-2.0, BSD, ISC) before you publish a build. GPL is OK if you ship the source link and license (the release already does). With no license, don't publish. Build for the user privately at most.

## Steps
1. **Check first.** `gh api repos/OWNER/NAME --jq .license.spdx_id` and `gh release list -R OWNER/NAME`. If upstream already ships a Windows `.exe`, send the user that link instead of building.
2. **Dry-run detection** (optional): clone shallow to /tmp and run `python3 scripts/detect.py /tmp/NAME`. It prints `{"lang","entry","name","gui"}`.
3. **Run the workflow:**
   `gh workflow run build-exe.yml -R PalmCoast/repo-to-exe -f repo=OWNER/NAME -f test_args="--help"`
   Then `gh run list -R PalmCoast/repo-to-exe -w build-exe.yml -L 1` and `gh run watch <id> -R PalmCoast/repo-to-exe --exit-status`.
4. **Read the smoke test**, not just the green check: `gh run view <id> --log | grep -A40 "Repo-to-EXE smoke test"`. Confirm exit code 0 and output that looks like the tool's real help or version text.
5. **Get the link:** release tag is `<name>-<shortsha>`. The download URL is
   `https://github.com/PalmCoast/repo-to-exe/releases/download/<tag>/<name>.exe`. Check it with `curl -sIL <url> | head -1`.
6. **Report** to the user in plain words (template below). Only say "tested" if step 4 really passed.

For a repo the user owns, they can instead copy `templates/exe-release.yml` into their repo. Every `v*` tag then publishes the exe on their own Releases page.

Pushing workflow files needs a token with the `workflow` scope. The box's `gh` login has `repo` only, so changes under `.github/workflows/` must go through a cloud agent or a user-run `gh auth refresh -s workflow`. Scripts and README can be pushed normally.

## How detection works (priority order)
`.csproj/.fsproj` → .NET; `Cargo.toml` → Rust; `go.mod` → Go (root `package main`, else `cmd/<module>`, else first `main` package); `package.json` → Node (`bin` entry, else `main`); Python (`[project.scripts]` / poetry scripts / `console_scripts` / a top-level `.py` with `__main__`).
A repo with several languages (e.g. a Python app with a `package.json` for docs) can mis-detect. Force `lang`.

## Edge cases and fixes
- **Python native deps** (numpy, cryptography, lxml): wheels exist for Windows and PyInstaller handles them. Missing DLLs or data files: add `extra="--collect-all pkgname"`. Hidden plugin imports: `--hidden-import mod`. Things that need a C compiler with no wheel: usually fail. Tell the user.
- **Python data files** (templates, JSON next to code): `--collect-data pkg` or `--add-data "src;dest"` (Windows uses `;`).
- **Python version lookups** (`importlib.metadata.version`): the build copies the package metadata automatically. If `--version` still crashes, add `--copy-metadata distname`.
- **Node ESM with top-level await**: the CJS bundle fails. Try `extra="--format=esm"` (needs Node ≥ 22 ESM SEA support), or tell the user it isn't supported yet. **Native addons (`.node`)** and **files read at runtime via `__dirname`** don't work inside a single exe. Say so rather than shipping a broken file. Optional deps that aren't installed (e.g. `spdy`) are auto-marked external.
- **Node exe size** is about 80–120 MB because it carries Node itself. That's normal. Say so.
- **Go with cgo** (sqlite3, GUI toolkits): set `CGO_ENABLED=1` needs MinGW, which isn't wired up. Pick a pure-Go driver or report it.
- **GUI vs CLI**: detect.py flags GUI (tkinter/PyQt/wx/pygame, WinExe .csproj, electron). Python GUI builds add `--windowed` (no console window). The smoke test then only checks the file is a valid exe unless you pass `test_args`. Electron apps are out of scope: use electron-builder instead.
- **Windows-only paths and POSIX calls**: code using `/usr/share`, `os.fork`, `fcntl`, `signal.SIGKILL`, `termios` or `~/.config` assumptions builds fine but crashes at runtime. The smoke test catches crashes on `--help`. Deeper features may still break, so tell the user it's tested for startup, not every feature.
- **Tools that need a network or argument to exit 0**: choose `test_args` that print and exit, like `--version`.
- **Monorepos**: pass `entry` (path to the main package, `cmd/x`, the `bin` file or the `.csproj`).
- **Long builds** (Rust or .NET with many deps) can take 10–20 min. The job timeout is 45 min.

## Explaining it to a non-technical user
Use short, plain sentences. Don't say "artifact", "CI", "PE" or "binary". Template:

> Here's **<Name> for Windows**: <download link>
> It's one file. There's nothing to install. I ran it on a fresh Windows machine first and it started up and worked.
> The first time you open it, Windows may say **"Windows protected your PC"**. That happens because the file is new and not signed with a paid certificate. Click **More info → Run anyway**.
> It runs in a terminal: open the folder you saved it in, type `cmd` in the address bar, press Enter, then type `<name>.exe --help`.
> This is an unofficial build of <owner/repo>. Credit goes to its authors.

Never claim it's signed, virus-checked or official. Never buy a signing certificate without the user's explicit OK. Don't open issues or PRs on the upstream repo.
