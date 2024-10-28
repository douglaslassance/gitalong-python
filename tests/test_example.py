import os
import tempfile
import logging
import asyncio

from git.repo import Repo
from gitalong import Repository, RepositoryNotSetup, CommitSpread


def test_example():
    """Testing example code featured in README.md."""
    dirname = tempfile.mkdtemp()
    logging.info(dirname)

    # Creating a dummy project repository and its clone in temp directory.
    project = Repo.init(path=os.path.join(dirname, "project.git"), bare=True)
    project_clone = project.clone(os.path.join(dirname, "project"))

    try:
        # This will raise as we never setup that repository with Gitalong.
        repository = Repository(str(project_clone.working_dir))

    except RepositoryNotSetup:

        # Creating a repository that Gitalong will use to store and share local changes.
        # You would normally host this somewhere like GitHub so your entire team has
        # access to it.
        store = Repo.init(path=os.path.join(dirname, "store.git"), bare=True)

        # Setting up Gitalong in your project repository.
        # This will clone the registry repository in an ignored `.gitalong` folder.
        # It will also start tracking a `.gitalong.json` configuration file.
        repository = Repository.setup(
            store_url=str(store.working_dir),
            managed_repository=str(project_clone.working_dir),
            modify_permissions=True,
            tracked_extensions=[".jpg", ".gif", ".png"],
            track_uncommitted=True,
            update_gitignore=True,
            # Skipping hook update for the test.
            update_hooks=False,
        )

    # Creating some files.
    uncomitted = os.path.join(project_clone.working_dir, "uncommitted.png")
    local = os.path.join(project_clone.working_dir, "local.gif")
    remote = os.path.join(project_clone.working_dir, "remote.jpg")
    untracked = os.path.join(project_clone.working_dir, "untracked.txt")
    open(uncomitted, "w", encoding="utf-8").close()
    open(local, "w", encoding="utf-8").close()
    open(remote, "w", encoding="utf-8").close()
    open(untracked, "w", encoding="utf-8").close()

    # Spreading them across branches.
    project_clone.index.add("untracked.txt")
    project_clone.index.commit(message="Add untracked.txt")
    project_clone.index.add("remote.jpg")
    project_clone.index.commit(message="Add remote.jpg")
    project_clone.remote().push()
    project_clone.git.reset("--hard", "HEAD^")
    project_clone.index.add("local.gif")
    project_clone.index.commit(message="Add local.gif")

    # Updating tracked commits with current local changes. Because we specified
    # `track_uncommitted`. Uncommitted changes will be stored as sha-less commit.
    repository.update_tracked_commits()

    # Update permissions of all files based on track commits. Because
    # `modify_permissions` was passed this will update all permissions of tracked files.
    # Permission updates currently comes at high performance cost and is not
    # recommended.
    locally_changed_files = repository.locally_changed_files
    for filename in repository.files:
        repository.update_file_permissions(filename, locally_changed_files)

    last_commits = asyncio.run(
        repository.batch.get_files_last_commits([uncomitted, local, remote, untracked])
    )

    # Now we'll get the last commit for our files.
    # This could return a dummy commit representing uncommitted changes.
    uncommitted_last_commit = last_commits[0]
    local_last_commit = last_commits[1]
    remote_last_commit = last_commits[2]
    untracked_last_commit = last_commits[3]

    # Getting the commit spreads.
    # Spread flags represent where the commit live.
    uncommitted_spread = uncommitted_last_commit.commit_spread
    local_spread = local_last_commit.commit_spread
    remote_spread = remote_last_commit.commit_spread
    untracked_spread = untracked_last_commit.commit_spread

    assert uncommitted_spread == CommitSpread.MINE_UNCOMMITTED
    assert local_spread == CommitSpread.MINE_ACTIVE_BRANCH
    assert remote_spread == CommitSpread.REMOTE_MATCHING_BRANCH
    assert untracked_spread == (
        CommitSpread.REMOTE_MATCHING_BRANCH | CommitSpread.MINE_ACTIVE_BRANCH
    )

    # Trying to claim the files.
    claims = asyncio.run(
        repository.batch.claim_files([uncomitted, local, remote, untracked])
    )

    assert bool(claims[0]) is False
    assert bool(claims[1]) is False
    assert bool(claims[2]) is True
    assert bool(claims[3]) is False


if __name__ == "__main__":
    test_example()
