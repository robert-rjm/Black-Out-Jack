"""Tests for GET /room_invite (join link + QR code SVG)."""

import pytest

from app import create_app
import app.routes.lobby as lobby


@pytest.fixture
def client():
    return create_app().test_client()


def test_invite_returns_a_join_link_and_an_svg_qr(client):
    data = client.get("/room_invite?code=Ace12").get_json()
    assert data["ok"] is True and data["code"] == "Ace12"
    assert data["url"].endswith("/?room=Ace12")
    assert data["svg"].startswith("<svg") and "</svg>" in data["svg"]


@pytest.mark.parametrize("bad", ["", "a b", "x" * 25, "Ace-12", "<script>"])
def test_invalid_codes_are_rejected(client, bad):
    resp = client.get("/room_invite", query_string={"code": bad})
    assert resp.status_code == 400 and resp.get_json()["ok"] is False


def test_localhost_is_replaced_by_the_lan_address(client, monkeypatch):
    monkeypatch.setattr(lobby, "_lan_ip", lambda: "192.168.0.9")
    data = client.get("/room_invite?code=Ace12", base_url="http://localhost:5000").get_json()
    assert data["url"] == "http://192.168.0.9:5000/?room=Ace12"


def test_localhost_stays_when_no_lan_address_is_found(client, monkeypatch):
    monkeypatch.setattr(lobby, "_lan_ip", lambda: None)
    data = client.get("/room_invite?code=Ace12", base_url="http://localhost:5000").get_json()
    assert data["url"] == "http://localhost:5000/?room=Ace12"


def test_a_real_host_is_used_as_is(client):
    data = client.get("/room_invite?code=Ace12", base_url="http://game.example.com").get_json()
    assert data["url"] == "http://game.example.com/?room=Ace12"


def test_proxy_headers_give_the_public_https_url(client):
    data = client.get(
        "/room_invite?code=Ace12",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "jack.onrender.com"},
    ).get_json()
    assert data["url"] == "https://jack.onrender.com/?room=Ace12"


def test_it_does_not_reveal_whether_a_room_exists(client):
    """Same shape for a code that was never created as for a real one."""
    a = client.get("/room_invite?code=Nope999").get_json()
    assert a["ok"] is True and a["svg"].startswith("<svg")


def test_beer_route_redirects_to_paypal(client):
    resp = client.get("/beer")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://paypal.me/")


def test_beer_qr_returns_svg_for_paypal_link(client):
    data = client.get("/beer_qr").get_json()
    assert data["ok"] and data["url"].startswith("https://paypal.me/")
    assert "<svg" in data["svg"] and "viewBox" in data["svg"]
