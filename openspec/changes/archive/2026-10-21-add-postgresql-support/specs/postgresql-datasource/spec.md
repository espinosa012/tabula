# Spec Delta

## Purpose

Enables connecting to local and remote PostgreSQL databases on the public schema with full feature parity to the SQLite data viewer and editor.

## ADDED Requirements

### Requirement: Connect to PostgreSQL using Individual Parameters
The system SHALL establish a connection to a PostgreSQL database using host, port, database name, username, password, and SSL mode.

#### Scenario: Successful connection with valid parameters
- **WHEN** user submits host "localhost", port 5432, database "postgres", user "postgres", password, and sslmode "prefer"
- **THEN** system connects successfully, sets search_path to public, registers the data source, and returns connection metadata

#### Scenario: Connection failure with invalid credentials
- **WHEN** user submits invalid host, credentials, or unreachable database
- **THEN** system returns an HTTP 400 or 500 error detailing the connection failure without entering the workspace

### Requirement: Connect to PostgreSQL using Connection URL
The system SHALL establish a connection to a PostgreSQL database using a standard PostgreSQL URI string.

#### Scenario: Successful connection with valid URI
- **WHEN** user submits a connection URI "postgresql://user:password@host:5432/dbname?sslmode=require"
- **THEN** system parses the URI, establishes the connection, and returns connection status

#### Scenario: Malformed connection URI
- **WHEN** user submits an invalid or malformed URI scheme
- **THEN** system returns an HTTP 400 error indicating the URI format is invalid

### Requirement: Test Connection Without Session Activation
The system SHALL provide an endpoint to test PostgreSQL credentials and network reachability without replacing the active data source.

#### Scenario: Test valid connection
- **WHEN** user requests a connection test with reachable credentials
- **THEN** system returns success with database version and response latency

#### Scenario: Test invalid connection
- **WHEN** user requests a connection test with incorrect credentials or network timeout
- **THEN** system returns failure with the diagnostic error message while keeping existing active session intact

### Requirement: Public Schema Introspection
The system SHALL restrict collection listing and schema inspection to tables and views within the public schema.

#### Scenario: Listing tables and views
- **WHEN** client requests table list for a connected PostgreSQL database
- **THEN** system returns only tables and views belonging to schema "public", including row counts

#### Scenario: Table column and constraint inspection
- **WHEN** client requests schema for a table in public schema
- **THEN** system returns column definitions, primary keys, not-null constraints, and default values

### Requirement: Paginated Records and Case-Insensitive Search
The system SHALL return paginated records with sorting and case-insensitive search across column values.

#### Scenario: Record search
- **WHEN** client requests records with search query "test"
- **THEN** system filters rows using case-insensitive comparison across text representations of columns

### Requirement: Row Identification for Tables Without Primary Keys
The system SHALL expose PostgreSQL ctid as a synthetic _rowid_ column for tables without primary keys to allow update and delete operations.

#### Scenario: Update row in table without primary key
- **WHEN** client requests an update to a record identified by _rowid_ in a table with no primary key
- **THEN** system executes the update targeted by the ctid value

#### Scenario: Delete row in table without primary key
- **WHEN** client requests a deletion of a record identified by _rowid_
- **THEN** system deletes the target row matching the ctid value

### Requirement: PostgreSQL Type Serialization
The system SHALL serialize PostgreSQL rich types into JSON-compatible formats without execution errors.

#### Scenario: Query returning UUID and Timestamp columns
- **WHEN** client queries a table with UUID, TIMESTAMPTZ, and NUMERIC columns
- **THEN** system returns records with UUIDs formatted as strings, timestamps as ISO-8601 strings, and numbers as floats or numbers
