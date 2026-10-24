"""MongoDB adapter for tabula using pymongo."""
from datetime import date, datetime, time
from decimal import Decimal
import re
import time as time_mod
from typing import Any, Dict, List, Optional
import uuid

from bson import ObjectId
from bson.binary import Binary
from bson.decimal128 import Decimal128
from bson.json_util import loads as bson_loads
from bson.regex import Regex
from bson.timestamp import Timestamp
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.uri_parser import parse_uri

from backend.app.core.interfaces import BaseDataSource
from backend.app.core.models import (
    ColumnDefinition,
    ConnectionInfo,
    CreateTableRequest,
    PaginatedRecords,
    PaginationParams,
    QueryResult,
    TableSchema,
    TableSummary,
)

DEFAULT_PORT = 27017
DEFAULT_DATABASE = "test"
DEFAULT_AUTH_SOURCE = "admin"
SCHEMA_SAMPLE_SIZE = 50
DEFAULT_FIND_LIMIT = 100

# Operations accepted by the JSON console.
READ_OPERATIONS = ("find", "findone", "aggregate", "count", "distinct", "listcollections")
WRITE_OPERATIONS = (
    "insertone",
    "insertmany",
    "updateone",
    "updatemany",
    "replaceone",
    "deleteone",
    "deletemany",
)
SUPPORTED_OPERATIONS = READ_OPERATIONS + WRITE_OPERATIONS
# Aggregation stages that write to the database; not allowed in read-only views.
WRITE_STAGES = ("$out", "$merge")


def _serialize_mongo_value(val: Any) -> Any:
    """Convert BSON/Python types into standard JSON-serializable types."""
    if val is None:
        return None
    if isinstance(val, ObjectId):
        return str(val)
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, Decimal128):
        return float(val.to_decimal())
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, Binary):
        return bytes(val).hex()
    if isinstance(val, (bytes, bytearray, memoryview)):
        return bytes(val).hex()
    if isinstance(val, Timestamp):
        try:
            return val.as_datetime().isoformat()
        except Exception:
            return str(val)
    if isinstance(val, Regex):
        return val.pattern
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, list):
        return [_serialize_mongo_value(item) for item in val]
    if isinstance(val, tuple):
        return [_serialize_mongo_value(item) for item in val]
    if isinstance(val, dict):
        return {str(k): _serialize_mongo_value(v) for k, v in val.items()}
    return val


