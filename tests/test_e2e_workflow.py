"""End-to-end (E2E) integration test for vg-data-visor."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def e2e_db_path():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_complete_e2e_lifecycle(e2e_db_path):
    # ================= STEP 1: Create a database from scratch =================
    res_create = client.post("/api/connection/create", json={"path": e2e_db_path})
    assert res_create.status_code == 200
    info = res_create.json()
    assert info["connected"] is True
    assert info["path"] == e2e_db_path
    assert os.path.exists(e2e_db_path)

    # Check that it initially has no tables
    tables_initial = client.get("/api/tables").json()
    assert len(tables_initial) == 0

    # ================= STEP 2: DDL - Create table 'customers' =================
    res_tbl_customers = client.post(
        "/api/tables/create",
        json={
            "name": "customers",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "name", "type": "TEXT", "not_null": True},
                {"name": "city", "type": "TEXT", "not_null": False, "default_value": "'Madrid'"},
            ],
        },
    )
    assert res_tbl_customers.status_code == 200

    # ================= STEP 3: DDL - Create table 'sales' =================
    res_tbl_sales = client.post(
        "/api/tables/create",
        json={
            "name": "sales",
            "columns": [
                {"name": "id", "type": "INTEGER", "is_pk": True, "auto_increment": True},
                {"name": "customer_id", "type": "INTEGER", "not_null": True},
                {"name": "amount", "type": "REAL", "not_null": True},
            ],
        },
    )
    assert res_tbl_sales.status_code == 200

    # Verify that the catalog lists both tables
    tables_list = client.get("/api/tables").json()
    table_names = [t["name"] for t in tables_list]
    assert "customers" in table_names
    assert "sales" in table_names

    # ================= STEP 4: DDL - Alter table (add column) =================
    res_alter = client.post(
        "/api/tables/sales/alter",
        json={"column": {"name": "status", "type": "TEXT", "default_value": "'completed'"}},
    )
    assert res_alter.status_code == 200

    schema_sales = client.get("/api/tables/sales/schema").json()
    col_names_sales = [c["name"] for c in schema_sales["columns"]]
    assert "status" in col_names_sales

    # ================= STEP 5: DML - Inserting records =================
    res_c1 = client.post("/api/tables/customers/records", json={"values": {"name": "Alice", "city": "Barcelona"}})
    assert res_c1.status_code == 200

    res_c2 = client.post("/api/tables/customers/records", json={"values": {"name": "Bernard", "city": "Seville"}})
    assert res_c2.status_code == 200

    res_c3 = client.post("/api/tables/customers/records", json={"values": {"name": "Charles", "city": "Valencia"}})
    assert res_c3.status_code == 200

    # Associated sales
    client.post("/api/tables/sales/records", json={"values": {"customer_id": 1, "amount": 150.0}})
    client.post("/api/tables/sales/records", json={"values": {"customer_id": 1, "amount": 75.5}})
    client.post("/api/tables/sales/records", json={"values": {"customer_id": 2, "amount": 200.0}})

    # ================= STEP 6: DML - Pagination, sorting, and search =================
    # Search
    search_res = client.get("/api/tables/customers/records?search=Bernard").json()
    assert search_res["total"] == 1
    assert search_res["records"][0]["name"] == "Bernard"

    # Descending sort
    sort_res = client.get("/api/tables/customers/records?sort_by=name&sort_dir=desc").json()
    assert sort_res["records"][0]["name"] == "Charles"

    # ================= STEP 7: DML - Update =================
    upd_res = client.put(
        "/api/tables/customers/records",
        json={"pk_values": {"id": 1}, "values": {"city": "Girona"}},
    )
    assert upd_res.status_code == 200

    verify_c1 = client.get("/api/tables/customers/records?search=Alice").json()
    assert verify_c1["records"][0]["city"] == "Girona"

    # ================= STEP 8: SQL Console - Complex JOIN and aggregation query =================
    query_complex = """
        SELECT 
            c.name, 
            COUNT(s.id) as num_sales, 
            SUM(s.amount) as total_spent
        FROM customers c
        JOIN sales s ON c.id = s.customer_id
        GROUP BY c.id, c.name
        ORDER BY total_spent DESC;
    """
    res_sql = client.post("/api/query", json={"query": query_complex})
    assert res_sql.status_code == 200
    sql_data = res_sql.json()
    assert sql_data["row_count"] == 2
    # Alice (150 + 75.5 = 225.5) and Bernard (200.0)
    assert sql_data["rows"][0]["name"] == "Alice"
    assert sql_data["rows"][0]["total_spent"] == 225.5
    assert sql_data["rows"][1]["name"] == "Bernard"
    assert sql_data["rows"][1]["total_spent"] == 200.0

    # ================= STEP 9: DML - Deleting a record =================
    del_res = client.post("/api/tables/customers/records/delete", json={"pk_values": {"id": 3}})
    assert del_res.status_code == 200

    after_del = client.get("/api/tables/customers/records").json()
    assert after_del["total"] == 2

    # ================= STEP 10: DDL - Drop table (DROP) =================
    drop_res = client.delete("/api/tables/sales/drop")
    assert drop_res.status_code == 200

    final_tables = client.get("/api/tables").json()
    assert len(final_tables) == 1
    assert final_tables[0]["name"] == "customers"

    # ================= STEP 11: Disconnect and reconnect to an existing file =================
    client.post("/api/connection/close")
    assert client.get("/api/connection/status").json()["connected"] is False

    reconnect_res = client.post("/api/connection/open", json={"path": e2e_db_path})
    assert reconnect_res.status_code == 200
    assert reconnect_res.json()["connected"] is True

    reconnect_tables = client.get("/api/tables").json()
    assert len(reconnect_tables) == 1
    assert reconnect_tables[0]["name"] == "customers"

    # ================= STEP 12: Custom Views Lifecycle =================
    # Create a custom view
    view_res = client.post(
        "/api/views",
        json={
            "name": "Girona Customers",
            "sql": "SELECT id, name, city FROM customers WHERE city = 'Girona'",
            "description": "Customers based in Girona",
        },
    )
    assert view_res.status_code == 201
    view_id = view_res.json()["id"]

    # Retrieve records through view endpoint
    rec_res = client.get(f"/api/views/{view_id}/records")
    assert rec_res.status_code == 200
    rec_json = rec_res.json()
    assert rec_json["total"] == 1
    assert rec_json["records"][0]["name"] == "Alice"

    # Cleanup view & close connection
    assert client.delete(f"/api/views/{view_id}").status_code == 200
    client.post("/api/connection/close")
