# pylint: disable=missing-class-docstring

import os
import tempfile

from git.repo import Repo

from .cases import GitalongCase


class GitStoreTestCase(GitalongCase):

    __test__ = True

    def setUp(self):
        temp_dir = tempfile.mkdtemp()
        store_url = os.path.join(temp_dir, "store.git")
        Repo.init(path=store_url, bare=True)
        self._setup_repository(temp_dir, store_url)
