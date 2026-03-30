"""Normalization logic for removing environment-specific fields."""

from __future__ import annotations

import copy
import re
from typing import Any

# Fields to strip at the rule level
_RULE_STRIP = {
    "id",
    "clientKey",
    "partitionId",
    "idUuid",
    "currentVersionId",
    "authorAccountId",
    "actor",
    "created",
    "updated",
    "ruleScope",
    "ruleScopeARIs",
    "ruleHome",
    "labels",
    "tags",
    "collaborators",
    "billingType",
    "checksum",
}

# Fields to strip inside components / trigger nodes
_NODE_STRIP = {
    "id",
    "parentId",
    "conditionParentId",
    "connectionId",
    "checksum",
    "schemaVersion",
}

# Regex for sensitive keys (used with --mask)
_SENSITIVE_RE = re.compile(
    r"webhookUrl|apiKey|api_key|x-api-key|token|secret|password|Authorization",
    re.IGNORECASE,
)


def _strip_keys(obj: dict, keys: set[str]) -> dict:
    return {k: v for k, v in obj.items() if k not in keys}


def _clean_node(node: dict) -> dict:
    """Recursively clean a trigger/component node."""
    cleaned = _strip_keys(node, _NODE_STRIP)

    # Remove ARI-based eventFilters from trigger value
    if "value" in cleaned and isinstance(cleaned["value"], dict):
        cleaned["value"] = {
            k: v
            for k, v in cleaned["value"].items()
            if k != "eventFilters"
        }

    for list_key in ("children", "conditions"):
        if list_key in cleaned and isinstance(cleaned[list_key], list):
            cleaned[list_key] = [
                _clean_node(child)
                for child in cleaned[list_key]
                if isinstance(child, dict)
            ]

    return cleaned


def normalize_overview(rule_summary: dict) -> dict:
    """Extract comparable overview fields from a summary entry."""
    return {
        "name": rule_summary.get("name", ""),
        "state": rule_summary.get("state", ""),
        "description": rule_summary.get("description", ""),
    }


def normalize_trigger(rule_detail: dict) -> dict:
    """Extract and normalize the trigger from a rule detail response."""
    trigger = rule_detail.get("rule", rule_detail).get("trigger", {})
    return _clean_node(copy.deepcopy(trigger))


def normalize_components(rule_detail: dict) -> list[dict]:
    """Extract and normalize the components from a rule detail response."""
    components = rule_detail.get("rule", rule_detail).get("components", [])
    return [_clean_node(copy.deepcopy(c)) for c in components]


def mask_sensitive(obj: Any) -> Any:
    """Recursively replace sensitive values with '***MASKED***'."""
    if isinstance(obj, dict):
        return {
            k: "***MASKED***" if _SENSITIVE_RE.search(k) else mask_sensitive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [mask_sensitive(item) for item in obj]
    return obj


# --- Environment-specific value normalization ---

# Keys whose values are environment-specific IDs/UUIDs
_ENV_SPECIFIC_KEYS = {
    "schemaId",
    "workspaceId",
}

# Regex patterns for environment-specific values
_CUSTOMFIELD_RE = re.compile(r"customfield_\d+")
_ATLASSIAN_URL_RE = re.compile(r"https://[a-zA-Z0-9_-]+\.atlassian\.net")


def normalize_env(obj: Any) -> Any:
    """Recursively normalize environment-specific values.

    - customfield_NNNNN -> customfield_*
    - schemaId, workspaceId -> {key}
    - Atlassian URLs -> {atlassian_url}
    """
    if isinstance(obj, dict):
        return {
            k: f"{{{k}}}" if k in _ENV_SPECIFIC_KEYS else normalize_env(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [normalize_env(item) for item in obj]
    if isinstance(obj, str):
        result = _CUSTOMFIELD_RE.sub("customfield_*", obj)
        result = _ATLASSIAN_URL_RE.sub("{atlassian_url}", result)
        return result
    return obj
