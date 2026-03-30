"""CLI entry point for jsm-compare."""

from __future__ import annotations

import sys

import click

from . import api, compare


@click.group()
@click.version_option()
def cli():
    """Compare JSM automation rules between Jira Cloud environments.

    Compares rule definitions between a source and target environment
    (e.g., sandbox vs production) to detect configuration drift.
    """


@cli.command()
@click.option(
    "--domain",
    envvar="JSM_DOMAIN",
    default=None,
    help="Domain prefix (e.g., my-project). Expands to {domain}-sandbox.atlassian.net and {domain}.atlassian.net",
)
@click.option(
    "--source",
    default=None,
    help="Source environment hostname (e.g., my-project-sandbox.atlassian.net)",
)
@click.option(
    "--target",
    default=None,
    help="Target environment hostname (e.g., my-project.atlassian.net)",
)
@click.option(
    "--user",
    required=True,
    envvar="JIRA_USER",
    help="Jira user email for authentication [env: JIRA_USER]",
)
@click.option(
    "--token",
    required=True,
    envvar="JIRA_API_TOKEN",
    help="Jira API token [env: JIRA_API_TOKEN]",
)
@click.option(
    "--section",
    type=click.Choice(["rules-overview", "triggers", "components"]),
    default=None,
    help="Compare a specific section only",
)
@click.option(
    "--filter",
    "prefix",
    default=None,
    help="Filter rules by name prefix (e.g., '[MyPrefix]')",
)
@click.option("--raw", is_flag=True, help="Show normalized JSON for debugging")
@click.option("--mask", is_flag=True, help="Mask sensitive values (webhook URLs, API keys)")
@click.option(
    "--ignore-env/--no-ignore-env",
    default=True,
    help="Ignore environment-specific differences (customfield IDs, domain URLs, workspaceId, schemaId). Default: enabled",
)
def rules(domain, source, target, user, token, section, prefix, raw, mask, ignore_env):
    """Compare automation rules between two environments.

    \b
    Examples:
      jsm-compare rules --domain my-project --user me@example.com
      jsm-compare rules --domain my-project --section components --mask
      jsm-compare rules --source sandbox.atlassian.net --target prod.atlassian.net --user me@example.com
    """
    if domain and (source or target):
        raise click.UsageError("--domain cannot be used with --source/--target")
    if domain:
        source = f"{domain}-sandbox.atlassian.net"
        target = f"{domain}.atlassian.net"
    if not source or not target:
        raise click.UsageError("Specify --domain or both --source and --target")

    client = api.build_client(user, token)
    try:
        all_match = compare.run_comparison(
            client,
            source,
            target,
            section=section,
            prefix=prefix,
            raw=raw,
            mask=mask,
            ignore_env=ignore_env,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    finally:
        client.close()

    sys.exit(0 if all_match else 1)
