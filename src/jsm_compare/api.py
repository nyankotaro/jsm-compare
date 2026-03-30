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
    """Fetch all automation rule summaries with pagination."""
    base_path = (
        f"https://{host}/gateway/api/automation/public/jira/{cloud_id}"
        f"/rest/v1/rule/summary"
    )
    all_rules: list[dict] = []
    url = base_path
    page = 0

    while url and page < 20:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        all_rules.extend(data.get("data", []))

        next_cursor = data.get("links", {}).get("next")
        if next_cursor:
            url = f"{base_path}{next_cursor}"
            page += 1
        else:
            break

    return all_rules


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
