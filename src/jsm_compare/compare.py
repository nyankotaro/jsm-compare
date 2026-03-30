"""Comparison logic for automation rules between two environments."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import api, normalize

console = Console()


@dataclass
class Stats:
    match: int = 0
    diff: int = 0
    source_only: int = 0
    target_only: int = 0

    @property
    def all_match(self) -> bool:
        return self.diff == 0 and self.source_only == 0 and self.target_only == 0


def _sorted_json(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def _format_value(val: object) -> str:
    """Format a value for compact diff display."""
    if isinstance(val, str):
        escaped = val.replace("\n", "\\n").replace("\t", "\\t")
        if len(escaped) > 80:
            return f'"{escaped[:77]}..."'
        return f'"{escaped}"'
    return json.dumps(val, ensure_ascii=False)


def _find_diffs(
    left: object, right: object, path: str = "",
) -> list[tuple[str, object, object]]:
    """Recursively find differing leaf values between two objects."""
    diffs: list[tuple[str, object, object]] = []

    if isinstance(left, dict) and isinstance(right, dict):
        all_keys = sorted(set(left) | set(right))
        for k in all_keys:
            child_path = f"{path}.{k}" if path else k
            if k not in left:
                diffs.append((child_path, "<missing>", right[k]))
            elif k not in right:
                diffs.append((child_path, left[k], "<missing>"))
            else:
                diffs.extend(_find_diffs(left[k], right[k], child_path))
    elif isinstance(left, list) and isinstance(right, list):
        if _sorted_json(left) != _sorted_json(right):
            max_len = max(len(left), len(right))
            for i in range(max_len):
                child_path = f"{path}[{i}]"
                if i >= len(left):
                    diffs.append((child_path, "<missing>", right[i]))
                elif i >= len(right):
                    diffs.append((child_path, left[i], "<missing>"))
                else:
                    diffs.extend(_find_diffs(left[i], right[i], child_path))
    else:
        if left != right:
            diffs.append((path, left, right))

    return diffs


def _show_diff(label: str, left: object, right: object, raw: bool) -> bool:
    """Compare two objects, print diff, return True if they match."""
    left_str = _sorted_json(left)
    right_str = _sorted_json(right)

    if left_str == right_str:
        console.print(f"  [green][MATCH][/] {label}")
        return True

    console.print(f"  [red][DIFF][/]  {label}")

    if raw:
        # Full unified diff for debugging
        diff_lines = list(
            difflib.unified_diff(
                left_str.splitlines(keepends=True),
                right_str.splitlines(keepends=True),
                fromfile=f"source: {label}",
                tofile=f"target: {label}",
            )
        )
        for line in diff_lines[:50]:
            line = line.rstrip("\n")
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/]")
            else:
                console.print(line)
    else:
        # Compact format: key: old -> new
        diffs = _find_diffs(left, right)
        for path, old, new in diffs:
            old_s = _format_value(old)
            new_s = _format_value(new)
            console.print(f"          [dim]{path}:[/] [red]{old_s}[/] -> [green]{new_s}[/]")

    console.print()
    return False


def _filter_by_prefix(rules: list[dict], prefix: str | None) -> list[dict]:
    if not prefix:
        return rules
    return [r for r in rules if r.get("name", "").startswith(prefix)]


def _index_by_name(rules: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in rules if "name" in r}


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

    src_idx = _index_by_name(source_rules)
    tgt_idx = _index_by_name(target_rules)
    src_names = set(src_idx)
    tgt_names = set(tgt_idx)

    only_source = sorted(src_names - tgt_names)
    only_target = sorted(tgt_names - src_names)
    common = sorted(src_names & tgt_names)

    stats = Stats(source_only=len(only_source), target_only=len(only_target))

    if only_source:
        console.print("  [yellow][INFO][/]  Only in source:")
        for name in only_source:
            state = src_idx[name].get("state", "?")
            console.print(f"    [yellow]{name}[/] [{state}]")
        console.print()

    if only_target:
        console.print("  [yellow][INFO][/]  Only in target:")
        for name in only_target:
            state = tgt_idx[name].get("state", "?")
            console.print(f"    [yellow]{name}[/] [{state}]")
        console.print()

    for name in common:
        src_ov = normalize.normalize_overview(src_idx[name])
        tgt_ov = normalize.normalize_overview(tgt_idx[name])
        if _show_diff(name, src_ov, tgt_ov, raw):
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

    src_idx = _index_by_name(source_rules)
    tgt_idx = _index_by_name(target_rules)
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

    all_equal = all(_sorted_json(s) == _sorted_json(t) for _, s, t in pairs)

    if all_equal and pairs:
        console.print(f"  [green]All {len(pairs)} triggers match.[/]")
        stats.match = len(pairs)
    else:
        for name, src, tgt in pairs:
            if _show_diff(name, src, tgt, raw):
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

    src_idx = _index_by_name(source_rules)
    tgt_idx = _index_by_name(target_rules)
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

    all_equal = all(_sorted_json(s) == _sorted_json(t) for _, s, t in pairs)

    if all_equal and pairs:
        console.print(f"  [green]All {len(pairs)} components match.[/]")
        stats.match = len(pairs)
    else:
        for name, src, tgt in pairs:
            if _show_diff(name, src, tgt, raw):
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
    console.print(f"  Source: {source_host}")
    console.print(f"  Target: {target_host}")
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
        console.print(f"  [yellow][INFO][/]  Source Cloud ID: {source_cloud_id}")
        console.print(f"  [yellow][INFO][/]  Target Cloud ID: {target_cloud_id}")

    # Fetch summaries
    with console.status("Fetching rule summaries..."):
        source_all = api.fetch_rules_summary(client, source_host, source_cloud_id)
        target_all = api.fetch_rules_summary(client, target_host, target_cloud_id)
    console.print(
        f"  [yellow][INFO][/]  Total rules: source={len(source_all)}, target={len(target_all)}"
    )

    source_filtered = _filter_by_prefix(source_all, prefix)
    target_filtered = _filter_by_prefix(target_all, prefix)
    if prefix:
        console.print(
            f"  [yellow][INFO][/]  Filtered: source={len(source_filtered)}, target={len(target_filtered)}"
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
    parts = [f"[green]{total_stats.match} match[/]"]
    if total_stats.diff:
        parts.append(f"[red]{total_stats.diff} diff[/]")
    if total_stats.source_only:
        parts.append(f"[yellow]{total_stats.source_only} source-only[/]")
    if total_stats.target_only:
        parts.append(f"[yellow]{total_stats.target_only} target-only[/]")
    console.print(f"[bold]Summary: {', '.join(parts)}[/]")

    if total_stats.all_match:
        console.print("[bold green]All sections match.[/]")
    else:
        console.print("[bold red]Differences found.[/]")

    return total_stats.all_match
