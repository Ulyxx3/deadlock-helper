"""CLI entry point for Deadlock Helper (live TAB tracker, image OCR test, and engine demo)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from backend.config.settings import (
    DEFAULT_ITEM_ICONS_DIR,
    AppSettings,
    load_user_pseudo,
    save_user_pseudo,
)
from backend.engine.recommender import RecommendationEngine
from backend.meta.deadlock_api_client import DeadlockApiClient
from backend.models.game_state import (
    MatchState,
    PlayerState,
    RecommendationSection,
    Team,
)
from backend.ocr.item_matcher import ItemMatcher
from backend.ocr.souls_tracker import OcrSoulsTracker


def _configure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _ensure_item_icons(force_sync: bool = False) -> ItemMatcher:
    manifest_path = DEFAULT_ITEM_ICONS_DIR / "manifest.json"
    if force_sync or not manifest_path.exists():
        print("Synchronisation des icônes d'items depuis api.deadlock-api.com...")
        try:
            DeadlockApiClient().sync_item_icons(DEFAULT_ITEM_ICONS_DIR)
        except Exception as exc:
            print(f"[!] Impossible de synchroniser les icônes ({exc}). Poursuite sans détection d'items.")
    return ItemMatcher(DEFAULT_ITEM_ICONS_DIR)


def _resolve_player_pseudo(cli_player: str | None, reset_player: bool) -> str | None:
    """Resolve the user's in-game pseudo from CLI arg, saved profile, or interactive prompt."""
    if cli_player and cli_player.strip():
        pseudo = cli_player.strip()
        save_user_pseudo(pseudo)
        print(f"Pseudo enregistré pour is_self : {pseudo}")
        return pseudo

    if not reset_player:
        saved = load_user_pseudo()
        if saved:
            print(f"Pseudo utilisé pour is_self : {saved} (change-le avec --player <pseudo> ou --reset-player)")
            return saved

    if sys.stdin is not None and sys.stdin.isatty():
        entered = input("Entre ton pseudo Deadlock en jeu (pour détecter ton slot automatiquement) : ").strip()
        if entered:
            save_user_pseudo(entered)
            print(f"Pseudo sauvegardé dans data/user_profile.json : {entered}")
            return entered

    return None


def _print_recommendations(match_state: MatchState, api_client: DeadlockApiClient | None = None) -> None:
    me = match_state.self_player
    if me is None:
        print("\n[!] Ton slot (is_self) n'a pas encore été identifié — lance avec --player <ton_pseudo> pour activer les recommandations ciblées.")
        return

    client = api_client or DeadlockApiClient()
    core_build = client.get_default_core_build(me.hero_name, max_items=8)

    engine = RecommendationEngine(settings=AppSettings())
    reports = engine.compute_snowball_reports(match_state)
    recs = engine.recommend(match_state, default_core_build=core_build)

    print("\n=== ANALYSE SNOWBALL ENNEMIE ===")
    for r in reports:
        flag = " [FED / DANGER]" if r.is_fed else ""
        spikes = f" | Objets clés: {', '.join(r.key_items)}" if r.key_items else ""
        print(f"  - {r.hero_name}: {r.souls:,} âmes (écart moyenne: {r.souls_gap_vs_avg:+,}) | score={r.snowball_score}{spikes}{flag}")

    print("\n=== RECOMMANDATIONS D'ITEMS ===")
    for section in RecommendationSection:
        section_recs = [r for r in recs if r.section == section]
        print(f"\n[{section.value}]")
        if not section_recs:
            print("  (Aucune recommandation spécifique pour l'instant)")
            continue
        for r in section_recs:
            tick = "✔ DÉJÀ ACHETÉ" if r.already_owned else f"{r.cost} âmes"
            print(f"  - {r.item_name} ({r.category} | {tick}) -> {r.reason}")


