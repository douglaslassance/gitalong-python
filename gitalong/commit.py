import socket
import getpass

from typing import List

import dictdiffer
import git

from git import Repo


from .functions import get_real_path
from .enums import CommitSpread


class Commit(dict):
    """A class to represent a commit object in Git."""

    def __init__(self, repository, *args, **kwargs):
        self._repository = repository
        self._git_commit = None
        super().__init__(*args, **kwargs)

    @property
    def repository(self):
        """Return the repository object that this commit belongs to."""
        return self._repository

    def update_with_git_commit(self, git_commit: git.Commit):
        """Update the commit using info from a GitPython commit object.

        Args:
            git_commit (git.Commit): _description_
        """
        self.update(
            {
                "remote": git_commit.repo.remote().url,
                "date": str(git_commit.committed_datetime),
                "author": git_commit.author.name,
                "clone": git_commit.repo.working_dir,
            }
        )

    def update_with_sha(self, sha):
        """
        Returns:
            dict: A dict of contextual values that we attached to tracked commits.
        """
        self["sha"] = sha

        if not self._repository:
            return

        git_commit = Repo(self._repository.working_dir).commit(sha)
        if git_commit:
            self.update_with_git_commit(git_commit)

    def update_context(self):
        """
        Returns:
            dict: A dict of contextual values that we attached to tracked commits.
        """
        self.update(self.context_dict)

    @property
    def context_dict(self) -> dict:
        """
        Returns:
            dict: A dict of contextual values that we attached to tracked commits.
        """
        context_dict = {"host": socket.gethostname(), "user": getpass.getuser()}
        if self._repository:
            context_dict["clone"] = get_real_path(self._repository.working_dir)
        return context_dict

    def is_issued_commit(self) -> bool:
        """
        Args:
            commit (dict): The commit dictionary to check for.

        Returns:
            bool: Whether the commit was issued by the current context.
        """
        context_dict = self.context_dict
        diff_keys = set()
        for diff in dictdiffer.diff(context_dict, self):
            if diff[0] == "change":
                diff_keys.add(diff[1])
            elif diff[0] in ("add", "remove"):
                diff_keys = diff_keys.union([key[0] for key in diff[2]])
        intersection = set(context_dict.keys()).intersection(diff_keys)
        return not intersection

    def is_issued_uncommitted_changes_commit(self) -> bool:
        """
        Args:`
            commit (dict): Description

        Returns:
            bool:
                Whether the commit represents uncommitted changes and is issued by the
                current context.
        """
        if not self.is_uncommitted_changes_commit():
            return False
        return self.is_issued_commit()

    def is_uncommitted_changes_commit(self) -> bool:
        """
        Args:
            commit (dict): The commit dictionary.

        Returns:
            bool: Whether the commit dictionary represents uncommitted changes.
        """
        return "user" in self.keys()

    @property
    def parents(self) -> List[str]:
        """
        Returns:
            Commit: The parent commit of the current commit.
        """
        parents = []
        if self._repository:
            self._git_commit = self._git_commit or Repo(
                self._repository.working_dir
            ).commit(self.get("sha"))
            if self._git_commit:
                for parent_git_commit in self._git_commit.parents:
                    parent = Commit(self._repository)
                    parent.update_with_git_commit(parent_git_commit)
                    parents.append(parent)
        return parents

    @property
    def commit_spread(self) -> int:
        """
        Args:
            commit (int): The commit to check for.

        Returns:
            dict:
                A dictionary of commit spread information containing all
                information about where this commit lives across branches and clones.
        """
        commit_spread = 0
        active_branch = self._repository.active_branch_name
        if self.get("user", ""):
            is_issued = self.is_issued_commit()
            if "sha" in self:
                if active_branch in self.get("branches", {}).get("local", []):
                    commit_spread |= (
                        CommitSpread.MINE_ACTIVE_BRANCH
                        if is_issued
                        else CommitSpread.THEIR_MATCHING_BRANCH
                    )
                else:
                    commit_spread |= (
                        CommitSpread.MINE_OTHER_BRANCH
                        if is_issued
                        else CommitSpread.THEIR_OTHER_BRANCH
                    )
            else:
                commit_spread |= (
                    CommitSpread.MINE_UNCOMMITTED
                    if is_issued
                    else CommitSpread.THEIR_UNCOMMITTED
                )
        else:
            remote_branches = self.get("branches", {}).get("remote", [])
            if active_branch in remote_branches:
                commit_spread |= CommitSpread.REMOTE_MATCHING_BRANCH
            if active_branch in self.get("branches", {}).get("local", []):
                commit_spread |= CommitSpread.MINE_ACTIVE_BRANCH
            if active_branch in remote_branches:
                remote_branches.remove(active_branch)
            if remote_branches:
                commit_spread |= CommitSpread.REMOTE_OTHER_BRANCH
        return commit_spread
