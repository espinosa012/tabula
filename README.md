# tabula

A local, 100% offline web tool for inspecting, editing, and managing SQLite, PostgreSQL, and MongoDB databases with Semantic UI (Fomantic-UI) and FastAPI.

---

## Features

- **Connection Management**:
  - Open any SQLite database by entering its path directly or using the assisted local file browser.
  - Create new SQLite databases from scratch.
  - Connect to local or remote PostgreSQL databases with either host/port/user parameters or a `postgresql://` URI.
  - Connect to local or remote MongoDB databases with either host/port/user parameters or a `mongodb://` / `mongodb+srv://` URI.
  - Test a PostgreSQL or MongoDB connection before activating it.
  - History of recent databases for one-click access.
- **Data Viewer & Editor (DML)**:
  - Tabular navigation with configurable pagination (25, 50, 100, 200 rows).
  - Real-time search and sorting by any column (ascending/descending).
  - Inserting, editing, and deleting records (with a safety confirmation).
- **Schema Designer (DDL)**:
  - Guided visual assistant to create new tables with SQLite types (`INTEGER`, `TEXT`, `REAL`, `BLOB`, `NUMERIC`) and constraints (`PRIMARY KEY`, `AUTOINCREMENT`, `NOT NULL`, `DEFAULT`).
  - Add columns to existing tables (`ALTER TABLE ADD COLUMN`).
  - Safe table deletion (`DROP TABLE`).
- **Interactive SQL Console**:
  - Execution of arbitrary SQL statements (`SELECT`, `INSERT`, `UPDATE`, `CREATE INDEX`, aggregations, and `JOIN`s) on SQLite and PostgreSQL.
  - Execution of JSON commands (`find`, `aggregate`, `count`, `insertOne`, `updateOne`, `deleteOne`, etc.) on MongoDB.
  - Dynamic results table with execution time and affected rows metrics.
- **100% Offline & Zero-Build**:
  - Served entirely by FastAPI.
  - No frontend build steps (no Node.js or npm).
  - All assets (CSS, JS, fonts, and icons) packaged locally.
- **Modern dependency manager**:
  - Based on `uv` and the standard [`pyproject.toml`](./pyproject.toml) specification (PEP 621 / PEP 735).

---

## Requirements

- Python 3.9 or higher
- [uv](https://github.com/astral-sh/uv) (blazing-fast Python package manager)

---

## Getting Started with `uv`

1. **Sync the virtual environment and install dependencies:**
   ```bash
   uv sync
   ```

2. **Start the application:**
   ```bash
   uv run python run.py
   ```

3. **Open in your browser:**
   Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## Running Tests

To run the full unit and end-to-end integration test suite with `uv`:

```bash
uv run pytest
```
