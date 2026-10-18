# Spec Delta

## ADDED Requirements

### Requirement: Dropping collections from the table list

The system SHALL allow dropping a table or view directly from the left table list,
acting on the specific list item chosen regardless of which table is currently
selected.

#### Scenario: Dropping the selected table from the list

- **WHEN** the user opens the actions menu of the currently selected table, chooses
  the drop action, and confirms the warning
- **THEN** the system executes `DROP TABLE`, removes the table, refreshes the table
  list, and clears the workspace because the active table was dropped

#### Scenario: Dropping a table that is not selected

- **WHEN** the user drops a table from the list while a different table is selected
- **THEN** the system drops the chosen table, refreshes the list, and keeps the
  currently selected table and its workspace unchanged

#### Scenario: Dropping a view from the list

- **WHEN** the user drops a view from the list and confirms the warning
- **THEN** the system executes `DROP VIEW`, removes the view from the list, and
  leaves the underlying tables and their data intact

#### Scenario: Cancelling the drop

- **WHEN** the user dismisses the confirmation without confirming
- **THEN** the system performs no drop and leaves the schema and list unchanged

#### Scenario: Drop rejected by the database

- **WHEN** the database refuses the drop (for example, a foreign-key dependency)
- **THEN** the system reports the SQLite error to the user and the session continues

### Requirement: Drop warning distinguishes tables from views

The system SHALL require an explicit confirmation before dropping, presenting a
warning whose text reflects the kind of entity being dropped.

#### Scenario: Warning for a table drop

- **WHEN** the user initiates dropping a table
- **THEN** the confirmation warns that all of the table's data will be destroyed

#### Scenario: Warning for a view drop

- **WHEN** the user initiates dropping a view
- **THEN** the confirmation states that the view is removed while its underlying
  data is preserved
