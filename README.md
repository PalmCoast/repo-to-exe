# Repo to EXE

**Turn a GitHub project into a Windows program you can double-click. Nobody has to install Python, Node or anything else.**

Lots of useful tools on GitHub only come as source code. To run them you'd normally have to install a programming language, open a terminal and type setup commands. Repo to EXE does all of that on GitHub's free build machines and gives you back one file: `something.exe`.

## Download the ready-made programs

Each one was built and then **run once for real on a clean Windows machine** before it was published:

| Program | What it does | Original project | Download |
|---|---|---|---|
| tldr | Short, plain-English cheat sheets for terminal commands | [tldr-pages/tldr-python-client](https://github.com/tldr-pages/tldr-python-client) (Python, MIT) | [tldr.exe](https://github.com/PalmCoast/repo-to-exe/releases/download/tldr-c33ca6d/tldr.exe) |
| hey | Load-tests a website by sending it lots of requests | [rakyll/hey](https://github.com/rakyll/hey) (Go, Apache-2.0) | [hey.exe](https://github.com/PalmCoast/repo-to-exe/releases/download/hey-5626f79/hey.exe) |
| http-server | Shares a folder as a website on your computer, with no setup | [http-party/http-server](https://github.com/http-party/http-server) (Node.js, MIT) | [http-server.exe](https://github.com/PalmCoast/repo-to-exe/releases/download/http-server-0d3b7bb/http-server.exe) |

Every release includes the `.exe`, a test log showing what happened when it ran, a SHA-256 checksum and the original project's license. These are unofficial builds, and all credit goes to the original authors.

### "Windows protected your PC"? Read this first
These `.exe` files are new and aren't **code-signed**. A signing certificate is a paid ID card for software. When Windows sees an unsigned file it hasn't seen before, SmartScreen shows a blue warning.

1. Click **More info**.
2. Click **Run anyway**.

The warning doesn't mean the file is broken or harmful. It means Windows doesn't recognize the publisher yet. If you want to be sure, check that the file's SHA-256 matches the `.sha256` file in the release (`certutil -hashfile hey.exe SHA256` in Command Prompt).

### How to run a command-line program
Most of these tools don't open a window. They run in a terminal:

1. Download the `.exe` into a folder, for example `Downloads`.
2. Open that folder in File Explorer, click the address bar, type `cmd` and press Enter.
3. Type the program name with `--help`, for example `tldr.exe --help`, and press Enter.

## Make an .exe from any other repo

1. Open the **Actions** tab of this repo, choose **Build EXE from a GitHub repo** and click **Run workflow**.
2. Type the repo, for example `owner/name`. Leave everything else blank.
3. Wait about 2–10 minutes. The new download shows up under **Releases**.

The bot works out the language itself:

| It finds… | It builds with… |
|---|---|
| `pyproject.toml` / `setup.py` / `requirements.txt` / a `.py` script | PyInstaller `--onefile` |
| `package.json` | esbuild bundle → Node.js Single Executable Application |
| `go.mod` | `go build` (static, no DLLs) |
| `Cargo.toml` | `cargo build --release` |
| `*.csproj` / `*.fsproj` | `dotnet publish` self-contained single file |

If it guesses wrong, fill in the optional boxes (`lang`, `entry`, `name`, `test_args`, `extra`).

### Add it to your own repo or fork
Copy [`templates/exe-release.yml`](templates/exe-release.yml) to `.github/workflows/` in your repo. Every `v*` tag then gets a tested `.exe` on that repo's Releases page.

## How it works (for developers)
- `scripts/detect.py` reads the repo's files and picks the language, entry point, program name and whether it's a GUI app.
- `scripts/build.sh` runs the matching recipe on `windows-latest` (Git Bash).
- `scripts/test-exe.sh` runs the built `.exe` with `--help` (or your `test_args`) and fails the build unless it exits with code 0, prints something and shows no crash trace.
- `.github/workflows/build-exe.yml` ties it together, uploads an artifact and publishes a GitHub Release. It runs entirely on free GitHub Actions.

## Limits, honestly
- No code signing, so expect the SmartScreen warning above.
- Python packages with compiled parts usually work. Ones that need system DLLs or data files might need `extra` flags such as `--collect-all pkgname`.
- Node projects that read their own files from disk at runtime (templates, images) or use native `.node` addons may not work as one file.
- Windows only. Code that hard-codes `/usr/...` paths or POSIX-only calls will build fine but fail when it runs. The smoke test is there to catch exactly that.

MIT licensed.
