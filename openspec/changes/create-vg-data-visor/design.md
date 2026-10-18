# Design: Technical Architecture of vg-data-visor

## Context

See `proposal.md` for the general motivation and project context. The technical goal is to implement a local, self-contained web tool that operates 100% offline without the need for Node.js, frontend builds, or external cloud services.

## Goals / Non-Goals

**Goals:**
- Serve both the REST API and the static web application from a single lightweight Python process.
- Design a decoupled abstraction layer (`BaseDataSource`) that today implements `SQLiteDataSource` and allows CSV, JSON, and XML adapters to be added in the future without refactoring the API or the frontend.
- Implement a secure filesystem browser for the local filesystem to work around the limitation of web browsers that hide absolute paths.
- Provide full support for DML operations (paginated query, filters, editing, inserting, and deleting records) and DDL operations (creating tables, adding columns, dropping tables, and an arbitrary SQL console).
- Package all frontend resources (Fomantic-UI, jQuery, fonts, and icons) locally to guarantee offline operation.

**Non-Goals:**
- Support for client-server databases (PostgreSQL, MySQL, Oracle) in this version.
- Implementation of adapters for CSV, JSON, or XML in this first iteration (only the architecture and interfaces are prepared for them).
- Multi-tenant user authentication system (the tool is designed for single-user local use).
- Support for advanced destructive column modification (such as changing column types in older SQLite versions that require fully recreating tables).

## Decisions

### 1. Backend: FastAPI + Python `sqlite3`
- **Decision**: Use FastAPI with Uvicorn for the HTTP layer and the `sqlite3` standard library for persistence.
- **Reason**: `sqlite3` ships with Python with no additional C dependencies. FastAPI offers automatic OpenAPI documentation, fast serialization with Pydantic, and native ability to mount static files via `StaticFiles`.
- **Alternatives considered**:
  - *Flask / Bottle*: Lightweight but lacking native strict typing and automatic OpenAPI.
  - *SQLAlchemy / Tortoise-ORM*: Too oriented toward predefined static models; for a generic dynamic database viewer, direct access with `sqlite3` (`PRAGMA table_info`, dynamic introspection, and `sqlite3.Row`) is more direct, flexible, and predictable.

### 2. Frontend: Fomantic-UI (Semantic UI) with no build step (Zero-Build)
- **Decision**: Serve a SPA based on HTML5, Fomantic-UI (minified CSS/JS distribution), jQuery, and modular vanilla scripts from the static directory.
- **Reason**: It lets the application start immediately after a simple `pip install -r requirements.txt && python run.py`, without needing Node.js or bundling tools like Vite or Webpack installed. Fomantic-UI is the active successor to Semantic UI and provides rich interactive components (modals, dropdowns, tables, toasts).
- **Alternatives considered**:
  - *React / Vue with Vite*: Would add a strict dependency on Node.js/npm and a build process, complicating distribution as a purely local Python tool.
  - *Original classic Semantic UI*: Has not received patches for years; Fomantic-UI is 100% visually compatible and adds modern support.

### 3. `BaseDataSource` Abstraction Layer
- **Decision**: Define an abstract class or Protocol in Python:
  ```python
  class BaseDataSource(ABC):
      @abstractmethod
      def list_collections(self) -> List[CollectionMetadata]: ...
      @abstractmethod
      def get_schema(self, name: str) -> SchemaDefinition: ...
      @abstractmethod
      def get_records(self, name: str, pagination: Pagination, filters: Filter) -> PageResult: ...
      @abstractmethod
      def insert_record(self, name: str, data: dict) -> RecordResult: ...
      @abstractmethod
      def update_record(self, name: str, pk_value: Any, data: dict) -> RecordResult: ...
      @abstractmethod
      def delete_record(self, name: str, pk_value: Any) -> DeleteResult: ...
  ```
- **Reason**: Decouples the HTTP API from the nature of the underlying storage. The `SQLiteDataSource` adapter implements this interface and adds specific methods for DDL (`create_table`, `alter_table`, `execute_query`).

### 4. Local Filesystem Browser and Connection
- **Decision**: Create an endpoint `/api/fs/browse` that accepts a directory path (defaulting to the current working directory or `Path.home()`) and lists subdirectories and `.db`/`.sqlite` files.
- **Reason**: Works around the browser sandbox limitation that prevents knowing the real path of a file on the local disk.

## Risks / Trade-offs

- **[Risk] SQLite concurrency and locks (`database is locked`)** → **Mitigation**: Open connections with `check_same_thread=False`, enable WAL mode (`PRAGMA journal_mode=WAL;`) on write connections, and configure an adequate `timeout` (e.g. 10.0 seconds).
- **[Risk] Dependency on icons and fonts in offline mode** → **Mitigation**: Host the Fomantic-UI `themes/default/assets/fonts/` folder locally in `static/` and verify that the CSS files use local relative paths.
- **[Risk] SQL injection in custom queries** → **Mitigation**: Use mandatory parameterized queries for the CRUD operations generated by the UI. In the free SQL console, document that it runs direct commands with the local user's permissions on their file.

## Migration Plan

1. Install and sync dependencies: `uv sync`.
2. Run: `uv run python run.py` (launches Uvicorn on `http://127.0.0.1:8000` and optionally opens the default browser).
3. Requires no prior migrations or external database configuration to work.
