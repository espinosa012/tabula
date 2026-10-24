"""SQLite adapter for tabula."""
import os
import sqlite3
import time
from typing import List, Dict, Any, Optional
from urllib.request import pathname2url

from backend.app.core.interfaces import BaseDataSource
from backend.app.core.models import (
    TableSummary,
    TableSchema,
    ColumnDefinition,
    PaginationParams,
    PaginatedRecords,
    QueryResult,
    ConnectionInfo,
    CreateTableRequest,
)


def _quote_ident(name: str) -> str:
    """Escape a SQL identifier by wrapping it in double quotes."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


class SQLiteDataSource(BaseDataSource):
    """BaseDataSource implementation for SQLite databases."""

    def __init__(self):
        self._path: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self, path: str) -> ConnectionInfo:
        """Connect to an existing SQLite file."""
        clean_path = path.strip().strip("'\"")
        abs_path = os.path.abspath(os.path.expanduser(clean_path))
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File does not exist: {abs_path}")
        if os.path.isdir(abs_path):
            raise ValueError(f"The specified path is a directory, not a file: {abs_path}")

        # Check whether it is a valid SQLite file
        try:
            uri = f"file:{pathname2url(abs_path)}?mode=rw"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA schema_version;")
            cursor.fetchone()
        except sqlite3.DatabaseError as e:
            raise ValueError(f"The file is not a valid SQLite database: {e}")

        # Close the previous connection if one existed
        self.close()

        self._path = abs_path
        self._conn = conn
        try:
            self._conn.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass

        return self.get_connection_info()

    def create_database(self, path: str) -> ConnectionInfo:
        """Create a new empty SQLite database file and connect to it."""
        clean_path = path.strip().strip("'\"")
        abs_path = os.path.abspath(os.path.expanduser(clean_path))
        if os.path.exists(abs_path):
            raise FileExistsError(f"File already exists: {abs_path}")

        parent_dir = os.path.dirname(abs_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        self.close()

        # Create an empty database
        conn = sqlite3.connect(abs_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA user_version = 0;")
        conn.commit()

        self._path = abs_path
        self._conn = conn
        try:
            self._conn.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass

        return self.get_connection_info()

    def close(self) -> None:
        """Close the current connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._path = None

    def is_connected(self) -> bool:
        """Check whether there is an active connection."""
        return self._conn is not None and self._path is not None

    def get_connection_info(self) -> ConnectionInfo:
        """Connection metadata."""
        if not self.is_connected():
            return ConnectionInfo(path="", connected=False)

        size_bytes = 0
        if self._path and os.path.exists(self._path):
            size_bytes = os.path.getsize(self._path)

        tables_count = len(self.list_collections())
        return ConnectionInfo(
            path=self._path,
            connected=True,
            size_bytes=size_bytes,
            tables_count=tables_count,
        )

    def list_collections(self) -> List[TableSummary]:
        """List the tables and views in the database."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT name, type FROM sqlite_master 
            WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' 
            ORDER BY name ASC;
            """
        )
        rows = cursor.fetchall()
        summaries = []
        for r in rows:
            name = r["name"]
            kind = r["type"]
            count = None
            try:
                c_cursor = self._conn.cursor()
                c_cursor.execute(f"SELECT COUNT(*) as c FROM {_quote_ident(name)};")
                c_res = c_cursor.fetchone()
                if c_res:
                    count = c_res["c"]
            except Exception:
                count = None
            summaries.append(TableSummary(name=name, type=kind, row_count=count))
        return summaries

    def get_schema(self, collection_name: str) -> TableSchema:
        """Get the column and key structure of a table or view."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT type, sql FROM sqlite_master WHERE name = ? AND type IN ('table', 'view');",
            (collection_name,),
        )
        meta = cursor.fetchone()
        if not meta:
            raise KeyError(f"Table or view '{collection_name}' does not exist.")

        kind = meta["type"]
        create_sql = meta["sql"]

        cursor.execute(f"PRAGMA table_info({_quote_ident(collection_name)});")
        columns_info = cursor.fetchall()

        columns: List[ColumnDefinition] = []
        pk_columns: List[str] = []

        for col in columns_info:
            col_name = col["name"]
            col_type = (col["type"] or "TEXT").upper()
            is_pk = bool(col["pk"] > 0)
            not_null = bool(col["notnull"])
            default_val = col["dflt_value"]

            # Check for AUTOINCREMENT by parsing create_sql
            auto_inc = False
            if is_pk and create_sql:
                if "AUTOINCREMENT" in create_sql.upper():
                    auto_inc = True

            if is_pk:
                pk_columns.append(col_name)

            columns.append(
                ColumnDefinition(
                    name=col_name,
                    type=col_type,
                    is_pk=is_pk,
                    not_null=not_null,
                    default_value=str(default_val) if default_val is not None else None,
                    auto_increment=auto_inc,
                )
            )

        return TableSchema(
            name=collection_name,
            type=kind,
            columns=columns,
            pk_columns=pk_columns,
            sql=create_sql,
        )

    def get_records(self, collection_name: str, pagination: PaginationParams) -> PaginatedRecords:
        """Read paginated, filtered, and sorted records."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        schema = self.get_schema(collection_name)
        col_names = [c.name for c in schema.columns]
        table_quoted = _quote_ident(collection_name)

        has_pk = len(schema.pk_columns) > 0
        select_cols = [_quote_ident(c) for c in col_names]
        if not has_pk and schema.type == "table":
            select_cols.insert(0, 'rowid AS "_rowid_"')

        cols_str = ", ".join(select_cols) if select_cols else "*"

        # WHERE clause
        where_clause = ""
        params: List[Any] = []
        if pagination.search and pagination.search.strip():
            search_term = f"%{pagination.search.strip()}%"
            or_parts = [f"CAST({_quote_ident(c)} AS TEXT) LIKE ?" for c in col_names]
            if or_parts:
                where_clause = " WHERE " + " OR ".join(or_parts)
                params.extend([search_term] * len(or_parts))

        # Total count with filter
        count_sql = f"SELECT COUNT(*) as total FROM {table_quoted}{where_clause};"
        cursor = self._conn.cursor()
        cursor.execute(count_sql, params)
        total = cursor.fetchone()["total"]

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
        query_sql = f"SELECT {cols_str} FROM {table_quoted}{where_clause}{order_clause} LIMIT ? OFFSET ?;"
        query_params = list(params) + [pagination.page_size, offset]

        cursor.execute(query_sql, query_params)
        raw_rows = cursor.fetchall()

        records = [dict(r) for r in raw_rows]
        total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1

        pk_cols = schema.pk_columns if has_pk else (["_rowid_"] if schema.type == "table" else [])

        return PaginatedRecords(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            columns=col_names,
            records=records,
            pk_columns=pk_cols,
        )

    def insert_record(self, collection_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new record into the table."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_quoted = _quote_ident(collection_name)
        clean_values = {k: v for k, v in values.items() if k != "_rowid_"}
        if not clean_values:
            sql = f"INSERT INTO {table_quoted} DEFAULT VALUES;"
            cursor = self._conn.cursor()
            cursor.execute(sql)
        else:
            col_list = list(clean_values.keys())
            cols_clause = ", ".join([_quote_ident(c) for c in col_list])
            placeholders = ", ".join(["?"] * len(col_list))
            sql = f"INSERT INTO {table_quoted} ({cols_clause}) VALUES ({placeholders});"
            cursor = self._conn.cursor()
            cursor.execute(sql, [clean_values[c] for c in col_list])

        self._conn.commit()
        last_id = cursor.lastrowid
        return {"status": "created", "lastrowid": last_id}

    def update_record(
        self, collection_name: str, pk_values: Dict[str, Any], values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a record identified by primary keys or _rowid_."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_quoted = _quote_ident(collection_name)
        clean_values = {k: v for k, v in values.items() if k != "_rowid_"}
        if not clean_values:
            return {"status": "unchanged", "rows_affected": 0}

        set_parts = [f"{_quote_ident(k)} = ?" for k in clean_values.keys()]
        set_clause = ", ".join(set_parts)
        params: List[Any] = list(clean_values.values())

        where_parts = []
        for pk_name, pk_val in pk_values.items():
            if pk_name == "_rowid_":
                where_parts.append("rowid = ?")
            else:
                where_parts.append(f"{_quote_ident(pk_name)} = ?")
            params.append(pk_val)

        if not where_parts:
            raise ValueError("Primary keys or _rowid_ are required to identify the row to update.")

        where_clause = " WHERE " + " AND ".join(where_parts)
        sql = f"UPDATE {table_quoted} SET {set_clause}{where_clause};"

        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        self._conn.commit()
        return {"status": "updated", "rows_affected": cursor.rowcount}

    def delete_record(self, collection_name: str, pk_values: Dict[str, Any]) -> bool:
        """Delete a record identified by its primary keys or _rowid_."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_quoted = _quote_ident(collection_name)
        where_parts = []
        params: List[Any] = []
        for pk_name, pk_val in pk_values.items():
            if pk_name == "_rowid_":
                where_parts.append("rowid = ?")
            else:
                where_parts.append(f"{_quote_ident(pk_name)} = ?")
            params.append(pk_val)

        if not where_parts:
            raise ValueError("Primary keys or _rowid_ are required to delete.")

        where_clause = " WHERE " + " AND ".join(where_parts)
        sql = f"DELETE FROM {table_quoted}{where_clause};"

        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        self._conn.commit()
        return cursor.rowcount > 0

    def create_table(self, request: CreateTableRequest) -> bool:
        """Create a new SQLite table with the specified columns."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_name = request.name.strip()
        if not table_name:
            raise ValueError("The table name cannot be empty.")

        col_defs = []
        pk_cols = []
        for col in request.columns:
            c_name = col.name.strip()
            c_type = col.type.strip().upper()
            parts = [f"{_quote_ident(c_name)} {c_type}"]

            if col.is_pk and col.auto_increment and c_type == "INTEGER":
                parts.append("PRIMARY KEY AUTOINCREMENT")
            elif col.is_pk:
                pk_cols.append(_quote_ident(c_name))

            if col.not_null and not col.is_pk:
                parts.append("NOT NULL")

            if col.default_value is not None and col.default_value.strip():
                parts.append(f"DEFAULT {col.default_value.strip()}")

            col_defs.append(" ".join(parts))

        if pk_cols and not any(c.auto_increment for c in request.columns if c.is_pk):
            col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

        sql = f"CREATE TABLE {_quote_ident(table_name)} (\n  " + ",\n  ".join(col_defs) + "\n);"
        cursor = self._conn.cursor()
        cursor.execute(sql)
        self._conn.commit()
        return True

    def add_column(self, collection_name: str, column: ColumnDefinition) -> bool:
        """Add a column to an existing table with ALTER TABLE."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        table_quoted = _quote_ident(collection_name)
        col_quoted = _quote_ident(column.name.strip())
        c_type = column.type.strip().upper()
        parts = [f"{col_quoted} {c_type}"]

        if column.not_null:
            parts.append("NOT NULL")
        if column.default_value is not None and column.default_value.strip():
            parts.append(f"DEFAULT {column.default_value.strip()}")

        sql = f"ALTER TABLE {table_quoted} ADD COLUMN {' '.join(parts)};"
        cursor = self._conn.cursor()
        cursor.execute(sql)
        self._conn.commit()
        return True

    def rename_table(self, collection_name: str, new_name: str) -> bool:
        """Rename an existing table with ALTER TABLE RENAME TO."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        new_name = new_name.strip()
        if not new_name:
            raise ValueError("The new table name cannot be empty.")
        if new_name == collection_name:
            return True

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT type FROM sqlite_master WHERE name = ? AND type IN ('table', 'view');",
            (collection_name,),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Table or view '{collection_name}' does not exist.")
        if row["type"] != "table":
            raise ValueError("Only tables can be renamed; views must be dropped and recreated.")

        cursor.execute("SELECT 1 FROM sqlite_master WHERE name = ?;", (new_name,))
        if cursor.fetchone():
            raise ValueError(f"An object named '{new_name}' already exists.")

        cursor.execute(
            f"ALTER TABLE {_quote_ident(collection_name)} RENAME TO {_quote_ident(new_name)};"
        )
        self._conn.commit()
        return True

    def drop_table(self, collection_name: str) -> bool:
        """Delete a table or view with DROP TABLE or DROP VIEW."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT type FROM sqlite_master WHERE name = ? AND type IN ('table', 'view');",
            (collection_name,),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Table or view '{collection_name}' does not exist.")

        kind = row["type"].upper()
        cursor.execute(f"DROP {kind} {_quote_ident(collection_name)};")
        self._conn.commit()
        return True

    def execute_query(self, query: str) -> QueryResult:
        """Execute an arbitrary SQL query."""
        if not self.is_connected():
            raise RuntimeError("Database not connected.")

        clean_query = query.strip()
        if not clean_query:
            return QueryResult(columns=[], rows=[], row_count=0, execution_time_ms=0.0)

        start_time = time.time()
        cursor = self._conn.cursor()

        try:
            cursor.execute(clean_query)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                raw_rows = cursor.fetchall()
                rows = [dict(r) for r in raw_rows]
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=elapsed_ms,
                    message=f"Query executed successfully ({len(rows)} rows returned)",
                )
            else:
                self._conn.commit()
                affected = cursor.rowcount if cursor.rowcount >= 0 else 0
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=affected,
                    execution_time_ms=elapsed_ms,
                    message=f"Statement executed successfully ({affected} rows affected)",
                )
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            raise RuntimeError(f"SQL execution error ({elapsed_ms} ms): {str(e)}")

    def get_query_records(self, query: str, pagination: PaginationParams) -> PaginatedRecords:
        """Read paginated, filtered, and sorted records from an arbitrary SELECT query or custom view."""
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

        cursor = self._conn.cursor()

        # Validate query syntax and extract columns
        try:
            cursor.execute(f"SELECT * FROM ({clean_query}) AS _subquery LIMIT 0;")
        except Exception as e:
            raise ValueError(f"Invalid query: {str(e)}")

        col_names: List[str] = []
        if cursor.description:
            seen: Dict[str, int] = {}
            for col in cursor.description:
                raw_name = col[0]
                cnt = seen.get(raw_name, 0)
                seen[raw_name] = cnt + 1
                col_names.append(raw_name if cnt == 0 else f"{raw_name}_{cnt}")

        # WHERE clause for search
        where_clause = ""
        params: List[Any] = []
        if pagination.search and pagination.search.strip():
            search_term = f"%{pagination.search.strip()}%"
            or_parts = [f"CAST({_quote_ident(c)} AS TEXT) LIKE ?" for c in col_names]
            if or_parts:
                where_clause = " WHERE " + " OR ".join(or_parts)
                params.extend([search_term] * len(or_parts))

        # Total count
        count_sql = f"SELECT COUNT(*) as total FROM ({clean_query}) AS _subquery{where_clause};"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()["total"]

        # Sorting
        order_clause = ""
        if pagination.sort_by and pagination.sort_by in col_names:
            direction = "DESC" if pagination.sort_dir.lower() == "desc" else "ASC"
            order_clause = f" ORDER BY {_quote_ident(pagination.sort_by)} {direction}"

        # Pagination
        offset = (pagination.page - 1) * pagination.page_size
        query_sql = f"SELECT * FROM ({clean_query}) AS _subquery{where_clause}{order_clause} LIMIT ? OFFSET ?;"
        query_params = list(params) + [pagination.page_size, offset]

        cursor.execute(query_sql, query_params)
        raw_rows = cursor.fetchall()

        records = [
            {col_names[i]: row[i] for i in range(len(col_names))}
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
