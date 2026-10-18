# Proposal

## Why

Dropping a table or view is already supported by the backend and surfaced in the
Structure (DDL) tab, but only for the currently selected table: the user must
first select the table in the left list, then switch tabs, then act. The drop
handler also reads the table name from the active-table state rather than from
the element the user acted on, so any second entry point would drop the wrong
table. Users want to delete a table directly from the left table list, with a
clear warning before the destructive action.

## What Changes

- Add a per-row "actions" (vertical ellipsis) menu to each item of the left
  table list, offering a drop action labeled for the item's kind (`Drop table` /
  `Drop view`).
- Route both the new list action and the existing Structure-tab button through a
  single confirmation flow that takes the target name and kind as explicit
  inputs, so the dropped entity is always the one the user acted on.
- Show a warning confirmation before the drop, with wording that distinguishes
  destructive table drops from view drops (which keep underlying data).
- After a drop, refresh the table list (preserving the active filter) and clear
  the workspace only when the dropped entity was the selected table.
- Keep the existing modal and endpoint unchanged; no backend work is required.

## Capabilities

### New Capabilities

<!-- None: this extends an existing capability. -->

### Modified Capabilities

- `schema-manager`: extends the existing drop behavior so tables and views can be
  dropped from the left table list with a warning confirmation, and so the drop
  target is always the acted-on element.

## Impact

- **Code**: `frontend/js/app.js` (table list rendering `renderTablesList`, the
  shared drop/confirmation flow, workspace reset), `frontend/css/custom.css`
  (styling/positioning of the row menu so it is not clipped by the scrolling
  list).
- **APIs**: none. `DELETE /api/tables/{name}/drop` already handles both tables
  and views and rejects missing entities.
- **Dependencies / environment**: none. No new packages, no frontend build step.
