#!/usr/bin/env python3
"""Repo-to-EXE detector.

Looks at a checked-out repo and decides which build recipe to use and what
the program's entry point is. Prints JSON, and also writes key=value lines to
$GITHUB_OUTPUT when running inside GitHub Actions.

Usage: python detect.py <repo_dir> [--lang LANG] [--entry ENTRY] [--name NAME]
"""
import json, os, re, sys, glob, argparse

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def safe_name(s):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-.")
    return s or "app"


def detect_dotnet(root):
    projs = [p for p in glob.glob(os.path.join(root, "**", "*.csproj"), recursive=True)
             if "test" not in p.lower()]
    projs += [p for p in glob.glob(os.path.join(root, "**", "*.fsproj"), recursive=True)
              if "test" not in p.lower()]
    exe = [p for p in projs if re.search(r"<OutputType>\s*(Win)?Exe\s*</OutputType>", read(p), re.I)]
    pick = (exe or projs or [None])[0]
    if not pick:
        return None
    gui = bool(re.search(r"<OutputType>\s*WinExe", read(pick), re.I)) or \
        bool(re.search(r"<Use(WPF|WindowsForms)>\s*true", read(pick), re.I))
    return {"lang": "dotnet", "entry": os.path.relpath(pick, root).replace("\\", "/"),
            "name": os.path.splitext(os.path.basename(pick))[0], "gui": gui}


def detect_rust(root):
    p = os.path.join(root, "Cargo.toml")
    if not os.path.exists(p):
        return None
    name, binname = None, None
    if tomllib:
        d = tomllib.loads(read(p))
        name = d.get("package", {}).get("name")
        bins = d.get("bin") or []
        if bins:
            binname = bins[0].get("name")
    return {"lang": "rust", "entry": binname or name or "",
            "name": binname or name or os.path.basename(os.path.abspath(root)), "gui": False}


def detect_go(root):
    if not os.path.exists(os.path.join(root, "go.mod")):
        return None
    mod = re.search(r"^module\s+(\S+)", read(os.path.join(root, "go.mod")), re.M)
    modname = mod.group(1).rstrip("/").split("/")[-1] if mod else os.path.basename(os.path.abspath(root))

    def is_main(d):
        for f in glob.glob(os.path.join(d, "*.go")):
            if f.endswith("_test.go"):
                continue
            if re.search(r"^package\s+main\b", read(f), re.M):
                return True
        return False

    if is_main(root):
        return {"lang": "go", "entry": ".", "name": modname, "gui": False}
    cands = sorted(d for d in glob.glob(os.path.join(root, "cmd", "*")) if os.path.isdir(d) and is_main(d))
    # prefer cmd/<module-name>
    for d in cands:
        if os.path.basename(d) == modname:
            return {"lang": "go", "entry": "./cmd/" + modname, "name": modname, "gui": False}
    if cands:
        b = os.path.basename(cands[0])
        return {"lang": "go", "entry": "./cmd/" + b, "name": b, "gui": False}
    for d, _, _ in os.walk(root):
        if "/vendor" in d.replace("\\", "/") or "/." in d.replace("\\", "/"):
            continue
        if is_main(d):
            rel = "./" + os.path.relpath(d, root).replace("\\", "/")
            return {"lang": "go", "entry": rel, "name": os.path.basename(d), "gui": False}
    return None


def detect_node(root):
    p = os.path.join(root, "package.json")
    if not os.path.exists(p):
        return None
    d = json.loads(read(p))
    name = (d.get("name") or os.path.basename(os.path.abspath(root))).split("/")[-1]
    b = d.get("bin")
    entry = None
    if isinstance(b, str):
        entry = b
    elif isinstance(b, dict) and b:
        entry = b.get(name) or next(iter(b.values()))
        if name not in b:
            name = next(iter(b.keys()))
    if not entry:
        entry = d.get("main") or "index.js"
    gui = "electron" in json.dumps(d.get("devDependencies", {})) + json.dumps(d.get("dependencies", {}))
    return {"lang": "node", "entry": entry.lstrip("./") if entry.startswith("./") else entry,
            "name": name, "gui": gui, "esm": d.get("type") == "module"}


