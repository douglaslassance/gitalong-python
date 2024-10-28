import json
import os
import typing

from abc import ABC, abstractmethod

from .commit import Commit


class Store(ABC):
    """Abstract class for storing commits information."""

    def __init__(self, managed_repository):
        super().__init__()
        self._managed_repository = managed_repository

    def _read_local_json(self) -> typing.List[Commit]:
        if os.path.exists(self._local_json_path):
            with open(self._local_json_path, "r", encoding="utf-8") as _file:
                return json.loads(_file.read())
        return []

    def _write_local_json(self, commits: typing.List[Commit]):
        cache_dirname = os.path.dirname(self._local_json_path)
        if not os.path.exists(cache_dirname):
            os.makedirs(cache_dirname)
        with open(self._local_json_path, "w", encoding="utf-8") as _file:
            json.dump(commits, _file, indent=4, sort_keys=True)

    @property
    @abstractmethod
    def _local_json_path(self) -> str:
        """
        Returns:
            str: The path to the JSON file that tracks the local commits.
        """
        return ""

    @property
    @abstractmethod
    def commits(self) -> typing.List[Commit]:
        """
        Returns:
            typing.List[Commit]: The stored commits.
        """
        return []

    @commits.setter
    @abstractmethod
    def commits(self, commits: typing.List[Commit]):
        """Update the stored commits.

        Args: commits (list, optional): The commits to update the store with.
        """
        pass  # pylint: disable=unnecessary-pass
