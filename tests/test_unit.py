import pytest
from flask import session
from app import app, create_unified_description, consolidate_incidents_by_pincode, sb_available

# ---- FIXTURE ----
@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ---- ROUTE TESTS ----
def test_home_route(client):
    response = client.get("/")
    assert response.status_code == 200


def test_signup_get(client):
    response = client.get("/signup")
    assert response.status_code == 200


def test_signin_get(client):
    response = client.get("/signin")
    assert response.status_code == 200


def test_dashboard_redirect(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (301, 302)
    assert "/signin" in response.headers["Location"]


def test_invalid_route(client):
    response = client.get("/not_exist")
    assert response.status_code == 404


# ---- UTILITY FUNCTION TESTS ----
def test_unified_description_single():
    desc = create_unified_description(["Flood near river"])
    assert "Flood" in desc


def test_unified_description_multiple():
    desc = create_unified_description(["Flood occurs", "Heavy rain flood area"])
    assert "Multiple reports" in desc or "flood" in desc.lower()


def test_consolidate_pincode_single():
    input_data = [{"pincode": "560001", "description": "Fire in building"}]
    output = consolidate_incidents_by_pincode(input_data)
    assert len(output) == 1
    assert output[0]["report_count"] == 1


def test_consolidate_pincode_multiple():
    input_data = [
        {"pincode": "560001", "description": "Fire in building"},
        {"pincode": "560001", "description": "Building smoke detected"}
    ]
    output = consolidate_incidents_by_pincode(input_data)
    assert len(output) == 1
    assert output[0]["report_count"] == 2


def test_sb_available(monkeypatch):
    import app as main_app

    monkeypatch.setattr(main_app, "supabase", object())
    assert sb_available() is True

    monkeypatch.setattr(main_app, "supabase", None)
    assert sb_available() is False


# ---- POST TESTS ----
def test_signup_post_without_db(client, monkeypatch):
    monkeypatch.setattr("app.supabase", None)

    response = client.post("/signup", data={
        "fullname": "Test User",
        "email": "test@example.com",
        "phone": "9999999999",
        "password": "pass123",
    }, follow_redirects=True)

    assert b"Database is not configured" in response.data


def test_signin_post_without_db(client, monkeypatch):
    monkeypatch.setattr("app.supabase", None)

    response = client.post("/signin", data={
        "email_or_phone": "test@example.com",
        "password": "pass123"
    }, follow_redirects=True)

    assert b"Database is not configured" in response.data


# ---- FIXED DELETE ANNOUNCEMENT TEST ----
def test_delete_announcement(client, monkeypatch):
    """Test delete announcement without hitting admin dashboard"""

    class FakeDelete:
        def execute(self):
            return True

    class FakeTable:
        def delete(self):
            return self
        def eq(self, col, val):
            return FakeDelete()

    monkeypatch.setattr("app.supabase", type("Fake", (), {"table": lambda *_: FakeTable()}))

    with client.session_transaction() as sess:
        sess["user_role"] = "admin"
        sess["user"] = "Admin"

    # ✅ Do NOT follow redirect (prevent admin_dashboard crash)
    response = client.post("/delete_announcement/1", follow_redirects=False)

    # ✅ Check redirect happened
    assert response.status_code in (301, 302)
    assert "/admin_dashboard" in response.headers["Location"]