def _serialize_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize an entire MongoDB document."""
    return {str(k): _serialize_mongo_value(v) for k, v in document.items()}


def _json_loads(text: str) -> Any:
    """Parse JSON, accepting MongoDB Extended JSON (e.g. {"$oid": "..."})."""
    try:
        return bson_loads(text)
    except Exception as exc:
        raise ValueError(f"Invalid MongoDB JSON: {exc}")


def _find_write_stage(value: Any) -> Optional[str]:
    """Return the first write stage ($out/$merge) found anywhere in a pipeline."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in WRITE_STAGES:
                return key
            found = _find_write_stage(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_write_stage(item)
            if found:
                return found
    return None


def _try_object_id(value: Any) -> Optional[ObjectId]:
    """Return an ObjectId for a valid 24-hex string, otherwise None."""
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return None


def _object_id_or_value(value: Any) -> Any:
    """Convert valid ObjectId strings, leaving anything else untouched."""
    oid = _try_object_id(value)
    return oid if oid is not None else value


def _mongo_type_name(value: Any) -> str:
    """Human-readable BSON-ish type name used in inferred schemas."""
    if value is None:
        return "null"
    if isinstance(value, ObjectId):
        return "ObjectId"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, Decimal128):
        return "decimal"
    if isinstance(value, (datetime, date, time)):
        return "date"
    if isinstance(value, (Binary, bytes, bytearray, memoryview)):
        return "binData"
    if isinstance(value, Timestamp):
        return "timestamp"
    if isinstance(value, Regex):
        return "regex"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _coerce_value(value: Any, type_hint: Optional[str] = None, field_name: Optional[str] = None) -> Any:
    """Coerce values coming from the JSON UI into sensible BSON values."""
    if field_name == "_id":
        return _object_id_or_value(value)
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    hint = ""
    if isinstance(type_hint, str):
        hint = type_hint.split("|")[0].strip().lower()

    if hint in ("int", "long", "integer", "numberint"):
        try:
            return int(stripped)
        except (TypeError, ValueError):
            pass
    if hint in ("double", "decimal", "number", "float", "numberdecimal"):
        try:
            return float(stripped)
        except (TypeError, ValueError):
            pass
    if hint in ("bool", "boolean"):
        lowered = stripped.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    if hint in ("date", "datetime"):
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            pass
    if hint in ("object", "array", "document"):
        try:
            parsed = _json_loads(stripped)
            if isinstance(parsed, (dict, list)):
                return parsed
        except ValueError:
            pass

    # New fields have no type hint: infer only unambiguous primitives so that
    # values entered in the UI behave naturally without corrupting zip codes,
    # phone numbers, or other strings with meaningful leading zeros.
    if not hint:
        lowered = stripped.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        if lowered == "null":
            return None
        if re.fullmatch(r"-?(0|[1-9]\d*)", stripped):
            try:
                return int(stripped)
            except ValueError:
                pass
        if re.fullmatch(r"-?(0|[1-9]\d*)\.\d+", stripped):
            try:
                return float(stripped)
            except ValueError:
                pass

    # Accept JSON objects/arrays verbatim.
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = _json_loads(stripped)
            if isinstance(parsed, (dict, list)):
                return parsed
        except ValueError:
            pass

    return value


