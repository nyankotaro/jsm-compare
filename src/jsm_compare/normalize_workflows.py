"""Normalization logic for workflow comparison data."""

from __future__ import annotations


def normalize_project_statuses(raw: list[dict]) -> dict[str, list[str]]:
    """Normalize project statuses to {issue_type_name: sorted_status_names}.

    Input format (Jira REST API v3 /project/{key}/statuses):
        [{"name": "Bug", "statuses": [{"name": "Open"}, ...]}, ...]
    """
    result: dict[str, list[str]] = {}
    for issue_type in raw:
        type_name = issue_type.get("name", "")
        statuses = sorted(s.get("name", "") for s in issue_type.get("statuses", []))
        result[type_name] = statuses
    return dict(sorted(result.items()))


def normalize_workflow(workflow: dict) -> dict:
    """Normalize a single workflow to comparable form.

    Extracts name, sorted status names, and transitions with ID-to-name
    resolution. The ``from`` field is kept as a sorted list (a transition
    can originate from multiple statuses).

    Input format (Jira REST API v3 /workflow/search with expand=statuses,transitions):
        {"id": {"name": "WF Name"}, "statuses": [...], "transitions": [...]}
    """
    # Build status ID -> name map from the workflow's own statuses
    wf_statuses = workflow.get("statuses", [])
    status_map: dict[str, str] = {}
    for s in wf_statuses:
        sid = s.get("id", "")
        if sid:
            status_map[sid] = s.get("name", "")

    status_names = sorted(s.get("name", "") for s in wf_statuses)

    # Normalize transitions
    transitions = []
    for t in workflow.get("transitions", []):
        # "from" is a list of status IDs
        from_ids = t.get("from", [])
        if isinstance(from_ids, list):
            from_names = sorted(status_map.get(fid, fid) for fid in from_ids)
        else:
            from_names = [status_map.get(from_ids, from_ids)]

        # "to" is a single status ID
        to_ref = t.get("to", "")
        if isinstance(to_ref, dict):
            to_name = status_map.get(to_ref.get("id", ""), to_ref.get("id", ""))
        else:
            to_name = status_map.get(to_ref, to_ref)

        transitions.append({
            "name": t.get("name", ""),
            "type": t.get("type", ""),
            "from": from_names,
            "to": to_name,
        })

    transitions.sort(key=lambda x: x["name"])

    # Extract workflow name from nested id object
    wf_id = workflow.get("id", {})
    if isinstance(wf_id, dict):
        name = wf_id.get("name", "")
    else:
        name = workflow.get("name", "")

    return {
        "name": name,
        "statuses": status_names,
        "transitions": transitions,
    }


def normalize_global_statuses(raw: list[dict]) -> list[dict]:
    """Normalize global statuses to comparable sorted list.

    Input format (Jira REST API v3 /statuses/search):
        [{"name": "Open", "statusCategory": "TODO", "scope": {"type": "PROJECT"}}, ...]
    """
    result = []
    for s in raw:
        scope = s.get("scope")
        scope_type = scope.get("type", "GLOBAL") if isinstance(scope, dict) else "GLOBAL"
        result.append({
            "name": s.get("name", ""),
            "statusCategory": s.get("statusCategory", ""),
            "scope_type": scope_type,
        })

    result.sort(key=lambda x: (x["name"], x["statusCategory"], x["scope_type"]))
    return result


def get_workflow_name(workflow: dict) -> str:
    """Extract workflow name from raw API response."""
    wf_id = workflow.get("id", {})
    if isinstance(wf_id, dict):
        return wf_id.get("name", "")
    return workflow.get("name", "")
