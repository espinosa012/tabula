# Tasks

## 1. Unify the drop flow (bug fix)

- [x] 1.1 Extract a single `confirmDropCollection(name, type)` helper in `frontend/js/app.js` that sets the confirmation title/message from `type` and binds `DELETE /api/tables/{name}/drop` using the passed `name`, not `state.activeTable`; verify by reading the request path to confirm no drop request reads the table name from the active-table state
- [x] 1.2 Route the existing Structure-tab Drop button through the helper, passing `state.activeTable` and the loaded schema's type; verify dropping from the Structure tab still works and clears the workspace
- [x] 1.3 Clear the workspace only when the dropped name equals the selected table, and refresh the list while preserving the `#filter-tables` value; verify by dropping a non-selected table and confirming the selection and filter are unchanged

## 2. Row actions menu in the table list

- [x] 2.1 Add a vertical-ellipsis actions menu to each item rendered by `renderTablesList()`, with the drop entry labeled by the item's kind (`Drop table` / `Drop view`); verify the menu appears on the row and shows the correct label for a table and for a view
- [x] 2.2 Stop event propagation on the menu toggle and the drop entry so opening the menu or choosing the action does not also select the table; verify selection does not change when the menu is opened
- [x] 2.3 Prevent the menu from being clipped by the scrolling list (`.table-list-scroll` has `overflow-y: auto`), using an upward-opening direction or equivalent CSS; verify the menu on the last row is fully visible
- [x] 2.4 Initialize the dropdown after every `renderTablesList()` call, including re-renders triggered by the filter input; verify the menus still work after typing in the filter

## 3. Integration verification

- [x] 3.1 Verify the confirmation wording differs for a table (data destroyed) and a view (underlying data preserved)
- [x] 3.2 Verify cancelling the confirmation performs no drop, and that a database-rejected drop (e.g. a foreign-key dependency) shows the SQLite error while the session keeps working
- [x] 3.3 Run the existing backend suite (`.venv/bin/python -m pytest`) to confirm the endpoint behavior used here still passes with no backend changes

## Workflow follow-up

- Archive the change after the work is implemented and verified.
