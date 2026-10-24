# Spec Delta

## Purpose

Provides the ability to manage connections to local SQLite databases, browse the machine's filesystem, create new databases from scratch, and keep a record of recent accesses.

## ADDED Requirements

### Requirement: Connection via local file path
The system SHALL allow the user to specify the absolute or relative path of a SQLite file on the local disk and establish an active connection.

#### Scenario: Successful connection with a valid path
- **WHEN** the user enters a valid path to a `.sqlite` or `.db` file and requests to connect
- **THEN** the system validates that the file is a valid SQLite database, establishes the active connection, and returns the connection status with basic metadata

#### Scenario: File not found
- **WHEN** the user requests to connect to a nonexistent path
- **THEN** the system SHALL reject the connection and report with a descriptive error message indicating that the file does not exist

#### Scenario: File is not a valid SQLite database
- **WHEN** the user attempts to connect to a file that does not have a valid SQLite format
- **THEN** the system SHALL reject the connection with an error code and an explanatory message

### Requirement: Local filesystem browser
The system SHALL offer a service to browse folders and select database files on the local server's filesystem.

#### Scenario: Listing directory contents
- **WHEN** the client requests the contents of a local directory
- **THEN** the system returns the list of subfolders and files with compatible extensions (`.db`, `.sqlite`, `.sqlite3`), indicating read and write permissions

#### Scenario: Selecting a file from the browser
- **WHEN** the user selects a compatible file in the visual browser
- **THEN** the interface automatically sets the selected absolute path in the connection field

### Requirement: Creating a new SQLite database
The system SHALL allow creating a new empty SQLite database file in the directory specified by the user.

#### Scenario: Successful creation of a new database
- **WHEN** the user enters a valid folder path and a nonexistent file name and requests to create the database
- **THEN** the system creates the empty physical SQLite file, establishes the active connection, and notifies the user of success

#### Scenario: Preventing overwrite of an existing file
- **WHEN** the user requests to create a new database with a file name that already exists in the given path
- **THEN** the system SHALL reject the creation to avoid data loss and warn that the file already exists

### Requirement: Recent database history
The system SHALL store the last successfully connected database paths to facilitate quick reconnections.

#### Scenario: Recording a connected database
- **WHEN** a connection to a database is made successfully
- **THEN** the system adds or updates that path in the recent accesses list

#### Scenario: Connecting from history
- **WHEN** the user selects an item from the recent history
- **THEN** the system fills in the corresponding path and proceeds to start the connection
