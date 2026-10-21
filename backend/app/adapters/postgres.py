"""PostgreSQL adapter for vg-data-visor using psycopg 3."""
from datetime import date, datetime, time
from decimal import Decimal
import os
import re
import time as time_mod
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

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


def _quote_ident(name: str) -> str:
    """Escape a PostgreSQL identifier by wrapping it in double quotes."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _serialize_pg_value(val: Any) -> Any:
    """Convert PostgreSQL/Python types into standard JSON-serializable types."""
    if val is None:
        return None
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (bytes, memoryview)):
        return bytes(val).hex()
    if isinstance(val, list):
        return [_serialize_pg_value(item) for item in val]
    if isinstance(val, dict):
        return {k: _serialize_pg_value(v) for k, v in val.items()}
    return val


class PostgreSQLDataSource(BaseDataSource):
    """BaseDataSource implementation for PostgreSQL databases."""

    def __init__(self):
        self._conn: Optional[psycopg.Connection] = None
        self._conn_str: Optional[str] = None
        self._host: Optional[str] = None
        self._port: int = 5432
        self._database: Optional[str] = None
        self._user: Optional[str] = None

    @classmethod
    def test_connection(
        cls,
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 5432,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        sslmode: str = "prefer",
        timeout: int = 5,
    ) -> Dict[str, Any]:
        """Test PostgreSQL connection without storing session state."""
        conn_kwargs: Dict[str, Any] = {"connect_timeout": timeout, "autocommit": True}
        if uri and uri.strip():
            conn_target: Union[str, Dict[str, Any]] = uri.strip()
        else:
            conn_target = {
                "host": host or "localhost",
                "port": port or 5432,
                "dbname": database or "postgres",
                "user": user or "postgres",
                "password": password or "",
                "sslmode": sslmode or "prefer",
                **conn_kwargs,
            }

        if isinstance(conn_target, str):
            conn = psycopg.connect(conn_target, **conn_kwargs)
        else:
            conn = psycopg.connect(**conn_target)

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), current_database();")
                row = cur.fetchone()
                version = row[0] if row else ""
                current_db = row[1] if row else (database or "")
            return {
                "success": True,
                "message": "Connection successful",
                "server_version": version,
                "database": current_db,
            }
        finally:
            conn.close()

    def connect(
        self,
        path: str = "",
        host: Optional[str] = None,
        port: int = 5432,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        sslmode: str = "prefer",
        timeout: int = 10,
    ) -> ConnectionInfo:
        """Connect to a PostgreSQL database."""
        self.close()

        conn_kwargs: Dict[str, Any] = {"connect_timeout": timeout, "autocommit": True}
        clean_path = path.strip() if path else ""

        if clean_path and (clean_path.startswith("postgresql://") or clean_path.startswith("postgres://")):
            conn = psycopg.connect(clean_path, **conn_kwargs)
            self._conn_str = clean_path
            # Extract info from connection
            info = conn.info
            self._host = info.host or "localhost"
            self._port = int(info.port or 5432)
            self._database = info.dbname or "postgres"
            self._user = info.user or "postgres"
        else:
            h = host or "localhost"
            p = port or 5432
            db = database or "postgres"
            u = user or "postgres"
            pwd = password or ""
            ssl_m = sslmode or "prefer"

            conn = psycopg.connect(
                host=h,
                port=p,
                dbname=db,
                user=u,
                password=pwd,
                sslmode=ssl_m,
                **conn_kwargs,
            )
            self._host = h
            self._port = p
            self._database = db
            self._user = u
            self._conn_str = f"postgres://{u}@{h}:{p}/{db}"

        # Restrict default search path to public
        with conn.cursor() as cur:
            cur.execute("SET search_path TO public;")

        self._conn = conn
        return self.get_connection_info()

    def close(self) -> None:
        """Close active connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._conn_str = None
            self._host = None
            self._database = None
            self._user = None

    def is_connected(self) -> bool:
        """Check whether connection is open."""
        return self._conn is not None and not self._conn.closed

    def get_connection_info(self) -> ConnectionInfo:
        """Return metadata about current connection."""
        if not self.is_connected():
            return ConnectionInfo(path="", connected=False, db_type="postgres")

        size_bytes = 0
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT pg_database_size(current_database());")
                res = cur.fetchone()
                if res and res[0] is not None:
                    size_bytes = int(res[0])
        except Exception:
            size_bytes = 0

        tables_count = 0
        try:
            tables_count = len(self.list_collections())
        except Exception:
            tables_count = 0

        display_path = f"{self._user}@{self._host}:{self._port}/{self._database}"

        return ConnectionInfo(
            path=display_path,
            connected=True,
            size_bytes=size_bytes,
            tables_count=tables_count,
            db_type="postgres",
            database=self._database,
            host=self._host,
            port=self._port,
            user=self._user,
            schema_name="public",
        )

    def list_collections(self) -> List[TableSummary]:
        """List tables and views in public schema."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        sql_query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name ASC;
        """
        summaries: List[TableSummary] = []
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_query)
            rows = cur.fetchall()
            for r in rows:
                name = r["table_name"]
                raw_type = r["table_type"]
                kind = "view" if "VIEW" in raw_type.upper() else "table"
                count = None
                try:
                    with self._conn.cursor() as count_cur:
                        count_cur.execute(f"SELECT COUNT(*) FROM {_quote_ident(name)};")
                        c_res = count_cur.fetchone()
                        if c_res and c_res[0] is not None:
                            count = int(c_res[0])
                except Exception:
                    count = None
                summaries.append(TableSummary(name=name, type=kind, row_count=count))
        return summaries

    def get_schema(self, collection_name: str) -> TableSchema:
        """Get column and constraint schema for a table/view in public schema."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        with self._conn.cursor(row_factory=dict_row) as cur:
            # Check existence and type
            cur.execute(
                """
                SELECT table_type 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = %s;
                """,
                (collection_name,),
            )
            tbl = cur.fetchone()
            if not tbl:
                raise KeyError(f"Table or view '{collection_name}' does not exist.")
            kind = "view" if "VIEW" in tbl["table_type"].upper() else "table"

            # Fetch primary keys
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position ASC;
                """,
                (collection_name,),
            )
            pk_rows = cur.fetchall()
            pk_columns = [r["column_name"] for r in pk_rows]

            # Fetch columns
            cur.execute(
                """
                SELECT 
                    column_name, 
                    data_type, 
                    is_nullable, 
                    column_default, 
                    identity_generation
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position ASC;
                """,
                (collection_name,),
            )
            col_rows = cur.fetchall()

        columns: List[ColumnDefinition] = []
        for c in col_rows:
            col_name = c["column_name"]
            raw_type = (c["data_type"] or "text").upper()
            is_pk = col_name in pk_columns
            not_null = c["is_nullable"] == "NO"
            dflt = c["column_default"]
            is_identity = c["identity_generation"] is not None
            is_auto = is_identity or (dflt and "nextval(" in str(dflt).lower())

            columns.append(
                ColumnDefinition(
                    name=col_name,
                    type=raw_type,
                    is_pk=is_pk,
                    not_null=not_null,
                    default_value=str(dflt) if dflt is not None else None,
                    auto_increment=bool(is_auto),
                )
            )

        return TableSchema(
            name=collection_name,
            type=kind,
            columns=columns,
            pk_columns=pk_columns,
            sql=None,
        )

    def get_records(self, collection_name: str, pagination: PaginationParams) -> PaginatedRecords:
        """Fetch paginated, filtered, and sorted records from a table/view."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        col_names = [c.name for c in schema.columns]
        table_quoted = _quote_ident(collection_name)
        has_pk = len(schema.pk_columns) > 0

        select_cols = [_quote_ident(c) for c in col_names]
        if not has_pk and schema.type == "table":
            select_cols.insert(0, 'ctid::text AS "_rowid_"')

        cols_str = ", ".join(select_cols) if select_cols else "*"

        where_clause = ""
        params: List[Any] = []
        if pagination.search and pagination.search.strip():
            search_term = f"%{pagination.search.strip()}%"
            or_parts = [f"CAST({_quote_ident(c)} AS TEXT) ILIKE %s" for c in col_names]
            if or_parts:
                where_clause = " WHERE " + " OR ".join(or_parts)
                params.extend([search_term] * len(or_parts))

        # Total count
        count_sql = f"SELECT COUNT(*) as total FROM {table_quoted}{where_clause};"
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["total"]

        # Sorting
        order_clause = ""
        if pagination.sort_by and pagination.sort_by in col_names:
            direction = "DESC" if pagination.sort_dir.lower() == "desc" else "ASC"
            order_clause = f" ORDER BY {_quote_ident(pagination.sort_by)} {direction}"
        elif has_pk:
            safe_pks = [f"{_quote_ident(p)} ASC" for p in schema.pk_columns]
            order_clause = f" ORDER BY {', '.join(safe_pks)}"
        elif not has_pk and schema.type == "table":
            order_clause = ' ORDER BY "_rowid_" ASC'

        # Pagination
        offset = (pagination.page - 1) * pagination.page_size
        query_sql = f"SELECT {cols_str} FROM {table_quoted}{where_clause}{order_clause} LIMIT %s OFFSET %s;"
        query_params = list(params) + [pagination.page_size, offset]

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query_sql, query_params)
            rows = cur.fetchall()

        records = [_serialize_pg_value(dict(r)) for r in rows]
        total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1

        returned_cols = list(col_names)
        if not has_pk and schema.type == "table":
            returned_cols.insert(0, "_rowid_")

        return PaginatedRecords(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            columns=returned_cols,
            records=records,
            pk_columns=schema.pk_columns,
        )

    def insert_record(self, collection_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a record into table and return inserted row."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        schema_cols = {c.name: c for c in schema.columns}

        clean_values: Dict[str, Any] = {}
        for k, v in values.items():
            if k in schema_cols:
                col = schema_cols[k]
                if col.auto_increment and (v is None or v == ""):
                    continue
                clean_values[k] = None if v == "" and not col.not_null else v

        if not clean_values:
            sql_stmt = f"INSERT INTO {_quote_ident(collection_name)} DEFAULT VALUES RETURNING *;"
            params: List[Any] = []
        else:
            col_list = list(clean_values.keys())
            cols_clause = ", ".join([_quote_ident(c) for c in col_list])
            placeholders = ", ".join(["%s"] * len(col_list))
            sql_stmt = f"INSERT INTO {_quote_ident(collection_name)} ({cols_clause}) VALUES ({placeholders}) RETURNING *;"
            params = [clean_values[c] for c in col_list]

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_stmt, params)
            row = cur.fetchone()
            if not row:
                raise RuntimeError("Failed to insert record.")
            return _serialize_pg_value(dict(row))

    def update_record(
        self, collection_name: str, pk_values: Dict[str, Any], values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a record identified by PK or _rowid_ (ctid)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")
        if not pk_values:
            raise ValueError("No primary key values provided to identify the record.")

        schema = self.get_schema(collection_name)
        schema_cols = {c.name: c for c in schema.columns}

        set_parts: List[str] = []
        set_params: List[Any] = []
        for k, v in values.items():
            if k in schema_cols:
                col = schema_cols[k]
                val = None if v == "" and not col.not_null else v
                set_parts.append(f"{_quote_ident(k)} = %s")
                set_params.append(val)

        if not set_parts:
            raise ValueError("No fields provided to update.")

        where_parts: List[str] = []
        where_params: List[Any] = []

        if "_rowid_" in pk_values:
            where_parts.append("ctid = %s::tid")
            where_params.append(str(pk_values["_rowid_"]))
        else:
            for pk_col in schema.pk_columns:
                if pk_col not in pk_values:
                    raise ValueError(f"Missing primary key value for '{pk_col}'.")
                where_parts.append(f"{_quote_ident(pk_col)} = %s")
                where_params.append(pk_values[pk_col])

        sql_stmt = (
            f"UPDATE {_quote_ident(collection_name)} "
            f"SET {', '.join(set_parts)} "
            f"WHERE {' AND '.join(where_parts)} "
            f"RETURNING *;"
        )
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_stmt, set_params + where_params)
            row = cur.fetchone()
            if not row:
                raise ValueError("Record not found or not modified.")
            return _serialize_pg_value(dict(row))

    def delete_record(self, collection_name: str, pk_values: Dict[str, Any]) -> bool:
        """Delete a record identified by PK or _rowid_ (ctid)."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")
        if not pk_values:
            raise ValueError("No primary key values provided to identify the record.")

        schema = self.get_schema(collection_name)
        where_parts: List[str] = []
        where_params: List[Any] = []

        if "_rowid_" in pk_values:
            where_parts.append("ctid = %s::tid")
            where_params.append(str(pk_values["_rowid_"]))
        else:
            for pk_col in schema.pk_columns:
                if pk_col not in pk_values:
                    raise ValueError(f"Missing primary key value for '{pk_col}'.")
                where_parts.append(f"{_quote_ident(pk_col)} = %s")
                where_params.append(pk_values[pk_col])

        sql_stmt = f"DELETE FROM {_quote_ident(collection_name)} WHERE {' AND '.join(where_parts)};"
        with self._conn.cursor() as cur:
            cur.execute(sql_stmt, where_params)
            return cur.rowcount > 0

    def create_table(self, request: CreateTableRequest) -> bool:
        """Create a new PostgreSQL table in public schema."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_name = request.name.strip()
        if not table_name:
            raise ValueError("Table name cannot be empty.")
        if not request.columns:
            raise ValueError("At least one column is required to create a table.")

        col_defs: List[str] = []
        pk_cols: List[str] = []

        for col in request.columns:
            c_name = col.name.strip()
            if not c_name:
                continue
            c_type = col.type.strip().upper()

            # Handle types
            if col.auto_increment:
                if c_type in ("INT", "INTEGER"):
                    c_type = "SERIAL"
                elif c_type in ("BIGINT",):
                    c_type = "BIGSERIAL"
            elif c_type == "BLOB":
                c_type = "BYTEA"

            parts = [f"{_quote_ident(c_name)} {c_type}"]

            if col.is_pk:
                pk_cols.append(_quote_ident(c_name))

            if col.not_null and not col.is_pk:
                parts.append("NOT NULL")

            if col.default_value is not None and col.default_value.strip():
                parts.append(f"DEFAULT {col.default_value.strip()}")

            col_defs.append(" ".join(parts))

        if pk_cols:
            col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

        sql_stmt = f"CREATE TABLE {_quote_ident(table_name)} (\n  " + ",\n  ".join(col_defs) + "\n);"
        with self._conn.cursor() as cur:
            cur.execute(sql_stmt)
        return True

    def add_column(self, collection_name: str, column: ColumnDefinition) -> bool:
        """Add a column to an existing PostgreSQL table."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_quoted = _quote_ident(collection_name)
        col_quoted = _quote_ident(column.name.strip())
        c_type = column.type.strip().upper()
        if c_type == "BLOB":
            c_type = "BYTEA"

        parts = [f"{col_quoted} {c_type}"]
        if column.not_null:
            parts.append("NOT NULL")
        if column.default_value is not None and column.default_value.strip():
            parts.append(f"DEFAULT {column.default_value.strip()}")

        sql_stmt = f"ALTER TABLE {table_quoted} ADD COLUMN {' '.join(parts)};"
        with self._conn.cursor() as cur:
            cur.execute(sql_stmt)
        return True

    def rename_table(self, collection_name: str, new_name: str) -> bool:
        """Rename an existing table in public schema."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_new = new_name.strip()
        if not clean_new:
            raise ValueError("The new table name cannot be empty.")
        if clean_new == collection_name:
            return True

        sql_stmt = f"ALTER TABLE {_quote_ident(collection_name)} RENAME TO {_quote_ident(clean_new)};"
        with self._conn.cursor() as cur:
            cur.execute(sql_stmt)
        return True

    def drop_table(self, collection_name: str) -> bool:
        """Drop a table or view in public schema."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        kind = "VIEW" if schema.type == "view" else "TABLE"
        sql_stmt = f"DROP {kind} {_quote_ident(collection_name)} CASCADE;"
        with self._conn.cursor() as cur:
            cur.execute(sql_stmt)
        return True

    def execute_query(self, query: str) -> QueryResult:
        """Execute an arbitrary SQL query."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_query = query.strip()
        if not clean_query:
            return QueryResult(columns=[], rows=[], row_count=0, execution_time_ms=0.0)

        start_time = time_mod.time()
        try:
            with self._conn.cursor() as cur:
                cur.execute(clean_query)
                elapsed_ms = round((time_mod.time() - start_time) * 1000, 2)

                if cur.description:
                    columns = [col[0] for col in cur.description]
                    raw_rows = cur.fetchall()
                    rows = [
                        _serialize_pg_value({columns[i]: row[i] for i in range(len(columns))})
                        for row in raw_rows
                    ]
                    return QueryResult(
                        columns=columns,
                        rows=rows,
                        row_count=len(rows),
                        execution_time_ms=elapsed_ms,
                        message=f"Query executed successfully ({len(rows)} rows returned)",
                    )
                else:
                    affected = cur.rowcount if cur.rowcount >= 0 else 0
                    return QueryResult(
                        columns=[],
                        rows=[],
                        row_count=affected,
                        execution_time_ms=elapsed_ms,
                        message=f"Statement executed successfully ({affected} rows affected)",
                    )
        except Exception as e:
            elapsed_ms = round((time_mod.time() - start_time) * 1000, 2)
            raise RuntimeError(f"SQL execution error ({elapsed_ms} ms): {str(e)}")

    def get_query_records(self, query: str, pagination: PaginationParams) -> PaginatedRecords:
        """Read paginated, filtered, and sorted records from an arbitrary SELECT query or view."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_query = query.strip().rstrip(";").strip()
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

        # Views are read-only: run them in a READ ONLY transaction, and always
        # bind at least one parameter so psycopg uses the extended protocol,
        # which rejects multiple statements (e.g. "...) s; COMMIT; DROP ...").
        # With bound parameters a literal "%" must be written as "%%".
        subquery = clean_query.replace("%", "%%")

        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY;")

            # Validate query syntax and extract columns
            try:
                cur.execute(f"SELECT * FROM ({subquery}) AS _subquery LIMIT %s;", [0])
            except Exception as e:
                raise ValueError(f"Invalid query: {str(e)}")

            col_names: List[str] = []
            if cur.description:
                seen: Dict[str, int] = {}
                for col in cur.description:
                    raw_name = col[0]
                    cnt = seen.get(raw_name, 0)
                    seen[raw_name] = cnt + 1
                    col_names.append(raw_name if cnt == 0 else f"{raw_name}_{cnt}")

            # WHERE clause for search
            where_clause = ""
            params: List[Any] = []
            if pagination.search and pagination.search.strip():
                search_term = f"%{pagination.search.strip()}%"
                or_parts = [
                    f"CAST({_quote_ident(c).replace('%', '%%')} AS TEXT) ILIKE %s" for c in col_names
                ]
                if or_parts:
                    where_clause = " WHERE " + " OR ".join(or_parts)
                    params.extend([search_term] * len(or_parts))

            # Total count (the LIMIT parameter only forces the extended protocol)
            count_sql = f"SELECT COUNT(*) as total FROM ({subquery}) AS _subquery{where_clause} LIMIT %s;"
            cur.execute(count_sql, params + [1])
            total = cur.fetchone()[0]

            # Sorting
            order_clause = ""
            if pagination.sort_by and pagination.sort_by in col_names:
                direction = "DESC" if pagination.sort_dir.lower() == "desc" else "ASC"
                order_clause = f" ORDER BY {_quote_ident(pagination.sort_by).replace('%', '%%')} {direction}"

            # Pagination
            offset = (pagination.page - 1) * pagination.page_size
            query_sql = (
                f"SELECT * FROM ({subquery}) AS _subquery{where_clause}{order_clause} LIMIT %s OFFSET %s;"
            )
            query_params = list(params) + [pagination.page_size, offset]

            cur.execute(query_sql, query_params)
            raw_rows = cur.fetchall()

        records = [
            _serialize_pg_value({col_names[i]: row[i] for i in range(len(col_names))})
            for row in raw_rows
        ]
        total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1

        return PaginatedRecords(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            columns=col_names,
            records=records,
            pk_columns=[],
        )
