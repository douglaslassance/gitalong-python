import os
import sys
import pstats
import cProfile

import click
import git
from click.decorators import pass_context

from .__info__ import __version__
from .enums import CommitSpread
from .exceptions import RepositoryNotSetup
from .repository import Repository
from .functions import set_read_only


def get_repository(  # pylint: disable=missing-function-docstring
    repository: str,
) -> Repository:
    try:
        # Initializing Gitalong for each file allows to handle files from multiple
        # repository. This is especially import to support submodules.
        return Repository(repository=repository, use_cached_instances=True)
    except RepositoryNotSetup:
        return None


def get_status(repository, filename, commit) -> str:
    """TODO: Add proper offline support."""
    spread = repository.get_commit_spread(commit) if repository else 0
    prop = "+" if spread & CommitSpread.MINE_UNCOMMITTED else "-"
    prop += "+" if spread & CommitSpread.MINE_ACTIVE_BRANCH else "-"
    prop += "+" if spread & CommitSpread.MINE_OTHER_BRANCH else "-"
    prop += "+" if spread & CommitSpread.REMOTE_MATCHING_BRANCH else "-"
    prop += "+" if spread & CommitSpread.REMOTE_OTHER_BRANCH else "-"
    prop += "+" if spread & CommitSpread.THEIR_OTHER_BRANCH else "-"
    prop += "+" if spread & CommitSpread.THEIR_MATCHING_BRANCH else "-"
    prop += "+" if spread & CommitSpread.THEIR_UNCOMMITTED else "-"
    splits = [
        prop,
        filename,
        commit.get("sha", "-"),
        ",".join(commit.get("branches", {}).get("local", ["-"])) or "-",
        ",".join(commit.get("branches", {}).get("remote", ["-"])) or "-",
        commit.get("host", "-"),
        commit.get("author", commit.get("user", "-")) or "-",
    ]
    return " ".join(splits)


def validate_key_value(ctx, param, value):  # pylint: disable=unused-argument
    """Validate that the provided value is a valid key-value."""
    result = {}
    for item in value:
        key, val = item.split("=")
        result[key] = val
    return result


@click.command(help="Prints the requested configuration property value.")
def version():  # pylint: disable=missing-function-docstring
    click.echo(f"gitalong version {__version__}")


@click.command(help="Prints the requested configuration property value.")
@click.argument(
    "prop",
    # help="The configuration property key to look for."
)
@click.pass_context
def config(ctx, prop):  # pylint: disable=missing-function-docstring
    repository = get_repository(ctx.obj.get("REPOSITORY", ""))
    if repository:
        repository_config = repository.config
        prop = prop.replace("-", "_")
        if prop in repository_config:
            value = repository_config[prop]
            if isinstance(value, bool):
                value = str(value).lower()
            click.echo(value)


@click.command(
    help=(
        "Update tracked commits with the local changes of this clone. echo a list of "
        "files that were made "
    )
)
@click.argument(
    "repository",
    nargs=-1,
    # help="The path to the file that should be made writable."
)
@click.pass_context
def update(ctx, repository):
    """TODO: Improve error handling."""
    repositories = repository or []
    repositories = list(repositories)
    repositories.insert(0, ctx.obj.get("REPOSITORY", ""))
    synced = set()
    perm_changes = []
    locally_changed = {}
    for repo_filename in repositories:
        repository = get_repository(repo_filename)
        root = repository.working_dir if repository else ""
        # We are not syncing the same repository twice.
        if not root or root in synced:
            continue
        repository.update_tracked_commits()
        synced.add(root)
        if repository.config.get("modify_permissions"):
            for filename in repository.files:
                if os.path.isfile(repository.get_absolute_path(filename)):
                    if root not in locally_changed:
                        locally_changed[root] = repository.locally_changed_files
                    perm_change = repository.update_file_permissions(
                        filename, locally_changed[root]
                    )
                    if perm_change:
                        perm_changes.append(f"{' '.join(perm_change)}")
    if perm_changes:
        click.echo("\n".join(perm_changes))


@click.command(
    help=(
        "Prints missing commits in this local branch for each filename. "
        "Format: `<spread> <filename> <commit> <local-branches> "
        "<remote-branches> <host> <author>`"
        # noqa: E501 pylint: disable=line-too-long
    )
)
@click.argument(
    "filename",
    nargs=-1,
    # help="The path to the file that should be made writable."
)
@click.option(
    "-p",
    "--profile",
    is_flag=True,
    help="Will generate a profile file in the current workin directory.",
)
@click.pass_context
def status(ctx, filename, profile=False):  # pylint: disable=missing-function-docstring
    if profile:
        with cProfile.Profile() as pr:
            run_status(ctx, filename)
        results = pstats.Stats(pr)
        results.dump_stats("gitalong.prof")
        return
    run_status(ctx, filename)


def run_status(ctx, filename):  # pylint: disable=missing-function-docstring
    statuses = []
    repo_filename = ctx.obj.get("REPOSITORY", "")
    for _filename in filename:
        repo_filename = repo_filename or _filename
        commit = {}
        repository = get_repository(repo_filename)
        if repository:
            commit = repository.get_file_last_commit(_filename)
        statuses.append(get_status(repository, _filename, commit))
    click.echo("\n".join(statuses), err=False)