def _run_image_mode(
    image_path: Path,
    dump_rois_dir: Path | None,
    player_pseudo: str | None,
    item_matcher: ItemMatcher,
) -> int:
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"Erreur : impossible de lire l'image '{image_path}'.")
        return 1

    tracker = OcrSoulsTracker(item_matcher=item_matcher)
    raw_timer, _ = tracker.extract_match_timer(frame)
    match_state = tracker.extract_match_state(
        frame,
        player_pseudo=player_pseudo,
        dump_debug_dir=dump_rois_dir,
    )

    print(f"Extraction OCR sur '{image_path}' ({frame.shape[1]}x{frame.shape[0]}):")
    print(f"  Chrono : {raw_timer or '?'} ({match_state.match_minutes:.2f} min)")
    for player in match_state.players:
        team_label = "Amber Hand" if player.team == Team.AMBER_HAND else "Sapphire Flame"
        self_tag = " <-- [TOI / is_self]" if player.is_self else ""
        pseudo_str = f" ({player.player_name})" if player.player_name else ""
        items_str = f" | Items ({len(player.items)}): {', '.join(player.items)}" if player.items else ""
        print(
            f"  Slot {player.slot_index:02d} [{team_label}] "
            f"{player.hero_name:12s}{pseudo_str}: {player.souls:,} âmes{self_tag}{items_str}"
        )

    if dump_rois_dir is not None:
        print(f"Images de calibration sauvegardées dans : {dump_rois_dir}")

    _print_recommendations(match_state)
    return 0


def _run_live_mode(
    dump_rois_dir: Path | None,
    player_pseudo: str | None,
    item_matcher: ItemMatcher,
) -> int:
    tracker = OcrSoulsTracker(item_matcher=item_matcher)
    api_client = DeadlockApiClient()
    print("Deadlock Helper — Tracker temps réel actif (VAC-safe, déclenchement sur touche TAB).")
    print("Maintenez TAB en jeu pour analyser le tableau des scores. Ctrl+C pour quitter.")

    def _on_match_update(match_state: MatchState) -> None:
        amber = sum(p.souls for p in match_state.players if p.team == Team.AMBER_HAND)
        sapphire = sum(p.souls for p in match_state.players if p.team == Team.SAPPHIRE_FLAME)
        print(
            f"\n[{time.strftime('%H:%M:%S')}] {match_state.match_minutes:.2f} min — "
            f"Amber total: {amber:,} | Sapphire total: {sapphire:,}"
        )
        for p in match_state.players:
            team = "Amber" if p.team == Team.AMBER_HAND else "Sapphire"
            self_tag = " [TOI]" if p.is_self else ""
            items_str = f" | Items: {', '.join(p.items)}" if p.items else ""
            print(f"  Slot {p.slot_index:02d} ({team}) {p.hero_name:12s}: {p.souls:,} âmes{self_tag}{items_str}")

        _print_recommendations(match_state, api_client=api_client)
        if dump_rois_dir is not None:
            tracker.poll_match_state(player_pseudo=player_pseudo, dump_debug_dir=dump_rois_dir)

    tracker.run_live_match(_on_match_update, player_pseudo=player_pseudo)
    return 0


