#!/usr/bin/env python3
"""Zero-dependency provisioner for `cron-job.org` -> `jamietan2002/trader` `workflow_dispatch` ($0/month).

Creates/updates all 4 DST-aware (`America/New_York` & `UTC`) webhook schedules for `trader`
via the official `cron-job.org` REST API. (For `spy-daytrader`, use the dedicated script in
`spy-daytrader/infrastructure/cloudflare_cron/setup_cronjob_org.py`.)

Usage:
    # Preview exact JSON payloads without network calls (no secrets needed):
    .venv/bin/python infrastructure/cloudflare_cron/setup_cronjob_org.py --dry-run

    # Provision / update all 4 `trader` schedules on cron-job.org:
    CRONJOB_API_KEY="..." GITHUB_PAT="..." \
      .venv/bin/python infrastructure/cloudflare_cron/setup_cronjob_org.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List

CRONJOB_API_BASE = "https://api.cron-job.org"


def build_dispatch_job_specs(github_owner: str, github_pat: str) -> List[Dict[str, Any]]:
    """Build the 4 idempotent `cron-job.org` job definitions for `jamietan2002/trader`."""

    url = f"https://api.github.com/repos/{github_owner}/trader/actions/workflows/autonomous_trading.yml/dispatches"
    common_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_pat}",
        "Content-Type": "application/json",
        "User-Agent": "trader-cronjob-org-dispatcher/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    raw_specs = [
        {
            "title": "[trader] Stage 2 Pre-Open Refresh (09:00 ET)",
            "timezone": "America/New_York",
            "hours": [9],
            "minutes": [0],
            "wdays": [1, 2, 3, 4, 5],
            "body": {"ref": "main", "inputs": {"mode": "daily"}},
        },
        {
            "title": "[trader] Stage 3 Market-Open Execution (09:35 ET)",
            "timezone": "America/New_York",
            "hours": [9],
            "minutes": [35],
            "wdays": [1, 2, 3, 4, 5],
            "body": {"ref": "main", "inputs": {"mode": "daily"}},
        },
        {
            "title": "[trader] Stage 1 Post-Close Reconciliation (16:30 ET)",
            "timezone": "America/New_York",
            "hours": [16],
            "minutes": [30],
            "wdays": [1, 2, 3, 4, 5],
            "body": {"ref": "main", "inputs": {"mode": "daily"}},
        },
        {
            "title": "[trader] Weekly 9-Gate Strategy Tournament (Sat 02:00 UTC / 10:00 SGT)",
            "timezone": "UTC",
            "hours": [2],
            "minutes": [0],
            "wdays": [6],
            "body": {"ref": "main", "inputs": {"mode": "weekly"}},
        },
    ]

    jobs: List[Dict[str, Any]] = []
    for item in raw_specs:
        jobs.append(
            {
                "title": item["title"],
                "url": url,
                "enabled": True,
                "saveResponses": True,
                "requestMethod": 1,  # 1 = HTTP POST in cron-job.org API
                "requestTimeout": 30,
                "schedule": {
                    "timezone": item["timezone"],
                    "expiresAt": 0,
                    "hours": item["hours"],
                    "mdays": [-1],
                    "minutes": item["minutes"],
                    "months": [-1],
                    "wdays": item["wdays"],
                },
                "extendedData": {
                    "headers": dict(common_headers),
                    "body": json.dumps(item["body"]),
                },
            }
        )
    return jobs


def _cronjob_api_request(method: str, path: str, api_key: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{CRONJOB_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity-cronjob-provisioner/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision DST-aware GitHub workflow_dispatch jobs for trader")
    parser.add_argument("--owner", default=os.environ.get("GITHUB_OWNER", "jamietan2002"), help="GitHub owner/org")
    parser.add_argument("--dry-run", action="store_true", help="Print scrubbed job specs without calling the API")
    args = parser.parse_args(argv)

    if args.dry_run:
        specs = build_dispatch_job_specs(args.owner, "<REDACTED_GITHUB_PAT>")
        print(json.dumps({"job_count": len(specs), "jobs": specs}, indent=2))
        return 0

    cronjob_key = os.environ.get("CRONJOB_API_KEY", "").strip()
    github_pat = os.environ.get("GITHUB_PAT", "").strip()
    if not cronjob_key or not github_pat:
        print(
            "ERROR: Both CRONJOB_API_KEY and GITHUB_PAT environment variables are required (or pass --dry-run).",
            file=sys.stderr,
        )
        return 1

    existing_resp = _cronjob_api_request("GET", "/jobs", cronjob_key)
    existing_by_title = {
        str(j.get("title", "")): int(j["jobId"])
        for j in (existing_resp.get("jobs") or [])
        if j.get("jobId") is not None
    }

    specs = build_dispatch_job_specs(args.owner, github_pat)
    for job in specs:
        title = job["title"]
        if title in existing_by_title:
            job_id = existing_by_title[title]
            _cronjob_api_request("PATCH", f"/jobs/{job_id}", cronjob_key, {"job": job})
            print(f"[UPDATED] jobId={job_id} :: {title}")
        else:
            created = _cronjob_api_request("PUT", "/jobs", cronjob_key, {"job": job})
            print(f"[CREATED] jobId={created.get('jobId')} :: {title}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
