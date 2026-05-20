"""Comparison logic for workflows between two environments."""

from __future__ import annotations

import httpx
from rich.console import Console

from . import api
from . import normalize_workflows as norm_wf
from .compare_utils import Stats, print_summary, show_diff

console = Console()


def compare_project_statuses(
    source_statuses: list[dict],
    target_statuses: list[dict],
    *,
    raw: bool = False,
) -> Stats:
    """Section 1: Compare project statuses by issue type."""
    console.print()
    console.print("[bold cyan]────────────── Section 1: Project Statuses ──────────────[/]")
    console.print()

    src = norm_wf.normalize_project_statuses(source_statuses)
    tgt = norm_wf.normalize_project_statuses(target_statuses)

    all_types = sorted(set(src) | set(tgt))
    stats = Stats()

    for type_name in all_types:
        if type_name not in tgt:
            console.print(f"  [yellow][INFO][/]  Only in sandbox: {type_name}")
            stats.source_only += 1
        elif type_name not in src:
            console.print(f"  [yellow][INFO][/]  Only in production: {type_name}")
            stats.target_only += 1
        elif show_diff(f"Issue Type: {type_name}", src[type_name], tgt[type_name], raw):
            stats.match += 1
        else:
            stats.diff += 1

    return stats


def compare_workflow_definitions(
    source_workflows: list[dict],
    target_workflows: list[dict],
    *,
    raw: bool = False,
) -> Stats:
    """Section 2: Compare workflow definitions (statuses + transitions)."""
    console.print()
    console.print("[bold cyan]────────────── Section 2: Workflows ────────────────────[/]")
    console.print()

    src_normalized = [norm_wf.normalize_workflow(w) for w in source_workflows]
    tgt_normalized = [norm_wf.normalize_workflow(w) for w in target_workflows]

    src_idx = {w["name"]: w for w in src_normalized}
    tgt_idx = {w["name"]: w for w in tgt_normalized}

    src_names = set(src_idx)
    tgt_names = set(tgt_idx)
    only_source = sorted(src_names - tgt_names)
    only_target = sorted(tgt_names - src_names)
    common = sorted(src_names & tgt_names)

    stats = Stats(source_only=len(only_source), target_only=len(only_target))

    if only_source:
        console.print("  [yellow][INFO][/]  Only in sandbox:")
        for name in only_source:
            console.print(f"    [yellow]{name}[/]")
        console.print()

    if only_target:
        console.print("  [yellow][INFO][/]  Only in production:")
        for name in only_target:
            console.print(f"    [yellow]{name}[/]")
        console.print()

    for name in common:
        if show_diff(name, src_idx[name], tgt_idx[name], raw):
            stats.match += 1
        else:
            stats.diff += 1

    return stats


def compare_global_statuses(
    source_statuses: list[dict],
    target_statuses: list[dict],
    *,
    raw: bool = False,
) -> Stats:
    """Section 3: Compare global statuses."""
    console.print()
    console.print("[bold cyan]────────────── Section 3: Global Statuses ──────────────[/]")
    console.print()

    src = norm_wf.normalize_global_statuses(source_statuses)
    tgt = norm_wf.normalize_global_statuses(target_statuses)

    src_idx = {s["name"]: s for s in src}
    tgt_idx = {s["name"]: s for s in tgt}

    src_names = set(src_idx)
    tgt_names = set(tgt_idx)
    only_source = sorted(src_names - tgt_names)
    only_target = sorted(tgt_names - src_names)
    common = sorted(src_names & tgt_names)

    stats = Stats(source_only=len(only_source), target_only=len(only_target))

    if only_source:
        console.print("  [yellow][INFO][/]  Only in sandbox:")
        for name in only_source:
            console.print(f"    [yellow]{name}[/]")
        console.print()

    if only_target:
        console.print("  [yellow][INFO][/]  Only in production:")
        for name in only_target:
            console.print(f"    [yellow]{name}[/]")
        console.print()

    for name in common:
        if show_diff(name, src_idx[name], tgt_idx[name], raw):
            stats.match += 1
        else:
            stats.diff += 1

    return stats


def run_workflow_comparison(
    client: httpx.Client,
    source_host: str,
    target_host: str,
    project_key: str,
    *,
    section: str | None = None,
    prefix: str | None = None,
    raw: bool = False,
) -> bool:
    """Run the full workflow comparison pipeline. Returns True if all match."""
    console.print("[bold]JSM Workflow Comparison[/]")
    console.print(f"  Sandbox:    {source_host}")
    console.print(f"  Production: {target_host}")
    console.print(f"  Project: {project_key}")
    if prefix:
        console.print(f"  Filter: {prefix}")
    console.print()

    total_stats = Stats()
    sections = [section] if section else ["project-statuses", "workflows", "global-statuses"]

    for sec in sections:
        if sec == "project-statuses":
            with console.status("Fetching project statuses..."):
                src_data = api.fetch_project_statuses(client, source_host, project_key)
                tgt_data = api.fetch_project_statuses(client, target_host, project_key)
            s = compare_project_statuses(src_data, tgt_data, raw=raw)

        elif sec == "workflows":
            with console.status("Fetching workflows..."):
                src_project = api.fetch_project(client, source_host, project_key)
                tgt_project = api.fetch_project(client, target_host, project_key)
                src_wf = api.fetch_workflows(client, source_host, src_project["id"])
                tgt_wf = api.fetch_workflows(client, target_host, tgt_project["id"])

            console.print(
                f"  [yellow][INFO][/]  Total workflows: sandbox={len(src_wf)}, production={len(tgt_wf)}"
            )

            if prefix:
                src_wf = [w for w in src_wf if norm_wf.get_workflow_name(w).startswith(prefix)]
                tgt_wf = [w for w in tgt_wf if norm_wf.get_workflow_name(w).startswith(prefix)]
                console.print(
                    f"  [yellow][INFO][/]  Filtered: sandbox={len(src_wf)}, production={len(tgt_wf)}"
                )

            s = compare_workflow_definitions(src_wf, tgt_wf, raw=raw)

        elif sec == "global-statuses":
            with console.status("Fetching global statuses..."):
                src_data = api.fetch_global_statuses(client, source_host)
                tgt_data = api.fetch_global_statuses(client, target_host)
            s = compare_global_statuses(src_data, tgt_data, raw=raw)

        else:
            continue

        total_stats.match += s.match
        total_stats.diff += s.diff
        total_stats.source_only += s.source_only
        total_stats.target_only += s.target_only

    console.print()
    print_summary(total_stats)

    return total_stats.all_match
