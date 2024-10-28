# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=attribute-defined-outside-init

import getpass
import logging
import os
import shutil
import socket
import unittest
import asyncio

from click.testing import CliRunner
from git.repo import Repo

from gitalong import Repository, CommitSpread, Commit, RepositoryNotSetup, cli
from gitalong.functions import is_read_only

# Deliberatedly import the module to avoid circular imports.
import gitalong.batch as batch

from .functions import save_image


class GitalongCase(unittest.TestCase):

    __test__ = False

    def _setup_repository(self, temp_dir, store_url, store_headers=None):
        self.temp_dir = temp_dir
        logging.info(self.temp_dir)
        self._managed_remote = Repo.init(
            path=os.path.join(self.temp_dir, "managed.git"), bare=True
        )
        self._managed_clone = self._managed_remote.clone(
            os.path.join(self.temp_dir, "managed")
        )
        self._store_url = store_url
        self._store_headers = store_headers or {}

        self.assertRaises(
            RepositoryNotSetup, Repository, self._managed_clone.working_dir
        )

        self.repository = Repository.setup(
            store_url=store_url,
            store_headers=store_headers,
            managed_repository=str(self._managed_clone.working_dir),
            modify_permissions=True,
            track_binaries=True,
            track_uncommitted=True,
            update_gitignore=True,
            # Hooks are turned off because we would have to install Gitalong CLI as
            # part of that test. Instead, we are simulating the hooks operations below.
            update_hooks=False,
        )

    def test_config(self):
        config = self.repository.config
        self.assertEqual(
            os.path.normpath(self._store_url),
            os.path.normpath(config.get("store_url", "")),
        )

    def test_lib(self):
        local_only_commits = self.repository.get_local_only_commits()
        working_dir = self._managed_clone.working_dir
        self.assertEqual(1, len(local_only_commits))
        self.assertEqual(2, len(local_only_commits[0]["changes"]))

        # Testing detecting un-tracked files.
        save_image(os.path.join(working_dir, "untracked_image_01.jpg"))

        # Testing detecting staged files.
        staged_image_01_path = os.path.join(working_dir, "staged_image_01.jpg")
        save_image(staged_image_01_path)
        self._managed_clone.index.add(staged_image_01_path)
        self.assertEqual(4, len(self.repository.get_local_only_commits()[0]["changes"]))

        commit = self._managed_clone.index.commit(message="Add staged_image.jpg")
        local_only_commits = self.repository.get_local_only_commits()
        self.assertEqual(2, len(local_only_commits))
        self.assertEqual(3, len(local_only_commits[0]["changes"]))
        self.assertEqual(1, len(local_only_commits[1]["changes"]))

        self._managed_clone.remote().push()
        local_only_commits = self.repository.get_local_only_commits()
        self.assertEqual(1, len(local_only_commits))
        self.assertEqual(3, len(local_only_commits[0]["changes"]))

        staged_image_02_path = os.path.join(working_dir, "staged_image_02.jpg")
        save_image(staged_image_02_path)
        # Simulating the application syncing when saving the file.
        self.repository.update_tracked_commits()
        # print("POST-SAVE TRACKED COMMITS")
        # pprint(self.repository.get_tracked_commits())

        self._managed_clone.index.add(staged_image_02_path)
        self._managed_clone.index.commit(message="Add staged_image_02.jpg")
        # Simulating the post-commit hook.
        self.repository.update_tracked_commits()
        # print("POST-COMMIT TRACKED COMMITS")
        # pprint(self.repository.get_tracked_commits())

        self._managed_clone.remote().push()
        # Simulating a post-push hook.
        # It could only be implemented server-side as it's not an actual Git hook.
        self.repository.update_tracked_commits()
        # print("POST-PUSH TRACKED COMMITS")
        # pprint(self.repository.get_tracked_commits())

        # We just pushed the changes therefore there should be no missing commit.
        last_commits = asyncio.run(batch.get_files_last_commits([staged_image_02_path]))
        last_commit = last_commits[0] if last_commits else Commit(None)
        spread = last_commit.commit_spread
        self.assertEqual(
            CommitSpread.MINE_ACTIVE_BRANCH | CommitSpread.REMOTE_MATCHING_BRANCH,
            spread,
        )

        # We are dropping the last commit locally.
        self._managed_clone.git.reset("--hard", commit.hexsha)

        # Simulating the post-checkout hook.
        self.repository.update_tracked_commits()

        # As a result it should be a commit we do no have locally.
        last_commits = asyncio.run(batch.get_files_last_commits([staged_image_02_path]))
        last_commit = last_commits[0] if last_commits else Commit(None)
        spread = last_commit.commit_spread
        self.assertEqual(CommitSpread.REMOTE_MATCHING_BRANCH, spread)

        self.assertEqual(False, is_read_only(staged_image_01_path))
        self.assertEqual(False, is_read_only(self.repository.config_path))

        self.repository.update_file_permissions(staged_image_01_path)
        self.assertEqual(True, is_read_only(staged_image_01_path))

        self.repository.update_file_permissions(self.repository.config_path)
        self.assertEqual(False, is_read_only(self.repository.config_path))

        self.repository.update_tracked_commits()

        claims = asyncio.run(
            batch.claim_files([staged_image_01_path, staged_image_02_path])
        )
        missing_commit = claims[0]
        self.assertEqual(False, bool(missing_commit))
        missing_commit = claims[1]
        self.assertEqual(True, bool(missing_commit))

    def test_cli(self):
        working_dir = self._managed_clone.working_dir
        obj = {"REPOSITORY": working_dir}

        runner = CliRunner()

        args = [self._store_url]
        for key, value in self._store_headers.items():
            args += ["--store-header", f"{key}={value}"]
        args += [
            "--track-uncommitted",
            "--track-binaries",
            "--modify-permissions",
            "--update-gitignore",
        ]

        result = runner.invoke(
            cli.setup,
            args,
            obj=obj,
        )
        self.assertEqual(0, result.exit_code, result.output)

        config_path = os.path.join(working_dir, ".gitalong.json")
        self.assertEqual(True, os.path.exists(config_path))

        # Testing detecting un-tracked files.
        untracked_image_01 = os.path.join(working_dir, "untracked_image_01.jpg")
        save_image(untracked_image_01)

        result = runner.invoke(cli.update, obj=obj)
        self.assertEqual(0, result.exit_code, result.output)

        result = runner.invoke(cli.status, [untracked_image_01], obj=obj)
        self.assertEqual(0, result.exit_code, result.output)
        host = socket.gethostname()
        user = getpass.getuser()
        output = f"+------- {untracked_image_01} - - - {host} {user}\n"
        self.assertEqual(output, result.output)

        result = runner.invoke(cli.claim, [untracked_image_01], obj=obj)
        self.assertEqual(0, result.exit_code, result.output)
        host = socket.gethostname()
        user = getpass.getuser()
        output = f"-------- {untracked_image_01} - - - - -\n"
        self.assertEqual(output, result.output)

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except PermissionError as error:
            logging.error(error)
