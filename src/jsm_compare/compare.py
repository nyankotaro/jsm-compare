"""Comparison logic for automation rules between two environments."""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import api, normalize
from .compare_utils import (
    Stats,
    filter_by_prefix,
    index_by_name,
    print_summary,
    show_diff,
    sorted_json,
)

console = Console()


def compare_rules_overview(
    source_rules: list[dict],
    target_rules: list[dict],
    *,
    raw: bool = False,
) -> Stats:
    """Compare rule overviews. Returns Stats."""
    console.print()
    console.print("[bold cyan]────────────────── Section 1: Rules Overview ──────────────────[/]")
    console.print()

    src_idx = index_by_name(source_rules)
    tgt_idx = index_by_name(target_rules)
    src_names = set(src_idx)
    tgt_names = set(tgt_idx)

    only_source = sorted(src_names - tgt_names)
    only_target = sorted(tgt_names - src_names)
    common = sorted(src_names & tgt_names)

    stats = Stats(source_only=len(only_source), target_only=len(only_target))

    if only_source:
        console.print("  [yellow][INFO][/]  Only in sandbox:")
        for name in only_source:
            state = src_idx[name].get("state", "?")
            console.print(f"    [yellow]{name}[/] [{state}]")
        console.print()

    if only_target:
        console.print("  [yellow][INFO][/]  Only in production:")
        for name in only_target:
            state = tgt_idx[name].get("state", "?")
            console.print(f"    [yellow]{name}[/] [{state}]")
        console.print()

    for name in common:
        src_ov = normalize.normalize_overview(src_idx[name])
        tgt_ov = normalize.normalize_overview(tgt_idx[name])
        if show_diff(name, src_ov, tgt_ov, raw):
            stats.match += 1
        else:
            stats.diff += 1

    return stats


