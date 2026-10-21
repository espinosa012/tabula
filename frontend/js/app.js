/**
 * vg-data-visor - SPA Frontend Logic
 */

$(document).ready(function () {
    // ================= GLOBAL STATE =================
    const state = {
        connected: false,
        dbPath: "",
        dbType: "sqlite", // "sqlite", "postgres" or "mongo"
        tables: [],
        views: [],
        activeTable: null,
        activeView: null,
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

    // CodeMirror instance for the console (null if the vendored library is missing).
    let sqlEditor = null;

    // ================= UI INITIALIZATION =================
    $("#connection-tabs .item").tab();
    $("#pg-connection-tabs .item").tab();
    $("#mongo-connection-tabs .item").tab();
    $("#workspace-tabs .item").tab({
        onVisible: function (tabPath) {
            state.activeTab = tabPath;
            if (tabPath === "tab-sql") {
                // The editor was likely initialized while its tab was hidden.
                refreshSqlEditor();
                suggestDefaultQuery();
            }
        },
    });
    $(".ui.dropdown").dropdown();

    // Check whether there is already an active connection on the server
    checkConnectionStatus();
    loadRecentDatabases();
    loadAppConfig();

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
    async function loadAppConfig() {
        try {
            const config = await apiRequest("/api/config");
            if (config && config.default_db_path && !$("#input-open-path").val()) {
                $("#input-open-path").val(config.default_db_path);
            }
        } catch (e) {
            console.warn("Could not load app config:", e);
        }
    }

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
        state.dbType = info.db_type || "sqlite";

        let statusHtml = "";
        if (state.dbType === "mongo") {
            const hostDisplay = info.host ? `${info.host}:${info.port || 27017}` : "MongoDB";
            const dbDisplay = info.database || "test";
            statusHtml = `<span class="ui green empty circular label"></span> &nbsp; <span title="${escapeHtml(info.path)}"><i class="leaf icon"></i> <strong>${escapeHtml(dbDisplay)}</strong> (${escapeHtml(hostDisplay)}) &nbsp; <small style="color: #cbd5e1;">${formatBytes(info.size_bytes)}</small></span>`;
        } else if (state.dbType === "postgres") {
            const hostDisplay = info.host ? `${info.host}:${info.port || 5432}` : "PostgreSQL";
            const dbDisplay = info.database || "postgres";
            statusHtml = `<span class="ui green empty circular label"></span> &nbsp; <span title="${escapeHtml(info.path)}"><i class="server icon"></i> <strong>${escapeHtml(dbDisplay)}</strong> (${escapeHtml(hostDisplay)}) &nbsp; <small style="color: #cbd5e1;">${formatBytes(info.size_bytes)}</small></span>`;
        } else {
            statusHtml = `<span class="ui green empty circular label"></span> &nbsp; <span title="${escapeHtml(info.path)}"><strong>${escapeHtml(getFileName(info.path))}</strong> (${formatBytes(info.size_bytes)})</span>`;
        }

        $("#nav-db-status").html(statusHtml);
        $("#btn-refresh-all, #btn-disconnect").show();
        $("#view-connection").hide();
        $("#view-workspace").show();
        applyDbTypeLabels();

        updateSqlTerminalTitle();
        loadTablesList();
        loadViewsList();
        loadRecentDatabases();
    }

    function setDisconnectedState() {
        state.connected = false;
        state.dbPath = "";
        state.dbType = "sqlite";
        state.tables = [];
        state.views = [];
        state.activeTable = null;
        state.activeView = null;
        state.activeSchema = null;

        $("#views-list").empty();
        $("#count-views").text("0");
        $("#nav-db-status").html('<span class="ui grey empty circular label"></span> &nbsp; Disconnected');
        $("#btn-refresh-all, #btn-disconnect").hide();
        $("#view-workspace").hide();
        $("#view-connection").show();
        $("#active-table-panel").hide();
        $("#empty-table-state").show();
        applyDbTypeLabels();
        updateSqlTerminalTitle();
    }

    // Makes workspace labels follow the active engine (table vs collection, SQL vs JSON).
    function applyDbTypeLabels() {
        const isMongo = state.dbType === "mongo";
        const objectWord = isMongo ? "collection" : "table";
        const objectsWord = isMongo ? "Collections" : "Tables";
        const queryPlaceholder = isMongo
            ? '{"collection": "my_collection", "operation": "find", "limit": 50}'
            : "SELECT * FROM my_table LIMIT 50;";

        $("#lbl-tables-section").text(objectsWord);
        $("#filter-tables").attr("placeholder", `Filter ${objectsWord.toLowerCase()} & views...`);
        $("#btn-filter-tables-toggle").attr("title", `Filter ${objectsWord.toLowerCase()} and views`);
        $("#lbl-new-table").text(isMongo ? "New Collection" : "New Table");
        $("#lbl-empty-message").text(`Select a ${objectWord} from the left panel or create a new one`);
        $("#lbl-tab-data").text(isMongo ? "Data" : "Data (DML)");
        $("#lbl-tab-schema").text(isMongo ? "Structure" : "Structure (DDL)");
        $("#lbl-tab-sql").text(isMongo ? "Query Console" : "SQL Console");
        $("#lbl-add-record").text(isMongo ? "New Document" : "New Record");
        $("#lbl-structure-title").text(isMongo ? "Collection Structure" : "Structure and Columns");
        $("#lbl-add-column").text(isMongo ? "Add Field" : "Add Column");
        $("#lbl-drop-table").text(isMongo ? "Drop Collection" : "Drop Table");
        $("#lbl-schema-type-header").text(isMongo ? "Inferred Type" : "SQLite Type");
        $("#lbl-query-console-title").text(isMongo ? "MongoDB Query Console" : "SQL Query Console");
        $("#lbl-open-console").text(isMongo ? "Open Query Console" : "Open SQL Console");
        $("#lbl-run-query").text(isMongo ? "Run Query" : "Run SQL");
        $("#lbl-terminal-prompt").text(isMongo ? "mongo>" : state.dbType === "postgres" ? "psql>" : "sqlite>");
        $("#mongo-query-help").toggle(isMongo);
        $("#lbl-create-table-title").text(isMongo ? "Create New Collection" : "Create New Table");
        $("#lbl-create-table-name").text(isMongo ? "Collection Name:" : "Table Name:");
        $("#lbl-create-table-confirm").text(isMongo ? "Create Collection" : "Create Table");
        $("#lbl-column-definition").toggle(!isMongo);
        $("#create-tbl-columns-section").toggle(!isMongo);
        $("#mongo-create-note").toggle(isMongo);
        $("#lbl-add-column-title").text(isMongo ? "Add Field to" : "Add Column to");
        $("#lbl-add-column-name").text(isMongo ? "Field Name:" : "Column Name:");
        $("#lbl-add-column-confirm").text(isMongo ? "Add Field" : "Add Column");
        $("#lbl-view-query").text(isMongo ? "MongoDB Query (JSON):" : "SQL Query:");
        $("#btn-sql-preset-select").text(isMongo ? "Find" : "SELECT *");
        $("#btn-sql-preset-count").text(isMongo ? "Count" : "COUNT(*)");
        $("#sql-query-input").attr("placeholder", queryPlaceholder);
        $("#input-search-records").attr("placeholder", isMongo ? "Search documents..." : "Search in table...");
        $("#input-view-sql").attr(
            "placeholder",
            isMongo
                ? '{"collection": "my_collection", "operation": "find", "filter": {}}'
                : "SELECT id, name FROM my_table WHERE ...;"
        );
        updateEmptyStateCreateButton();
        if (sqlEditor) sqlEditor.setOption("placeholder", queryPlaceholder);
    }

    function classifyRecentConnection(path) {
        if (/^mongodb(\+srv)?:\/\//i.test(path)) return "mongo";
        if (/^postgres(ql)?:\/\//i.test(path)) return "postgres";
        // Parameter-based PostgreSQL connections look like user@host:port/db.
        if (path.includes("@") && !path.startsWith("/") && !/^[A-Za-z]:[\\/]/.test(path)) return "postgres";
        return "sqlite";
    }

    async function loadRecentDatabases() {
        try {
            const recents = await apiRequest("/api/connection/recent");
            const $listSqlite = $("#list-recent-dbs");
            const $listPg = $("#list-recent-pg");
            const $listMongo = $("#list-recent-mongo");
            $listSqlite.empty();
            if ($listPg.length) $listPg.empty();
            if ($listMongo.length) $listMongo.empty();

            const sqliteRecents = [];
            const pgRecents = [];
            const mongoRecents = [];

            (recents || []).forEach((path) => {
                const kind = classifyRecentConnection(path);
                if (kind === "mongo") mongoRecents.push(path);
                else if (kind === "postgres") pgRecents.push(path);
                else sqliteRecents.push(path);
            });

            if (sqliteRecents.length > 0) {
                $("#section-recent-dbs").show();
                sqliteRecents.forEach((path) => {
                    const $item = $(`
                        <div class="item fs-item">
                            <i class="database icon"></i>
                            <div class="content" style="flex: 1;">
                                <div class="header">${escapeHtml(getFileName(path))}</div>
                                <div class="description" style="font-size: 0.85em; color: #718096;">${escapeHtml(path)}</div>
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
                    $listSqlite.append($item);
                });
            } else {
                $("#section-recent-dbs").hide();
            }

            if (pgRecents.length > 0 && $listPg.length) {
                $("#section-recent-pg").show();
                pgRecents.forEach((path) => {
                    const $item = $(`
                        <div class="item fs-item">
                            <i class="server icon"></i>
                            <div class="content" style="flex: 1;">
                                <div class="header">${escapeHtml(path)}</div>
                            </div>
                            <button class="ui mini basic button btn-connect-recent-pg">Connect</button>
                        </div>
                    `);
                    $item.find(".btn-connect-recent-pg").on("click", function (e) {
                        e.stopPropagation();
                        connectToPostgres("uri", null, path);
                    });
                    $item.on("click", function () {
                        $("#pg-connection-tabs .item").tab("change tab", "tab-pg-uri");
                        $("#input-pg-uri").val(path);
                    });
                    $listPg.append($item);
                });
            } else if ($listPg.length) {
                $("#section-recent-pg").hide();
            }

            if (mongoRecents.length > 0 && $listMongo.length) {
                $("#section-recent-mongo").show();
                mongoRecents.forEach((path) => {
                    const $item = $(`
                        <div class="item fs-item">
                            <i class="leaf icon"></i>
                            <div class="content" style="flex: 1;">
                                <div class="header">${escapeHtml(path)}</div>
                            </div>
                            <button class="ui mini basic button btn-connect-recent-mongo">Connect</button>
                        </div>
                    `);
                    $item.find(".btn-connect-recent-mongo").on("click", function (e) {
                        e.stopPropagation();
                        connectToMongo("uri", null, path);
                    });
                    $item.on("click", function () {
                        $("#mongo-connection-tabs .item").tab("change tab", "tab-mongo-uri");
                        $("#input-mongo-uri").val(path);
                    });
                    $listMongo.append($item);
                });
            } else if ($listMongo.length) {
                $("#section-recent-mongo").hide();
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

    // Engine Selector Switcher
    $("#btn-select-engine-sqlite").on("click", function () {
        $(this).addClass("positive active");
        $("#btn-select-engine-pg, #btn-select-engine-mongo").removeClass("positive active");
        $("#container-engine-sqlite").show();
        $("#container-engine-pg, #container-engine-mongo").hide();
    });

    $("#btn-select-engine-pg").on("click", function () {
        $(this).addClass("positive active");
        $("#btn-select-engine-sqlite, #btn-select-engine-mongo").removeClass("positive active");
        $("#container-engine-sqlite, #container-engine-mongo").hide();
        $("#container-engine-pg").show();
        $("#pg-connection-tabs .item").tab();
    });

    $("#btn-select-engine-mongo").on("click", function () {
        $(this).addClass("positive active");
        $("#btn-select-engine-sqlite, #btn-select-engine-pg").removeClass("positive active");
        $("#container-engine-sqlite, #container-engine-pg").hide();
        $("#container-engine-mongo").show();
        $("#mongo-connection-tabs .item").tab();
    });

    // PostgreSQL Connection & Testing Logic
    function getPgParamsFromForm() {
        return {
            host: $("#input-pg-host").val().trim() || "localhost",
            port: parseInt($("#input-pg-port").val(), 10) || 5432,
            database: $("#input-pg-db").val().trim() || "postgres",
            user: $("#input-pg-user").val().trim() || "postgres",
            password: $("#input-pg-pass").val() || "",
            sslmode: $("#select-pg-sslmode").val() || "prefer",
        };
    }

    async function testPostgresConnection(mode, params, uri) {
        const $btn = mode === "uri" ? $("#btn-pg-test-uri") : $("#btn-pg-test-params");
        $btn.addClass("loading disabled");
        $("#pg-test-result").hide().removeClass("positive negative");

        try {
            const payload = mode === "uri" ? { mode: "uri", uri: uri } : { mode: "params", params: params };
            const res = await apiRequest("/api/connection/postgres/test", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            if (res.success) {
                $("#pg-test-result")
                    .addClass("positive")
                    .html(`<i class="check circle icon"></i> <strong>Connection successful!</strong> ${escapeHtml(res.server_version || '')} (${escapeHtml(res.database || '')})`)
                    .show();
                showToast("Connection Test OK", "PostgreSQL server is reachable", "success");
            } else {
                $("#pg-test-result")
                    .addClass("negative")
                    .html(`<i class="times circle icon"></i> <strong>Connection failed:</strong> ${escapeHtml(res.message)}`)
                    .show();
                showToast("Connection Failed", res.message, "error");
            }
        } catch (err) {
            $("#pg-test-result")
                .addClass("negative")
                .html(`<i class="times circle icon"></i> <strong>Error:</strong> ${escapeHtml(err.message)}`)
                .show();
            showToast("Test Error", err.message, "error");
        } finally {
            $btn.removeClass("loading disabled");
        }
    }

    async function connectToPostgres(mode, params, uri) {
        const $btn = mode === "uri" ? $("#btn-pg-connect-uri") : $("#btn-pg-connect-params");
        $btn.addClass("loading disabled");
        $("#pg-test-result").hide();

        try {
            const payload = mode === "uri" ? { mode: "uri", uri: uri } : { mode: "params", params: params };
            const info = await apiRequest("/api/connection/postgres/connect", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            showToast("Connected", `Connected to PostgreSQL: ${info.database || info.path}`, "success");
            setConnectedState(info);
        } catch (err) {
            showToast("PostgreSQL Connection Error", err.message, "error");
        } finally {
            $btn.removeClass("loading disabled");
        }
    }

    $("#btn-pg-test-params").on("click", function () {
        const params = getPgParamsFromForm();
        testPostgresConnection("params", params, null);
    });

    $("#form-pg-params").on("submit", function (e) {
        e.preventDefault();
        const params = getPgParamsFromForm();
        connectToPostgres("params", params, null);
    });

    $("#btn-pg-test-uri").on("click", function () {
        const uri = $("#input-pg-uri").val().trim();
        if (!uri) {
            showToast("Missing URI", "Please enter a PostgreSQL connection URL", "error");
            return;
        }
        testPostgresConnection("uri", null, uri);
    });

    $("#form-pg-uri").on("submit", function (e) {
        e.preventDefault();
        const uri = $("#input-pg-uri").val().trim();
        if (uri) connectToPostgres("uri", null, uri);
    });

    // MongoDB Connection & Testing Logic
    function getMongoParamsFromForm() {
        return {
            host: $("#input-mongo-host").val().trim() || "localhost",
            port: parseInt($("#input-mongo-port").val(), 10) || 27017,
            database: $("#input-mongo-db").val().trim() || "test",
            user: $("#input-mongo-user").val().trim() || "",
            password: $("#input-mongo-pass").val() || "",
            auth_source: $("#input-mongo-authsource").val().trim() || "admin",
            tls: $("#check-mongo-tls").is(":checked"),
        };
    }

    async function testMongoConnection(mode, params, uri) {
        const $btn = mode === "uri" ? $("#btn-mongo-test-uri") : $("#btn-mongo-test-params");
        $btn.addClass("loading disabled");
        $("#mongo-test-result").hide().removeClass("positive negative");

        try {
            const payload = mode === "uri" ? { mode: "uri", uri: uri } : { mode: "params", params: params };
            const res = await apiRequest("/api/connection/mongo/test", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            if (res.success) {
                $("#mongo-test-result")
                    .addClass("positive")
                    .html(`<i class="check circle icon"></i> <strong>Connection successful!</strong> ${escapeHtml(res.server_version || "")} (${escapeHtml(res.database || "")})`)
                    .show();
                showToast("Connection Test OK", "MongoDB server is reachable", "success");
            } else {
                $("#mongo-test-result")
                    .addClass("negative")
                    .html(`<i class="times circle icon"></i> <strong>Connection failed:</strong> ${escapeHtml(res.message)}`)
                    .show();
                showToast("Connection Failed", res.message, "error");
            }
        } catch (err) {
            $("#mongo-test-result")
                .addClass("negative")
                .html(`<i class="times circle icon"></i> <strong>Error:</strong> ${escapeHtml(err.message)}`)
                .show();
            showToast("Test Error", err.message, "error");
        } finally {
            $btn.removeClass("loading disabled");
        }
    }

    async function connectToMongo(mode, params, uri) {
        const $btn = mode === "uri" ? $("#btn-mongo-connect-uri") : $("#btn-mongo-connect-params");
        $btn.addClass("loading disabled");
        $("#mongo-test-result").hide();

        try {
            const payload = mode === "uri" ? { mode: "uri", uri: uri } : { mode: "params", params: params };
            const info = await apiRequest("/api/connection/mongo/connect", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            showToast("Connected", `Connected to MongoDB: ${info.database || info.path}`, "success");
            setConnectedState(info);
        } catch (err) {
            showToast("MongoDB Connection Error", err.message, "error");
        } finally {
            $btn.removeClass("loading disabled");
        }
    }

    $("#btn-mongo-test-params").on("click", function () {
        testMongoConnection("params", getMongoParamsFromForm(), null);
    });

    $("#form-mongo-params").on("submit", function (e) {
        e.preventDefault();
        connectToMongo("params", getMongoParamsFromForm(), null);
    });

    $("#btn-mongo-test-uri").on("click", function () {
        const uri = $("#input-mongo-uri").val().trim();
        if (!uri) {
            showToast("Missing URI", "Please enter a MongoDB connection URL", "error");
            return;
        }
        testMongoConnection("uri", null, uri);
    });

    $("#form-mongo-uri").on("submit", function (e) {
        e.preventDefault();
        const uri = $("#input-mongo-uri").val().trim();
        if (uri) connectToMongo("uri", null, uri);
    });

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
        loadViewsList();
        if (state.activeTable) {
            loadActiveTable();
        } else if (state.activeView) {
            loadActiveView();
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
        openFsBrowser("file", "input-open-path", ($("#input-open-path").val() || "").trim());
    });

    $("#btn-create-browse-dir").on("click", function () {
        openFsBrowser("dir", "input-create-dir", ($("#input-create-dir").val() || "").trim());
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
        if (state.dbType === "mongo") {
            $("#btn-empty-create-table-label").text(hasTables ? "Add New Collection" : "Create First Collection");
        } else {
            $("#btn-empty-create-table-label").text(hasTables ? "Add New Table" : "Create First Table");
        }
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
            const isMongo = state.dbType === "mongo";
            const icon = isView ? "eye icon blue" : isMongo ? "leaf icon green" : "table icon";
            const countLabel = t.row_count !== null ? `<span class="ui mini label">${t.row_count}</span>` : "";
            const activeClass = state.activeTable === t.name ? "active teal" : "";
            const dropLabel = isView ? "Drop view" : isMongo ? "Drop collection" : "Drop table";
            const renameItem = isView
                ? ""
                : `<div class="item row-action-rename">
                                <i class="edit icon"></i> Rename ${isMongo ? "collection" : "table"}
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

    // Sidebar "Filter tables & views" input: its icon doubles as a clear button, showing
    // a magnifier when empty and an "x" (which clears the filter) once there is text.
    function updateTablesFilterButton() {
        const hasText = $("#filter-tables").val().length > 0;
        $("#btn-filter-tables-toggle")
            .toggleClass("search", !hasText)
            .toggleClass("times", hasText)
            .attr("title", hasText ? "Clear filter" : "Filter tables & views");
    }

    $("#filter-tables").on("input", function () {
        renderTablesList();
        renderViewsList();
        updateTablesFilterButton();
    });

    $("#btn-filter-tables-toggle").on("click", function () {
        if ($("#filter-tables").val().length > 0) {
            $("#filter-tables").val("");
            renderTablesList();
            renderViewsList();
            updateTablesFilterButton();
        } else {
            $("#filter-tables").focus();
        }
    });

    function selectActiveTable(tableName) {
        state.activeTable = tableName;
        state.activeView = null;
        state.pagination.page = 1;
        state.pagination.search = "";
        state.pagination.sortBy = null;
        state.pagination.sortDir = "asc";
        $("#input-search-records").val("");
        updateSearchButton();

        renderTablesList();
        renderViewsList();
        loadActiveTable();
    }

    async function loadActiveTable() {
        if (!state.activeTable) return;

        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $("#active-table-name").text(state.activeTable);
        $("#badge-active-type").hide();
        $("#active-table-subheader").html('Total: <span id="table-total-records">0</span> records');
        $("#btn-add-record").show();
        $("#table-schema-actions").show();
        $("#view-schema-actions").hide();
        $("#schema-sql-view-title").text(state.dbType === "mongo" ? "Collection Notes" : "CREATE SQL Statement");

        await loadTableSchema();
        await loadTableRecords();
    }

    // ================= CUSTOM VIEWS SIDEBAR & MANAGEMENT =================
    async function loadViewsList() {
        try {
            const views = await apiRequest("/api/views");
            state.views = views;
            $("#count-views").text(views.length);
            renderViewsList();
        } catch (err) {
            console.warn("Could not load custom views:", err);
        }
    }

    function renderViewsList() {
        const filter = $("#filter-tables").val().toLowerCase().trim();
        const $list = $("#views-list");
        $list.empty();

        if (state.views.length === 0) {
            $list.append(`
                <div class="item" style="color: #a0aec0; font-size: 0.85em; text-align: center; padding: 0.8rem 0.5rem;">
                    No custom views yet.<br>
                    <a href="#" id="link-create-first-view" style="color: #00b5ad; cursor: pointer; text-decoration: underline;">Create view</a>
                </div>
            `);
            $list.find("#link-create-first-view").on("click", function (e) {
                e.preventDefault();
                openCreateViewModal();
            });
            return;
        }

        const filtered = state.views.filter(
            (v) => v.name.toLowerCase().includes(filter) || (v.description && v.description.toLowerCase().includes(filter))
        );

        if (filtered.length === 0) {
            $list.append('<div class="item" style="color: #a0aec0; font-size: 0.85em;">No matching views</div>');
            return;
        }

        filtered.forEach((v) => {
            const isActive = state.activeView && state.activeView.id === v.id;
            const activeClass = isActive ? "active teal" : "";

            const $item = $(`
                <a class="item table-list-item ${activeClass}" data-view-id="${v.id}">
                    <i class="bookmark icon teal"></i>
                    <span class="table-list-name" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</span>
                    <div class="ui dropdown row-actions">
                        <i class="ellipsis vertical icon"></i>
                        <div class="menu">
                            <div class="item row-action-view-open-sql">
                                <i class="terminal icon"></i> Open in SQL Console
                            </div>
                            <div class="item row-action-view-edit">
                                <i class="edit icon"></i> Edit view
                            </div>
                            <div class="item row-action-view-delete">
                                <i class="trash icon red"></i> Delete view
                            </div>
                        </div>
                    </div>
                </a>
            `);

            $item.find(".row-actions").on("click", function (e) {
                e.stopPropagation();
            });
            $item.find(".row-action-view-open-sql").on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                openViewInSqlConsole(v);
            });
            $item.find(".row-action-view-edit").on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                openEditViewModal(v);
            });
            $item.find(".row-action-view-delete").on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                confirmDeleteView(v);
            });

            $item.on("click", function (e) {
                if ($(e.target).closest(".row-actions").length) return;
                selectActiveView(v.id);
            });

            $list.append($item);
        });

        $list.find(".row-actions").dropdown({
            direction: "auto",
            context: "#views-list",
        });
    }

    function selectActiveView(viewId) {
        const view = state.views.find((v) => v.id === viewId);
        if (!view) return;

        state.activeView = view;
        state.activeTable = null;
        state.activeSchema = null;
        state.pagination.page = 1;
        state.pagination.search = "";
        state.pagination.sortBy = null;
        state.pagination.sortDir = "asc";
        $("#input-search-records").val("");
        updateSearchButton();

        renderTablesList();
        renderViewsList();
        loadActiveView();
    }

    async function loadActiveView() {
        if (!state.activeView) return;

        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $("#active-table-name").text(state.activeView.name);
        $("#badge-active-type").text("Custom View").show();
        $("#active-table-subheader").html(
            `Total: <span id="table-total-records">0</span> records` +
            (state.activeView.description ? ` &bull; <em>${escapeHtml(state.activeView.description)}</em>` : "")
        );
        $("#btn-add-record").hide();

        $("#table-schema-actions").hide();
        $("#view-schema-actions").show();
        $("#schema-sql-view-title").text("View SQL Query");
        $("#schema-sql-view").text(state.activeView.sql);

        await loadViewRecords();
    }

    async function loadViewRecords() {
        if (!state.activeView) return;
        const $head = $("#grid-head");
        const $body = $("#grid-body");
        $body.html('<tr><td colspan="100" class="center aligned"><div class="ui active inline loader"></div> Loading view data...</td></tr>');

        const params = new URLSearchParams({
            page: state.pagination.page,
            page_size: state.pagination.pageSize,
            sort_dir: state.pagination.sortDir,
        });
        if (state.pagination.sortBy) params.append("sort_by", state.pagination.sortBy);
        if (state.pagination.search) params.append("search", state.pagination.search);

        try {
            const data = await apiRequest(`/api/views/${encodeURIComponent(state.activeView.id)}/records?${params.toString()}`);
            state.pagination.totalRecords = data.total;
            state.pagination.totalPages = data.total_pages;

            $("#table-total-records").text(data.total);
            $("#lbl-page-current").text(data.page);
            $("#lbl-page-num").text(data.page);
            $("#lbl-page-total").text(data.total_pages);

            renderRecordsTable(data, true);
        } catch (err) {
            $body.html(`<tr><td colspan="100" class="negative center aligned">${escapeHtml(err.message)}</td></tr>`);
        }
    }

    function openCreateViewModal(initialSql = "") {
        $("#modal-custom-view-title").html('<i class="bookmark icon teal"></i> Create New Custom View');
        $("#input-view-id").val("");
        $("#input-view-name").val("");
        $("#input-view-description").val("");
        let defaultQuery = initialSql;
        if (!defaultQuery && state.activeTable) {
            defaultQuery = state.dbType === "mongo"
                ? JSON.stringify({ collection: state.activeTable, operation: "find", filter: {}, limit: 50 }, null, 2)
                : `SELECT * FROM "${state.activeTable}" LIMIT 50;`;
        }
        $("#input-view-sql").val(defaultQuery || "");
        $("#view-test-result").hide().empty();
        $("#btn-confirm-save-view").text("Save View");
        $("#modal-custom-view").modal("show");
    }

    function openEditViewModal(view) {
        $("#modal-custom-view-title").html(`<i class="edit icon teal"></i> Edit Custom View: ${escapeHtml(view.name)}`);
        $("#input-view-id").val(view.id);
        $("#input-view-name").val(view.name);
        $("#input-view-description").val(view.description || "");
        $("#input-view-sql").val(view.sql);
        $("#view-test-result").hide().empty();
        $("#btn-confirm-save-view").text("Update View");
        $("#modal-custom-view").modal("show");
    }

    function openViewInSqlConsole(view) {
        setSqlQuery(view.sql);
        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $('#workspace-tabs .item[data-tab="tab-sql"]').click();
        refreshSqlEditor();
        focusSqlEditor();
    }

    function confirmDeleteView(view) {
        $("#confirm-delete-title").text("Delete Custom View");
        $("#confirm-delete-message").html(
            `Are you sure you want to delete custom view <strong>${escapeHtml(view.name)}</strong>? This will remove the view from local storage. Your database is not modified.`
        );

        $("#btn-confirm-delete-execute").off("click").on("click", async function () {
            try {
                await apiRequest(`/api/views/${encodeURIComponent(view.id)}`, { method: "DELETE" });
                showToast("View Deleted", `Custom view "${view.name}" deleted successfully`, "info");
                $("#modal-confirm-delete").modal("hide");

                if (state.activeView && state.activeView.id === view.id) {
                    state.activeView = null;
                    $("#active-table-panel").hide();
                    $("#empty-table-state").show();
                }
                loadViewsList();
            } catch (err) {
                showToast("Error deleting view", err.message, "error");
            }
        });

        $("#modal-confirm-delete").modal("show");
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
        if (state.activeView) {
            return loadViewRecords();
        }
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

            renderRecordsTable(data, false);
        } catch (err) {
            $body.html(`<tr><td colspan="100" class="negative center aligned">${err.message}</td></tr>`);
        }
    }

    function renderRecordsTable(data, isCustomView = false) {
        const $head = $("#grid-head");
        const $body = $("#grid-body");
        $head.empty();
        $body.empty();

        if (!data.columns || data.columns.length === 0) {
            $head.append("<tr><th>No columns</th></tr>");
            $body.append('<tr><td class="center aligned">No columns returned</td></tr>');
            return;
        }

        // Header
        const $trHead = $("<tr></tr>");
        if (!isCustomView) {
            $trHead.append('<th style="width: 80px; text-align: center;">Actions</th>');
        }

        data.columns.forEach((col) => {
            const isPk = data.pk_columns && data.pk_columns.includes(col);
            const isSorted = state.pagination.sortBy === col;
            let sortIcon = "";
            if (isSorted) {
                sortIcon = state.pagination.sortDir === "desc" ? '<i class="sort down icon"></i>' : '<i class="sort up icon"></i>';
            }

            const $th = $(`
                <th>
                    ${escapeHtml(col)} ${isPk ? '<span class="badge-pk">PK</span>' : ""}
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
        const totalColSpan = data.columns.length + (isCustomView ? 0 : 1);
        if (!data.records || data.records.length === 0) {
            $body.append(`<tr><td colspan="${totalColSpan}" class="center aligned" style="color: #a0aec0; padding: 2rem;">No records available</td></tr>`);
            return;
        }

        data.records.forEach((row) => {
            const $tr = $("<tr></tr>");

            // Action buttons (only for editable tables)
            if (!isCustomView) {
                const $tdActions = $('<td style="text-align: center;"></td>');
                const $btnEdit = $('<button class="ui mini icon button basic teal" title="Edit row"><i class="edit icon"></i></button>');
                const $btnDel = $('<button class="ui mini icon button basic red" title="Delete row"><i class="trash icon"></i></button>');

                $btnEdit.on("click", () => openEditRecordModal(row, data.pk_columns));
                $btnDel.on("click", () => confirmDeleteRecord(row, data.pk_columns));

                $tdActions.append($btnEdit).append(" ").append($btnDel);
                $tr.append($tdActions);
            }

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

        // For custom views, populate the structure tab with detected columns
        if (isCustomView) {
            const $schemaBody = $("#schema-body");
            $schemaBody.empty();
            data.columns.forEach((col) => {
                $schemaBody.append(`
                    <tr>
                        <td><strong>${escapeHtml(col)}</strong></td>
                        <td>EXPRESSION</td>
                        <td>-</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>
                `);
            });
        }
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
        const noun = state.dbType === "mongo" ? "Document" : "Record";
        $("#modal-record-title").html(`<i class="plus icon"></i> Insert New ${noun}`);
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
        const noun = state.dbType === "mongo" ? "Document" : "Record";
        $("#modal-record-title").html(`<i class="edit icon"></i> Edit ${noun}`);
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
            const displayVal = currentVal !== null && typeof currentVal === "object"
                ? JSON.stringify(currentVal)
                : (currentVal ?? "");

            // Disable input if it is an autoincrement key when inserting
            const isDisabled = isAutoInc && !isEditing ? "disabled placeholder='(Auto-numbered)'" : "";

            const $field = $(`
                <div class="field">
                    <label>
                        ${col.name} <span style="font-weight: normal; color: #718096;">(${col.type})</span>
                        ${col.is_pk ? '<span class="badge-pk">PK</span>' : ""}
                        ${col.not_null ? '<span style="color: red;">*</span>' : ""}
                    </label>
                    <input type="text" class="field-record-input" data-col="${col.name}" value="${escapeHtml(String(displayVal))}" ${isDisabled}>
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

        $("#confirm-delete-title").text(state.dbType === "mongo" ? "Delete Document" : "Delete Record");
        $("#confirm-delete-message").text(
            state.dbType === "mongo"
                ? `Are you sure you want to delete this document from collection '${state.activeTable}'?`
                : `Are you sure you want to delete this record from table '${state.activeTable}'?`
        );

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

        $("#schema-sql-view").text(schema.sql || (state.dbType === "mongo"
            ? "MongoDB collections are schemaless. Fields and types above are inferred from a sample of documents; every document always has a unique _id."
            : "-- Definition not available"));
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
            if (state.dbType === "mongo" && !defaultVal) {
                showToast(
                    "Schemaless collection",
                    "No default value was provided, so existing documents are unchanged. New or updated documents can now include this field.",
                    "info"
                );
            }
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
                showToast("Table Renamed", `${state.dbType === "mongo" ? "Collection" : "Table"} '${currentName}' renamed to '${newName}'`, "success");
                $("#modal-rename-table").modal("hide");

                // Keep the workspace pointed at the same (now renamed) table.
                if (state.activeTable === currentName) {
                    state.activeTable = newName;
                    $("#active-table-name").text(newName);
                }
                await loadTablesList();
                if (state.activeTable) loadActiveTable();
            } catch (err) {
                showToast("Error renaming", err.message, "error");
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
        const isMongo = state.dbType === "mongo";
        const kindLabel = isView ? "View" : isMongo ? "Collection" : "Table";

        $("#confirm-delete-title").text(`Drop ${kindLabel}`);
        $("#confirm-delete-message").html(
            isView
                ? `Are you sure you want to drop view <strong>${name}</strong>? The view will be removed, but its underlying data is preserved.`
                : isMongo
                ? `Are you sure you want to permanently drop collection <strong>${name}</strong>? All its documents will be destroyed.`
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
    // The console is a terminal-styled CodeMirror editor (vendored CodeMirror 5 +
    // SQL mode + Dracula dark theme). `sqlEditor` is null if the library failed to
    // load, in which case every helper below transparently falls back to the
    // plain <textarea> so the console keeps working.
    function initSqlEditor() {
        const el = document.getElementById("sql-query-input");
        if (!el || typeof CodeMirror === "undefined") return;

        sqlEditor = CodeMirror.fromTextArea(el, {
            mode: "text/x-sql",
            theme: "dracula",
            lineNumbers: true,
            lineWrapping: true,
            indentUnit: 4,
            tabSize: 4,
            extraKeys: {
                "Ctrl-Enter": executeSql,
                "Cmd-Enter": executeSql,
            },
        });
    }

    function getSqlQuery() {
        return sqlEditor ? sqlEditor.getValue() : $("#sql-query-input").val() || "";
    }

    function setSqlQuery(query) {
        if (sqlEditor) {
            sqlEditor.setValue(query);
            sqlEditor.refresh();
        } else {
            $("#sql-query-input").val(query);
        }
    }

    // CodeMirror cannot measure itself while its tab is hidden, so refresh the
    // editor whenever the SQL tab becomes visible.
    function refreshSqlEditor() {
        if (sqlEditor) sqlEditor.refresh();
    }

    // Keeps the terminal title bar showing the connected database file or host.
    function updateSqlTerminalTitle() {
        if (!state.connected || !state.dbPath) {
            $("#sql-terminal-title").text("sql console — not connected");
            return;
        }
        if (state.dbType === "mongo") {
            $("#sql-terminal-title").text(`mongosh — ${state.dbPath}`);
        } else if (state.dbType === "postgres") {
            $("#sql-terminal-title").text(`psql — ${state.dbPath}`);
        } else {
            $("#sql-terminal-title").text(`sqlite — ${getFileName(state.dbPath)}`);
        }
    }

    initSqlEditor();

    $("#btn-empty-open-sql").on("click", function () {
        $("#empty-table-state").hide();
        $("#active-table-panel").show();
        $('#workspace-tabs .item[data-tab="tab-sql"]').click();
    });

    function suggestDefaultQuery() {
        if (state.activeTable && !getSqlQuery().trim()) {
            if (state.dbType === "mongo") {
                setSqlQuery(JSON.stringify({
                    collection: state.activeTable,
                    operation: "find",
                    filter: {},
                    limit: 50,
                }, null, 2));
            } else {
                setSqlQuery(`SELECT * FROM "${state.activeTable}" LIMIT 50;`);
            }
        } else if (state.activeView && !getSqlQuery().trim()) {
            setSqlQuery(state.activeView.sql);
        }
    }

    $("#btn-sql-preset-select").on("click", function () {
        if (state.activeView) {
            setSqlQuery(state.activeView.sql);
            return;
        }
        const tbl = state.activeTable || (state.dbType === "mongo" ? "my_collection" : "my_table");
        if (state.dbType === "mongo") {
            setSqlQuery(JSON.stringify({
                collection: tbl,
                operation: "find",
                filter: {},
                limit: 50,
            }, null, 2));
        } else {
            setSqlQuery(`SELECT * FROM "${tbl}" LIMIT 50;`);
        }
    });

    $("#btn-sql-preset-count").on("click", function () {
        if (state.dbType === "mongo") {
            if (state.activeView) {
                setSqlQuery(state.activeView.sql);
                return;
            }
            const coll = state.activeTable || "my_collection";
            setSqlQuery(JSON.stringify({ collection: coll, operation: "count", filter: {} }, null, 2));
            return;
        }
        if (state.activeView) {
            const clean = state.activeView.sql.replace(/;+\s*$/, "");
            setSqlQuery(`SELECT COUNT(*) as total_rows FROM (${clean}) AS _subquery;`);
            return;
        }
        const tbl = state.activeTable || "my_table";
        setSqlQuery(`SELECT COUNT(*) as total_rows FROM "${tbl}";`);
    });

    $("#btn-sql-clear").on("click", function () {
        setSqlQuery("");
        $("#sql-message-area").hide();
        $("#sql-results-container").hide();
    });

    // Bound to the "Run SQL" button and to Ctrl/Cmd+Enter inside the editor.
    async function executeSql() {
        const query = getSqlQuery().trim();
        if (!query) {
            showToast("Warning", state.dbType === "mongo" ? "Enter a MongoDB JSON command to run" : "Enter a SQL statement to run", "info");
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
            const errorLabel = state.dbType === "mongo" ? "MongoDB Error:" : "SQL Error:";
            $msgArea.show().html(`
                <div class="ui negative message">
                    <i class="exclamation triangle icon"></i>
                    <strong>${errorLabel}</strong> ${escapeHtml(err.message)}
                </div>
            `);
            $resContainer.hide();
        } finally {
            $("#btn-execute-sql").removeClass("loading disabled");
        }
    }

    $("#btn-execute-sql").on("click", executeSql);

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

    // ================= CUSTOM VIEW EVENT LISTENERS =================
    $("#btn-modal-create-view").on("click", function () {
        openCreateViewModal();
    });

    $("#btn-sql-save-as-view").on("click", function () {
        const query = getSqlQuery().trim();
        if (!query) {
            showToast("Empty Query", "Please enter a query in the console before saving as a view.", "warning");
            return;
        }
        openCreateViewModal(query);
    });

    $("#btn-schema-edit-view").on("click", function () {
        if (state.activeView) {
            openEditViewModal(state.activeView);
        }
    });

    $("#btn-schema-open-view-sql").on("click", function () {
        if (state.activeView) {
            openViewInSqlConsole(state.activeView);
        }
    });

    $("#btn-schema-delete-view").on("click", function () {
        if (state.activeView) {
            confirmDeleteView(state.activeView);
        }
    });

    $("#btn-test-view-sql").on("click", async function () {
        const sql = $("#input-view-sql").val().trim();
        if (!sql) {
            $("#view-test-result").html('<div class="ui warning message mini">Please enter a query to test.</div>').show();
            return;
        }
        $("#btn-test-view-sql").addClass("loading disabled");
        try {
            const res = await apiRequest("/api/views/preview", {
                method: "POST",
                body: JSON.stringify({ name: "preview", sql: sql }),
            });
            $("#view-test-result").html(
                `<div class="ui positive message mini"><i class="check circle icon"></i> Query valid! Returns ${res.total} total rows, ${res.columns.length} columns (${res.columns.slice(0, 5).join(", ")}${res.columns.length > 5 ? "..." : ""}).</div>`
            ).show();
        } catch (err) {
            $("#view-test-result").html(
                `<div class="ui negative message mini"><i class="exclamation triangle icon"></i> ${escapeHtml(err.message)}</div>`
            ).show();
        } finally {
            $("#btn-test-view-sql").removeClass("loading disabled");
        }
    });

    $("#btn-confirm-save-view").on("click", async function (e) {
        e.preventDefault();
        const id = $("#input-view-id").val();
        const name = $("#input-view-name").val().trim();
        const description = $("#input-view-description").val().trim();
        const sql = $("#input-view-sql").val().trim();

        if (!name) {
            showToast("Missing Name", "Please provide a name for the custom view.", "warning");
            return;
        }
        if (!sql) {
            showToast("Missing Query", "Please provide a query for the custom view.", "warning");
            return;
        }

        $("#btn-confirm-save-view").addClass("loading disabled");
        try {
            if (id) {
                const updated = await apiRequest(`/api/views/${encodeURIComponent(id)}`, {
                    method: "PUT",
                    body: JSON.stringify({ name: name, sql: sql, description: description }),
                });
                showToast("View Updated", `Custom view "${updated.name}" updated successfully.`, "success");
                $("#modal-custom-view").modal("hide");
                await loadViewsList();
                if (state.activeView && state.activeView.id === id) {
                    selectActiveView(id);
                }
            } else {
                const created = await apiRequest("/api/views", {
                    method: "POST",
                    body: JSON.stringify({ name: name, sql: sql, description: description }),
                });
                showToast("View Created", `Custom view "${created.name}" created successfully.`, "success");
                $("#modal-custom-view").modal("hide");
                await loadViewsList();
                selectActiveView(created.id);
            }
        } catch (err) {
            showToast("Error saving view", err.message, "error");
        } finally {
            $("#btn-confirm-save-view").removeClass("loading disabled");
        }
    });

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
