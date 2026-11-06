#!/usr/bin/env python3
"""Tell the person their Windows build has started. One comment per issue."""
import json
import os
import subprocess

body = f"""I got your request for `{os.environ['REPO']}`.

I'm building it now on a Windows machine. This usually takes a few minutes. I'll comment again with the download link.

<!-- r2e-started -->
"""
repo = os.environ["GH_REPO"]
number = os.environ["ISSUE_NUMBER"]
subprocess.run(
    ["gh", "api", "--method", "POST", f"repos/{repo}/issues/{number}/comments", "--input", "-"],
    input=json.dumps({"body": body}),
    text=True,
    check=True,
)
