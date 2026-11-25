"""REST client for Deadlock API (api.deadlock-api.com/v1 & /v1/assets)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from backend.config.settings import DEFAULT_CACHE_DIR, DEFAULT_ITEM_ICONS_DIR


class DeadlockApiClient:
    """Fetches hero/item metadata, shop icons, and live builds with disk caching."""

    API_BASE = "https://api.deadlock-api.com/v1"
    ASSETS_BASE = "https://api.deadlock-api.com/v1/assets"

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        timeout_s: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "deadlock-helper/0.1 (+https://github.com/deadlock-helper)",
            "Accept": "application/json",
        })

    def _get_json(self, url: str, cache_name: str, ttl_seconds: int, params: dict[str, Any] | None = None) -> Any:
        cache_file = self.cache_dir / f"{cache_name}.json"
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < ttl_seconds:
                return json.loads(cache_file.read_text(encoding="utf-8"))

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
                if resp.status_code == 503:
                    retry_after = float(resp.headers.get("Retry-After", 2.0 * (attempt + 1)))
                    time.sleep(min(retry_after, 10.0))
                    continue
                resp.raise_for_status()
                payload = resp.json()
                cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return payload
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(0.8 * (attempt + 1))

        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}") from last_exc

    def get_heroes(self, ttl_seconds: int = 86_400) -> list[dict[str, Any]]:
        """Fetch hero definitions and base stats from /v1/assets/heroes."""
        return self._get_json(f"{self.ASSETS_BASE}/heroes", "assets_heroes", ttl_seconds)

    def get_shop_items(self, ttl_seconds: int = 86_400) -> list[dict[str, Any]]:
        """Fetch shop upgrade items (Weapon, Vitality, Spirit) from /v1/assets/items/by-type/upgrade."""
        return self._get_json(f"{self.ASSETS_BASE}/items/by-type/upgrade", "assets_upgrade_items", ttl_seconds)

    def get_item_names_fr(self, ttl_seconds: int = 86_400) -> dict[str, str]:
        """Map normalized English item names to official French Deadlock names."""
        try:
            en_items = self.get_shop_items(ttl_seconds=ttl_seconds)
            fr_items = self._get_json(
                f"{self.ASSETS_BASE}/items/by-type/upgrade",
                "assets_upgrade_items_fr",
                ttl_seconds,
                params={"language": "french"},
            )
        except Exception:
            return {}

        fr_by_id = {
            int(item["id"]): str(item["name"]).strip()
            for item in fr_items
            if item.get("id") is not None and item.get("name")
        }
        mapping: dict[str, str] = {}
        for item in en_items:
            if item.get("id") is None or not item.get("name"):
                continue
            item_id = int(item["id"])
            en_lower = str(item["name"]).strip().lower()
            if item_id in fr_by_id:
                mapping[en_lower] = fr_by_id[item_id]
        return mapping

    def get_items(self, ttl_seconds: int = 86_400) -> list[dict[str, Any]]:
        """Alias returning upgrade shop items."""
        return self.get_shop_items(ttl_seconds=ttl_seconds)

    def get_hero_id(self, hero_name: str) -> int | None:
        """Resolve a canonical hero name (e.g. 'Vindicta') to its Deadlock hero_id."""
        target = hero_name.strip().lower()
        for hero in self.get_heroes():
            if str(hero.get("name", "")).strip().lower() == target:
                return int(hero["id"])
        return None

    def get_items_by_id(self) -> dict[int, dict[str, Any]]:
        """Return a mapping of item_id -> item metadata for shopable upgrades."""
        return {
            int(item["id"]): item
            for item in self.get_shop_items()
            if item.get("id") is not None and item.get("shopable", True)
        }

    def sync_item_icons(
        self,
        icons_dir: Path = DEFAULT_ITEM_ICONS_DIR,
        max_workers: int = 12,
    ) -> Path:
        """Download shop item PNG icons locally and write manifest.json."""
        icons_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = icons_dir / "manifest.json"
        shop_items = [
            item for item in self.get_shop_items()
            if item.get("shopable", True) and item.get("name") and (item.get("shop_image") or item.get("image"))
        ]

        manifest: dict[str, dict[str, Any]] = {}
        tasks: list[tuple[int, str, Path]] = []

        for item in shop_items:
            item_id = int(item["id"])
            img_url = str(item.get("shop_image") or item.get("image"))
            filename = f"{item_id}.png"
            dest = icons_dir / filename
            slot_type = str(item.get("item_slot_type", "weapon")).lower()
            category_map = {"weapon": "Weapon", "vitality": "Vitality", "spirit": "Spirit"}
            manifest[str(item_id)] = {
                "id": item_id,
                "name": str(item["name"]),
                "category": category_map.get(slot_type, slot_type.title()),
                "slot_type": slot_type,
                "cost": int(item.get("cost") or 0),
                "tier": int(item.get("item_tier") or 1),
                "filename": filename,
            }
            if not dest.exists():
                tasks.append((item_id, img_url, dest))

        def _download(url: str, target: Path) -> None:
            resp = requests.get(url, headers={"User-Agent": "deadlock-helper/0.1"}, timeout=self.timeout_s)
            resp.raise_for_status()
            target.write_bytes(resp.content)

        if tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(_download, url, dest) for _, url, dest in tasks]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception:
                        pass

        # Keep only entries whose PNG actually exists on disk
        valid_manifest = {
            k: v for k, v in manifest.items()
            if (icons_dir / v["filename"]).exists()
        }
        manifest_path.write_text(json.dumps(valid_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path

    def get_hero_item_analytics(
        self,
        hero_id: int,
        min_badge: int | None = None,
        ttl_seconds: int = 7_200,
    ) -> Any:
        """Fetch item pick/winrate analytics for a hero filtered by rank badge."""
        params: dict[str, Any] = {"hero_id": hero_id}
        if min_badge is not None:
            params["min_average_badge"] = min_badge
        cache_key = f"analytics_items_hero_{hero_id}_badge_{min_badge or 'all'}"
        return self._get_json(f"{self.API_BASE}/analytics/item-stats", cache_key, ttl_seconds, params=params)

    def get_builds(self, hero_id: int, limit: int = 5, ttl_seconds: int = 7_200) -> Any:
        """Fetch community & high-MMR builds for a given hero."""
        params = {"hero_id": hero_id, "limit": limit}
        return self._get_json(f"{self.API_BASE}/builds", f"builds_hero_{hero_id}_l{limit}", ttl_seconds, params=params)

    def get_default_core_build(
        self,
        hero_name: str,
        max_items: int = 24,
    ) -> list[dict[str, str | int]]:
        """Extract a hero's multi-phase item progression (Early -> Mid -> Late) from live builds."""
        try:
            hero_id = self.get_hero_id(hero_name)
            if hero_id is None:
                return []
            builds = self.get_builds(hero_id, limit=5)
            items_by_id = self.get_items_by_id()
        except Exception:
            return []

        if not isinstance(builds, list) or not builds:
            return []

        slot_to_cat = {"weapon": "Weapon", "vitality": "Vitality", "spirit": "Spirit"}
        seen_names: set[str] = set()
        core_items: list[dict[str, str | int]] = []

        for entry in builds:
            hb = entry.get("hero_build", entry) if isinstance(entry, dict) else {}
            categories = hb.get("details", {}).get("mod_categories", [])
            if not categories:
                continue

            for cat in categories:
                for mod in cat.get("mods", []):
                    ability_id = mod.get("ability_id")
                    if ability_id is None:
                        continue
                    meta = items_by_id.get(int(ability_id))
                    if not meta:
                        continue
                    name = str(meta["name"])
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    slot_type = str(meta.get("item_slot_type", "weapon")).lower()
                    core_items.append({
                        "item_name": name,
                        "category": slot_to_cat.get(slot_type, "Core"),
                        "cost": int(meta.get("cost") or 0),
                        "tier": int(meta.get("item_tier") or 1),
                    })
                    if len(core_items) >= max_items:
                        return core_items
            if core_items:
                return core_items

        return core_items

    def get_upgrade_graph(self, ttl_seconds: int = 86_400) -> dict[str, Any]:
        """Build Deadlock's item upgrade tree (components -> upgraded items & transitive ancestors)."""
        try:
            shop_items = self.get_shop_items(ttl_seconds=ttl_seconds)
        except Exception:
            return {"upgrades_from": {}, "upgrades_into": {}, "ancestors": {}}

        slot_to_cat = {"weapon": "Weapon", "vitality": "Vitality", "spirit": "Spirit"}
        by_class: dict[str, dict[str, Any]] = {}
        for item in shop_items:
            cname = str(item.get("class_name", "")).strip()
            if not cname or not item.get("name"):
                continue
            slot_type = str(item.get("item_slot_type", "weapon")).lower()
            by_class[cname] = {
                "name": str(item["name"]).strip(),
                "cost": int(item.get("cost") or 0),
                "category": slot_to_cat.get(slot_type, "Core"),
                "tier": int(item.get("item_tier") or 1),
            }

        upgrades_from: dict[str, list[dict[str, Any]]] = {}
        upgrades_into: dict[str, list[dict[str, Any]]] = {}

        for item in shop_items:
            if not item.get("name"):
                continue
            up_name = str(item["name"]).strip()
            up_lower = up_name.lower()
            up_slot = str(item.get("item_slot_type", "weapon")).lower()
            up_meta = {
                "name": up_name,
                "cost": int(item.get("cost") or 0),
                "category": slot_to_cat.get(up_slot, "Core"),
                "tier": int(item.get("item_tier") or 1),
            }
            for comp_cls in item.get("component_items") or []:
                comp_meta = by_class.get(str(comp_cls).strip())
                if not comp_meta:
                    continue
                comp_lower = comp_meta["name"].lower()
                upgrades_from.setdefault(up_lower, []).append(comp_meta)
                upgrades_into.setdefault(comp_lower, []).append(up_meta)

        # Transitive closure: if Crippling Headshot -> Headhunter -> Headshot Booster,
        # owning Crippling Headshot means Headhunter & Headshot Booster are already evolved.
        ancestors: dict[str, set[str]] = {}
        for up_lower in upgrades_from:
            visited: set[str] = set()
            stack = [c["name"].lower() for c in upgrades_from.get(up_lower, [])]
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                for parent in upgrades_from.get(cur, []):
                    stack.append(parent["name"].lower())
            ancestors[up_lower] = visited

        return {
            "upgrades_from": upgrades_from,
            "upgrades_into": upgrades_into,
            "ancestors": ancestors,
        }
