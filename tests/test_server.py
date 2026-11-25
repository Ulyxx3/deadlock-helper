"""Integration tests for the FastAPI HTTP & WebSocket companion server."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.config.settings import AppSettings, DEFAULT_ITEM_ICONS_DIR
from backend.server.app import create_app


def test_server_state_player_websocket_and_reset(tmp_path: Path) -> None:
    settings = AppSettings(user_profile_path=tmp_path / "user_profile.json")
    app = create_app(
        enable_live_listener=False,
        initial_pseudo="Ulyxx3",
        frontend_dist=tmp_path / "missing_dist",
        settings=settings,
    )

    with TestClient(app) as client:
        res = client.get("/api/state")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "waiting_for_tab"
        assert data["player_pseudo"] == "Ulyxx3"

        with client.websocket_connect("/ws") as ws:
            ws_msg = ws.receive_json()
            assert ws_msg["status"] == "waiting_for_tab"
            assert ws_msg["player_pseudo"] == "Ulyxx3"

        upd = client.post("/api/player", json={"player_name": "NewPseudo"})
        assert upd.status_code == 200
        assert upd.json()["player_pseudo"] == "NewPseudo"

        rst = client.post("/api/reset-match")
        assert rst.status_code == 200
        assert rst.json()["status"] == "waiting_for_tab"


def test_server_test_image_endpoint_on_real_screenshot(tmp_path: Path) -> None:
    sample_path = Path("images/image.png")
    if not sample_path.exists() or not (DEFAULT_ITEM_ICONS_DIR / "manifest.json").exists():
        return

    settings = AppSettings(user_profile_path=tmp_path / "user_profile.json")
    app = create_app(
        enable_live_listener=False,
        initial_pseudo="Ulyxx3",
        settings=settings,
    )

    with TestClient(app) as client:
        res = client.post("/api/test-image", json={"image_path": str(sample_path)})
        assert res.status_code == 200
        snap = res.json()
        assert snap["status"] == "ready"
        assert snap["self_is_dead"] is False
        assert snap["build_balance"] is not None
        assert snap["build_balance"]["weapon_count"] >= 1
        assert snap["match_timer_display"] == "27:53"
        assert snap["self_player"] is not None
        assert snap["self_player"]["hero_name"] == "Vindicta"
        assert len(snap["self_player"]["items"]) == 9

        core_items = snap["sections"]["Items Core"]
        assert len(core_items) > 0
        all_items = [i for sec_items in snap["sections"].values() for i in sec_items]
        battle_vest = [i for i in all_items if i["item_name"] == "Battle Vest"]
        assert battle_vest and battle_vest[0]["already_owned"] is True
        assert battle_vest[0]["icon_url"].startswith("/icons/")

        # Every recommended item across all sections must have a real icon and FR/EN localization
        assert len(snap["sections"]["Priorité absolue"]) >= 1
        for section_items in snap["sections"].values():
            for item in section_items:
                assert item["icon_url"] and item["icon_url"].startswith("/icons/"), f"Missing icon for {item['item_name']}"
                assert item.get("item_name_fr")
                assert item.get("reason_en")
                assert item.get("upgrade_status") in {"new", "upgrade_ready", "owned", "evolved"}

        # Pin custom lane opponents and verify Matchup direct updates
        pin_res = client.post("/api/lane-opponents", json={"heroes": ["Pocket", "Lady Geist"]})
        assert pin_res.status_code == 200
        pin_snap = pin_res.json()
        assert pin_snap["pinned_lane_opponents"] == ["Pocket", "Lady Geist"]
        assert len(pin_snap["sections"]["Matchup direct"]) >= 1
