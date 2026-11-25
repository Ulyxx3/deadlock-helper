"""FastAPI HTTP & WebSocket server pushing live TAB scoreboard snapshots to the UI."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.capture.tab_listener import TabScoreboardListener
from backend.config.settings import (
    DEFAULT_ITEM_ICONS_DIR,
    PROJECT_ROOT,
    AppSettings,
    load_user_pseudo,
    save_user_pseudo,
)
from backend.engine.recommender import RecommendationEngine
from backend.meta.deadlock_api_client import DeadlockApiClient
from backend.models.game_state import MatchState, RecommendationSection, Team
from backend.ocr.item_matcher import ItemMatcher
from backend.ocr.souls_tracker import OcrSoulsTracker

DEFAULT_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
DEFAULT_TEST_IMAGE = PROJECT_ROOT / "images" / "image.png"


class PlayerUpdateRequest(BaseModel):
    """Payload to set or update the local player's in-game pseudo."""

    player_name: str


class LaneOpponentsRequest(BaseModel):
    """Payload to pin/unpin direct lane enemy heroes from the UI."""

    heroes: list[str]


class TestImageRequest(BaseModel):
    """Optional image path override for offline testing from the UI."""

    image_path: str | None = None


def build_icon_lookup(icons_dir: Path = DEFAULT_ITEM_ICONS_DIR) -> dict[str, str]:
    """Build normalized item_name -> /icons/<filename> URL lookup from manifest.json."""
    manifest_path = icons_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest: dict[str, dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    lookup: dict[str, str] = {}
    for entry in manifest.values():
        name = str(entry.get("name", "")).strip().lower()
        filename = str(entry.get("filename", "")).strip()
        if name and filename and (icons_dir / filename).exists():
            lookup[name] = f"/icons/{filename}"
    return lookup


def _format_timer_display(match_minutes: float) -> str:
    total_seconds = max(0, int(round(match_minutes * 60)))
    mins, secs = divmod(total_seconds, 60)
    return f"{mins:02d}:{secs:02d}"


def build_snapshot(
    match_state: MatchState | None,
    player_pseudo: str | None,
    live_enabled: bool,
    api_client: DeadlockApiClient,
    engine: RecommendationEngine,
    icon_lookup: dict[str, str],
    fr_names: dict[str, str] | None = None,
    upgrade_graph: dict[str, Any] | None = None,
    pinned_lane_opponents: list[str] | None = None,
    source: str = "idle",
) -> dict[str, Any]:
    """Serialize MatchState + Snowball + Upgrades + Recommendations into the UI JSON contract."""
    empty_sections = {sec.value: [] for sec in RecommendationSection}
    fr_map = fr_names or {}
    pinned_lanes = list(pinned_lane_opponents or [])

    if match_state is None or not match_state.players:
        return {
            "status": "waiting_for_tab",
            "source": source,
            "live_enabled": live_enabled,
            "player_pseudo": player_pseudo,
            "pinned_lane_opponents": pinned_lanes,
            "inventory_slots_used": 0,
            "inventory_slots_max": 12,
            "updated_at": time.time(),
            "match_minutes": 0.0,
            "match_timer_display": "00:00",
            "lane_status": "even",
            "team_totals": {"amber_hand": 0, "sapphire_flame": 0},
            "self_player": None,
            "players": [],
            "snowball_reports": [],
            "sections": empty_sections,
        }

    amber_total = sum(p.souls for p in match_state.players if p.team == Team.AMBER_HAND)
    sapphire_total = sum(p.souls for p in match_state.players if p.team == Team.SAPPHIRE_FLAME)

    def _item_obj(name: str) -> dict[str, Any]:
        key = name.strip().lower()
        return {
            "name": name,
            "name_fr": fr_map.get(key, name),
            "icon_url": icon_lookup.get(key),
        }

    me = match_state.self_player
    self_payload = None
    if me is not None:
        self_payload = {
            "slot_index": me.slot_index,
            "hero_name": me.hero_name,
            "player_name": me.player_name,
            "team": me.team.value,
            "souls": me.souls,
            "items": [_item_obj(name) for name in me.items],
        }

    players_payload = [
        {
            "slot_index": p.slot_index,
            "team": p.team.value,
            "hero_name": p.hero_name,
            "player_name": p.player_name,
            "souls": p.souls,
            "is_self": p.is_self,
            "items": [_item_obj(name) for name in p.items],
        }
        for p in match_state.players
    ]

    lane_status_str = "even"
    snowball_payload: list[dict[str, Any]] = []
    sections_payload: dict[str, list[dict[str, Any]]] = {sec.value: [] for sec in RecommendationSection}

    if me is not None:
        lane_arg = pinned_lanes if pinned_lanes else None
        lane_status, _, resolved_lane_opponents = engine.evaluate_lane_status(
            match_state, lane_opponent_heroes=lane_arg
        )
        lane_status_str = lane_status.value
        if not pinned_lanes and resolved_lane_opponents:
            pinned_lanes = [o.hero_name for o in resolved_lane_opponents]

        reports = engine.compute_snowball_reports(match_state)
        snowball_payload = [
            {
                "hero_name": r.hero_name,
                "souls": r.souls,
                "souls_gap_vs_avg": r.souls_gap_vs_avg,
                "snowball_score": r.snowball_score,
                "is_fed": r.is_fed,
                "key_items": r.key_items,
            }
            for r in reports
        ]
        core_build = api_client.get_default_core_build(me.hero_name, max_items=24)
        recs = engine.recommend(
            match_state,
            default_core_build=core_build,
            upgrade_graph=upgrade_graph,
            lane_opponent_heroes=lane_arg,
        )
        for rec in recs:
            key = rec.item_name.strip().lower()
            from_fr = (
                fr_map.get(rec.upgrades_from_owned.strip().lower(), rec.upgrades_from_owned)
                if rec.upgrades_from_owned
                else None
            )
            sections_payload[rec.section.value].append({
                "item_name": rec.item_name,
                "item_name_fr": fr_map.get(key, rec.item_name),
                "category": rec.category,
                "cost": rec.cost,
                "net_cost": rec.net_cost if rec.net_cost is not None else rec.cost,
                "reason": rec.reason,
                "reason_en": rec.reason_en or rec.reason,
                "priority": rec.priority,
                "already_owned": rec.already_owned,
                "upgrade_status": rec.upgrade_status,
                "upgrades_from_owned": rec.upgrades_from_owned,
                "upgrades_from_owned_fr": from_fr,
                "target_heroes": rec.target_heroes,
                "icon_url": icon_lookup.get(key),
            })

    return {
        "status": "ready",
        "source": source,
        "live_enabled": live_enabled,
        "player_pseudo": player_pseudo,
        "pinned_lane_opponents": pinned_lanes,
        "inventory_slots_used": len(me.items) if me else 0,
        "inventory_slots_max": 12,
        "updated_at": time.time(),
        "match_minutes": match_state.match_minutes,
        "match_timer_display": _format_timer_display(match_state.match_minutes),
        "lane_status": lane_status_str,
        "team_totals": {"amber_hand": amber_total, "sapphire_flame": sapphire_total},
        "self_player": self_payload,
        "players": players_payload,
        "snowball_reports": snowball_payload,
        "sections": sections_payload,
    }


class CompanionServerState:
    """Thread-safe coordinator between TAB screen capture, FastAPI endpoints, and WebSockets."""

    def __init__(
        self,
        enable_live_listener: bool = False,
        initial_pseudo: str | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.settings = settings or AppSettings()
        self.enable_live_listener = enable_live_listener
        self.player_pseudo = initial_pseudo or load_user_pseudo(self.settings.user_profile_path)
        self.api_client = DeadlockApiClient(cache_dir=self.settings.cache_dir)
        self.engine = RecommendationEngine(rules_path=self.settings.rules_path, settings=self.settings)
        self.icon_lookup = build_icon_lookup(self.settings.item_icons_dir)
        self.fr_names = self.api_client.get_item_names_fr()
        self.upgrade_graph = self.api_client.get_upgrade_graph()
        self.tracker = OcrSoulsTracker(
            settings=self.settings,
            item_matcher=ItemMatcher(self.settings.item_icons_dir),
        )

        self._lock = threading.Lock()
        self._last_match_state: MatchState | None = None
        self._last_source: str = "idle"
        self._last_image_path: Path | None = None
        self.pinned_lane_opponents: list[str] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listener: TabScoreboardListener | None = None
        self.clients: set[WebSocket] = set()
        self.latest_snapshot: dict[str, Any] = self._build_current_snapshot(None, source="idle")

    def _build_current_snapshot(self, match_state: MatchState | None, source: str) -> dict[str, Any]:
        return build_snapshot(
            match_state=match_state,
            player_pseudo=self.player_pseudo,
            live_enabled=self.enable_live_listener,
            api_client=self.api_client,
            engine=self.engine,
            icon_lookup=self.icon_lookup,
            fr_names=self.fr_names,
            upgrade_graph=self.upgrade_graph,
            pinned_lane_opponents=self.pinned_lane_opponents,
            source=source,
        )

    async def broadcast_snapshot(self, snapshot: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(snapshot)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def _schedule_broadcast(self, snapshot: dict[str, Any]) -> None:
        if self._loop is not None and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.broadcast_snapshot(snapshot), self._loop)

    def analyze_image(self, image_path: Path) -> dict[str, Any]:
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise FileNotFoundError(f"Impossible de lire l'image : {image_path}")
        with self._lock:
            self._last_image_path = image_path
            self.tracker.reset_match()
            match_state = self.tracker.extract_match_state(frame, player_pseudo=self.player_pseudo)
            self._last_match_state = match_state
            self._last_source = "test_image"
            snapshot = self._build_current_snapshot(match_state, source="test_image")
            self.latest_snapshot = snapshot
        return snapshot

    def set_player_pseudo(self, pseudo: str) -> dict[str, Any]:
        cleaned = pseudo.strip()
        with self._lock:
            self.player_pseudo = cleaned or None
            if cleaned:
                save_user_pseudo(cleaned, self.settings.user_profile_path)
            if self._last_image_path is not None and self._last_image_path.exists():
                frame = cv2.imread(str(self._last_image_path))
                if frame is not None:
                    self.tracker.reset_match()
                    match_state = self.tracker.extract_match_state(frame, player_pseudo=self.player_pseudo)
                    self._last_match_state = match_state
                    self._last_source = "test_image"
                    self.latest_snapshot = self._build_current_snapshot(match_state, source="test_image")
                    return self.latest_snapshot
            self.latest_snapshot = {**self.latest_snapshot, "player_pseudo": self.player_pseudo, "updated_at": time.time()}
            return self.latest_snapshot

    def set_lane_opponents(self, heroes: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pinned_lane_opponents = [h.strip() for h in heroes if h.strip()]
            self.latest_snapshot = self._build_current_snapshot(
                self._last_match_state, source=self._last_source
            )
            return self.latest_snapshot

    def reset_match(self) -> dict[str, Any]:
        with self._lock:
            self._last_image_path = None
            self._last_match_state = None
            self._last_source = "idle"
            self.pinned_lane_opponents = []
            self.tracker.reset_match()
            self.latest_snapshot = self._build_current_snapshot(None, source="idle")
            return self.latest_snapshot

    def _handle_tab_capture(self) -> None:
        with self._lock:
            self._last_image_path = None
            match_state = self.tracker.poll_match_state(player_pseudo=self.player_pseudo)
            self._last_match_state = match_state
            self._last_source = "live_tab"
            snapshot = self._build_current_snapshot(match_state, source="live_tab")
            self.latest_snapshot = snapshot
        self._schedule_broadcast(snapshot)

    def start_background_listener(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if not self.enable_live_listener:
            return
        _ = self.tracker.ocr_backend
        _ = self.tracker.hero_matcher
        _ = self.tracker.item_matcher

        self._listener = TabScoreboardListener(
            on_scoreboard_visible=self._handle_tab_capture,
            settle_delay_ms=self.settings.tab_settle_delay_ms,
            min_interval_s=self.settings.tab_min_interval_s,
            hold_poll_interval_s=self.settings.tab_hold_poll_interval_s,
        )
        self._listener.start()

    def stop_background_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def create_app(
    enable_live_listener: bool = False,
    initial_pseudo: str | None = None,
    frontend_dist: Path | None = None,
    settings: AppSettings | None = None,
) -> FastAPI:
    """Create the Deadlock Helper FastAPI + WebSocket application."""
    app_settings = settings or AppSettings()
    state = CompanionServerState(
        enable_live_listener=enable_live_listener,
        initial_pseudo=initial_pseudo,
        settings=app_settings,
    )
    dist_dir = frontend_dist or DEFAULT_FRONTEND_DIST

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state.start_background_listener(asyncio.get_running_loop())
        try:
            yield
        finally:
            state.stop_background_listener()

    app = FastAPI(title="Deadlock Helper Companion API", lifespan=lifespan)
    app.state.companion = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8765", "http://127.0.0.1:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if app_settings.item_icons_dir.exists():
        app.mount("/icons", StaticFiles(directory=str(app_settings.item_icons_dir)), name="icons")

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        return state.latest_snapshot

    @app.post("/api/player")
    async def update_player(payload: PlayerUpdateRequest) -> dict[str, Any]:
        snapshot = state.set_player_pseudo(payload.player_name)
        await state.broadcast_snapshot(snapshot)
        return snapshot

    @app.post("/api/lane-opponents")
    async def update_lane_opponents(payload: LaneOpponentsRequest) -> dict[str, Any]:
        snapshot = state.set_lane_opponents(payload.heroes)
        await state.broadcast_snapshot(snapshot)
        return snapshot

    @app.post("/api/reset-match")
    async def reset_match() -> dict[str, Any]:
        snapshot = state.reset_match()
        await state.broadcast_snapshot(snapshot)
        return snapshot

    @app.post("/api/test-image")
    async def test_image(payload: TestImageRequest | None = None) -> dict[str, Any]:
        target = Path(payload.image_path) if (payload and payload.image_path) else DEFAULT_TEST_IMAGE
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Image introuvable : {target}")
        snapshot = state.analyze_image(target)
        await state.broadcast_snapshot(snapshot)
        return snapshot

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        state.clients.add(websocket)
        try:
            await websocket.send_json(state.latest_snapshot)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            state.clients.discard(websocket)
        except Exception:
            state.clients.discard(websocket)

    if dist_dir.exists() and (dist_dir / "index.html").exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend_assets")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(dist_dir / "index.html")

    return app
