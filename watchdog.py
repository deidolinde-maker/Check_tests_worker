#!/usr/bin/env python3
"""Restart overdue Jenkins jobs without creating parallel test runs."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Target:
    job: str
    max_age_minutes: int
    max_runtime_minutes: int
    parameters: dict[str, str]
    group: str | None


def load_targets(path: str) -> list[Target]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("targets.json must contain a list")

    targets = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each target must be an object")
        targets.append(
            Target(
                job=str(item["job"]),
                max_age_minutes=int(item["max_age_minutes"]),
                max_runtime_minutes=int(item["max_runtime_minutes"]),
                parameters={str(key): str(value) for key, value in (item.get("parameters") or {}).items()},
                group=str(item["group"]) if item.get("group") else None,
            )
        )
    return targets


def job_path(job_name: str) -> str:
    return "/".join(f"job/{urllib.parse.quote(part, safe='')}" for part in job_name.split("/"))


def api_url(base_url: str, job_name: str) -> str:
    return f"{base_url.rstrip('/')}/{job_path(job_name)}/api/json"


def request_json(url: str, username: str, token: str) -> dict[str, Any]:
    credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Jenkins response from {url}")
    return payload


def request_crumb(base_url: str, username: str, token: str) -> tuple[str, str] | None:
    try:
        data = request_json(f"{base_url.rstrip('/')}/crumbIssuer/api/json", username, token)
    except urllib.error.HTTPError as error:
        if error.code in (403, 404):
            return None
        raise
    return str(data["crumbRequestField"]), str(data["crumb"])


def queued_jobs(base_url: str, username: str, token: str) -> set[str]:
    data = request_json(f"{base_url.rstrip('/')}/queue/api/json", username, token)
    jobs = set()
    for item in data.get("items", []):
        task = item.get("task") or {}
        task_name = task.get("name")
        task_url = (task.get("url") or "").rstrip("/")
        if task_name:
            jobs.add(str(task_name))
        if task_url:
            jobs.add(task_url)
    return jobs


def is_queued(job_name: str, queued: set[str], base_url: str) -> bool:
    return job_name in queued or f"{base_url.rstrip('/')}/{job_path(job_name)}" in queued


def trigger_job(
    base_url: str,
    job_name: str,
    username: str,
    token: str,
    parameters: dict[str, str] | None = None,
) -> None:
    credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}
    crumb = request_crumb(base_url, username, token)
    if crumb:
        headers[crumb[0]] = crumb[1]
    endpoint = "buildWithParameters" if parameters else "build"
    url = f"{base_url.rstrip('/')}/{job_path(job_name)}/{endpoint}"
    body = urllib.parse.urlencode(parameters or {}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=20):
        return


def decide_action(job_data: dict[str, Any], now_ms: int, target: Target) -> str:
    last_build = job_data.get("lastBuild") or {}
    if last_build.get("building"):
        started_at = int(last_build.get("timestamp") or now_ms)
        runtime_minutes = max(0, now_ms - started_at) / 60_000
        if runtime_minutes > target.max_runtime_minutes:
            return "running-too-long"
        return "running"

    completed = job_data.get("lastCompletedBuild") or {}
    completed_at = completed.get("timestamp")
    if not completed_at:
        return "trigger"
    age_minutes = max(0, now_ms - int(completed_at)) / 60_000
    return "trigger" if age_minutes > target.max_age_minutes else "healthy"


def select_group_recovery_target(
    targets: list[Target], data_by_job: dict[str, dict[str, Any]], queued: set[str], base_url: str, now_ms: int
) -> Target | None:
    """Return only the first chain target when the whole group is idle."""
    if any(
        (data_by_job[target.job].get("lastBuild") or {}).get("building")
        or is_queued(target.job, queued, base_url)
        for target in targets
    ):
        return None
    return targets[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", default="targets.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_url = os.environ.get("JENKINS_URL", "").strip()
    username = os.environ.get("JENKINS_API_USER", "").strip()
    token = os.environ.get("JENKINS_API_TOKEN", "").strip()
    if not base_url or not username or not token:
        print("[WATCHDOG] JENKINS_URL, JENKINS_API_USER and JENKINS_API_TOKEN are required", file=sys.stderr)
        return 2

    exit_code = 0
    now_ms = int(time.time() * 1000)
    targets = load_targets(args.targets)
    try:
        queued = queued_jobs(base_url, username, token)
        print(f"[WATCHDOG] queued jobs: {len(queued)}")
    except Exception as error:
        print(f"[WATCHDOG] failed to read Jenkins queue: {error}", file=sys.stderr)
        return 1
    grouped: dict[str, list[Target]] = {}
    for target in targets:
        if target.group:
            grouped.setdefault(target.group, []).append(target)

    target_data: dict[str, dict[str, Any]] = {}
    for target in targets:
        try:
            target_data[target.job] = request_json(api_url(base_url, target.job), username, token)
        except Exception as error:
            exit_code = 1
            print(f"[WATCHDOG] failed for {target.job}: {error}", file=sys.stderr)

    handled = set()
    for group_name, group_targets in grouped.items():
        if any(target.job not in target_data for target in group_targets):
            continue
        handled.update(target.job for target in group_targets)
        running = [target.job for target in group_targets if (target_data[target.job].get("lastBuild") or {}).get("building")]
        if running:
            print(f"[WATCHDOG] group={group_name} healthy: active={', '.join(running)}")
            continue
        recovery_target = select_group_recovery_target(group_targets, target_data, queued, base_url, now_ms)
        if recovery_target is None:
            print(f"[WATCHDOG] group={group_name} healthy: active or queued build exists")
            continue
        print(f"[WATCHDOG] group={group_name} action=trigger job={recovery_target.job}")
        if args.dry_run:
            print(f"[WATCHDOG] dry-run: would trigger {recovery_target.job}")
        else:
            try:
                trigger_job(base_url, recovery_target.job, username, token, recovery_target.parameters)
                print(f"[WATCHDOG] triggered {recovery_target.job}")
            except Exception as error:
                exit_code = 1
                print(f"[WATCHDOG] failed to trigger {recovery_target.job}: {error}", file=sys.stderr)

    for target in targets:
        if target.job in handled or target.job not in target_data:
            continue
        if is_queued(target.job, queued, base_url):
            print(f"[WATCHDOG] job={target.job} action=queued")
            continue
        action = decide_action(target_data[target.job], now_ms, target)
        print(f"[WATCHDOG] job={target.job} action={action}")
        if action == "trigger":
            if args.dry_run:
                print(f"[WATCHDOG] dry-run: would trigger {target.job}")
            else:
                try:
                    trigger_job(base_url, target.job, username, token, target.parameters)
                    print(f"[WATCHDOG] triggered {target.job}")
                except Exception as error:
                    exit_code = 1
                    print(f"[WATCHDOG] failed to trigger {target.job}: {error}", file=sys.stderr)
        elif action == "running-too-long":
            print(f"[WATCHDOG] alert: {target.job} is running longer than allowed", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
