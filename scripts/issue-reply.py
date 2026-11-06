#!/usr/bin/env python3
"""Comment on the request issue in plain language, and close it when the exe works.

Uses the REST API. The workflow token has issues: write; this does not need GraphQL.
"""
import json
import os
import subprocess


def api(method, path, payload=None):
    args = ["gh", "api", "--method", method, path]
    kwargs = {"check": True}
    if payload is not None:
        args.append("--input")
        args.append("-")
        kwargs["input"] = json.dumps(payload)
        kwargs["text"] = True
    subprocess.run(args, **kwargs)


def comment(repo, number, body):
    api("POST", f"repos/{repo}/issues/{number}/comments", {"body": body})


def close_completed(repo, number):
    api("PATCH", f"repos/{repo}/issues/{number}", {"state": "closed", "state_reason": "completed"})


def asset_exists(url):
    """Release downloads answer 302 before the file bytes. Don't download the exe."""
    if not url:
        return False
    result = subprocess.run(
        ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() in {"200", "302"}


def already_replied(repo, number):
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}/comments?per_page=30"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return "<!-- r2e-result -->" in result.stdout


def main():
    repo = os.environ["GH_REPO"]
    number = os.environ["ISSUE_NUMBER"]
    mode = os.environ.get("MODE", "result")
    if already_replied(repo, number):
        print("Already replied. Not commenting again.")
        return
    if mode == "reject":
        message = (os.environ.get("MSG") or "I couldn't use that request.").strip()
        comment(
            repo,
            number,
            message + "\n\nYou can open a new request with a different link.\n\n<!-- r2e-result -->\n",
        )
        return
    if mode == "oops":
        comment(
            repo,
            number,
            "Something went wrong on my side before the build started.\n\n"
            f"The log is here: {os.environ.get('RUN_URL', '')}\n\n"
            "<!-- r2e-result -->\n",
        )
        return
    job = os.environ.get("JOB_RESULT", "failure")
    name = os.environ.get("NAME", "") or "the program"
    url = os.environ.get("DOWNLOAD_URL", "")
    detail = (os.environ.get("DETAIL") or "").strip()
    snippet = (os.environ.get("SNIPPET") or "").strip().replace("`", "'")
    source = os.environ.get("SOURCE_REPO", "")
    test_args = os.environ.get("TEST_ARGS") or "--help"
    run_url = os.environ["RUN_URL"]

    if job == "success" and url and asset_exists(url):
        printed = f"\nIt printed: `{snippet}`\n" if snippet else ""
        body = f"""Here's **{name} for Windows**: {url}

It's one file. There's nothing to install. I ran it on a fresh Windows machine and it started up and worked.
{printed}
The first time you open it, Windows may say **"Windows protected your PC"**. The file is new and isn't signed with a paid certificate. Click **More info**, then **Run anyway**.

It runs in a terminal. Save the file, open that folder, click the address bar, type `cmd`, press Enter, then type `{name}.exe {test_args}`.

This is an unofficial build of [{source}](https://github.com/{source}). Credit goes to its authors.

<!-- r2e-result -->
"""
        comment(repo, number, body)
        close_completed(repo, number)
        return

    if job == "cancelled":
        why = "The build took too long, so I stopped it. The limit is 20 minutes."
    elif detail:
        why = detail
    else:
        why = "The build stopped before it could finish."
    body = f"""I couldn't turn that project into a working Windows program.

{why}

The full log is here: {run_url}

You can open a new request and try again. If the program needs a special flag to print help and quit, put that in "Test arguments" (for example `--version`).

<!-- r2e-result -->
"""
    comment(repo, number, body)


if __name__ == "__main__":
    main()
