"""The upload status listing tolerates a file consumed while it is being read."""
from pathlib import Path
import errno
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from finance_dashboard.original_uploads import OriginalImportManager, README


class UploadStatusRaceTests(unittest.TestCase):
    def test_file_removed_between_listing_and_sizing_is_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "incoming"
            root.mkdir()
            (root / README).write_bytes(b"readme")
            vanishing = root / "2016-2022_EXT.zip"
            vanishing.write_bytes(b"archive")
            real_stat, seen = Path.stat, []

            def stat(self, *args, **kwargs):
                # The importer moves an accepted archive out of the folder;
                # every look after the first finds it gone.
                if self == vanishing:
                    seen.append(1)
                    if len(seen) > 1:
                        raise FileNotFoundError(errno.ENOENT, "No such file", str(self))
                return real_stat(self, *args, **kwargs)

            with patch.dict("os.environ", {
                    "FINANCE_ORIGINAL_IMPORT_JOURNAL": str(Path(tmp) / "journal.json")}):
                manager = OriginalImportManager(root=root, evidence=Path(tmp) / "evidence")
                with patch.object(Path, "stat", stat):
                    status = manager.public_status()
            names = [item["filename"] for item in status["files"]]
            self.assertIn(README, names)
            self.assertNotIn(vanishing.name, names)
            self.assertGreater(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
