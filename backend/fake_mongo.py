"""In-process fake MongoDB, TEST USE ONLY (installed by conftest.py).

Why it exists: the test suite must never touch the real Atlas database, and a local mongod is
not always available. This implements just the slice of the Motor / PyMongo / GridFS API that the
app and its tests actually use, backed by plain dicts. It is deliberately small - anything it does
not implement raises AttributeError so a test never silently passes on unsupported behaviour.

Supported: find_one/find(sort, skip, limit, projection)/insert_one/insert_many/update_one/
update_many/delete_one/delete_many/count_documents/create_index(unique)/drop_index/
index_information; query operators $in $nin $gt $gte $lt $lte $ne $exists $regex($options) $or
$and; update operators $set $inc $unset $setOnInsert; a GridFS bucket (upload_from_stream,
open_download_stream, delete).
"""

import copy
import re
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from bson import ObjectId
from gridfs.errors import NoFile
from pymongo.errors import DuplicateKeyError, OperationFailure

# ---------------------------------------------------------------------------
# Shared in-memory store (one per process; every client sees the same data, like one server)
# ---------------------------------------------------------------------------


class _Store:
    def __init__(self) -> None:
        # db name -> collection name -> list of documents
        self.data: dict[str, dict[str, list[dict[str, Any]]]] = {}
        # db name -> collection name -> index name -> (keys, unique)
        self.indexes: dict[str, dict[str, dict[str, tuple[list[tuple[str, int]], bool]]]] = {}
        # db name -> file id -> (filename, bytes, metadata)
        self.files: dict[str, dict[ObjectId, tuple[str, bytes, dict[str, Any]]]] = {}

    def docs(self, db: str, coll: str) -> list[dict[str, Any]]:
        return self.data.setdefault(db, {}).setdefault(coll, [])

    def clear_data(self) -> None:
        """Empties every collection and every stored file but KEEPS index definitions (the app
        creates them once at startup, so tests must not lose unique constraints)."""
        self.data.clear()
        self.files.clear()


STORE = _Store()


# ---------------------------------------------------------------------------
# Query / update engine
# ---------------------------------------------------------------------------

_MISSING = object()


