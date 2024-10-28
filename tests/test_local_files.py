import os
import json
import asyncio

from gitalong import Repository
from gitalong.batch import get_files_last_commits


def test_local_files():
    """A test dedicated to local files. It expects a JSON file mapping path to
    commit spreads as shown below.

    {
        "C:\\file\\uncomitted": 1,
        "C:\\file\\in\\local\\active\\branch\\only": 2
    }
    """

    # Parse JSON file to get file paths and corresponding assertions.
    json_path = __file__.replace(".py", ".json")
    files = []
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            files = json.loads(f.read())
    else:
        return

    filenames = files.keys()
    last_commits = asyncio.run(get_files_last_commits(filenames))

    for filename, last_commit in zip(filenames, last_commits):
        repository = Repository.from_filename(filename)
        spread = last_commit.commit_spread if repository else 0
        assert files[filename] == spread
