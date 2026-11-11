"""Bounded reuse of bundles whose assessed inputs have not changed.

SQLite's data_version is meaningful only on the same connection, so a private
read-only connection monitors commits. File identities also catch replacement
of the database or WAL. Other stores take the normal guarded computation path.
No assessment, original-content verification or observation digest is skipped
when a database revision changes.
"""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
import sqlite3
from threading import Lock

from .evidence_guard import AcceptedInputsChanged, _identity


class SQLiteRevision:
    def __init__(self, engine):
        url = engine.url
        self._path = (Path(url.database).absolute()
                      if url.get_backend_name() == 'sqlite' and url.database not in (None, '', ':memory:')
                      and not url.query.get('uri') and not url.database.startswith('file:') else None)
        self._connection = None
        self._file = None
        self._generation = 0
        self._lock = Lock()

    def capture(self):
        if self._path is None:
            return None
        with self._lock:
            try:
                identity = _identity(self._path)
                if identity is None:
                    return None
                if self._connection is None or self._file != identity[:2]:
                    self._close()
                    self._connection = sqlite3.connect(self._path.as_uri() + '?mode=ro', uri=True,
                                                       check_same_thread=False, timeout=1)
                    self._file = identity[:2]
                    self._generation += 1
                version = self._connection.execute('PRAGMA data_version').fetchone()[0]
                return self._generation, version, _identity(self._path), _identity(Path(str(self._path) + '-wal'))
            except (OSError, sqlite3.Error):
                # Failure to prove the revision means no reuse, never stale data.
                self._close()
                return None

    def _close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def close(self):
        with self._lock:
            self._close()


class BundleCache:
    def __init__(self, engine, max_entries=64):
        self._revision = SQLiteRevision(engine)
        self._max_entries = max_entries
        self._entries = OrderedDict()
        self._pending = {}
        self._lock = Lock()

    @staticmethod
    def _check_evidence(snapshot):
        if snapshot.evidence_state is not None and not snapshot.evidence_state.unchanged():
            raise AcceptedInputsChanged('Original evidence changed during computation')

    def get(self, request_key, snapshot, loader):
        revision = self._revision.capture()
        if revision is None or snapshot.evidence_state is None:
            return loader()
        key = id(snapshot), revision, request_key
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                result = self._entries[key][1]
                pending, owner = None, False
            else:
                pending = self._pending.get(key)
                owner = pending is None
                if owner:
                    pending = self._pending[key] = Future()
                result = None
        if not owner:
            if pending is not None:
                result = pending.result()
            self._check_evidence(snapshot)
            if self._revision.capture() != revision:
                return loader()
            return deepcopy(result)
        try:
            result = loader()
            self._check_evidence(snapshot)
            unchanged = self._revision.capture() == revision
            if not unchanged:
                # A commit while computing/waiting must take the normal guarded
                # path again; the earlier computation cannot become a cache hit.
                result = loader()
            with self._lock:
                if unchanged:
                    # Keep the snapshot alive so its identity cannot be recycled.
                    self._entries[key] = snapshot, deepcopy(result)
                    self._entries.move_to_end(key)
                    while len(self._entries) > self._max_entries:
                        self._entries.popitem(last=False)
                pending.set_result(result)
            return deepcopy(result)
        except BaseException as error:
            pending.set_exception(error)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)

    def close(self):
        self._revision.close()
        with self._lock:
            self._entries.clear()
