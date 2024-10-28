import json
import os
import typing

import git
import git.exc
from git.repo import Repo

from ..exceptions import RepositoryInvalidConfig
from ..functions import pulled_within
from ..store import Store
from ..commit import Commit


class GitStore(Store):
    """Implementation using a Git repository as storage."""

    def __init__(self, managed_repository):
        super().__init__(managed_repository)
        self._store_repository = self._clone()

    @property
    def _local_json_path(self) -> str:
        return os.path.join(self._store_repository.working_dir, "commits.json")

    def _clone(self):
        """
        Returns:
            git.Repo: Clones the Gitalong repository if not done already.
        """
        try:
            return Repo(os.path.join(self._managed_repository.working_dir, ".gitalong"))
        except (git.exc.NoSuchPathError, git.exc.InvalidGitRepositoryError):
            try:
                remote = self._managed_repository.config["store_url"]
            except KeyError as error:
                config = self._managed_repository.config_path
                message = f'Could not find value for "store_url" in "{config}".'
                raise RepositoryInvalidConfig(message) from error
            return Repo.clone_from(
                remote,
                os.path.join(self._managed_repository.working_dir, ".gitalong"),
            )

    @property
    def commits(self) -> typing.List[Commit]:
        """
        Returns:
            typing.List[Commit]:
                A list of commits that haven't been pushed to remote. Also includes
                commits representing uncommitted changes.
        """
        store_repository = self._store_repository
        remote = store_repository.remote()
        pull_threshold = self._managed_repository.config.get("pull_threshold", 60)
        if not pulled_within(store_repository, pull_threshold) and remote.refs:
            # TODO: We could check that a pull is already happening thus avoiding this
            # try except and save time.
            try:
                remote.pull(
                    ff=True,
                    quiet=True,
                    rebase=True,
                    autostash=True,
                    verify=False,
                    summary=False,
                )
            except git.exc.GitCommandError:
                pass
        serializable_commits = self._read_local_json()
        if os.path.exists(self._local_json_path):
            with open(self._local_json_path, "r", encoding="utf-8") as _file:
                serializable_commits = json.loads(_file.read())
        commits = []
        for serializable_commit in serializable_commits:
            commit = Commit(self._managed_repository)
            commit.update(serializable_commit)
            commits.append(commit)
        return commits

    @commits.setter
    def commits(self, commits: typing.List[Commit]):
        self._write_local_json(commits)
        self._store_repository.index.add(self._local_json_path)
        basename = os.path.basename(self._local_json_path)
        self._store_repository.index.commit(message=f"Update {basename}")
        self._store_repository.remote().push()
