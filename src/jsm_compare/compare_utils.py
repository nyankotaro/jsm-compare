"""Shared comparison utilities used by rules and workflows comparison modules."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass

from rich.console import Console

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


def sorted_json(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def format_value(val: object) -> str:
    """Format a value for compact diff display."""
    if isinstance(val, str):
        escaped = val.replace("\n", "\\n").replace("\t", "\\t")
        if len(escaped) > 80:
            return f'"{escaped[:77]}..."'
        return f'"{escaped}"'
    return json.dumps(val, ensure_ascii=False)


def find_diffs(
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
                diffs.extend(find_diffs(left[k], right[k], child_path))
    elif isinstance(left, list) and isinstance(right, list):
        if sorted_json(left) != sorted_json(right):
            max_len = max(len(left), len(right))
            for i in range(max_len):
                child_path = f"{path}[{i}]"
                if i >= len(left):
                    diffs.append((child_path, "<missing>", right[i]))
                elif i >= len(right):
                    diffs.append((child_path, left[i], "<missing>"))
                else:
                    diffs.extend(find_diffs(left[i], right[i], child_path))
    else:
        if left != right:
            diffs.append((path, left, right))

    return diffs


def show_diff(label: str, left: object, right: object, raw: bool) -> bool:
    """Compare two objects, print diff, return True if they match."""
    left_str = sorted_json(left)
    right_str = sorted_json(right)

    if left_str == right_str:
        console.print(f"  [green][MATCH][/] {label}")
        return True

    console.print(f"  [red][DIFF][/]  {label}")

    if raw:
        diff_lines = list(
            difflib.unified_diff(
                left_str.splitlines(keepends=True),
                right_str.splitlines(keepends=True),
                fromfile=f"sandbox: {label}",
                tofile=f"production: {label}",
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
        diffs = find_diffs(left, right)
        for path, old, new in diffs:
            old_s = format_value(old)
            new_s = format_value(new)
            console.print(f"          [dim]{path}:[/]")
            console.print(f"            [cyan]sandbox:[/]    [red]{old_s}[/]")
            console.print(f"            [cyan]production:[/] [green]{new_s}[/]")

    console.print()
    return False


def filter_by_prefix(rules: list[dict], prefix: str | None) -> list[dict]:
    if not prefix:
        return rules
    return [r for r in rules if r.get("name", "").startswith(prefix)]


def index_by_name(rules: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in rules if "name" in r}


def print_summary(stats: Stats) -> None:
    """Print a colored summary line from Stats."""
    parts = [f"[green]{stats.match} match[/]"]
    if stats.diff:
        parts.append(f"[red]{stats.diff} diff[/]")
    if stats.source_only:
        parts.append(f"[yellow]{stats.source_only} sandbox-only[/]")
    if stats.target_only:
        parts.append(f"[yellow]{stats.target_only} production-only[/]")
    console.print(f"[bold]Summary: {', '.join(parts)}[/]")

    if stats.all_match:
        console.print("[bold green]All sections match.[/]")
    else:
        console.print("[bold red]Differences found.[/]")
