#!/usr/bin/env python3
"""Read a "Make me an .exe" issue and decide whether a build is allowed.

Prints key=value records to $GITHUB_OUTPUT. The issue body is untrusted:
nothing in it is executed.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

HEAD_REPO = "GitHub repo URL"
HEAD_ARGS = "Test arguments"
# GitHub's repo size field is kilobytes of the git data, not a built program.
MAX_REPO_KB = 80_000
MAX_ARGS = 80

MESSAGES = {
    "missing-url": "Paste the GitHub link in the form. It should look like https://github.com/owner/name.",
    "not-github": "That doesn't look like a public GitHub link. Paste a link like https://github.com/owner/name. Other sites aren't accepted.",
    "not-found": "I couldn't find that GitHub project. Check the link, and make sure the project is public.",
    "private": "That project is private, or I can't see it. I can only build public projects on github.com.",
    "no-license": "That project doesn't have a license, so I won't publish a build of it.",
    "too-big": "That project is too big for a free build (over about 80 MB). Try a smaller one.",
    "bad-args": "Test arguments can only be simple flags, like --help or --version.",
}


def section(body, heading):
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    match = re.search(
        rf"(?m)^### {re.escape(heading)}\s*\n(.*?)(?=^### |\Z)",
        body,
        re.S,
    )
    if not match:
        return ""
    return match.group(1).strip()


def parse_repo(raw):
    """Return (owner/name, error_code). error_code is None when the slug is usable."""
    if not raw or raw.strip() in {"_No response_", "None"}:
        return None, "missing-url"
    text = raw.strip().splitlines()[0].strip().strip("<>")
    # Autolinked form values sometimes arrive as [label](url).
    link = re.search(r"\((https?://[^)\s]+)\)", text)
    if link:
        text = link.group(1)
    text = text.split("?")[0].split("#")[0].rstrip("/")
    text = re.sub(r"\.git$", "", text, flags=re.I)
    lowered = text.lower()
    hosted = "://" in lowered or lowered.startswith("git@")
    if hosted and not re.match(r"^(https?://([^/]+\.)?github\.com/|git@github\.com:)", lowered):
        return None, "not-github"
    match = re.match(
        r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$",
        text,
        re.I,
    )
    if not match:
        match = re.match(r"^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", text, re.I)
    if not match and not hosted:
        match = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", text)
    if not match:
        return None, "not-github"
    owner, name = match.group(1), match.group(2)
    if owner in {".", ".."} or name in {".", ".."}:
        return None, "not-github"
    if owner.lower() in {"settings", "topics", "marketplace", "features", "orgs", "apps", "sponsors"}:
        return None, "not-github"
    return f"{owner}/{name}", None


def clean_args(raw):
    text = (raw or "").strip()
    if text in {"", "_No response_", "None", "n/a", "N/A"}:
        return "--help", None
    if len(text) > MAX_ARGS or any(ch in text for ch in "\n\r\t"):
        return None, "bad-args"
    if not re.fullmatch(r"[A-Za-z0-9_./:+@,=-]+(?: [A-Za-z0-9_./:+@,=-]+)*", text):
        return None, "bad-args"
    return text, None


def github_json(url, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-to-exe",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response), response.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except urllib.error.URLError:
        return None, 0


def already_started(full_repo, number, token):
    if not number or str(number) in {"0", ""}:
        return False
    data, status = github_json(
        f"https://api.github.com/repos/{full_repo}/issues/{number}/comments?per_page=30",
        token,
    )
    if status != 200 or not isinstance(data, list):
        return False
    return any("<!-- r2e-started -->" in (comment.get("body") or "") for comment in data)


def emit(name, value):
    path = os.environ["GITHUB_OUTPUT"]
    delimiter = f"R2E_{name.upper()}_END"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def decide(body, token, full_repo, issue_number):
    slug, error = parse_repo(section(body, HEAD_REPO))
    args, arg_error = clean_args(section(body, HEAD_ARGS))
    if error:
        return {"ok": "false", "skip": "false", "message": MESSAGES[error], "repo": "", "test_args": ""}
    if arg_error:
        return {"ok": "false", "skip": "false", "message": MESSAGES[arg_error], "repo": slug, "test_args": ""}
    if already_started(full_repo, issue_number, token):
        return {"ok": "false", "skip": "true", "message": "", "repo": slug, "test_args": args}
    info, status = github_json(f"https://api.github.com/repos/{slug}", token)
    if status == 0:
        return {
            "ok": "false",
            "skip": "false",
            "message": "I couldn't check that link just now. Please open a new request in a few minutes.",
            "repo": slug,
            "test_args": "",
        }
    if status == 404 or info is None:
        return {"ok": "false", "skip": "false", "message": MESSAGES["not-found"], "repo": slug, "test_args": ""}
    if status != 200:
        return {
            "ok": "false",
            "skip": "false",
            "message": "I couldn't check that link just now. Please open a new request in a few minutes.",
            "repo": slug,
            "test_args": "",
        }
    if info.get("private") or info.get("visibility") in {"private", "internal"}:
        return {"ok": "false", "skip": "false", "message": MESSAGES["private"], "repo": slug, "test_args": ""}
    if not info.get("license"):
        return {"ok": "false", "skip": "false", "message": MESSAGES["no-license"], "repo": slug, "test_args": ""}
    size = info.get("size") or 0
    if size > MAX_REPO_KB:
        return {"ok": "false", "skip": "false", "message": MESSAGES["too-big"], "repo": slug, "test_args": ""}
    return {"ok": "true", "skip": "false", "message": "", "repo": slug, "test_args": args}


def main():
    result = decide(
        os.environ.get("ISSUE_BODY", ""),
        os.environ.get("GH_TOKEN", ""),
        os.environ.get("REPO_FULL", ""),
        os.environ.get("ISSUE_NUMBER", ""),
    )
    for key, value in result.items():
        emit(key, value)
    print(json.dumps(result))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        samples = {
            "url": "### GitHub repo URL\n\nhttps://github.com/davecheney/httpstat.git\n\n### Test arguments\n\n_No response_\n",
            "shorthand": "### GitHub repo URL\n\ndavecheney/httpstat\n",
            "gitlab": "### GitHub repo URL\n\nhttps://gitlab.com/foo/bar\n",
            "ssh": "### GitHub repo URL\n\ngit@github.com:davecheney/httpstat.git\n",
            "extra": "### GitHub repo URL\n\nhttps://github.com/foo/bar/issues/1\n",
            "inject": "### GitHub repo URL\n\nhttps://github.com/foo/bar\n\n### Test arguments\n\n--help; rm -rf /\n",
            "version": "### GitHub repo URL\n\nhttps://github.com/Foo/Bar\n\n### Test arguments\n\n-v\n",
        }
        for name, body in samples.items():
            slug, err = parse_repo(section(body, HEAD_REPO))
            args, arg_err = clean_args(section(body, HEAD_ARGS))
            print(f"{name}: repo={slug!r} err={err!r} args={args!r} arg_err={arg_err!r}")
        sys.exit(0)
    main()
