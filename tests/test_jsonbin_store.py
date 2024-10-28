# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=attribute-defined-outside-init

import tempfile
from unittest.mock import patch, MagicMock

from .cases import GitalongCase


class JsonbinStoreTestCase(GitalongCase):

    __test__ = True

    def setUp(self):
        temp_dir = tempfile.mkdtemp()
        url = "https://api.jsonbin.io/v3/b/<BIN_ID>/"

        self._stored_value = {"record": {}}

        self._get_patcher = patch("requests.get", self._get_patch)
        self._get_patcher.start()

        self._put_patcher = patch("requests.put", self._put_patch)
        self._put_patcher.start()

        self._store_headers = {"X-Master-Key": "<ACCESS_KEY>"}

        self._setup_repository(temp_dir, url, store_headers=self._store_headers)

    def _get_patch(
        self, url, headers=None, timeout=0
    ):  # pylint: disable=unused-argument
        self.assertEqual(url, self._store_url)
        self.assertDictEqual(headers or {}, self._store_headers)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._stored_value
        return mock_response

    def _put_patch(
        self, url, headers=None, timeout=0, json=None
    ):  # pylint: disable=unused-argument
        self.assertEqual(url, self._store_url)
        store_headers = {"Content-Type": "application/json"}
        store_headers.update(self._store_headers)
        self.assertDictEqual(headers or {}, store_headers)
        self._stored_value = {"record": json or {}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        return mock_response

    def tearDown(self):
        super(JsonbinStoreTestCase, self).tearDown()
        self._get_patcher.stop()
        self._put_patcher.stop()