GUI_PY = ("tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "kivy", "pygame", "customtkinter", "flet")


def detect_python(root):
    files = [os.path.join(root, f) for f in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")]
    pys = glob.glob(os.path.join(root, "*.py"))
    if not any(os.path.exists(f) for f in files) and not pys:
        return None
    name, entry = None, None
    pp = os.path.join(root, "pyproject.toml")
    if os.path.exists(pp) and tomllib:
        d = tomllib.loads(read(pp))
        proj = d.get("project", {})
        scripts = proj.get("scripts") or proj.get("gui-scripts") or \
            d.get("tool", {}).get("poetry", {}).get("scripts") or {}
        if scripts:
            name, entry = next(iter(scripts.items()))
            if isinstance(entry, dict):
                entry = entry.get("reference") or entry.get("callable")
        name = name or proj.get("name")
    if not entry:
        sc = os.path.join(root, "setup.cfg")
        if os.path.exists(sc):
            m = re.search(r"console_scripts\s*=\s*\n\s*(\S+)\s*=\s*(\S+)", read(sc))
            if m:
                name, entry = m.group(1), m.group(2)
    if not entry:
        sp = os.path.join(root, "setup.py")
        if os.path.exists(sp):
            m = re.search(r"['\"]([\w.-]+)\s*=\s*([\w.]+:[\w.]+)['\"]", read(sp))
            if m:
                name, entry = m.group(1), m.group(2)
    if not entry:
        # a top-level script with a __main__ guard; prefer main.py/app.py/<repo>.py
        repo = os.path.basename(os.path.abspath(root))
        order = ["main.py", "app.py", "cli.py", "__main__.py", repo + ".py"]
        cands = [p for p in pys if "__main__" in read(p)]
        cands.sort(key=lambda p: order.index(os.path.basename(p)) if os.path.basename(p) in order else 99)
        if cands:
            entry = os.path.basename(cands[0])
            name = name or (repo if entry in ("main.py", "app.py", "cli.py", "__main__.py") else entry[:-3])
    if not entry:
        return None
    gui = False
    blob = ""
    for f in pys[:50] + files:
        if os.path.exists(f):
            blob += read(f)
    if re.search(r"^\s*(import|from)\s+(%s)\b" % "|".join(GUI_PY), blob, re.M):
        gui = True
    return {"lang": "python", "entry": entry, "name": name or "app", "gui": gui}


ORDER = [detect_dotnet, detect_rust, detect_go, detect_node, detect_python]
BY_LANG = {"dotnet": detect_dotnet, "rust": detect_rust, "go": detect_go,
           "node": detect_node, "python": detect_python}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--lang", default="")
    ap.add_argument("--entry", default="")
    ap.add_argument("--name", default="")
    a = ap.parse_args()
    res = None
    if a.lang:
        res = BY_LANG[a.lang](a.root) or {"lang": a.lang, "entry": "", "name": "", "gui": False}
    else:
        for fn in ORDER:
            res = fn(a.root)
            if res:
                break
    if not res:
        print(json.dumps({"error": "Could not tell what language this repo is in."}))
        sys.exit(2)
    if a.entry:
        res["entry"] = a.entry
    if a.name:
        res["name"] = a.name
    res["name"] = safe_name(res["name"])
    res["gui"] = bool(res.get("gui"))
    print(json.dumps(res))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k in ("lang", "entry", "name"):
                f.write(f"{k}={res.get(k, '')}\n")
            f.write(f"gui={'true' if res['gui'] else 'false'}\n")
            f.write(f"esm={'true' if res.get('esm') else 'false'}\n")


if __name__ == "__main__":
    main()