def compare_triggers(
    source_rules: list[dict],
    target_rules: list[dict],
    client: "httpx.Client",
    source_host: str,
    source_cloud_id: str,
    target_host: str,
    target_cloud_id: str,
    *,
    raw: bool = False,
    ignore_env: bool = True,
) -> Stats:
    """Compare triggers for common rules. Returns Stats."""
    console.print()
    console.print("[bold cyan]────────────────── Section 2: Triggers ─────────────────────[/]")
    console.print()

    src_idx = index_by_name(source_rules)
    tgt_idx = index_by_name(target_rules)
    common = sorted(set(src_idx) & set(tgt_idx))

    stats = Stats()
    pairs: list[tuple[str, object, object]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching rule details...", total=len(common))

        for name in common:
            progress.update(task, description=f"[dim]{name}[/]")

            src_detail = api.fetch_rule_detail(
                client, source_host, source_cloud_id, src_idx[name]["uuid"]
            )
            tgt_detail = api.fetch_rule_detail(
                client, target_host, target_cloud_id, tgt_idx[name]["uuid"]
            )

            src_trigger = normalize.normalize_trigger(src_detail)
            tgt_trigger = normalize.normalize_trigger(tgt_detail)

            if ignore_env:
                src_trigger = normalize.normalize_env(src_trigger)
                tgt_trigger = normalize.normalize_env(tgt_trigger)

            pairs.append((name, src_trigger, tgt_trigger))
            progress.advance(task)

    all_equal = all(sorted_json(s) == sorted_json(t) for _, s, t in pairs)

    if all_equal and pairs:
        console.print(f"  [green]All {len(pairs)} triggers match.[/]")
        stats.match = len(pairs)
    else:
        for name, src, tgt in pairs:
            if show_diff(name, src, tgt, raw):
                stats.match += 1
            else:
                stats.diff += 1

    return stats


def compare_components(
    source_rules: list[dict],
    target_rules: list[dict],
    client: "httpx.Client",
    source_host: str,
    source_cloud_id: str,
    target_host: str,
    target_cloud_id: str,
    *,
    raw: bool = False,
    mask: bool = False,
    ignore_env: bool = True,
) -> Stats:
    """Compare components for common rules. Returns Stats."""
    console.print()
    console.print("[bold cyan]────────────────── Section 3: Components ───────────────────[/]")
    console.print()

    src_idx = index_by_name(source_rules)
    tgt_idx = index_by_name(target_rules)
    common = sorted(set(src_idx) & set(tgt_idx))

    stats = Stats()
    pairs: list[tuple[str, object, object]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching rule details...", total=len(common))

        for name in common:
            progress.update(task, description=f"[dim]{name}[/]")

            src_detail = api.fetch_rule_detail(
                client, source_host, source_cloud_id, src_idx[name]["uuid"]
            )
            tgt_detail = api.fetch_rule_detail(
                client, target_host, target_cloud_id, tgt_idx[name]["uuid"]
            )

            src_comp = normalize.normalize_components(src_detail)
            tgt_comp = normalize.normalize_components(tgt_detail)

            if ignore_env:
                src_comp = normalize.normalize_env(src_comp)
                tgt_comp = normalize.normalize_env(tgt_comp)

            if mask:
                src_comp = normalize.mask_sensitive(src_comp)
                tgt_comp = normalize.mask_sensitive(tgt_comp)

            pairs.append((name, src_comp, tgt_comp))
            progress.advance(task)

    all_equal = all(sorted_json(s) == sorted_json(t) for _, s, t in pairs)

    if all_equal and pairs:
        console.print(f"  [green]All {len(pairs)} components match.[/]")
        stats.match = len(pairs)
    else:
        for name, src, tgt in pairs:
            if show_diff(name, src, tgt, raw):
                stats.match += 1
            else:
                stats.diff += 1

    return stats


def run_comparison(
    client: "httpx.Client",
    source_host: str,
    target_host: str,
    *,
    section: str | None = None,
    prefix: str | None = None,
    raw: bool = False,
    mask: bool = False,
    ignore_env: bool = True,
) -> bool:
    """Run the full comparison pipeline. Returns True if all match."""
    console.print("[bold]JSM Automation Rules Comparison[/]")
    console.print(f"  Sandbox:    {source_host}")
    console.print(f"  Production: {target_host}")
    if prefix:
        console.print(f"  Filter: {prefix}")
    if ignore_env:
        console.print("  Ignore env-specific: ON (customfield IDs, domain URLs, workspaceId, schemaId)")
    console.print()

    # Resolve Cloud IDs
    with console.status("Resolving Cloud IDs..."):
        source_cloud_id = api.get_cloud_id(client, source_host)
        target_cloud_id = api.get_cloud_id(client, target_host)
    if raw:
        console.print(f"  [yellow][INFO][/]  Sandbox Cloud ID:    {source_cloud_id}")
        console.print(f"  [yellow][INFO][/]  Production Cloud ID: {target_cloud_id}")

    # Fetch summaries
    with console.status("Fetching rule summaries..."):
        source_all = api.fetch_rules_summary(client, source_host, source_cloud_id)
        target_all = api.fetch_rules_summary(client, target_host, target_cloud_id)
    console.print(
        f"  [yellow][INFO][/]  Total rules: sandbox={len(source_all)}, production={len(target_all)}"
    )

    source_filtered = filter_by_prefix(source_all, prefix)
    target_filtered = filter_by_prefix(target_all, prefix)
    if prefix:
        console.print(
            f"  [yellow][INFO][/]  Filtered: sandbox={len(source_filtered)}, production={len(target_filtered)}"
        )

    total_stats = Stats()
    sections = [section] if section else ["rules-overview", "triggers", "components"]

    for sec in sections:
        if sec == "rules-overview":
            s = compare_rules_overview(source_filtered, target_filtered, raw=raw)

        elif sec == "triggers":
            s = compare_triggers(
                source_filtered,
                target_filtered,
                client,
                source_host,
                source_cloud_id,
                target_host,
                target_cloud_id,
                raw=raw,
                ignore_env=ignore_env,
            )

        elif sec == "components":
            s = compare_components(
                source_filtered,
                target_filtered,
                client,
                source_host,
                source_cloud_id,
                target_host,
                target_cloud_id,
                raw=raw,
                mask=mask,
                ignore_env=ignore_env,
            )
        else:
            continue

        total_stats.match += s.match
        total_stats.diff += s.diff
        total_stats.source_only += s.source_only
        total_stats.target_only += s.target_only

    console.print()
    print_summary(total_stats)

    return total_stats.all_match