@click.command(
    help=(
        "Make provided files writeable if possible. Return error code 1 if one or more "
        "files cannot be made writeable."
    )
)
@click.argument(
    "filename",
    nargs=-1,
    # help="The path to the file that should be made writable."
)
@pass_context
def claim(ctx, filename):  # pylint: disable=missing-function-docstring
    repo_filename = ctx.obj.get("REPOSITORY", "")
    statuses = []
    claimables = []
    error = False
    for _filename in filename:
        commit = {}
        repo_filename = repo_filename or _filename
        repository = get_repository(repo_filename)
        if repository:
            commit = repository.make_file_writable(_filename)
        statuses.append(get_status(repository, _filename, commit))
        claimables.append(_filename)
        if commit:
            error = True
    if statuses:
        click.echo("\n".join(statuses))
    if error:
        sys.exit(1)
    repository.update_tracked_commits(claims=claimables)
    if repository.config.get("modify_permissions"):
        if os.path.isfile(repository.get_absolute_path(filename)):
            set_read_only(
                repository.get_absolute_path(filename),
                read_only=False,
            )


@click.command(help="Setup Gitalong in a repository.")
@click.argument(
    "store-url",
    # help="The URL or path to the repository or REST API endpoint that will store the
    # Gitalong data.",
    required=True,
)
@click.option(
    "-sh",
    "--store-header",
    callback=validate_key_value,
    help=(
        "If using JSONBin.io as a store, the headers used to connect the" "end point."
    ),
    required=False,
    multiple=True,
)
@click.option(
    "-mp",
    "--modify-permissions",
    is_flag=True,
    help=(
        "Whether or not Gitalong should affect file permissions of tracked files "
        "to prevent editing of files that are modified elsewhere. This is too "
        "expensive option for repositories with many files and should should be "
        "enabled."
    ),
)
@click.option(
    "-pt",
    "--pull-threshold",
    default=60,
    help=(
        "Time in seconds that need to pass before Gitalong pulls again. Defaults to 10"
        "seconds. This is for optimization sake as pull and fetch operation are "
        "expensive. Defaults to 60 seconds."
    ),
    required=False,
)
@click.option(
    "-tb",
    "--track-binaries",
    is_flag=True,
    help=(
        "Gitalong should track all auto-detected binary files "
        "to prevent conflicts on them. There is a performance cost to this feature so "
        "it's always better if you can specify the extensions you care about tracking "
        "using --tracked-extensions."
    ),
    required=False,
)
@click.option(
    "-tu",
    "--track-uncommitted",
    is_flag=True,
    help=(
        "Track uncommitted changes. Better for collaboration but requires to push"
        "tracked commits after each file system operation."
    ),
)
@click.option(
    "-te",
    "--tracked-extensions",
    default="",
    help=(
        "A comma separated list of extensions to track to prevent conflicts. "
        "to prevent conflicts on them."
    ),
)
@click.option(
    "-ug",
    "--update-gitignore",
    is_flag=True,
    help=(
        ".gitignore should be modified in the repository to ignore " "Gitalong files."
    ),
)
@click.option(
    "-ug",
    "--update-hooks",
    is_flag=True,
    help="Hooks should be updated with Gitalong logic.",
)
@click.pass_context
def setup(
    ctx,
    store_url,
    store_header,
    modify_permissions,
    pull_threshold,
    track_binaries,
    track_uncommitted,
    tracked_extensions,
    update_gitignore,
    update_hooks,
):
    """TODO: Add support for branch groups."""
    Repository.setup(
        store_url=store_url,
        store_headers=store_header,
        managed_repository=ctx.obj.get("REPOSITORY", ""),
        modify_permissions=modify_permissions,
        pull_threshold=pull_threshold,
        track_binaries=track_binaries,
        track_uncommitted=track_uncommitted,
        tracked_extensions=tracked_extensions.split(","),
        update_gitignore=update_gitignore,
        update_hooks=update_hooks,
    )


class Group(click.Group):  # pylint: disable=missing-class-docstring
    def format_help(self, ctx, formatter):
        return click.Group.format_help(self, ctx, formatter)


@click.group(cls=Group)
@click.version_option(
    prog_name="gitalong",
    version=__version__,
    message="%(prog)s version %(version)s",
)
@click.option(
    "-C",
    "--repository",
    default="",
    help=(
        "The repository to apply operations to. "
        "Defaults to current working directory."
    ),
    required=False,
)
@click.option(
    "-gb",
    "--git-binary",
    default="",
    help="Path to the git binary to use. Defaults to the one available in PATH.",
    required=False,
)
@click.pass_context
def cli(ctx, repository, git_binary):  # pylint: disable=missing-function-docstring
    ctx.ensure_object(dict)
    if repository:
        ctx.obj["REPOSITORY"] = repository
    if git_binary:
        git.refresh(git_binary)


cli.add_command(config)
cli.add_command(update)
cli.add_command(claim)
cli.add_command(setup)
cli.add_command(status)
cli.add_command(version)


def main():
    """This main function will be register as the console script when installing the
    package.
    """
    cli(obj={})  # pylint: disable=unexpected-keyword-arg,no-value-for-parameter


if __name__ == "__main__":
    main()
