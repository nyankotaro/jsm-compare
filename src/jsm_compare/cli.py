"""CLI entry point for jsm-compare."""

from __future__ import annotations

import functools
import sys

import click

from . import api, compare, compare_workflows


def common_options(f):
    """Shared Click options for environment connection (domain/sandbox/production, auth)."""

    @click.option(
        "--domain",
        envvar="JSM_DOMAIN",
        default=None,
        help="Domain prefix (e.g., my-project). Expands to {domain}-sandbox.atlassian.net and {domain}.atlassian.net",
    )
    @click.option(
        "--sandbox",
        default=None,
        help="Sandbox environment hostname (e.g., my-project-sandbox.atlassian.net)",
    )
    @click.option(
        "--production",
        default=None,
        help="Production environment hostname (e.g., my-project.atlassian.net)",
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
    @functools.wraps(f)
    def wrapper(**kwargs):
        return f(**kwargs)

    return wrapper


def _resolve_hosts(domain, sandbox, production):
    """Resolve sandbox/production hostnames from --domain or --sandbox/--production."""
    if domain and (sandbox or production):
        raise click.UsageError("--domain cannot be used with --sandbox/--production")
    if domain:
        sandbox = f"{domain}-sandbox.atlassian.net"
        production = f"{domain}.atlassian.net"
    if not sandbox or not production:
        raise click.UsageError("Specify --domain or both --sandbox and --production")
    return sandbox, production


@click.group()
@click.version_option()
def cli():
    """Compare JSM configurations between Jira Cloud environments.

    Compares automation rules, workflows, and other settings between a sandbox
    and production environment to detect configuration drift.
    """


@cli.command()
@common_options
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
def rules(domain, sandbox, production, user, token, section, prefix, raw, mask, ignore_env):
    """Compare automation rules between two environments.

    \b
    Examples:
      jsm-compare rules --domain my-project --user me@example.com
      jsm-compare rules --domain my-project --section components --mask
      jsm-compare rules --sandbox sandbox.atlassian.net --production prod.atlassian.net --user me@example.com
    """
    sandbox, production = _resolve_hosts(domain, sandbox, production)

    client = api.build_client(user, token)
    try:
        all_match = compare.run_comparison(
            client,
            sandbox,
            production,
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


@cli.command()
@common_options
@click.option(
    "--project-key",
    required=True,
    envvar="JSM_PROJECT_KEY",
    help="Jira project key (e.g., MYPROJ) [env: JSM_PROJECT_KEY]",
)
@click.option(
    "--section",
    type=click.Choice(["project-statuses", "workflows", "global-statuses"]),
    default=None,
    help="Compare a specific section only",
)
@click.option(
    "--filter",
    "prefix",
    default=None,
    help="Filter workflows by name prefix (applies to workflows section only)",
)
@click.option("--raw", is_flag=True, help="Show normalized JSON for debugging")
def workflows(domain, sandbox, production, user, token, project_key, section, prefix, raw):
    """Compare workflow configurations between two environments.

    \b
    Examples:
      jsm-compare workflows --domain my-project --project-key MYPROJ --user me@example.com
      jsm-compare workflows --domain my-project --project-key MYPROJ --section workflows --filter "MyPrefix"
    """
    sandbox, production = _resolve_hosts(domain, sandbox, production)

    client = api.build_client(user, token)
    try:
        all_match = compare_workflows.run_workflow_comparison(
            client,
            sandbox,
            production,
            project_key,
            section=section,
            prefix=prefix,
            raw=raw,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    finally:
        client.close()

    sys.exit(0 if all_match else 1)
