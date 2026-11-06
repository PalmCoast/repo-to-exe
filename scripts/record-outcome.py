#!/usr/bin/env python3
"""Copy the build's short result into GitHub Actions job outputs."""
import os
from pathlib import Path


def emit(name, value):
    path = os.environ["GITHUB_OUTPUT"]
    delimiter = f"R2E_{name.upper()}_END"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def read(path):
    file = Path(path)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8", errors="replace").strip()


FALLBACK = {
    "build-failed": "I couldn't build that project. It may use a language I don't know, or the build stopped with an error.",
    "unknown-lang": "I couldn't tell how to build that project. It needs to be Python, Node, Go, Rust, or C#.",
    "too-large": "The program came out bigger than 200 MB, so I didn't publish it.",
    "not-exe": "The file that was built isn't a Windows program.",
    "timeout": "I ran it on Windows and it didn't finish within 2 minutes.",
    "exit-code": "I ran it on Windows and it stopped with an error instead of printing help.",
    "no-output": "I ran it on Windows and it didn't print anything, so I didn't publish it.",
    "crash": "I ran it on Windows and it crashed when it started.",
}


def main():
    result = read("outcome/result.txt") or "build-failed"
    detail = read("outcome/result-detail.txt") or FALLBACK.get(result, FALLBACK["build-failed"])
    snippet = read("outcome/result-snippet.txt").replace("`", "'")[:160]
    emit("name", os.environ.get("NAME", ""))
    emit("tag", os.environ.get("TAG", ""))
    emit("sha", os.environ.get("SHA", ""))
    emit("lang", os.environ.get("LANG_ID", ""))
    emit("test_result", result)
    emit("detail", detail if result != "pass" else "")
    emit("snippet", snippet)


if __name__ == "__main__":
    main()
