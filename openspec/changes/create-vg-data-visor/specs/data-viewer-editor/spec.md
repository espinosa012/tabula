# Spec Delta

## Purpose

Enables tabular inspection of data from SQLite tables and views with pagination, filters, and sorting, as well as record manipulation through insert, edit, and delete operations.

## ADDED Requirements

### Requirement: Listing and selecting collections
The system SHALL list all tables and views available in the connected database so the user can select which one to inspect.

#### Scenario: Retrieve the list of tables and views
- **WHEN** the user connects to a database with existing tables and views
- **THEN** the system returns the full list, classifying each entity as a table or a view, along with the approximate or exact row count

#### Scenario: Selecting a table for visualization
- **WHEN** the user clicks a table in the side list
- **THEN** the interface loads the schema and the first paginated block of records for that table

### Requirement: Paginated visualization and sorting of records
The system SHALL allow viewing the records of the selected table with support for configurable pagination and ascending or descending sorting by any column.

#### Scenario: Loading a page of data
- **WHEN** the user navigates to a specific page or changes the page size (e.g. 25, 50, 100 records)
- **THEN** the system returns exclusively the requested subset of records and the total record count for computing pagination

#### Scenario: Sorting by column
- **WHEN** the user clicks a column header
- **THEN** the system requests and presents the records sorted by the selected column and direction

### Requirement: Searching and filtering records
The system SHALL allow filtering the displayed records through search terms applied to the table columns.

#### Scenario: Filtering by search term
- **WHEN** the user enters a search term in the filter bar
- **THEN** the system queries and displays only the rows that match that term in one or more columns

#### Scenario: Clearing the filter
- **WHEN** the user clears the search field
- **THEN** the system resets the query to display all records in the table

#### Scenario: Clearing the filter with the inline button
- **WHEN** the search field contains text and the user clicks the inline button (which shows an "x" instead of the magnifier while there is text)
- **THEN** the system empties the search field and resets the query to display all records

### Requirement: Editing existing records
The system SHALL allow modifying the column values of an existing row by identifying it through its primary key or `rowid`.

#### Scenario: Successful update of a cell or row
- **WHEN** the user modifies one or more values of a record and confirms the changes
- **THEN** the system executes the update in the database, confirms persistence, and refreshes the view

#### Scenario: Error due to incompatible value or constraint violation
- **WHEN** the user enters a value that violates a constraint (such as NOT NULL, CHECK, or an invalid type)
- **THEN** the system rejects the update, keeps the original data, and shows a descriptive error message

### Requirement: Inserting new records
The system SHALL provide a form or interactive row to insert new records into the active table.

#### Scenario: Inserting a row with valid values
- **WHEN** the user provides the required values and requests to save the new record
- **THEN** the system inserts the new row into SQLite, generates auto-numbered values where applicable, and refreshes the table

#### Scenario: Failed insertion due to an unsatisfied constraint
- **WHEN** an attempt is made to save a new record while omitting required fields that have no default value
- **THEN** the system cancels the insertion and flags the fields with errors

### Requirement: Deleting records
The system SHALL allow deleting individual records after explicit user confirmation.

#### Scenario: Confirmed deletion of a row
- **WHEN** the user requests to delete a record and confirms the action in the safety dialog
- **THEN** the system deletes the corresponding row from the database and removes it from the current view

#### Scenario: Canceling a deletion
- **WHEN** the user cancels the delete confirmation dialog
- **THEN** the system performs no action and the record remains intact