def _get_path(doc: Any, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _cmp_key(value: Any) -> tuple[int, Any]:
    # Mongo sorts missing/null first; keep types from raising on mixed comparisons.
    if value is None or value is _MISSING:
        return (0, 0)
    if isinstance(value, bool):
        return (3, value)
    if isinstance(value, int | float):
        return (1, value)
    if isinstance(value, str):
        return (2, value)
    if isinstance(value, datetime):
        return (4, value.timestamp() if value.tzinfo else value.replace(tzinfo=None).timestamp())
    if isinstance(value, ObjectId):
        return (5, str(value))
    return (6, str(value))


def _eq(doc_value: Any, expected: Any) -> bool:
    if doc_value is _MISSING:
        return expected is None
    if isinstance(doc_value, list) and not isinstance(expected, list):
        return expected in doc_value
    return bool(doc_value == expected)


def _match_operator(doc_value: Any, op: str, arg: Any, options: str = "") -> bool:
    present = doc_value is not _MISSING
    if op == "$in":
        if isinstance(doc_value, list):
            return any(_eq(doc_value, a) or a in doc_value for a in arg)
        return any(_eq(doc_value, a) for a in arg)
    if op == "$nin":
        return not _match_operator(doc_value, "$in", arg)
    if op == "$ne":
        return not _eq(doc_value, arg)
    if op == "$exists":
        return present == bool(arg)
    if op in ("$gt", "$gte", "$lt", "$lte"):
        if not present or doc_value is None:
            return False
        a, b = _cmp_key(doc_value), _cmp_key(arg)
        if a[0] != b[0]:
            return False
        return {"$gt": a > b, "$gte": a >= b, "$lt": a < b, "$lte": a <= b}[op]
    if op == "$regex":
        if not present or not isinstance(doc_value, str):
            return False
        flags = re.IGNORECASE if "i" in options else 0
        return re.search(arg, doc_value, flags) is not None
    if op == "$options":
        return True  # consumed together with $regex
    raise AttributeError(f"fake_mongo: unsupported query operator {op}")


def _matches(doc: dict[str, Any], filt: dict[str, Any]) -> bool:
    for key, cond in filt.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
        elif key == "$and":
            if not all(_matches(doc, sub) for sub in cond):
                return False
        elif key.startswith("$"):
            raise AttributeError(f"fake_mongo: unsupported top-level operator {key}")
        else:
            value = _get_path(doc, key)
            if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
                options = cond.get("$options", "")
                if not all(_match_operator(value, op, arg, options) for op, arg in cond.items()):
                    return False
            elif not _eq(value, cond):
                return False
    return True


def _set_path(doc: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _unset_path(doc: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    cur: Any = doc
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _apply_update(doc: dict[str, Any], update: dict[str, Any], inserting: bool) -> None:
    for op, fields in update.items():
        if op == "$set":
            for k, v in fields.items():
                _set_path(doc, k, copy.deepcopy(v))
        elif op == "$inc":
            for k, v in fields.items():
                cur = _get_path(doc, k)
                _set_path(doc, k, (0 if cur is _MISSING else cur) + v)
        elif op == "$unset":
            for k in fields:
                _unset_path(doc, k)
        elif op == "$setOnInsert":
            if inserting:
                for k, v in fields.items():
                    _set_path(doc, k, copy.deepcopy(v))
        else:
            raise AttributeError(f"fake_mongo: unsupported update operator {op}")


def _project(doc: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    if not projection:
        return out
    includes = {k for k, v in projection.items() if v and k != "_id"}
    excludes = {k for k, v in projection.items() if not v and k != "_id"}
    if includes:
        kept = {k: out[k] for k in includes if k in out}
        if projection.get("_id", 1):
            kept["_id"] = out["_id"]
        return kept
    for k in excludes:
        out.pop(k, None)
    if "_id" in projection and not projection["_id"]:
        out.pop("_id", None)
    return out


class InsertOneResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id
        self.acknowledged = True


class InsertManyResult:
    def __init__(self, inserted_ids: list[Any]) -> None:
        self.inserted_ids = inserted_ids
        self.acknowledged = True


class UpdateResult:
    def __init__(self, matched: int, modified: int, upserted_id: Any = None) -> None:
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id
        self.acknowledged = True


class DeleteResult:
    def __init__(self, deleted: int) -> None:
        self.deleted_count = deleted
        self.acknowledged = True


# ---------------------------------------------------------------------------
# Synchronous core collection / cursor (PyMongo-shaped)
# ---------------------------------------------------------------------------


def _sort_key(path: str) -> Callable[[dict[str, Any]], tuple[int, Any]]:
    def key(doc: dict[str, Any]) -> tuple[int, Any]:
        return _cmp_key(_get_path(doc, path))

    return key


class _SyncCursor:
    def __init__(self, docs: list[dict[str, Any]], projection: dict[str, Any] | None) -> None:
        self._docs = docs
        self._projection = projection
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit = 0

    def sort(self, key_or_list: Any, direction: int | None = None) -> "_SyncCursor":
        if isinstance(key_or_list, str):
            self._sort = [(key_or_list, direction if direction is not None else 1)]
        else:
            self._sort = list(key_or_list)
        return self

    def skip(self, n: int) -> "_SyncCursor":
        self._skip = n
        return self

    def limit(self, n: int) -> "_SyncCursor":
        self._limit = n
        return self

    def _materialize(self) -> list[dict[str, Any]]:
        rows = list(self._docs)
        for key, direction in reversed(self._sort):
            rows.sort(key=_sort_key(key), reverse=direction < 0)
        rows = rows[self._skip :]
        if self._limit:
            rows = rows[: self._limit]
        return [_project(d, self._projection) for d in rows]

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._materialize())

    def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        rows = self._materialize()
        return rows if length is None else rows[:length]


class _SyncCollection:
    def __init__(self, db_name: str, name: str) -> None:
        self._db_name = db_name
        self.name = name

    @property
    def _docs(self) -> list[dict[str, Any]]:
        return STORE.docs(self._db_name, self.name)

    @property
    def _indexes(self) -> dict[str, tuple[list[tuple[str, int]], bool]]:
        return STORE.indexes.setdefault(self._db_name, {}).setdefault(self.name, {})

    def _check_unique(self, candidate: dict[str, Any], ignore: dict[str, Any] | None) -> None:
        for index_name, (keys, unique) in self._indexes.items():
            if not unique:
                continue
            ident = tuple(_norm(_get_path(candidate, k)) for k, _ in keys)
            for other in self._docs:
                if other is ignore:
                    continue
                if tuple(_norm(_get_path(other, k)) for k, _ in keys) == ident:
                    raise DuplicateKeyError(
                        f"E11000 duplicate key error collection: {self._db_name}.{self.name} "
                        f"index: {index_name}"
                    )

    # -- writes
    def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
        doc = copy.deepcopy(document)
        doc.setdefault("_id", ObjectId())
        if any(d["_id"] == doc["_id"] for d in self._docs):
            raise DuplicateKeyError(f"E11000 duplicate key error index: _id_ in {self.name}")
        self._check_unique(doc, None)
        self._docs.append(doc)
        document.setdefault("_id", doc["_id"])  # PyMongo mutates the caller's dict the same way
        return InsertOneResult(doc["_id"])

    def insert_many(self, documents: list[dict[str, Any]]) -> InsertManyResult:
        return InsertManyResult([self.insert_one(d).inserted_id for d in documents])

    def _update(
        self, filt: dict[str, Any], update: dict[str, Any], many: bool, upsert: bool
    ) -> UpdateResult:
        matched = [d for d in self._docs if _matches(d, filt)]
        if not many:
            matched = matched[:1]
        if not matched and upsert:
            new: dict[str, Any] = {
                k: v for k, v in filt.items() if not k.startswith("$") and not isinstance(v, dict)
            }
            _apply_update(new, update, inserting=True)
            new.setdefault("_id", ObjectId())
            self._check_unique(new, None)
            self._docs.append(new)
            return UpdateResult(0, 0, new["_id"])
        modified = 0
        for doc in matched:
            before = copy.deepcopy(doc)
            candidate = copy.deepcopy(doc)
            _apply_update(candidate, update, inserting=False)
            self._check_unique(candidate, doc)
            doc.clear()
            doc.update(candidate)
            modified += int(before != doc)
        return UpdateResult(len(matched), modified)

    def update_one(
        self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> UpdateResult:
        return self._update(filt, update, many=False, upsert=upsert)

    def update_many(
        self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> UpdateResult:
        return self._update(filt, update, many=True, upsert=upsert)

    def delete_one(self, filt: dict[str, Any]) -> DeleteResult:
        for i, d in enumerate(self._docs):
            if _matches(d, filt):
                del self._docs[i]
                return DeleteResult(1)
        return DeleteResult(0)

    def delete_many(self, filt: dict[str, Any]) -> DeleteResult:
        keep = [d for d in self._docs if not _matches(d, filt)]
        removed = len(self._docs) - len(keep)
        self._docs[:] = keep
        return DeleteResult(removed)

    # -- reads
    def find_one(
        self, filt: dict[str, Any] | None = None, projection: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        for d in self._docs:
            if _matches(d, filt or {}):
                return _project(d, projection)
        return None

    def find(
        self, filt: dict[str, Any] | None = None, projection: dict[str, Any] | None = None
    ) -> _SyncCursor:
        return _SyncCursor([d for d in self._docs if _matches(d, filt or {})], projection)

    def count_documents(self, filt: dict[str, Any]) -> int:
        return sum(1 for d in self._docs if _matches(d, filt))

    # -- indexes
    def create_index(self, keys: Any, unique: bool = False, **_: Any) -> str:
        key_list = [(keys, 1)] if isinstance(keys, str) else [(k, int(v)) for k, v in keys]
        name = "_".join(f"{k}_{v}" for k, v in key_list)
        self._indexes[name] = (key_list, unique)
        return name

    def drop_index(self, name: str) -> None:
        if name not in self._indexes:
            raise OperationFailure(f"index not found with name [{name}]")
        del self._indexes[name]

    def index_information(self) -> dict[str, Any]:
        info: dict[str, Any] = {"_id_": {"key": [("_id", 1)]}}
        for name, (keys, unique) in self._indexes.items():
            info[name] = {"key": keys, **({"unique": True} if unique else {})}
        return info


def _norm(value: Any) -> Any:
    return None if value is _MISSING else value


# ---------------------------------------------------------------------------
# Async (Motor-shaped) wrappers
# ---------------------------------------------------------------------------


class _AsyncCursor:
    def __init__(self, cursor: _SyncCursor) -> None:
        self._cursor = cursor

    def sort(self, key_or_list: Any, direction: int | None = None) -> "_AsyncCursor":
        self._cursor.sort(key_or_list, direction)
        return self

    def skip(self, n: int) -> "_AsyncCursor":
        self._cursor.skip(n)
        return self

    def limit(self, n: int) -> "_AsyncCursor":
        self._cursor.limit(n)
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self._cursor.to_list(length)

    def __aiter__(self) -> "_AsyncCursor":
        self._iter = iter(self._cursor)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class _AsyncCollection:
    def __init__(self, sync: _SyncCollection) -> None:
        self._sync = sync
        self.name = sync.name

    async def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
        return self._sync.insert_one(document)

    async def insert_many(self, documents: list[dict[str, Any]]) -> InsertManyResult:
        return self._sync.insert_many(documents)

    async def update_one(self, *args: Any, **kwargs: Any) -> UpdateResult:
        return self._sync.update_one(*args, **kwargs)

    async def update_many(self, *args: Any, **kwargs: Any) -> UpdateResult:
        return self._sync.update_many(*args, **kwargs)

    async def delete_one(self, filt: dict[str, Any]) -> DeleteResult:
        return self._sync.delete_one(filt)

    async def delete_many(self, filt: dict[str, Any]) -> DeleteResult:
        return self._sync.delete_many(filt)

    async def find_one(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._sync.find_one(*args, **kwargs)

    def find(self, *args: Any, **kwargs: Any) -> _AsyncCursor:
        return _AsyncCursor(self._sync.find(*args, **kwargs))

    async def count_documents(self, filt: dict[str, Any]) -> int:
        return self._sync.count_documents(filt)

    async def create_index(self, *args: Any, **kwargs: Any) -> str:
        return self._sync.create_index(*args, **kwargs)

    async def drop_index(self, name: str) -> None:
        self._sync.drop_index(name)

    async def index_information(self) -> dict[str, Any]:
        return self._sync.index_information()


class _Database:
    def __init__(self, name: str, wrap: Callable[[_SyncCollection], Any]) -> None:
        self.name = name
        self._wrap = wrap

    def __getitem__(self, coll: str) -> Any:
        return self._wrap(_SyncCollection(self.name, coll))

    def __getattr__(self, coll: str) -> Any:
        if coll.startswith("_"):
            raise AttributeError(coll)
        return self[coll]


class _AsyncDatabase(_Database):
    def __init__(self, name: str) -> None:
        super().__init__(name, _AsyncCollection)

    async def list_collection_names(self) -> list[str]:
        return [c for c, docs in STORE.data.get(self.name, {}).items() if docs is not None]

    async def command(self, *_: Any, **__: Any) -> dict[str, Any]:
        return {"ok": 1.0}


class _SyncDatabase(_Database):
    def __init__(self, name: str) -> None:
        super().__init__(name, lambda c: c)


def _default_db_name(uri: str) -> str:
    return urlparse(uri).path.lstrip("/") or "test"


class FakeAsyncMongoClient:
    """Stands in for motor.motor_asyncio.AsyncIOMotorClient."""

    def __init__(self, uri: str = "", *_: Any, **__: Any) -> None:
        self._uri = uri
        self.admin = _AsyncDatabase("admin")

    def __getitem__(self, name: str) -> _AsyncDatabase:
        return _AsyncDatabase(name)

    def __getattr__(self, name: str) -> _AsyncDatabase:
        if name.startswith("_"):
            raise AttributeError(name)
        return _AsyncDatabase(name)

    def get_default_database(self) -> _AsyncDatabase:
        return _AsyncDatabase(_default_db_name(self._uri))

    def close(self) -> None:
        return None


class FakeSyncMongoClient:
    """Stands in for pymongo.MongoClient."""

    def __init__(self, uri: str = "", *_: Any, **__: Any) -> None:
        self._uri = uri

    def __getitem__(self, name: str) -> _SyncDatabase:
        return _SyncDatabase(name)

    def get_default_database(self) -> _SyncDatabase:
        return _SyncDatabase(_default_db_name(self._uri))

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# GridFS
# ---------------------------------------------------------------------------


class _DownloadStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class FakeGridFSBucket:
    """Stands in for motor.motor_asyncio.AsyncIOMotorGridFSBucket."""

    def __init__(self, db: _Database) -> None:
        self._db_name = db.name

    @property
    def _files(self) -> dict[ObjectId, tuple[str, bytes, dict[str, Any]]]:
        return STORE.files.setdefault(self._db_name, {})

    async def upload_from_stream(
        self, filename: str, source: bytes, metadata: dict[str, Any] | None = None, **_: Any
    ) -> ObjectId:
        file_id = ObjectId()
        self._files[file_id] = (filename, bytes(source), dict(metadata or {}))
        # Mirror GridFS's own bookkeeping collection so tests can count stored files.
        STORE.docs(self._db_name, "fs.files").append(
            {"_id": file_id, "filename": filename, "length": len(source)}
        )
        return file_id

    async def open_download_stream(self, file_id: ObjectId) -> _DownloadStream:
        if file_id not in self._files:
            raise NoFile(f"no file in gridfs for id {file_id}")
        return _DownloadStream(self._files[file_id][1])

    async def delete(self, file_id: ObjectId) -> None:
        if file_id not in self._files:
            raise NoFile(f"no file in gridfs for id {file_id}")
        del self._files[file_id]
        files_meta = STORE.docs(self._db_name, "fs.files")
        files_meta[:] = [m for m in files_meta if m["_id"] != file_id]
