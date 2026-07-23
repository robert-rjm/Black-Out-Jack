"""
Tests for the profanity filter (app/services/validators.py's
is_offensive_name, built on better-profanity) and its three real
entry points: POST /setup (lobby.py), POST /update_settings's
add_player branch, and POST /request_rejoin (both admin.py).

Every other sanitize_name() call site in the app only matches an
already-existing player/seat name and doesn't need this check -- see the
call-site audit behind this feature.
"""

import pytest

from app import create_app
from app.services.validators import is_offensive_name


# ---------------------------------------------------------------------------
# is_offensive_name -- direct unit tests
# ---------------------------------------------------------------------------

def test_clean_name_not_flagged():
    assert is_offensive_name("Bob") is False
    assert is_offensive_name("Alice") is False


def test_empty_name_not_flagged():
    assert is_offensive_name("") is False


def test_profane_name_flagged():
    assert is_offensive_name("Fuck") is True


def test_leetspeak_profanity_flagged():
    assert is_offensive_name("Sh1t") is True


def test_word_boundary_false_positive_avoided():
    # The classic "Scunthorpe problem" -- better-profanity matches whole
    # words, not raw substrings, so a legitimate name isn't caught just
    # because it contains a profane substring.
    assert is_offensive_name("Scunthorpe") is False
    assert is_offensive_name("Assassin") is False


# ---------------------------------------------------------------------------
# Flask app + route fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def _create_room(client):
    resp = client.post("/create_room", json={})
    return resp.get_json()["code"]


# ---------------------------------------------------------------------------
# POST /setup
# ---------------------------------------------------------------------------

def test_setup_rejects_offensive_player_name(client):
    room_code = _create_room(client)
    resp = client.post("/setup", json={
        "room_code": room_code, "client_id": "c1",
        "players": ["Alice", "Fuck"],
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "Fuck" in data["error"]


def test_setup_accepts_clean_player_names(client):
    room_code = _create_room(client)
    resp = client.post("/setup", json={
        "room_code": room_code, "client_id": "c1",
        "players": ["Alice", "Bob"],
    })
    data = resp.get_json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# POST /update_settings (add_player branch)
# ---------------------------------------------------------------------------

def test_update_settings_rejects_offensive_add_player(client):
    room_code = _create_room(client)
    client.post("/setup", json={
        "room_code": room_code, "client_id": "c1", "players": ["Alice", "Bob"],
    })
    resp = client.post("/update_settings", json={
        "room_code": room_code, "client_id": "c1", "add_player": "Fuck",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "Fuck" in data["error"]


def test_update_settings_accepts_clean_add_player(client):
    room_code = _create_room(client)
    client.post("/setup", json={
        "room_code": room_code, "client_id": "c1", "players": ["Alice", "Bob"],
    })
    resp = client.post("/update_settings", json={
        "room_code": room_code, "client_id": "c1", "add_player": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# POST /request_rejoin
# ---------------------------------------------------------------------------

def test_request_rejoin_falls_back_to_unknown_for_offensive_name(client):
    room_code = _create_room(client)
    client.post("/setup", json={
        "room_code": room_code, "client_id": "c1", "players": ["Alice", "Bob"],
    })
    # c1 (the admin) is already registered and not kicked -- /request_rejoin
    # only requires an existing, non-kicked client entry, so it's a valid
    # (if unusual) caller for exercising the display_name fallback path.
    resp = client.post("/request_rejoin", json={
        "room_code": room_code, "client_id": "c1", "display_name": "Fuck",
    })
    data = resp.get_json()
    assert data["ok"] is True   # never a hard rejection -- just relabeled
    rejoin_requests = data.get("rejoin_requests") or []
    assert any(r.get("display_name") == "Unknown" for r in rejoin_requests)
    assert not any(r.get("display_name") == "Fuck" for r in rejoin_requests)
