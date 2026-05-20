"""Jira Cloud Automation REST API client."""

from __future__ import annotations

import httpx
from rich.console import Console

console = Console(stderr=True)


def get_cloud_id(client: httpx.Client, host: str) -> str:
    """Retrieve the Atlassian Cloud ID for a given host."""
    url = f"https://{host}/_edge/tenant_info"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()["cloudId"]


def fetch_rules_summary(
    client: httpx.Client, host: str, cloud_id: str
) -> list[dict]:
    """Fetch all automation rule summaries.

    Why ?limit=1000:
        The upstream /rule/summary endpoint has a cursor-based pagination defect.
        On a tenant with ~180 rules across multiple pages:
        - default paging: duplicated records across page boundaries, missed rules
        - ?limit=1000 (single shot): all unique, no misses
        Setting a large limit makes the server respond in a single batch which
        avoids the bug. The cursor loop is retained as a fallback for tenants
        that exceed 1000 rules. uuid-based dedupe is applied unconditionally as
        a safety net.
    """
    base_path = (
        f"https://{host}/gateway/api/automation/public/jira/{cloud_id}"
        f"/rest/v1/rule/summary"
    )
    seen: dict[str, dict] = {}
    seen_cursors: set[str] = set()
    url = f"{base_path}?limit=1000"

    while url:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("data", []):
            uuid = r.get("uuid")
            if uuid:
                seen[uuid] = r

        next_cursor = data.get("links", {}).get("next")
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        url = f"{base_path}{next_cursor}"

    return list(seen.values())


def fetch_rule_detail(
    client: httpx.Client, host: str, cloud_id: str, uuid: str
) -> dict:
    """Fetch a single rule's full definition by UUID."""
    url = (
        f"https://{host}/gateway/api/automation/public/jira/{cloud_id}"
        f"/rest/v1/rule/{uuid}"
    )
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def build_client(user: str, token: str) -> httpx.Client:
    """Create an httpx Client with Basic auth and sensible defaults."""
    return httpx.Client(
        auth=httpx.BasicAuth(user, token),
        headers={"Accept": "application/json"},
        timeout=30,
    )


# --- Jira REST API v3 (for workflows comparison) ---


def fetch_project(client: httpx.Client, host: str, project_key: str) -> dict:
    """Fetch project details including project ID."""
    url = f"https://{host}/rest/api/3/project/{project_key}"
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def fetch_project_statuses(
    client: httpx.Client, host: str, project_key: str
) -> list[dict]:
    """Fetch statuses grouped by issue type for a project."""
    url = f"https://{host}/rest/api/3/project/{project_key}/statuses"
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def fetch_workflows(
    client: httpx.Client, host: str, project_id: str
) -> list[dict]:
    """Fetch workflows for a project with statuses and transitions expanded."""
    url = f"https://{host}/rest/api/3/workflow/search"
    all_workflows: list[dict] = []
    start_at = 0

    while True:
        resp = client.get(
            url,
            params={
                "projectId": project_id,
                "expand": "statuses,transitions",
                "startAt": start_at,
                "maxResults": 50,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        all_workflows.extend(values)
        if data.get("isLast", True) or not values:
            break
        start_at += len(values)

    return all_workflows


def fetch_global_statuses(client: httpx.Client, host: str) -> list[dict]:
    """Fetch all global statuses with pagination."""
    url = f"https://{host}/rest/api/3/statuses/search"
    all_statuses: list[dict] = []
    start_at = 0

    while True:
        resp = client.get(
            url, params={"maxResults": 200, "startAt": start_at}
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        all_statuses.extend(values)
        if data.get("isLast", True) or not values:
            break
        start_at += len(values)

    return all_statuses
