"""Filesystem identities invalidate an original-content audit after changes.

The assessment hashes original bytes. Subsequent requests check file/directory
identity, size, mtime and ctime, detecting modification, removal, replacement,
permission changes and new archives without hashing gigabytes on every request.
An invalidated assessment re-hashes content before releasing results again.
"""
from dataclasses import dataclass
import os
from pathlib import Path


class AcceptedInputsChanged(RuntimeError):
    """Current inputs no longer match the independently assessed snapshot."""


def _identity(path):
    try:
        s = path.lstat()
        return s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class EvidenceState:
    entries: tuple

    @classmethod
    def capture(cls, roots):
        entries = {}
        def failed(error): raise error
        for root in roots:
            root = Path(root).absolute()
            entries[root] = _identity(root)
            if root.is_dir() and not root.is_symlink():
                for parent, directories, files in os.walk(root, followlinks=False, onerror=failed):
                    parent = Path(parent)
                    for name in [*directories, *files]:
                        path = parent/name
                        entries[path] = _identity(path)
        return cls(tuple(entries.items()))

    def unchanged(self):
        try:
            return all(_identity(path) == identity for path, identity in self.entries)
        except OSError:
            return False