def _run_demo_mode() -> int:
    sample_match = MatchState(
        timestamp=time.time(),
        match_minutes=14.5,
        players=[
            PlayerState(0, Team.SAPPHIRE_FLAME, "Haze", 10_400, 3, 2, 4, ["Headshot Booster", "Fleetfoot"], lane_id=1, is_self=True),
            PlayerState(1, Team.SAPPHIRE_FLAME, "Dynamo", 9_200, 1, 3, 7, ["Extra Regen"], lane_id=2),
            PlayerState(2, Team.SAPPHIRE_FLAME, "Pocket", 11_100, 4, 2, 3, ["Mystic Burst"], lane_id=3),
            PlayerState(3, Team.SAPPHIRE_FLAME, "Ivy", 9_800, 2, 2, 6, ["Healing Rite"], lane_id=1),
            PlayerState(4, Team.SAPPHIRE_FLAME, "Warden", 10_100, 3, 3, 2, ["Bullet Armor"], lane_id=2),
            PlayerState(5, Team.SAPPHIRE_FLAME, "Vindicta", 10_600, 4, 4, 3, ["High-Velocity Mag"], lane_id=3),
            PlayerState(6, Team.AMBER_HAND, "Abrams", 14_900, 3, 1, 5, ["Leech", "Spirit Lifesteal"], lane_id=1),
            PlayerState(7, Team.AMBER_HAND, "Seven", 13_400, 5, 2, 4, ["Boundless Spirit"], lane_id=2),
            PlayerState(8, Team.AMBER_HAND, "Wraith", 10_200, 2, 3, 2, ["Tesla Bullets"], lane_id=3),
            PlayerState(9, Team.AMBER_HAND, "Lady Geist", 11_300, 2, 2, 4, [], lane_id=1),
            PlayerState(10, Team.AMBER_HAND, "Mo & Krill", 9_500, 1, 4, 6, [], lane_id=2),
            PlayerState(11, Team.AMBER_HAND, "Infernus", 10_800, 3, 3, 2, [], lane_id=3),
        ],
    )

    core_build = [
        {"item_name": "Headshot Booster", "category": "Weapon", "cost": 500},
        {"item_name": "Fleetfoot", "category": "Vitality", "cost": 1250},
        {"item_name": "Ricochet", "category": "Weapon", "cost": 6200},
    ]

    engine = RecommendationEngine(settings=AppSettings())
    reports = engine.compute_snowball_reports(sample_match)
    recs = engine.recommend(sample_match, default_core_build=core_build)

    print("=== ANALYSE SNOWBALL ENNEMIE ===")
    for r in reports:
        flag = " [FED / DANGER]" if r.is_fed else ""
        spikes = f" | Objets clés: {', '.join(r.key_items)}" if r.key_items else ""
        print(f"  - {r.hero_name}: {r.souls:,} âmes (écart moyenne: {r.souls_gap_vs_avg:+,}) | score={r.snowball_score}{spikes}{flag}")

    print("\n=== RECOMMANDATIONS D'ITEMS ===")
    for section in RecommendationSection:
        section_recs = [r for r in recs if r.section == section]
        print(f"\n[{section.value}]")
        if not section_recs:
            print("  (Aucune recommandation spécifique)")
            continue
        for r in section_recs:
            tick = "✔ DÉJÀ ACHETÉ" if r.already_owned else f"{r.cost} âmes"
            print(f"  - {r.item_name} ({r.category} | {tick}) -> {r.reason}")

    return 0


def main() -> int:
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Deadlock Helper — Companion VAC-Safe")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Lance le tracker en direct (touche TAB).")
    mode.add_argument("--server", action="store_true", help="Lance le serveur Companion + interface Web/Overlay.")
    mode.add_argument("--image", type=Path, help="Teste l'OCR sur une capture d'écran du scoreboard.")
    mode.add_argument("--demo", action="store_true", help="Exécute une simulation complète du moteur de recommandation.")
    mode.add_argument("--sync-assets", action="store_true", help="Télécharge/met à jour le cache local des icônes d'items.")
    parser.add_argument("--player", type=str, default=None, help="Ton pseudo en jeu (sauvegardé pour détecter is_self).")
    parser.add_argument("--reset-player", action="store_true", help="Redemande ton pseudo en jeu.")
    parser.add_argument("--dump-rois", type=Path, default=None, help="Dossier où sauvegarder les ROIs annotés pour calibration.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Adresse d'écoute pour --server.")
    parser.add_argument("--port", type=int, default=8765, help="Port d'écoute pour --server.")
    parser.add_argument("--no-live", action="store_true", help="Désactive l'écoute TAB en mode --server (tests UI uniquement).")
    args = parser.parse_args()

    if args.sync_assets:
        matcher = _ensure_item_icons(force_sync=True)
        print(f"{len(matcher.item_names)} icônes d'items prêtes dans {DEFAULT_ITEM_ICONS_DIR}.")
        return 0

    if args.demo:
        return _run_demo_mode()

    item_matcher = _ensure_item_icons(force_sync=False)
    pseudo = _resolve_player_pseudo(args.player, args.reset_player)

    if args.server:
        import uvicorn
        from backend.server.app import create_app

        live_enabled = not args.no_live
        print(f"Deadlock Helper Companion prêt sur http://{args.host}:{args.port}")
        print(f"Écoute TAB en direct : {'ACTIVE (VAC-safe)' if live_enabled else 'DÉSACTIVÉE (--no-live)'}")
        app = create_app(enable_live_listener=live_enabled, initial_pseudo=pseudo)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return 0

    if args.image:
        return _run_image_mode(args.image, args.dump_rois, pseudo, item_matcher)
    return _run_live_mode(args.dump_rois, pseudo, item_matcher)


if __name__ == "__main__":
    raise SystemExit(main())
