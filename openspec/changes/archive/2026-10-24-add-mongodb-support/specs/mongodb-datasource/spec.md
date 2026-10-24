# mongodb-datasource Specification

## Purpose

Enables connecting to local and remote MongoDB databases and inspecting, querying, and editing collections with the same workflow as the SQLite and PostgreSQL data sources.

## Requirements

### Requirement: Connect to MongoDB using Individual Parameters
The system SHALL establish a connection using host, port, database, optional credentials, auth source, and TLS setting.

#### Scenario: Successful local connection
- **WHEN** user submits host "localhost", port 27017, and database "test" without credentials
- **THEN** system pings the server, selects the database, registers the data source, and returns connection metadata with `db_type` "mongo"

#### Scenario: Connection failure with invalid credentials
- **WHEN** user submits unreachable parameters or invalid credentials
- **THEN** system returns an error detailing the failure and does not replace the active data source

### Requirement: Connect to MongoDB using Connection URI
The system SHALL establish a connection using `mongodb://` or `mongodb+srv://` URIs, including TLS and replica-set options handled by the driver.

#### Scenario: Successful connection with Atlas URI
- **WHEN** user submits `mongodb+srv://user:password@cluster.example.net/dbname`
- **THEN** system connects, uses the database named in the URI, and returns connection metadata

#### Scenario: Malformed URI or missing database
- **WHEN** user submits an invalid URI
- **THEN** system returns an error and keeps any existing session intact

### Requirement: Test Connection Without Session Activation
The system SHALL provide an endpoint to test MongoDB connectivity without replacing the active data source.

#### Scenario: Test valid connection
- **WHEN** user requests a connection test with reachable credentials
- **THEN** system returns success with the server version and selected database

#### Scenario: Test invalid connection
- **WHEN** user requests a connection test that fails
- **THEN** system returns success=false with the diagnostic message and the active source is unchanged

### Requirement: Collection Listing and Schema Inference
The system SHALL list collections and views in the selected database and infer a schema by sampling documents.

#### Scenario: Listing collections
- **WHEN** client requests the collection list
- **THEN** system returns collection and view names with row counts

#### Scenario: Inferring fields
- **WHEN** client requests the schema of a collection
- **THEN** system returns fields observed in the sample, their BSON types, and `_id` as the primary key

#### Scenario: Empty collection
- **WHEN** client requests the schema of an empty collection
- **THEN** system returns a single `_id` primary-key column

### Requirement: Paginated Documents and Case-Insensitive Search
The system SHALL return paginated, sorted documents and search text fields case-insensitively.

#### Scenario: Searching documents
- **WHEN** client requests documents with search "alice"
- **THEN** system filters documents whose string fields match the term case-insensitively, and also matches `_id` when the term is a valid ObjectId

#### Scenario: Sorting documents
- **WHEN** client sorts by an inferred field
- **THEN** system applies that sort order before pagination

### Requirement: Document CRUD using _id
The system SHALL insert documents, update them by `_id`, and delete them by `_id`.

#### Scenario: Inserting a document
- **WHEN** client submits values without `_id`
- **THEN** system inserts the document, lets MongoDB generate `_id`, and returns the stored document

#### Scenario: Updating and deleting by ObjectId
- **WHEN** client submits `_id` as a 24-hex string
- **THEN** system converts it to an ObjectId and updates or deletes only the matching document

### Requirement: JSON Query Console
The system SHALL execute JSON commands through the existing query endpoint.

#### Scenario: Find command
- **WHEN** client submits `{"collection":"users","operation":"find","filter":{"active":true},"limit":10}`
- **THEN** system returns the matching documents as rows with execution time

#### Scenario: Write command
- **WHEN** client submits an `insertOne`, `updateOne`, or `deleteOne` command
- **THEN** system performs the write and returns a message describing the affected count or inserted id

#### Scenario: Unsupported command
- **WHEN** client submits a malformed command or unknown operation
- **THEN** system returns an HTTP 400 error with a descriptive message

### Requirement: Custom Views as Find or Aggregate Commands
The system SHALL save `find` and `aggregate` commands as custom views and paginate their results.

#### Scenario: Saved find view
- **WHEN** client creates a custom view whose query is `{"collection":"users","filter":{"active":true}}`
- **THEN** system validates the command and returns paginated results with search and sorting

#### Scenario: Write command rejected as view
- **WHEN** client attempts to save a write operation as a custom view
- **THEN** system rejects the view with an HTTP 400 error

### Requirement: BSON Type Serialization
The system SHALL serialize BSON values into JSON-compatible values.

#### Scenario: Documents with rich BSON types
- **WHEN** documents contain ObjectId, dates, decimals, binary, nested objects, or arrays
- **THEN** system returns ObjectIds as strings, dates as ISO-8601 strings, decimals as numbers, and nested structures recursively