class MongoDataSource(BaseDataSource):
    """BaseDataSource implementation for MongoDB databases."""

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db: Optional[Any] = None
        self._host: Optional[str] = None
        self._port: int = DEFAULT_PORT
        self._database: Optional[str] = None
        self._user: Optional[str] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    @staticmethod
    def _create_client(
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: int = DEFAULT_PORT,
        user: Optional[str] = None,
        password: Optional[str] = None,
        auth_source: str = DEFAULT_AUTH_SOURCE,
        tls: bool = False,
        timeout: int = 5,
    ) -> MongoClient:
        """Build a MongoClient from a URI or individual parameters."""
        common: Dict[str, Any] = {
            "serverSelectionTimeoutMS": max(timeout, 1) * 1000,
            "connectTimeoutMS": max(timeout, 1) * 1000,
        }
        clean_uri = (uri or "").strip()
        if clean_uri:
            return MongoClient(clean_uri, **common)

        kwargs: Dict[str, Any] = {
            "host": host or "localhost",
            "port": port or DEFAULT_PORT,
            **common,
        }
        if user:
            kwargs["username"] = user
            kwargs["password"] = password or ""
            kwargs["authSource"] = auth_source or DEFAULT_AUTH_SOURCE
        if tls:
            kwargs["tls"] = True
        return MongoClient(**kwargs)

    @classmethod
    def test_connection(
        cls,
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: int = DEFAULT_PORT,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        auth_source: str = DEFAULT_AUTH_SOURCE,
        tls: bool = False,
        timeout: int = 5,
    ) -> Dict[str, Any]:
        """Test a MongoDB connection without storing session state."""
        client = None
        try:
            client = cls._create_client(
                uri=uri,
                host=host,
                port=port,
                user=user,
                password=password,
                auth_source=auth_source,
                tls=tls,
                timeout=timeout,
            )
            client.admin.command("ping")

            version = ""
            try:
                build = client.admin.command("buildInfo")
                raw_version = build.get("version") if isinstance(build, dict) else None
                if raw_version:
                    version = f"MongoDB {raw_version}"
            except Exception:
                version = "MongoDB"

            selected_db = database or DEFAULT_DATABASE
            if uri and uri.strip():
                try:
                    parsed = parse_uri(uri.strip())
                    selected_db = parsed.get("database") or selected_db
                except Exception:
                    pass

            return {
                "success": True,
                "message": "Connection successful",
                "server_version": version,
                "database": selected_db,
            }
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    def connect(
        self,
        path: str = "",
        host: Optional[str] = None,
        port: int = DEFAULT_PORT,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        auth_source: str = DEFAULT_AUTH_SOURCE,
        tls: bool = False,
        timeout: int = 10,
    ) -> ConnectionInfo:
        """Connect to a MongoDB database using a URI or parameters."""
        self.close()

        clean_path = path.strip() if path else ""
        selected_db = (database or DEFAULT_DATABASE).strip() or DEFAULT_DATABASE

        if clean_path:
            if not (clean_path.startswith("mongodb://") or clean_path.startswith("mongodb+srv://")):
                raise ValueError(
                    "Invalid MongoDB URI. It must start with 'mongodb://' or 'mongodb+srv://'."
                )
            parsed: Dict[str, Any] = {}
            try:
                parsed = parse_uri(clean_path)
            except Exception as exc:
                raise ValueError(f"Invalid MongoDB URI: {exc}")

            nodelist = parsed.get("nodelist") or []
            if nodelist:
                self._host = nodelist[0][0]
                self._port = int(nodelist[0][1] or DEFAULT_PORT)
            else:
                self._host = "localhost"
                self._port = DEFAULT_PORT
            self._database = parsed.get("database") or selected_db
            self._user = parsed.get("username") or user
        else:
            self._host = host or "localhost"
            self._port = int(port or DEFAULT_PORT)
            self._database = selected_db
            self._user = user

        client = self._create_client(
            uri=clean_path or None,
            host=self._host,
            port=self._port,
            user=user,
            password=password,
            auth_source=auth_source,
            tls=tls,
            timeout=timeout,
        )

        try:
            client.admin.command("ping")
        except Exception as exc:
            try:
                client.close()
            except Exception:
                pass
            raise RuntimeError(f"Could not connect to MongoDB: {exc}")

        self._client = client
        self._db = client[self._database]
        return self.get_connection_info()

    def close(self) -> None:
        """Close the active connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._db = None
        self._host = None
        self._database = None
        self._user = None

    def is_connected(self) -> bool:
        """Check whether a client is open."""
        return self._client is not None and self._db is not None

    def get_connection_info(self) -> ConnectionInfo:
        """Return metadata about the current connection."""
        if not self.is_connected():
            return ConnectionInfo(path="", connected=False, db_type="mongo")

        size_bytes = 0
        try:
            stats = self._db.command("dbStats")
            if isinstance(stats, dict):
                size_bytes = int(stats.get("dataSize") or stats.get("storageSize") or 0)
        except Exception:
            size_bytes = 0

        tables_count = 0
        try:
            tables_count = len(self.list_collections())
        except Exception:
            tables_count = 0

        user_part = f"{self._user}@" if self._user else ""
        display_path = f"mongodb://{user_part}{self._host}:{self._port}/{self._database}"

        return ConnectionInfo(
            path=display_path,
            connected=True,
            size_bytes=size_bytes,
            tables_count=tables_count,
            db_type="mongo",
            database=self._database,
            host=self._host,
            port=self._port,
            user=self._user,
        )

    # ------------------------------------------------------------------
    # Catalog inspection
    # ------------------------------------------------------------------
    def _collection_names(self) -> List[str]:
        """Return user collection/view names, excluding system namespaces."""
        names = []
        for name in self._db.list_collection_names():
            if name.startswith("system."):
                continue
            names.append(name)
        return sorted(names)

    def _view_names(self) -> set:
        """Return the set of view names, falling back to an empty set."""
        try:
            return {
                entry.get("name")
                for entry in self._db.list_collections()
                if entry.get("type") == "view"
            }
        except (NotImplementedError, AttributeError):
            return set()
        except Exception:
            return set()

    def _is_view(self, collection_name: str) -> bool:
        """Best-effort check for MongoDB views (falls back to False)."""
        return collection_name in self._view_names()

    def list_collections(self) -> List[TableSummary]:
        """List collections and views with document counts."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        view_names = self._view_names()
        summaries: List[TableSummary] = []
        for name in self._collection_names():
            kind = "view" if name in view_names else "table"
            count = None
            collection = self._db[name]
            try:
                if kind == "view":
                    count = int(collection.count_documents({}))
                else:
                    count = int(collection.estimated_document_count())
            except Exception:
                try:
                    count = int(collection.count_documents({}))
                except Exception:
                    count = None
            summaries.append(TableSummary(name=name, type=kind, row_count=count))
        return summaries

    def get_schema(self, collection_name: str) -> TableSchema:
        """Infer a schema by sampling documents in the collection."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        names = self._collection_names()
        if collection_name not in names:
            raise KeyError(f"Collection or view '{collection_name}' does not exist.")

        kind = "view" if self._is_view(collection_name) else "table"
        collection = self._db[collection_name]

        try:
            documents = list(collection.find({}).limit(SCHEMA_SAMPLE_SIZE))
        except Exception as exc:
            raise RuntimeError(f"Could not sample documents from '{collection_name}': {exc}")

        field_order: List[str] = []
        field_types: Dict[str, set] = {}
        field_presence: Dict[str, int] = {}

        for document in documents:
            for key, value in document.items():
                if key not in field_types:
                    field_order.append(key)
                    field_types[key] = set()
                    field_presence[key] = 0
                field_types[key].add(_mongo_type_name(value))
                field_presence[key] += 1

        if "_id" not in field_order:
            field_order.insert(0, "_id")
            field_types["_id"] = {"ObjectId"}
            field_presence["_id"] = len(documents)
        elif field_order[0] != "_id":
            field_order.remove("_id")
            field_order.insert(0, "_id")

        sample_size = len(documents)
        columns: List[ColumnDefinition] = []
        for field in field_order:
            types = sorted(field_types.get(field, set()))
            type_label = " | ".join(types) if types else "mixed"
            is_id = field == "_id"
            columns.append(
                ColumnDefinition(
                    name=field,
                    type=type_label,
                    is_pk=is_id,
                    not_null=bool(sample_size and field_presence.get(field, 0) == sample_size),
                    default_value=None,
                    auto_increment=bool(is_id and "ObjectId" in types),
                )
            )

        return TableSchema(
            name=collection_name,
            type=kind,
            columns=columns,
            pk_columns=["_id"] if any(c.name == "_id" for c in columns) else [],
            sql=None,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def _build_search_filter(self, search: Optional[str], field_names: List[str]) -> Dict[str, Any]:
        """Build a case-insensitive $or regex filter plus an exact ObjectId match."""
        term = (search or "").strip()
        if not term:
            return {}

        pattern = {"$regex": re.escape(term), "$options": "i"}
        or_parts: List[Dict[str, Any]] = [{field: pattern} for field in field_names]
        object_id = _try_object_id(term)
        if object_id is not None:
            or_parts.append({"_id": object_id})
        return {"$or": or_parts} if or_parts else {}

    def _merge_filters(self, base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        """Combine two filters with $and when both are present."""
        if not base:
            return extra
        if not extra:
            return base
        return {"$and": [base, extra]}

    def _resolve_sort(self, sort_by: Optional[str], sort_dir: str, fields: List[str]):
        """Translate a UI sort into a pymongo sort specification."""
        if sort_by and sort_by in fields:
            direction = DESCENDING if (sort_dir or "").lower() == "desc" else ASCENDING
            return [(sort_by, direction)]
        if "_id" in fields:
            return [("_id", ASCENDING)]
        return None

    def _columns_and_records(self, documents: List[Dict[str, Any]], field_names: List[str]):
        """Union the inferred fields with keys present in the returned documents."""
        columns = list(field_names)
        for document in documents:
            for key in document.keys():
                if key not in columns:
                    columns.append(key)
        records = [_serialize_document(document) for document in documents]
        return columns, records

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------
    def get_records(self, collection_name: str, pagination: PaginationParams) -> PaginatedRecords:
        """Fetch paginated, filtered, and sorted documents."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        field_names = [column.name for column in schema.columns]
        collection = self._db[collection_name]

        query_filter = self._build_search_filter(pagination.search, field_names)
        try:
            total = int(collection.count_documents(query_filter))
        except Exception as exc:
            raise RuntimeError(f"Could not count documents in '{collection_name}': {exc}")

        offset = (pagination.page - 1) * pagination.page_size
        cursor = collection.find(query_filter)
        sort_spec = self._resolve_sort(pagination.sort_by, pagination.sort_dir, field_names)
        if sort_spec:
            cursor = cursor.sort(sort_spec)
        cursor = cursor.skip(offset).limit(pagination.page_size)
        documents = list(cursor)

        columns, records = self._columns_and_records(documents, field_names)
        total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1

        return PaginatedRecords(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            columns=columns,
            records=records,
            pk_columns=["_id"] if "_id" in columns else [],
        )

    def insert_record(self, collection_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a document and return the stored version."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        type_hints = {column.name: column.type for column in schema.columns}

        document: Dict[str, Any] = {}
        for key, value in values.items():
            if key == "_rowid_":
                continue
            if key == "_id" and (value is None or (isinstance(value, str) and not value.strip())):
                continue
            document[key] = _coerce_value(value, type_hints.get(key), key)

        collection = self._db[collection_name]
        try:
            result = collection.insert_one(document)
        except Exception as exc:
            raise RuntimeError(f"Could not insert document: {exc}")

        inserted = collection.find_one({"_id": result.inserted_id})
        if inserted is None:
            raise RuntimeError("Failed to read the inserted document.")
        return _serialize_document(inserted)

    def update_record(
        self, collection_name: str, pk_values: Dict[str, Any], values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a document identified by _id (or another key)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")
        if not pk_values:
            raise ValueError("No primary key values provided to identify the document.")

        schema = self.get_schema(collection_name)
        type_hints = {column.name: column.type for column in schema.columns}

        query_filter: Dict[str, Any] = {}
        for key, value in pk_values.items():
            lookup_key = "_id" if key == "_rowid_" else key
            query_filter[lookup_key] = _coerce_value(value, type_hints.get(lookup_key), lookup_key)

        set_values: Dict[str, Any] = {}
        for key, value in values.items():
            if key in ("_id", "_rowid_"):
                continue
            set_values[key] = _coerce_value(value, type_hints.get(key), key)

        if not set_values:
            raise ValueError("No fields provided to update.")

        collection = self._db[collection_name]
        try:
            updated = collection.find_one_and_update(
                query_filter,
                {"$set": set_values},
                return_document=ReturnDocument.AFTER,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not update document: {exc}")

        if updated is None:
            raise ValueError("Document not found or not modified.")
        return _serialize_document(updated)

    def delete_record(self, collection_name: str, pk_values: Dict[str, Any]) -> bool:
        """Delete a document identified by _id (or another key)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")
        if not pk_values:
            raise ValueError("No primary key values provided to identify the document.")

        schema = self.get_schema(collection_name)
        type_hints = {column.name: column.type for column in schema.columns}

        query_filter: Dict[str, Any] = {}
        for key, value in pk_values.items():
            lookup_key = "_id" if key == "_rowid_" else key
            query_filter[lookup_key] = _coerce_value(value, type_hints.get(lookup_key), lookup_key)

        try:
            result = self._db[collection_name].delete_one(query_filter)
        except Exception as exc:
            raise RuntimeError(f"Could not delete document: {exc}")
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # Collection DDL
    # ------------------------------------------------------------------
    def create_table(self, request: CreateTableRequest) -> bool:
        """Create a MongoDB collection (documents are schemaless)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        name = request.name.strip()
        if not name:
            raise ValueError("Collection name cannot be empty.")

        try:
            self._db.create_collection(name)
        except Exception as exc:
            raise ValueError(f"Could not create collection '{name}': {exc}")
        return True

    def add_column(self, collection_name: str, column: ColumnDefinition) -> bool:
        """Add a field to every document, or no-op when no default is supplied."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        name = column.name.strip()
        if not name:
            raise ValueError("Field name cannot be empty.")
        if collection_name not in self._collection_names():
            raise KeyError(f"Collection or view '{collection_name}' does not exist.")

        default_value = column.default_value
        if default_value is not None and str(default_value).strip():
            value = _coerce_value(default_value, column.type, name)
            try:
                self._db[collection_name].update_many({}, {"$set": {name: value}})
            except Exception as exc:
                raise RuntimeError(f"Could not add field '{name}': {exc}")
        return True

    def rename_table(self, collection_name: str, new_name: str) -> bool:
        """Rename a collection."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_new = new_name.strip()
        if not clean_new:
            raise ValueError("The new collection name cannot be empty.")
        if clean_new == collection_name:
            return True
        if collection_name not in self._collection_names():
            raise KeyError(f"Collection or view '{collection_name}' does not exist.")

        try:
            self._db[collection_name].rename(clean_new)
        except Exception as exc:
            raise ValueError(f"Could not rename collection: {exc}")
        return True

    def drop_table(self, collection_name: str) -> bool:
        """Drop a collection or view."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")
        if collection_name not in self._collection_names():
            raise KeyError(f"Collection or view '{collection_name}' does not exist.")

        try:
            self._db[collection_name].drop()
        except Exception as exc:
            raise RuntimeError(f"Could not drop collection '{collection_name}': {exc}")
        return True

    # ------------------------------------------------------------------
    # Query console
    # ------------------------------------------------------------------
    def _apply_find_options(self, cursor, payload: Dict[str, Any]):
        """Apply sort, skip, and limit from a JSON command."""
        sort_spec = payload.get("sort")
        if sort_spec:
            if isinstance(sort_spec, dict):
                cursor = cursor.sort([(key, value) for key, value in sort_spec.items()])
            elif isinstance(sort_spec, list):
                cursor = cursor.sort([tuple(item) for item in sort_spec])

        skip = int(payload.get("skip") or 0)
        if skip > 0:
            cursor = cursor.skip(skip)

        limit = int(payload.get("limit") or DEFAULT_FIND_LIMIT)
        if limit > 0:
            cursor = cursor.limit(limit)
        return cursor

    def _rows_from_documents(self, documents: List[Dict[str, Any]]):
        """Build ordered columns and serialized rows from documents."""
        columns: List[str] = []
        for document in documents:
            for key in document.keys():
                if key not in columns:
                    columns.append(key)
        rows = [_serialize_document(document) for document in documents]
        return columns, rows

    def execute_query(self, query: str) -> QueryResult:
        """Execute a JSON MongoDB command (find, aggregate, writes, etc.)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_query = query.strip()
        if not clean_query:
            return QueryResult(columns=[], rows=[], row_count=0, execution_time_ms=0.0)

        start_time = time_mod.time()
        try:
            payload = _json_loads(clean_query)
            if isinstance(payload, list):
                payload = {"operation": "aggregate", "pipeline": payload}
            if not isinstance(payload, dict):
                raise ValueError("The MongoDB command must be a JSON object.")

            operation = str(payload.get("operation") or payload.get("op") or "find").lower()
            if operation not in SUPPORTED_OPERATIONS:
                raise ValueError(
                    f"Unsupported MongoDB operation '{operation}'. Supported: "
                    + ", ".join(SUPPORTED_OPERATIONS)
                )

            if operation == "listcollections":
                names = self._collection_names()
                rows = [{"name": name} for name in names]
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=["name"],
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({len(rows)} collections)",
                )

            collection_name = payload.get("collection") or payload.get("coll")
            if not collection_name:
                raise ValueError("The MongoDB command requires a 'collection' field.")

            collection = self._db[str(collection_name)]
            query_filter = payload.get("filter") or {}
            projection = payload.get("projection")

            if operation == "find":
                cursor = collection.find(query_filter, projection)
                documents = list(self._apply_find_options(cursor, payload))
                columns, rows = self._rows_from_documents(documents)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({len(rows)} documents returned)",
                )

            if operation == "findone":
                document = collection.find_one(query_filter, projection)
                documents = [document] if document else []
                columns, rows = self._rows_from_documents(documents)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({len(rows)} document returned)",
                )

            if operation == "aggregate":
                pipeline = payload.get("pipeline") or []
                if not isinstance(pipeline, list):
                    raise ValueError("'pipeline' must be a JSON array of stages.")
                documents = list(collection.aggregate(pipeline))
                columns, rows = self._rows_from_documents(documents)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({len(rows)} documents returned)",
                )

            if operation == "count":
                total = int(collection.count_documents(query_filter))
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=["count"],
                    rows=[{"count": total}],
                    row_count=1,
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({total} documents matched)",
                )

            if operation == "distinct":
                field = payload.get("field")
                if not field:
                    raise ValueError("'distinct' requires a 'field'.")
                values = collection.distinct(field, query_filter)
                rows = [{"value": _serialize_mongo_value(value)} for value in values]
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=["value"],
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed,
                    message=f"Query executed successfully ({len(rows)} distinct values)",
                )

            if operation == "insertone":
                document = payload.get("document") or payload.get("doc")
                if not isinstance(document, dict):
                    raise ValueError("'insertOne' requires a 'document' object.")
                result = collection.insert_one(document)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=1,
                    execution_time_ms=elapsed,
                    message=f"Statement executed successfully (inserted _id: {result.inserted_id})",
                )

            if operation == "insertmany":
                documents = payload.get("documents") or payload.get("docs")
                if not isinstance(documents, list):
                    raise ValueError("'insertMany' requires a 'documents' array.")
                result = collection.insert_many(documents)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=len(result.inserted_ids),
                    execution_time_ms=elapsed,
                    message=f"Statement executed successfully ({len(result.inserted_ids)} documents inserted)",
                )

            if operation in ("updateone", "updatemany"):
                update_doc = payload.get("update")
                if not isinstance(update_doc, dict):
                    raise ValueError(f"'{operation}' requires an 'update' object.")
                if not any(key.startswith("$") for key in update_doc.keys()):
                    update_doc = {"$set": update_doc}
                method = collection.update_one if operation == "updateone" else collection.update_many
                result = method(query_filter, update_doc)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=int(result.modified_count),
                    execution_time_ms=elapsed,
                    message=(
                        "Statement executed successfully "
                        f"({result.matched_count} matched, {result.modified_count} modified)"
                    ),
                )

            if operation == "replaceone":
                document = payload.get("document") or payload.get("doc")
                if not isinstance(document, dict):
                    raise ValueError("'replaceOne' requires a 'document' object.")
                result = collection.replace_one(query_filter, document)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=int(result.modified_count),
                    execution_time_ms=elapsed,
                    message=(
                        "Statement executed successfully "
                        f"({result.matched_count} matched, {result.modified_count} modified)"
                    ),
                )

            if operation in ("deleteone", "deletemany"):
                method = collection.delete_one if operation == "deleteone" else collection.delete_many
                result = method(query_filter)
                elapsed = round((time_mod.time() - start_time) * 1000, 2)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=int(result.deleted_count),
                    execution_time_ms=elapsed,
                    message=f"Statement executed successfully ({result.deleted_count} documents deleted)",
                )

            raise ValueError(f"Unsupported MongoDB operation '{operation}'.")
        except Exception as exc:
            elapsed = round((time_mod.time() - start_time) * 1000, 2)
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"MongoDB execution error ({elapsed} ms): {exc}")

    def get_query_records(self, query: str, pagination: PaginationParams) -> PaginatedRecords:
        """Read paginated records from a saved find or aggregate command."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_query = query.strip()
        if not clean_query:
            return PaginatedRecords(
                total=0,
                page=pagination.page,
                page_size=pagination.page_size,
                total_pages=1,
                columns=[],
                records=[],
                pk_columns=[],
            )

        payload = _json_loads(clean_query)
        if isinstance(payload, list):
            payload = {"operation": "aggregate", "pipeline": payload}
        if not isinstance(payload, dict):
            raise ValueError("The MongoDB view query must be a JSON object.")

        operation = str(payload.get("operation") or payload.get("op") or "find").lower()
        if operation not in ("find", "aggregate"):
            raise ValueError("Custom MongoDB views support only 'find' or 'aggregate' operations.")

        collection_name = payload.get("collection") or payload.get("coll")
        if not collection_name:
            raise ValueError("The MongoDB view query requires a 'collection' field.")

        collection = self._db[str(collection_name)]
        schema = self.get_schema(collection_name)
        field_names = [column.name for column in schema.columns]
        search_filter = self._build_search_filter(pagination.search, field_names)
        offset = (pagination.page - 1) * pagination.page_size

        if pagination.sort_by:
            sort_spec = self._resolve_sort(pagination.sort_by, pagination.sort_dir, field_names)
        elif payload.get("sort"):
            payload_sort = payload.get("sort")
            if isinstance(payload_sort, dict):
                sort_spec = [(key, value) for key, value in payload_sort.items()]
            elif isinstance(payload_sort, list):
                sort_spec = [tuple(item) for item in payload_sort]
            else:
                sort_spec = None
        elif operation == "find":
            # Stable default order so pagination is deterministic. Aggregates
            # keep whatever ordering their pipeline already defines.
            sort_spec = self._resolve_sort(None, "asc", field_names)
        else:
            sort_spec = None

        if operation == "find":
            query_filter = self._merge_filters(payload.get("filter") or {}, search_filter)
            total = int(collection.count_documents(query_filter))
            cursor = collection.find(query_filter, payload.get("projection"))
            if sort_spec:
                cursor = cursor.sort(sort_spec)
            documents = list(cursor.skip(offset).limit(pagination.page_size))
        else:
            base_pipeline = payload.get("pipeline") or []
            if not isinstance(base_pipeline, list):
                raise ValueError("'pipeline' must be a JSON array of stages.")
            write_stage = _find_write_stage(base_pipeline)
            if write_stage:
                raise ValueError(
                    f"Custom MongoDB views are read-only; the '{write_stage}' stage is not allowed."
                )

            count_pipeline = list(base_pipeline)
            if search_filter:
                count_pipeline.append({"$match": search_filter})
            count_pipeline.append({"$count": "total"})
            count_result = list(collection.aggregate(count_pipeline))
            total = int(count_result[0]["total"]) if count_result else 0

            page_pipeline = list(base_pipeline)
            if search_filter:
                page_pipeline.append({"$match": search_filter})
            if sort_spec:
                page_pipeline.append(
                    {
                        "$sort": {
                            field: 1 if direction == ASCENDING else -1
                            for field, direction in sort_spec
                        }
                    }
                )
            page_pipeline.append({"$skip": offset})
            page_pipeline.append({"$limit": pagination.page_size})
            documents = list(collection.aggregate(page_pipeline))

        columns, records = self._columns_and_records(documents, field_names)
        total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1

        return PaginatedRecords(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            columns=columns,
            records=records,
            pk_columns=[],
        )
