"""End-to-end tests for the wheel API, auth, and rig behavior."""

import re

import pytest
from fastapi.testclient import TestClient

from app import database as db
from app.main import create_app

NAMES = ["Ava", "Liam", "Sofia", "Noah", "Mia"]


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient backed by a fresh, temporary SQLite database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    return TestClient(create_app())


@pytest.fixture()
def wheel(client: TestClient) -> str:
    """Create a wheel and return its code. The client is logged in as admin."""
    res = client.post(
        "/wheels",
        data={"title": "Test Class", "password": "hunter2", "names": "\n".join(NAMES)},
        follow_redirects=False,
    )
    assert res.status_code == 303
    match = re.search(r"/w/([^/]+)/admin", res.headers["location"])
    assert match
    return match.group(1)


def spin(client: TestClient, code: str) -> dict:
    """Spin a wheel and return the JSON result."""
    res = client.post(f"/w/{code}/api/spin")
    assert res.status_code == 200
    return res.json()


def test_create_wheel_requires_two_names(client: TestClient) -> None:
    """A wheel with fewer than 2 names is rejected."""
    res = client.post(
        "/wheels",
        data={"title": "Tiny", "password": "hunter2", "names": "OnlyOne"},
    )
    assert res.status_code == 400


def test_wheel_page_and_data_are_public(client: TestClient, wheel: str) -> None:
    """The class-facing pages need no authentication."""
    anonymous = TestClient(client.app)
    assert anonymous.get(f"/w/{wheel}").status_code == 200
    data = anonymous.get(f"/w/{wheel}/api/wheel").json()
    assert data["title"] == "Test Class"
    assert data["names"] == NAMES


def test_admin_requires_login(client: TestClient, wheel: str) -> None:
    """Admin APIs reject unauthenticated requests."""
    anonymous = TestClient(client.app)
    page = anonymous.get(f"/w/{wheel}/admin")
    assert page.status_code == 200
    assert 'type="password"' in page.text  # shows login form, not the panel
    assert anonymous.post(f"/w/{wheel}/admin/rig", json={"rig_index": 0, "mode": "once"}).status_code == 403
    assert anonymous.post(
        f"/w/{wheel}/admin/content", json={"title": "X", "names": NAMES}
    ).status_code == 403


def test_wrong_password_rejected(client: TestClient, wheel: str) -> None:
    """A bad admin password does not authenticate."""
    anonymous = TestClient(client.app)
    res = anonymous.post(
        f"/w/{wheel}/admin/login", data={"password": "wrong"}, follow_redirects=False
    )
    assert res.status_code == 303
    assert "error=1" in res.headers["location"]
    assert anonymous.post(f"/w/{wheel}/admin/rig", json={"rig_index": 0}).status_code == 403


def test_correct_password_authenticates(client: TestClient, wheel: str) -> None:
    """The wheel password grants admin access."""
    anonymous = TestClient(client.app)
    anonymous.post(f"/w/{wheel}/admin/login", data={"password": "hunter2"})
    assert anonymous.post(f"/w/{wheel}/admin/rig", json={"rig_index": 0}).status_code == 200


def test_random_spin_stays_in_range(client: TestClient, wheel: str) -> None:
    """Unrigged spins always return a valid index and matching name."""
    for _ in range(25):
        result = spin(client, wheel)
        assert 0 <= result["winner_index"] < len(NAMES)
        assert result["winner_name"] == NAMES[result["winner_index"]]


def test_rig_once_lands_then_clears(client: TestClient, wheel: str) -> None:
    """A 'once' rig forces the next spin, then resets to random."""
    client.post(f"/w/{wheel}/admin/rig", json={"rig_index": 2, "mode": "once"})
    result = spin(client, wheel)
    assert result["winner_index"] == 2
    assert result["winner_name"] == "Sofia"
    # rig must be gone now — many spins should hit someone else
    assert any(spin(client, wheel)["winner_index"] != 2 for _ in range(30))


def test_rig_sticky_persists(client: TestClient, wheel: str) -> None:
    """A 'sticky' rig forces every spin until cleared."""
    client.post(f"/w/{wheel}/admin/rig", json={"rig_index": 4, "mode": "sticky"})
    for _ in range(10):
        assert spin(client, wheel)["winner_index"] == 4
    client.post(f"/w/{wheel}/admin/rig", json={"rig_index": None})
    assert any(spin(client, wheel)["winner_index"] != 4 for _ in range(30))


def test_rig_index_out_of_range_rejected(client: TestClient, wheel: str) -> None:
    """Rigging a nonexistent name index is a 400."""
    assert client.post(f"/w/{wheel}/admin/rig", json={"rig_index": 99}).status_code == 400


def test_updating_content_clears_rig(client: TestClient, wheel: str) -> None:
    """Editing the name list invalidates any rigged outcome."""
    client.post(f"/w/{wheel}/admin/rig", json={"rig_index": 0, "mode": "sticky"})
    res = client.post(
        f"/w/{wheel}/admin/content",
        json={"title": "New Title", "names": ["Zed", "Yara", "Xander"]},
    )
    assert res.status_code == 200
    stored = db.get_wheel(wheel)
    assert stored["rig_index"] is None
    assert db.wheel_names(stored) == ["Zed", "Yara", "Xander"]


def test_spin_unknown_wheel_is_404(client: TestClient) -> None:
    """Spinning a nonexistent wheel returns 404."""
    assert client.post("/w/nope/api/spin").status_code == 404


def test_wheel_codes_are_unique(client: TestClient) -> None:
    """Many wheels can coexist with distinct codes."""
    codes = set()
    for i in range(5):
        c = TestClient(client.app)
        res = c.post(
            "/wheels",
            data={"title": f"Class {i}", "password": "pass1234", "names": "A\nB\nC"},
            follow_redirects=False,
        )
        codes.add(re.search(r"/w/([^/]+)/admin", res.headers["location"]).group(1))
    assert len(codes) == 5
