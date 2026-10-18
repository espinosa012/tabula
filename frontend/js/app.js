/**
 * vg-data-visor - SPA Frontend Logic
 */

$(document).ready(function () {
    // ================= GLOBAL STATE =================
    const state = {
        connected: false,
        dbPath: "",
        tables: [],
        activeTable: null,
        activeSchema: null,
        activeTab: "tab-data",
        pagination: {
            page: 1,
            pageSize: 50,
            totalPages: 1,
            totalRecords: 0,
            sortBy: null,
            sortDir: "asc",
            search: "",
        },
        fsBrowser: {
            mode: "file", // "file" or "dir"
            targetInputId: null,
            currentPath: null,
        },
        editingRecordPk: null,
    };

    // ================= UI INITIALIZATION =================
    $("#connection-tabs .item").tab();
    $("#workspace-tabs .item").tab({
        onVisible: function (tabPath) {
            state.activeTab = tabPath;
            if (tabPath === "tab-sql") {
                suggestDefaultQuery();
            }
        },
    });
    $(".ui.dropdown").dropdown();

    // Check whether there is already an active connection on the server
    checkConnectionStatus();
    loadRecentDatabases();

    // ================= API CLIENT =================
    async function apiRequest(endpoint, options = {}) {
        const config = {
            headers: {
                "Content-Type": "application/json",
            },
            ...options,
        };
        try {
            const resp = await fetch(endpoint, config);
            const data = await resp.json().catch(() => null);
            if (!resp.ok) {
                const errorMsg = data && data.detail ? data.detail : `HTTP error ${resp.status}`;
                throw new Error(errorMsg);
            }
            return data;
        } catch (err) {
            console.error(`API error at ${endpoint}:`, err);
            throw err;
        }
    }

    function showToast(title, message, type = "info") {
        if ($.toast) {
            $.toast({
                title: title,
                message: message,
                class: type === "error" ? "error" : type === "success" ? "success" : "info",
                showProgress: "bottom",
                position: "bottom right",
            });
        } else {
            if (type === "error") {
                alert(`${title}: ${message}`);
            }
        }
    }

    // ================= CONNECTION MANAGEMENT =================
    async function checkConnectionStatus() {
        try {
            const status = await apiRequest("/api/connection/status");
            if (status.connected && status.path) {
                setConnectedState(status);
            } else {
                setDisconnectedState();
            }
        } catch (e) {
            setDisconnectedState();
        }
    }

    function setConnectedState(info) {
        state.connected = true;
        state.dbPath = info.path;

        $("#nav-db-status").html(
            `<span class="ui green empty circular label"></span> &nbsp; <span title="${info.path}"><strong>${getFileName(info.path)}</strong> (${formatBytes(info.size_bytes)})</span>`
        );
        $("#btn-refresh-all, #btn-disconnect").show();
        $("#view-connection").hide();
        $("#view-workspace").show();

        loadTablesList();
        loadRecentDatabases();
    }

    function setDisconnectedState() {
        state.connected = false;
        state.dbPath = "";
        state.tables = [];
        state.activeTable = null;
        state.activeSchema = null;

        $("#nav-db-status").html('<span class="ui grey empty circular label"></span> &nbsp; Disconnected');
        $("#btn-refresh-all, #btn-disconnect").hide();
        $("#view-workspace").hide();
        $("#view-connection").show();
        $("#active-table-panel").hide();
        $("#empty-table-state").show();
    }

    async function loadRecentDatabases() {
        try {
            const recents = await apiRequest("/api/connection/recent");
            const $list = $("#list-recent-dbs");
            $list.empty();
            if (recents && recents.length > 0) {
                $("#section-recent-dbs").show();
                recents.forEach((path) => {
                    const $item = $(`
                        <div class="item fs-item">
                            <i class="database icon"></i>
                            <div class="content" style="flex: 1;">
                                <div class="header">${getFileName(path)}</div>
                                <div class="description" style="font-size: 0.85em; color: #718096;">${path}</div>
                            </div>
                            <button class="ui mini basic button btn-connect-recent">Connect</button>
                        </div>
                    `);
                    $item.find(".btn-connect-recent").on("click", function (e) {
                        e.stopPropagation();
                        connectToDatabase(path);
                    });
                    $item.on("click", function () {
                        $("#input-open-path").val(path);
                    });
                    $list.append($item);
                });
            } else {
                $("#section-recent-dbs").hide();
            }
        } catch (e) {
            console.warn("Could not load recent databases:", e);
        }
    }

    async function connectToDatabase(path) {
        $("#btn-submit-open").addClass("loading disabled");
        try {
            const info = await apiRequest("/api/connection/open", {
                method: "POST",
                body: JSON.stringify({ path: path }),
            });
            showToast("Connected", `Database opened: ${getFileName(path)}`, "success");
            setConnectedState(info);
        } catch (err) {
            showToast("Connection Error", err.message, "error");
        } finally {
            $("#btn-submit-open").removeClass("loading disabled");
        }
    }

    async function createDatabase(path) {
        $("#btn-submit-create").addClass("loading disabled");
        try {
            const info = await apiRequest("/api/connection/create", {
                method: "POST",
                body: JSON.stringify({ path: path }),
            });
            showToast("Created Successfully", `New database created at: ${path}`, "success");
            setConnectedState(info);
        } catch (err) {
            showToast("Creation Error", err.message, "error");
        } finally {
            $("#btn-submit-create").removeClass("loading disabled");
        }
    }

    $("#form-open-db").on("submit", function (e) {
        e.preventDefault();
        const p = $("#input-open-path").val().trim();
        if (p) connectToDatabase(p);
    });

    $("#form-create-db").on("submit", function (e) {
        e.preventDefault();
        const dir = $("#input-create-dir").val().trim();
        let fname = $("#input-create-filename").val().trim();
        if (!fname.includes(".")) {
            fname += ".sqlite";
        }
        const fullPath = dir.endsWith("/") ? dir + fname : dir + "/" + fname;
        createDatabase(fullPath);
    });

    $("#btn-disconnect").on("click", async function () {
        try {
            await apiRequest("/api/connection/close", { method: "POST" });
            showToast("Disconnected", "Session closed successfully", "info");
            setDisconnectedState();
            loadRecentDatabases();
        } catch (e) {
            console.error(e);
        }
    });

    $("#btn-refresh-all").on("click", function () {
        loadTablesList();
        if (state.activeTable) {
            loadActiveTable();
        }
    });

    // ================= FILESYSTEM BROWSER =================
    function openFsBrowser(mode, targetInputId, initialPath) {
        state.fsBrowser.mode = mode;
        state.fsBrowser.targetInputId = targetInputId;
        $("#btn-fs-select-current").toggle(mode === "dir");
        loadFsDirectory(initialPath || "");
        $("#modal-fs-browser").modal("show");
    }

    async function loadFsDirectory(path) {
        const $list = $("#fs-item-list");
        $list.html('<div class="ui active centered inline loader"></div>');

        try {
            const url = path ? `/api/fs/browse?path=${encodeURIComponent(path)}` : "/api/fs/browse";
            const data = await apiRequest(url);
            state.fsBrowser.currentPath = data.current_path;

            // Render breadcrumbs
            renderFsBreadcrumbs(data.current_path, data.parent_path);

            $list.empty();

            // Option to go up to the parent directory
            if (data.parent_path) {
                const $parent = $(`
                    <div class="item fs-item">
                        <i class="folder open outline icon"></i>
                        <div class="content"><strong>.. (Go up one level)</strong></div>
                    </div>
                `);
                $parent.on("click", () => loadFsDirectory(data.parent_path));
                $list.append($parent);
            }

            if (!data.items || data.items.length === 0) {
                $list.append('<div class="item" style="color: #a0aec0;">Empty directory</div>');
                return;
            }

            data.items.forEach((item) => {
                const iconClass = item.is_dir ? "folder icon yellow" : item.is_db ? "database icon green" : "file outline icon grey";
                const sizeLabel = item.size_bytes ? `(${formatBytes(item.size_bytes)})` : "";
                const $it = $(`
                    <div class="item fs-item">
                        <i class="${iconClass}"></i>
                        <div class="content" style="flex: 1;">
                            <span class="header">${item.name}</span>
                            <span style="font-size: 0.8em; color: #718096; margin-left: 0.5rem;">${sizeLabel}</span>
                        </div>
                    </div>
                `);

                if (item.is_dir) {
                    $it.on("click", () => loadFsDirectory(item.path));
                } else if (state.fsBrowser.mode === "file") {
                    $it.on("click", () => {
                        $(`#${state.fsBrowser.targetInputId}`).val(item.path);
                        $("#modal-fs-browser").modal("hide");
                    });
                }
                $list.append($it);
            });
        } catch (err) {
            $list.html(`<div class="ui negative message">${err.message}</div>`);
        }
    }

    function renderFsBreadcrumbs(currentPath, parentPath) {
        const $bc = $("#fs-breadcrumb");
        $bc.empty();
        const parts = currentPath.split("/").filter(Boolean);
        let accumulated = "";

        $bc.append('<i class="home icon"></i> ');
        const $root = $('<a class="section">/</a>');
        $root.on("click", () => loadFsDirectory("/"));
        $bc.append($root);

        parts.forEach((p, idx) => {
            accumulated += "/" + p;
            const target = accumulated;
            $bc.append(' <i class="right angle icon divider"></i> ');
            if (idx === parts.length - 1) {
                $bc.append(`<div class="active section">${p}</div>`);
            } else {
                const $sec = $(`<a class="section">${p}</a>`);
                $sec.on("click", () => loadFsDirectory(target));
                $bc.append($sec);
            }
        });
    }

    $("#btn-open-browse").on("click", function () {
        openFsBrowser("file", "input-open-path", $("#input-open-path").val());
    });

    $("#btn-create-browse-dir").on("click", function () {
        openFsBrowser("dir", "input-create-dir", $("#input-create-dir").val());
    });

    $("#btn-fs-select-current").on("click", function () {
        if (state.fsBrowser.currentPath && state.fsBrowser.targetInputId) {
            $(`#${state.fsBrowser.targetInputId}`).val(state.fsBrowser.currentPath);
            $("#modal-fs-browser").modal("hide");
        }
    });

    // ================= TABLES SIDEBAR =================
    // The empty-state button reads "Create First Table" only while the database
    // has no tables; once it has any, creating another one is "Add New Table".
    function updateEmptyStateCreateButton() {
        const hasTables = state.tables.length > 0;
        $("#btn-empty-create-table-label").text(hasTables ? "Add New Table" : "Create First Table");
    }

    async function loadTablesList() {
        try {
            const tables = await apiRequest("/api/tables");
            state.tables = tables;
            $("#count-tables").text(tables.length);
            updateEmptyStateCreateButton();
            renderTablesList();
        } catch (err) {
            showToast("Error", err.message, "error");
        }
    }

    function renderTablesList() {
        const filter = $("#filter-tables").val().toLowerCase().trim();
        const $list = $("#tables-list");
        $list.empty();

        const filtered = state.tables.filter((t) => t.name.toLowerCase().includes(filter));

        if (filtered.length === 0) {
            $list.append('<div class="item" style="color: #a0aec0;">No matching tables</div>');
            return;
        }

        filtered.forEach((t) => {
            const isView = t.type === "view";
            const icon = isView ? "eye icon blue" : "table icon";
            const countLabel = t.row_count !== null ? `<span class="ui mini label">${t.row_count}</span>` : "";
            const activeClass = state.activeTable === t.name ? "active teal" : "";
            const dropLabel = isView ? "Drop view" : "Drop table";
            const renameItem = isView
                ? ""
                : `<div class="item row-action-rename">
                                <i class="edit icon"></i> Rename table
                            </div>`;

            const $item = $(`
                <a class="item table-list-item ${activeClass}" data-table="${t.name}">
                    <i class="${icon}"></i>
                    <span class="table-list-name">${t.name}</span>
                    ${countLabel}
                    <div class="ui dropdown row-actions">
                        <i class="ellipsis vertical icon"></i>
                        <div class="menu">
                            ${renameItem}
                            <div class="item row-action-drop">
                                <i class="trash icon"></i> ${dropLabel}
                            </div>
                        </div>
                    </div>
                </a>
            `);

            // Keep the actions menu from also selecting the table
            $item.find(".row-actions").on("click", function (e) {
                e.stopPropagation();
            });
            $item.find(".row-action-drop").on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                confirmDropCollection(t.name, t.type);
            });
            $item.find(".row-action-rename").on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                openRenameTableModal(t.name);
            });

            $item.on("click", function (e) {
                if ($(e.target).closest(".row-actions").length) return;
                selectActiveTable(t.name);
            });

            $list.append($item);
        });

        // The list is re-rendered on every change, so (re)initialize the row menus.
        // `context` points at the scrolling list so the menu opens upward when it
        // would otherwise be clipped by the container's overflow.
        $list.find(".row-actions").dropdown({
            direction: "auto",
            context: "#tables-list",
        });
    }

    // Sidebar "Filter tables" input: its icon doubles as a clear button, showing
    // a magnifier when empty and an "x" (which clears the filter) once there is text.
    function updateTablesFilterButton() {
        const hasText = $("#filter-tables").val().length > 0;
        $("#btn-filter-tables-toggle")
            .toggleClass("search", !hasText)
            .toggleClass("times", hasText)
            .attr("title", hasText ? "Clear filter" : "Filter tables");
    }

    $("#filter-tables").on("input", function () {
        renderTablesList();
        updateTablesFilterButton();
    });

    $("#btn-filter-tables-toggle").on("click", function () {
        if ($("#filter-tables").val().length > 0) {
            $("#filter-tables").val("");
            renderTablesList();
            updateTablesFilterButton();
        } else {
            $("#filter-tables").focus();
        }
    });

    function selectActiveTable(tableName) {
        state.activeTable = tableName;
        state.pagination.page = 1;
        state.pagination.search = "";
        state.pagination.sortBy = null;
        state.pagination.sortDir = "asc";
        $("#input-search-records").val("");
        updateSearchButton();

        renderTablesList();
        loadActiveTable();
    }

    async function loadActiveTable() {
        if (!state.activeTable) return;

        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $("#active-table-name").text(state.activeTable);

        await loadTableSchema();
        await loadTableRecords();
    }

    // ================= TAB 1: DATA VIEWER AND EDITOR =================
    async function loadTableSchema() {
        try {
            const schema = await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/schema`);
            state.activeSchema = schema;
            renderSchemaTable(schema);
        } catch (err) {
            showToast("Error fetching schema", err.message, "error");
        }
    }

    async function loadTableRecords() {
        if (!state.activeTable) return;
        const $head = $("#grid-head");
        const $body = $("#grid-body");
        $body.html('<tr><td colspan="100" class="center aligned"><div class="ui active inline loader"></div> Loading data...</td></tr>');

        const params = new URLSearchParams({
            page: state.pagination.page,
            page_size: state.pagination.pageSize,
            sort_dir: state.pagination.sortDir,
        });
        if (state.pagination.sortBy) params.append("sort_by", state.pagination.sortBy);
        if (state.pagination.search) params.append("search", state.pagination.search);

        try {
            const data = await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/records?${params.toString()}`);
            state.pagination.totalRecords = data.total;
            state.pagination.totalPages = data.total_pages;

            $("#table-total-records").text(data.total);
            $("#lbl-page-current").text(data.page);
            $("#lbl-page-num").text(data.page);
            $("#lbl-page-total").text(data.total_pages);

            renderRecordsTable(data);
        } catch (err) {
            $body.html(`<tr><td colspan="100" class="negative center aligned">${err.message}</td></tr>`);
        }
    }

    function renderRecordsTable(data) {
        const $head = $("#grid-head");
        const $body = $("#grid-body");
        $head.empty();
        $body.empty();

        if (!data.columns || data.columns.length === 0) {
            $head.append("<tr><th>No columns</th></tr>");
            $body.append('<tr><td class="center aligned">This table has no columns defined</td></tr>');
            return;
        }

        // Header
        const $trHead = $("<tr></tr>");
        $trHead.append('<th style="width: 80px; text-align: center;">Actions</th>');

        data.columns.forEach((col) => {
            const isPk = data.pk_columns && data.pk_columns.includes(col);
            const isSorted = state.pagination.sortBy === col;
            let sortIcon = "";
            if (isSorted) {
                sortIcon = state.pagination.sortDir === "desc" ? '<i class="sort down icon"></i>' : '<i class="sort up icon"></i>';
            }

            const $th = $(`
                <th>
                    ${col} ${isPk ? '<span class="badge-pk">PK</span>' : ""}
                    ${sortIcon}
                </th>
            `);

            $th.on("click", () => {
                if (state.pagination.sortBy === col) {
                    state.pagination.sortDir = state.pagination.sortDir === "asc" ? "desc" : "asc";
                } else {
                    state.pagination.sortBy = col;
                    state.pagination.sortDir = "asc";
                }
                loadTableRecords();
            });

            $trHead.append($th);
        });
        $head.append($trHead);

        // Rows
        if (!data.records || data.records.length === 0) {
            $body.append(`<tr><td colspan="${data.columns.length + 1}" class="center aligned" style="color: #a0aec0; padding: 2rem;">No records available</td></tr>`);
            return;
        }

        data.records.forEach((row) => {
            const $tr = $("<tr></tr>");

            // Action buttons
            const $tdActions = $('<td style="text-align: center;"></td>');
            const $btnEdit = $('<button class="ui mini icon button basic teal" title="Edit row"><i class="edit icon"></i></button>');
            const $btnDel = $('<button class="ui mini icon button basic red" title="Delete row"><i class="trash icon"></i></button>');

            $btnEdit.on("click", () => openEditRecordModal(row, data.pk_columns));
            $btnDel.on("click", () => confirmDeleteRecord(row, data.pk_columns));

            $tdActions.append($btnEdit).append(" ").append($btnDel);
            $tr.append($tdActions);

            // Data cells
            data.columns.forEach((col) => {
                const val = row[col];
                let displayVal = val;
                let cellClass = "";
                if (val === null || val === undefined) {
                    displayVal = "NULL";
                    cellClass = "cell-null";
                } else if (typeof val === "object") {
                    displayVal = JSON.stringify(val);
                }

                const $td = $(`<td class="${cellClass}" title="${escapeHtml(String(displayVal))}">${escapeHtml(String(displayVal))}</td>`);
                $tr.append($td);
            });

            $body.append($tr);
        });
    }

    // Pagination and search
    $("#select-page-size").on("change", function () {
        state.pagination.pageSize = parseInt($(this).val(), 10);
        state.pagination.page = 1;
        loadTableRecords();
    });

    $("#btn-page-first").on("click", function () {
        if (state.pagination.page > 1) {
            state.pagination.page = 1;
            loadTableRecords();
        }
    });

    $("#btn-page-prev").on("click", function () {
        if (state.pagination.page > 1) {
            state.pagination.page--;
            loadTableRecords();
        }
    });

    $("#btn-page-next").on("click", function () {
        if (state.pagination.page < state.pagination.totalPages) {
            state.pagination.page++;
            loadTableRecords();
        }
    });

    $("#btn-page-last").on("click", function () {
        if (state.pagination.page < state.pagination.totalPages) {
            state.pagination.page = state.pagination.totalPages;
            loadTableRecords();
        }
    });

    // The search button doubles as a clear button: it shows a magnifier when
    // the field is empty and an "x" (which clears the text) once there is input.
    function updateSearchButton() {
        const hasText = $("#input-search-records").val().length > 0;
        $("#btn-search-records")
            .attr("title", hasText ? "Clear search" : "Search")
            .html(hasText ? '<i class="times icon"></i>' : '<i class="search icon"></i>');
    }

    function runRecordSearch() {
        state.pagination.search = $("#input-search-records").val().trim();
        state.pagination.page = 1;
        updateSearchButton();
        loadTableRecords();
    }

    function clearRecordSearch() {
        $("#input-search-records").val("");
        state.pagination.search = "";
        state.pagination.page = 1;
        updateSearchButton();
        loadTableRecords();
    }

    $("#btn-search-records").on("click", function () {
        if ($("#input-search-records").val().length > 0) {
            clearRecordSearch();
        } else {
            runRecordSearch();
        }
    });

    $("#input-search-records").on("input", updateSearchButton);

    $("#input-search-records").on("keyup", function (e) {
        if (e.key === "Enter") {
            runRecordSearch();
        }
    });

    $("#btn-refresh-records").on("click", loadTableRecords);

    // ================= MODAL: INSERT / EDIT RECORD =================
    $("#btn-add-record").on("click", function () {
        openNewRecordModal();
    });

    function openNewRecordModal() {
        if (!state.activeSchema) return;
        state.editingRecordPk = null;
        $("#modal-record-title").html('<i class="plus icon"></i> Insert New Record');
        renderRecordFields({});
        $("#modal-record-editor").modal("show");
    }

    function openEditRecordModal(row, pkCols) {
        if (!state.activeSchema) return;
        // Extract primary keys
        const pkValues = {};
        if (pkCols && pkCols.length > 0) {
            pkCols.forEach((pk) => {
                pkValues[pk] = row[pk];
            });
        } else if ("_rowid_" in row) {
            pkValues["_rowid_"] = row["_rowid_"];
        }

        state.editingRecordPk = pkValues;
        $("#modal-record-title").html('<i class="edit icon"></i> Edit Record');
        renderRecordFields(row);
        $("#modal-record-editor").modal("show");
    }

    function renderRecordFields(rowValues) {
        const $container = $("#record-fields-container");
        $container.empty();

        state.activeSchema.columns.forEach((col) => {
            const isAutoInc = col.auto_increment;
            const isEditing = state.editingRecordPk !== null;
            const currentVal = col.name in rowValues ? rowValues[col.name] : (col.default_value || "");

            // Disable input if it is an autoincrement key when inserting
            const isDisabled = isAutoInc && !isEditing ? "disabled placeholder='(Auto-numbered)'" : "";

            const $field = $(`
                <div class="field">
                    <label>
                        ${col.name} <span style="font-weight: normal; color: #718096;">(${col.type})</span>
                        ${col.is_pk ? '<span class="badge-pk">PK</span>' : ""}
                        ${col.not_null ? '<span style="color: red;">*</span>' : ""}
                    </label>
                    <input type="text" class="field-record-input" data-col="${col.name}" value="${escapeHtml(String(currentVal ?? ''))}" ${isDisabled}>
                </div>
            `);
            $container.append($field);
        });
    }

    $("#btn-confirm-save-record").on("click", async function () {
        const values = {};
        $(".field-record-input").each(function () {
            const col = $(this).data("col");
            if (!$(this).prop("disabled")) {
                let v = $(this).val();
                values[col] = v === "" ? null : v;
            }
        });

        try {
            if (state.editingRecordPk) {
                // Update
                await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/records`, {
                    method: "PUT",
                    body: JSON.stringify({
                        pk_values: state.editingRecordPk,
                        values: values,
                    }),
                });
                showToast("Updated", "Record updated successfully", "success");
            } else {
                // Insert
                await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/records`, {
                    method: "POST",
                    body: JSON.stringify({ values: values }),
                });
                showToast("Inserted", "Record saved successfully", "success");
            }
            $("#modal-record-editor").modal("hide");
            loadTableRecords();
            loadTablesList();
        } catch (err) {
            showToast("Error saving", err.message, "error");
        }
    });

    // ================= MODAL: DELETE RECORD =================
    function confirmDeleteRecord(row, pkCols) {
        const pkValues = {};
        if (pkCols && pkCols.length > 0) {
            pkCols.forEach((pk) => {
                pkValues[pk] = row[pk];
            });
        } else if ("_rowid_" in row) {
            pkValues["_rowid_"] = row["_rowid_"];
        }

        $("#confirm-delete-title").text("Delete Record");
        $("#confirm-delete-message").text(`Are you sure you want to delete this record from table '${state.activeTable}'?`);

        $("#btn-confirm-delete-execute").off("click").on("click", async function () {
            try {
                await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/records/delete`, {
                    method: "POST",
                    body: JSON.stringify({ pk_values: pkValues }),
                });
                showToast("Deleted", "Record deleted", "success");
                $("#modal-confirm-delete").modal("hide");
                loadTableRecords();
                loadTablesList();
            } catch (err) {
                showToast("Error deleting", err.message, "error");
            }
        });

        $("#modal-confirm-delete").modal("show");
    }

    // ================= TAB 2: STRUCTURE (DDL) =================
    function renderSchemaTable(schema) {
        const $body = $("#schema-body");
        $body.empty();

        schema.columns.forEach((col) => {
            const pkBadge = col.is_pk ? '<span class="ui orange tiny label">Yes</span>' : '<span style="color: #a0aec0;">No</span>';
            const notNullBadge = col.not_null ? '<span class="ui red tiny label">NOT NULL</span>' : '<span style="color: #a0aec0;">Nullable</span>';
            const defaultText = col.default_value !== null ? `<code>${col.default_value}</code>` : '<span style="color: #a0aec0;">-</span>';

            $body.append(`
                <tr>
                    <td><strong>${col.name}</strong></td>
                    <td><code>${col.type}</code></td>
                    <td>${pkBadge}</td>
                    <td>${notNullBadge}</td>
                    <td>${defaultText}</td>
                </tr>
            `);
        });

        $("#schema-sql-view").text(schema.sql || "-- Definition not available");
    }

    // Create Table DDL Modal
    $("#btn-modal-create-table, #btn-empty-create-table").on("click", function () {
        $("#create-tbl-name").val("");
        const $container = $("#create-tbl-columns-container");
        $container.empty();

        // Default row: id INTEGER PRIMARY KEY AUTOINCREMENT
        addColumnRow("id", "INTEGER", true, true, true, "");
        // Second default row: name TEXT NOT NULL
        addColumnRow("name", "TEXT", false, false, true, "");

        $("#modal-create-table").modal("show");
    });

    $("#btn-add-column-row").on("click", function () {
        addColumnRow("", "TEXT", false, false, false, "");
    });

    function addColumnRow(name, type, isPk, autoInc, notNull, dflt) {
        const rowId = "col-row-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
        const $row = $(`
            <div class="fields" id="${rowId}" style="border-bottom: 1px dashed #e2e8f0; padding-bottom: 0.5rem; margin-bottom: 0.5rem;">
                <div class="six wide field">
                    <label>Name</label>
                    <input type="text" class="col-def-name" value="${name}" placeholder="column" required>
                </div>
                <div class="four wide field">
                    <label>Type</label>
                    <select class="ui dropdown col-def-type">
                        <option value="INTEGER" ${type === "INTEGER" ? "selected" : ""}>INTEGER</option>
                        <option value="TEXT" ${type === "TEXT" ? "selected" : ""}>TEXT</option>
                        <option value="REAL" ${type === "REAL" ? "selected" : ""}>REAL</option>
                        <option value="BLOB" ${type === "BLOB" ? "selected" : ""}>BLOB</option>
                        <option value="NUMERIC" ${type === "NUMERIC" ? "selected" : ""}>NUMERIC</option>
                    </select>
                </div>
                <div class="two wide field" style="display: flex; flex-direction: column; justify-content: center;">
                    <div class="ui checkbox">
                        <input type="checkbox" class="col-def-pk" ${isPk ? "checked" : ""}>
                        <label>PK</label>
                    </div>
                    <div class="ui checkbox" style="margin-top: 4px;">
                        <input type="checkbox" class="col-def-auto" ${autoInc ? "checked" : ""}>
                        <label>Auto</label>
                    </div>
                </div>
                <div class="two wide field" style="display: flex; flex-direction: column; justify-content: center;">
                    <div class="ui checkbox">
                        <input type="checkbox" class="col-def-notnull" ${notNull ? "checked" : ""}>
                        <label>Not Null</label>
                    </div>
                </div>
                <div class="two wide field" style="display: flex; align-items: flex-end;">
                    <button type="button" class="ui mini red icon button btn-remove-col-row" title="Remove row">
                        <i class="times icon"></i>
                    </button>
                </div>
            </div>
        `);

        $row.find(".btn-remove-col-row").on("click", function () {
            $row.remove();
        });

        $("#create-tbl-columns-container").append($row);
        $row.find(".ui.dropdown").dropdown();
    }

    $("#btn-confirm-create-table").on("click", async function () {
        const tblName = $("#create-tbl-name").val().trim();
        if (!tblName) {
            showToast("Warning", "The table name is required", "error");
            return;
        }

        const columns = [];
        let valid = true;

        $("#create-tbl-columns-container .fields").each(function () {
            const name = $(this).find(".col-def-name").val().trim();
            const type = $(this).find(".col-def-type").val();
            const isPk = $(this).find(".col-def-pk").is(":checked");
            const autoInc = $(this).find(".col-def-auto").is(":checked");
            const notNull = $(this).find(".col-def-notnull").is(":checked");

            if (!name) {
                valid = false;
                return false;
            }

            columns.push({
                name: name,
                type: type,
                is_pk: isPk,
                auto_increment: autoInc,
                not_null: notNull,
            });
        });

        if (!valid || columns.length === 0) {
            showToast("Warning", "All columns must have a name", "error");
            return;
        }

        try {
            await apiRequest("/api/tables/create", {
                method: "POST",
                body: JSON.stringify({
                    name: tblName,
                    columns: columns,
                }),
            });
            showToast("Table Created", `Table '${tblName}' created successfully`, "success");
            $("#modal-create-table").modal("hide");
            await loadTablesList();
            selectActiveTable(tblName);
        } catch (err) {
            showToast("Error creating table", err.message, "error");
        }
    });

    // Add Column Modal
    $("#btn-modal-add-column").on("click", function () {
        if (!state.activeTable) return;
        $("#modal-add-col-table").text(state.activeTable);
        $("#add-col-name").val("");
        $("#add-col-default").val("");
        $("#add-col-notnull").prop("checked", false);
        $("#modal-add-column").modal("show");
    });

    $("#btn-confirm-add-column").on("click", async function () {
        const colName = $("#add-col-name").val().trim();
        const colType = $("#add-col-type").val();
        const notNull = $("#add-col-notnull").is(":checked");
        const defaultVal = $("#add-col-default").val().trim();

        if (!colName) {
            showToast("Warning", "The column name is required", "error");
            return;
        }

        try {
            await apiRequest(`/api/tables/${encodeURIComponent(state.activeTable)}/alter`, {
                method: "POST",
                body: JSON.stringify({
                    column: {
                        name: colName,
                        type: colType,
                        not_null: notNull,
                        default_value: defaultVal || null,
                    },
                }),
            });
            showToast("Column Added", `Column '${colName}' added to '${state.activeTable}'`, "success");
            $("#modal-add-column").modal("hide");
            loadActiveTable();
        } catch (err) {
            showToast("Error adding column", err.message, "error");
        }
    });

    // Shared rename flow — used by the table-list row menu.
    function openRenameTableModal(currentName) {
        $("#rename-tbl-original").text(currentName);
        $("#rename-tbl-name").val(currentName);
        $("#modal-rename-table").modal("show");

        const submit = async function () {
            const newName = $("#rename-tbl-name").val().trim();
            if (!newName) {
                showToast("Warning", "The new table name is required", "error");
                return;
            }
            if (newName === currentName) {
                $("#modal-rename-table").modal("hide");
                return;
            }

            $("#btn-confirm-rename-table").addClass("loading disabled");
            try {
                await apiRequest(`/api/tables/${encodeURIComponent(currentName)}/rename`, {
                    method: "POST",
                    body: JSON.stringify({ new_name: newName }),
                });
                showToast("Table Renamed", `Table '${currentName}' renamed to '${newName}'`, "success");
                $("#modal-rename-table").modal("hide");

                // Keep the workspace pointed at the same (now renamed) table.
                if (state.activeTable === currentName) {
                    state.activeTable = newName;
                    $("#active-table-name").text(newName);
                }
                await loadTablesList();
                if (state.activeTable) loadActiveTable();
            } catch (err) {
                showToast("Error renaming table", err.message, "error");
            } finally {
                $("#btn-confirm-rename-table").removeClass("loading disabled");
            }
        };

        $("#btn-confirm-rename-table").off("click").on("click", submit);
        $("#rename-tbl-name").off("keyup").on("keyup", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                submit();
            }
        });
    }

    // Shared drop flow — used by the Structure-tab button and the table-list menu.
    // The target name/type come from the caller, never from the active-table state.
    function confirmDropCollection(name, type) {
        const isView = type === "view";
        const kindLabel = isView ? "View" : "Table";

        $("#confirm-delete-title").text(`Drop ${kindLabel}`);
        $("#confirm-delete-message").html(
            isView
                ? `Are you sure you want to drop view <strong>${name}</strong>? The view will be removed, but its underlying data is preserved.`
                : `Are you sure you want to permanently drop table <strong>${name}</strong>? All its data will be destroyed.`
        );

        $("#btn-confirm-delete-execute").off("click").on("click", async function () {
            try {
                await apiRequest(`/api/tables/${encodeURIComponent(name)}/drop`, {
                    method: "DELETE",
                });
                showToast(`${kindLabel} Dropped`, `${kindLabel} '${name}' dropped successfully`, "success");
                $("#modal-confirm-delete").modal("hide");

                // Only reset the workspace when the dropped entity was the selected one.
                if (state.activeTable === name) {
                    state.activeTable = null;
                    state.activeSchema = null;
                    $("#active-table-panel").hide();
                    $("#empty-table-state").show();
                }
                loadTablesList();
            } catch (err) {
                showToast(`Error dropping ${isView ? "view" : "table"}`, err.message, "error");
            }
        });

        $("#modal-confirm-delete").modal("show");
    }

    // Drop Table Modal (DROP) — Structure-tab entry point
    $("#btn-modal-drop-table").on("click", function () {
        if (!state.activeTable) return;
        const type = state.activeSchema && state.activeSchema.type ? state.activeSchema.type : "table";
        confirmDropCollection(state.activeTable, type);
    });

    // ================= TAB 3: SQL CONSOLE =================
    $("#btn-empty-open-sql").on("click", function () {
        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $('#workspace-tabs .item[data-tab="tab-sql"]').click();
    });

    function suggestDefaultQuery() {
        if (state.activeTable && !$("#sql-query-input").val().trim()) {
            $("#sql-query-input").val(`SELECT * FROM "${state.activeTable}" LIMIT 50;`);
        }
    }

    $("#btn-sql-preset-select").on("click", function () {
        const tbl = state.activeTable || "my_table";
        $("#sql-query-input").val(`SELECT * FROM "${tbl}" LIMIT 50;`);
    });

    $("#btn-sql-preset-count").on("click", function () {
        const tbl = state.activeTable || "my_table";
        $("#sql-query-input").val(`SELECT COUNT(*) as total_rows FROM "${tbl}";`);
    });

    $("#btn-sql-clear").on("click", function () {
        $("#sql-query-input").val("");
        $("#sql-message-area").hide();
        $("#sql-results-container").hide();
    });

    $("#btn-execute-sql").on("click", async function () {
        const query = $("#sql-query-input").val().trim();
        if (!query) {
            showToast("Warning", "Enter a SQL statement to run", "info");
            return;
        }

        const $msgArea = $("#sql-message-area");
        const $resContainer = $("#sql-results-container");
        $("#btn-execute-sql").addClass("loading disabled");

        try {
            const result = await apiRequest("/api/query", {
                method: "POST",
                body: JSON.stringify({ query: query }),
            });

            $msgArea.show().html(`
                <div class="ui positive message">
                    <i class="check circle icon"></i>
                    <strong>${result.message || "Executed successfully"}</strong> (${result.execution_time_ms} ms)
                </div>
            `);

            if (result.columns && result.columns.length > 0) {
                renderSqlResults(result);
                $resContainer.show();
            } else {
                $resContainer.hide();
                // If it ran DDL or an insert, refresh the table list
                loadTablesList();
                if (state.activeTable) loadTableRecords();
            }
        } catch (err) {
            $msgArea.show().html(`
                <div class="ui negative message">
                    <i class="exclamation triangle icon"></i>
                    <strong>SQL Error:</strong> ${err.message}
                </div>
            `);
            $resContainer.hide();
        } finally {
            $("#btn-execute-sql").removeClass("loading disabled");
        }
    });

    function renderSqlResults(result) {
        const $head = $("#grid-sql-head");
        const $body = $("#grid-sql-body");
        $head.empty();
        $body.empty();

        const $trHead = $("<tr></tr>");
        result.columns.forEach((col) => {
            $trHead.append(`<th>${escapeHtml(col)}</th>`);
        });
        $head.append($trHead);

        if (!result.rows || result.rows.length === 0) {
            $body.append(`<tr><td colspan="${result.columns.length}" class="center aligned" style="color: #a0aec0;">0 rows returned</td></tr>`);
            return;
        }

        result.rows.forEach((row) => {
            const $tr = $("<tr></tr>");
            result.columns.forEach((col) => {
                const val = row[col];
                let displayVal = val;
                let cellClass = "";
                if (val === null || val === undefined) {
                    displayVal = "NULL";
                    cellClass = "cell-null";
                } else if (typeof val === "object") {
                    displayVal = JSON.stringify(val);
                }
                $tr.append(`<td class="${cellClass}">${escapeHtml(String(displayVal))}</td>`);
            });
            $body.append($tr);
        });
    }

    // ================= UTILITIES =================
    function getFileName(path) {
        if (!path) return "";
        return path.split("/").pop().split("\\").pop();
    }

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
