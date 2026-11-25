"""Snowball, build-balance, and dynamic matchup-aware item recommendation engine."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.config.settings import DEFAULT_RULES_PATH, AppSettings
from backend.models.game_state import (
    BuildBalance,
    ItemRecommendation,
    LaneStatus,
    MatchState,
    PlayerState,
    RecommendationSection,
    SnowballReport,
)

SUSTAIN_ITEMS = {
    "extra regen",
    "healing rite",
    "bullet lifesteal",
    "spirit lifesteal",
    "melee lifesteal",
    "healbane",
    "healing booster",
    "healing nova",
    "fortitude",
    "leech",
    "siphon bullets",
    "restorative locket",
    "radiant regeneration",
    "healing tempo",
    "mystic regeneration",
}
SPIRIT_RESIST_ITEMS = {
    "spirit shielding",
    "spirit resilience",
    "spellbreaker",
    "enchanter's emblem",
    "counterspell",
}
BULLET_RESIST_ITEMS = {
    "battle vest",
    "bullet resilience",
    "metal skin",
    "plated armor",
    "weapon shielding",
}
CC_DEFENSE_ITEMS = {
    "debuff reducer",
    "dispel magic",
    "reactive barrier",
    "unstoppable",
}
ANTI_HEAL_ITEMS = {
    "healbane",
    "decay",
    "toxic bullets",
}


def _format_souls(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _format_souls_en(amount: int) -> str:
    return f"{amount:,}"


def _format_hero_list(reports: list[SnowballReport], english: bool = False) -> str:
    """Format ALL matching enemy heroes concisely, showing soul leads on ahead/fed enemies."""
    parts: list[str] = []
    seen: set[str] = set()
    for rep in reports:
        if rep.hero_name in seen:
            continue
        seen.add(rep.hero_name)
        if rep.is_fed or rep.souls_gap_vs_avg >= 1000:
            gap_fmt = _format_souls_en(rep.souls_gap_vs_avg) if english else _format_souls(rep.souls_gap_vs_avg)
            parts.append(f"{rep.hero_name} (+{gap_fmt})")
        else:
            parts.append(rep.hero_name)
    return ", ".join(parts)


class RecommendationEngine:
    """Computes snowball scores, build balance, upgrade paths, and dynamic priorities."""

    def __init__(
        self,
        rules_path: Path = DEFAULT_RULES_PATH,
        settings: AppSettings | None = None,
    ) -> None:
        self.settings = settings or AppSettings()
        self.rules = json.loads(rules_path.read_text(encoding="utf-8"))
        self.hero_tags: dict[str, list[str]] = self.rules.get("hero_threat_tags", {})
        self.key_spikes: dict[str, dict] = self.rules.get("key_power_spike_items", {})
        self._rule_categories: dict[str, str] = {}
        for grp in ("counter_items", "lane_defensive_items", "lane_snowball_items"):
            for entry in self.rules.get(grp, []):
                self._rule_categories[entry["item_name"].strip().lower()] = entry["category"]

    def analyze_build_balance(
        self,
        match: MatchState,
        item_categories: dict[str, str] | None = None,
    ) -> BuildBalance:
        """Analyze Weapon/Spirit/Vitality/Sustain balance in the player's current inventory."""
        me = match.self_player
        if me is None:
            return BuildBalance(0, 0, 0, 0, False, False, False)

        cat_lookup = {**self._rule_categories, **(item_categories or {})}
        weapon = spirit = vitality = sustain = 0

        for item in me.items:
            key = item.strip().lower()
            cat = cat_lookup.get(key)
            if cat is None:
                if key in SPIRIT_RESIST_ITEMS | BULLET_RESIST_ITEMS | CC_DEFENSE_ITEMS | SUSTAIN_ITEMS:
                    cat = "Vitality"
                else:
                    cat = "Weapon"
            if cat == "Weapon":
                weapon += 1
            elif cat == "Spirit":
                spirit += 1
            elif cat == "Vitality":
                vitality += 1

            if key in SUSTAIN_ITEMS:
                sustain += 1

        damage_count = weapon + spirit
        needs_damage = match.match_minutes >= 12.0 and (
            damage_count < 3 or (vitality >= 3 and damage_count <= vitality)
        )
        needs_sustain = match.match_minutes >= 12.0 and sustain == 0
        needs_defense = match.match_minutes >= 15.0 and vitality == 0

        return BuildBalance(
            weapon_count=weapon,
            spirit_count=spirit,
            vitality_count=vitality,
            sustain_count=sustain,
            needs_damage=needs_damage,
            needs_sustain=needs_sustain,
            needs_defense=needs_defense,
        )

    def compute_snowball_reports(self, match: MatchState) -> list[SnowballReport]:
        """Quantify each enemy's snowball state primarily from souls gap & key items."""
        avg_souls = max(1.0, match.lobby_average_souls)
        reports: list[SnowballReport] = []

        for enemy in match.enemies:
            souls_gap = int(round(enemy.souls - avg_souls))
            souls_ratio_gap = souls_gap / avg_souls

            owned_spikes = [item for item in enemy.items if item in self.key_spikes]
            spike_power = sum(float(self.key_spikes[item]["power"]) for item in owned_spikes)
            key_item_power = min(1.0, spike_power / 1.8)

            kd_diff = enemy.kills - enemy.deaths
            kd_modifier = max(-0.5, min(1.0, kd_diff / 8.0))

            snowball_score = round(
                0.65 * souls_ratio_gap + 0.25 * key_item_power + 0.10 * kd_modifier,
                3,
            )
            is_fed = (
                souls_gap >= self.settings.fed_souls_gap_threshold
                or snowball_score >= self.settings.fed_snowball_score_threshold
            )
            reports.append(
                SnowballReport(
                    hero_name=enemy.hero_name,
                    souls=enemy.souls,
                    souls_gap_vs_avg=souls_gap,
                    snowball_score=snowball_score,
                    is_fed=is_fed,
                    key_items=owned_spikes,
                )
            )

        reports.sort(key=lambda r: r.snowball_score, reverse=True)
        return reports

    def evaluate_lane_status(
        self,
        match: MatchState,
        lane_opponent_heroes: list[str] | None = None,
    ) -> tuple[LaneStatus, int, list[PlayerState]]:
        """Evaluate local player's direct lane economy vs pinned or inferred lane opponents."""
        me = match.self_player
        if me is None:
            return LaneStatus.EVEN, 0, []

        if lane_opponent_heroes:
            wanted = {h.strip().lower() for h in lane_opponent_heroes if h.strip()}
            lane_opponents = [e for e in match.enemies if e.hero_name.strip().lower() in wanted]
        else:
            lane_opponents = [
                e for e in match.enemies
                if me.lane_id is not None and e.lane_id == me.lane_id
            ]

        if not lane_opponents:
            return LaneStatus.EVEN, 0, []

        opp_avg = sum(o.souls for o in lane_opponents) / len(lane_opponents)
        lane_diff = int(round(me.souls - opp_avg))

        if lane_diff >= self.settings.lane_lead_threshold:
            return LaneStatus.SNOWBALLING, lane_diff, lane_opponents
        if lane_diff <= -self.settings.lane_lead_threshold:
            return LaneStatus.BEHIND, lane_diff, lane_opponents
        return LaneStatus.EVEN, lane_diff, lane_opponents

    def _collect_threat_weights(
        self,
        players: list[PlayerState],
        snowball_by_hero: dict[str, SnowballReport],
    ) -> tuple[dict[str, float], dict[str, list[SnowballReport]]]:
        """Aggregate threat tags and ALL enemy heroes matching each tag."""
        tag_weights: dict[str, float] = defaultdict(float)
        heroes_for_tag: dict[str, list[SnowballReport]] = defaultdict(list)

        for enemy in players:
            report = snowball_by_hero.get(enemy.hero_name)
            multiplier = 1.0
            if report is not None:
                if report.is_fed:
                    multiplier = 1.65
                elif report.souls_gap_vs_avg > 0:
                    multiplier = 1.2

            tags = set(self.hero_tags.get(enemy.hero_name, []))
            for item in enemy.items:
                spike_meta = self.key_spikes.get(item)
                if spike_meta:
                    tags.update(spike_meta.get("adds_tags", []))

            for tag in tags:
                tag_weights[tag] += multiplier
                if report is not None:
                    heroes_for_tag[tag].append(report)

        for tag, rep_list in heroes_for_tag.items():
            rep_list.sort(key=lambda r: r.snowball_score, reverse=True)

        return dict(tag_weights), dict(heroes_for_tag)

    @staticmethod
    def _resolve_upgrade_status(
        item_name: str,
        item_cost: int,
        owned_display_by_lower: dict[str, str],
        upgrade_graph: dict[str, Any] | None,
    ) -> tuple[str, str | None, int]:
        """Determine whether an item is owned, already evolved, ready to upgrade, or new."""
        item_lower = item_name.strip().lower()
        if item_lower in owned_display_by_lower:
            return "owned", None, 0

        if upgrade_graph:
            ancestors_map: dict[str, set[str]] = upgrade_graph.get("ancestors", {})
            for owned_lower in owned_display_by_lower:
                if item_lower in ancestors_map.get(owned_lower, set()):
                    return "evolved", None, 0

            upgrades_from: dict[str, list[dict[str, Any]]] = upgrade_graph.get("upgrades_from", {})
            for comp in upgrades_from.get(item_lower, []):
                comp_lower = str(comp["name"]).strip().lower()
                if comp_lower in owned_display_by_lower:
                    comp_cost = int(comp.get("cost") or 0)
                    return "upgrade_ready", owned_display_by_lower[comp_lower], max(0, item_cost - comp_cost)

        return "new", None, item_cost

    def _apply_upgrade_fields(
        self,
        rec: ItemRecommendation,
        owned_display_by_lower: dict[str, str],
        upgrade_graph: dict[str, Any] | None,
    ) -> ItemRecommendation:
        status, comp_name, net_cost = self._resolve_upgrade_status(
            rec.item_name,
            rec.cost,
            owned_display_by_lower,
            upgrade_graph,
        )
        rec.upgrade_status = status
        rec.upgrades_from_owned = comp_name
        rec.net_cost = net_cost
        rec.already_owned = status in {"owned", "evolved"}
        return rec

    def _build_counter_recs(
        self,
        tag_weights: dict[str, float],
        heroes_for_tag: dict[str, list[SnowballReport]],
        section: RecommendationSection,
        owned_display_by_lower: dict[str, str],
        upgrade_graph: dict[str, Any] | None,
        balance: BuildBalance,
        min_weight_override: float | None = None,
    ) -> list[ItemRecommendation]:
        owned_keys = set(owned_display_by_lower.keys())
        has_spirit_res = bool(owned_keys & SPIRIT_RESIST_ITEMS)
        has_bullet_res = bool(owned_keys & BULLET_RESIST_ITEMS)
        has_cc_def = bool(owned_keys & CC_DEFENSE_ITEMS)
        has_anti_heal = bool(owned_keys & ANTI_HEAL_ITEMS)

        recs: list[ItemRecommendation] = []
        for rule in self.rules.get("counter_items", []):
            tag = rule["counters_tag"]
            weight = tag_weights.get(tag, 0.0)
            threshold = min_weight_override if min_weight_override is not None else float(rule["min_threat_weight"])
            if weight < threshold:
                continue

            matching_reports = heroes_for_tag.get(tag, [])
            if not matching_reports:
                continue

            top_driver = matching_reports[0]
            any_fed_driver = any(r.is_fed for r in matching_reports)
            heroes_str = _format_hero_list(matching_reports, english=False)
            heroes_str_en = _format_hero_list(matching_reports, english=True)
            reason_fr = rule["template_reason"].format(
                item=rule["item_name"],
                heroes_str=heroes_str,
            )
            reason_en = rule.get("template_reason_en", rule["template_reason"]).format(
                item=rule["item_name"],
                heroes_str_en=heroes_str_en,
            )

            prio = weight * (1.25 if any_fed_driver else 1.0)
            # Diminishing returns: avoid piling redundant resists if one is already owned
            if tag == "spirit" and has_spirit_res and not any_fed_driver:
                prio *= 0.55
            elif tag == "bullet_carry" and has_bullet_res and not any_fed_driver:
                prio *= 0.55
            elif tag == "cc" and has_cc_def and not any_fed_driver:
                prio *= 0.60
            elif tag == "lifesteal" and has_anti_heal:
                prio *= 0.60

            # If player already lacks damage/sustain, gently dampen pure defensive non-fed counters
            if balance.needs_damage and rule["category"] == "Vitality" and not any_fed_driver:
                prio *= 0.75
            if balance.needs_sustain and rule["item_name"].strip().lower() in SUSTAIN_ITEMS:
                prio *= 1.35

            rec = ItemRecommendation(
                item_name=rule["item_name"],
                category=rule["category"],
                cost=int(rule["cost"]),
                section=section,
                reason=reason_fr,
                reason_en=reason_en,
                priority=round(prio, 3),
                target_heroes=[r.hero_name for r in matching_reports],
            )
            recs.append(self._apply_upgrade_fields(rec, owned_display_by_lower, upgrade_graph))

        recs.sort(key=lambda r: r.priority, reverse=True)
        return recs

    def _build_evolving_core(
        self,
        me: PlayerState,
        match: MatchState,
        default_core_build: list[dict[str, str | int]] | list[str] | None,
        owned_display_by_lower: dict[str, str],
        upgrade_graph: dict[str, Any] | None,
        balance: BuildBalance,
    ) -> list[ItemRecommendation]:
        """Adapt Core build to match phase, build balance, and owned-item upgrade paths."""
        is_late_or_mid = (
            match.match_minutes >= 12.0
            or me.souls >= 10_000
            or len(owned_display_by_lower) >= 7
        )

        candidates: list[tuple[str, str, int, float, str, str]] = []
        seen_lower: set[str] = set()

        if upgrade_graph:
            upgrades_into: dict[str, list[dict[str, Any]]] = upgrade_graph.get("upgrades_into", {})
            for owned_lower, owned_display in owned_display_by_lower.items():
                for upg in upgrades_into.get(owned_lower, []):
                    upg_name = str(upg["name"])
                    upg_lower = upg_name.lower()
                    if upg_lower in seen_lower or upg_lower in owned_display_by_lower:
                        continue
                    seen_lower.add(upg_lower)
                    cost = int(upg.get("cost") or 3200)
                    cat = str(upg.get("category", "Core"))
                    prio = 3.3
                    if balance.needs_damage and cat in {"Weapon", "Spirit"}:
                        prio += 0.4
                    if balance.needs_sustain and upg_lower in SUSTAIN_ITEMS:
                        prio += 0.45
                    candidates.append((
                        upg_name,
                        cat,
                        cost,
                        prio,
                        f"Améliore {owned_display} (0 slot en plus).",
                        f"Upgrades {owned_display} (0 extra slot).",
                    ))

        for idx, entry in enumerate(default_core_build or []):
            if isinstance(entry, str):
                name, category, cost, tier = entry, "Core", 1600, 2
            else:
                name = str(entry["item_name"])
                category = str(entry.get("category", "Core"))
                cost = int(entry.get("cost", 1600))
                tier = int(entry.get("tier", 1 if cost <= 800 else (2 if cost <= 1600 else (3 if cost <= 3200 else 4))))

            name_lower = name.strip().lower()
            if name_lower in seen_lower:
                continue

            status, comp_name, _ = self._resolve_upgrade_status(
                name, cost, owned_display_by_lower, upgrade_graph
            )
            if is_late_or_mid and tier <= 1 and status == "new":
                continue

            seen_lower.add(name_lower)
            if status == "upgrade_ready" and comp_name:
                r_fr = f"Améliore {comp_name} (0 slot en plus)."
                r_en = f"Upgrades {comp_name} (0 extra slot)."
                prio = 3.1 - idx * 0.04
            elif status == "evolved":
                r_fr = f"Déjà évolué via ton inventaire."
                r_en = f"Already evolved in inventory."
                prio = 0.5 - idx * 0.02
            elif status == "owned":
                r_fr = f"Core {me.hero_name} acquis."
                r_en = f"Core {me.hero_name} owned."
                prio = 0.6 - idx * 0.02
            else:
                phase_tag = "Late spike" if tier >= 4 else ("Mid spike" if tier == 3 else "Core")
                r_fr = f"{phase_tag} {me.hero_name} (#{idx + 1})."
                r_en = f"{phase_tag} {me.hero_name} (#{idx + 1})."
                prio = (2.6 if (is_late_or_mid and tier >= 3) else 2.4) - idx * 0.05

            if balance.needs_damage and category in {"Weapon", "Spirit"} and status == "new":
                prio += 0.35
            if balance.needs_sustain and name_lower in SUSTAIN_ITEMS and status in {"new", "upgrade_ready"}:
                prio += 0.45

            candidates.append((name, category, cost, prio, r_fr, r_en))

        built: list[ItemRecommendation] = []
        for name, category, cost, prio, r_fr, r_en in candidates:
            rec = ItemRecommendation(
                item_name=name,
                category=category,
                cost=cost,
                section=RecommendationSection.CORE_ITEMS,
                reason=r_fr,
                reason_en=r_en,
                priority=round(prio, 3),
            )
            built.append(self._apply_upgrade_fields(rec, owned_display_by_lower, upgrade_graph))

        status_rank = {"upgrade_ready": 0, "new": 1, "owned": 2, "evolved": 3}
        built.sort(key=lambda r: (status_rank.get(r.upgrade_status, 9), -r.priority))
        return built[:10]

    def _build_top_priority(
        self,
        all_recs: list[ItemRecommendation],
        owned_count: int,
        balance: BuildBalance,
    ) -> list[ItemRecommendation]:
        """Select top 3-4 balanced items: cap pure defense at 2 and ensure damage/sustain."""
        inventory_tight = owned_count >= 9
        scored: list[tuple[float, ItemRecommendation]] = []
        seen_lower: set[str] = set()

        for rec in all_recs:
            if rec.upgrade_status in {"owned", "evolved"}:
                continue
            key = rec.item_name.strip().lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)

            score = rec.priority
            if rec.section == RecommendationSection.GLOBAL_THREATS:
                score += 0.65
            elif rec.section == RecommendationSection.DIRECT_MATCHUP:
                score += 0.45
            if rec.upgrade_status == "upgrade_ready":
                score += 1.4 if inventory_tight else 0.75
            if balance.needs_damage and rec.category in {"Weapon", "Spirit"}:
                score += 0.95
            if balance.needs_sustain and key in SUSTAIN_ITEMS:
                score += 1.05

            scored.append((score, rec))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        selected: list[tuple[float, ItemRecommendation]] = []
        picked_keys: set[str] = set()

        def _is_pure_defense(r: ItemRecommendation) -> bool:
            return r.category == "Vitality" and r.item_name.strip().lower() not in SUSTAIN_ITEMS

        # 1. Guarantee at least 1 damage/upgrade item if available
        for sc, rec in scored:
            if rec.category in {"Weapon", "Spirit"} or rec.upgrade_status == "upgrade_ready":
                selected.append((sc, rec))
                picked_keys.add(rec.item_name.strip().lower())
                break

        # 2. Guarantee 1 sustain item if build lacks sustain
        if balance.needs_sustain:
            for sc, rec in scored:
                k = rec.item_name.strip().lower()
                if k not in picked_keys and k in SUSTAIN_ITEMS:
                    selected.append((sc, rec))
                    picked_keys.add(k)
                    break

        # 3. Fill remaining slots up to 4, capping pure defensive Vitality items at 2
        defense_count = sum(1 for _, r in selected if _is_pure_defense(r))
        for sc, rec in scored:
            if len(selected) >= 4:
                break
            k = rec.item_name.strip().lower()
            if k in picked_keys:
                continue
            if _is_pure_defense(rec) and defense_count >= 2:
                continue
            selected.append((sc, rec))
            picked_keys.add(k)
            if _is_pure_defense(rec):
                defense_count += 1

        selected.sort(key=lambda pair: pair[0], reverse=True)
        top_items: list[ItemRecommendation] = []
        for score, src in selected[:4]:
            suffix_fr = f" (0 slot via {src.upgrades_from_owned})" if src.upgrades_from_owned else ""
            suffix_en = f" (0 slot from {src.upgrades_from_owned})" if src.upgrades_from_owned else ""
            top_items.append(
                ItemRecommendation(
                    item_name=src.item_name,
                    category=src.category,
                    cost=src.cost,
                    section=RecommendationSection.TOP_PRIORITY,
                    reason=f"{src.reason}{suffix_fr}" if suffix_fr and src.upgrades_from_owned not in src.reason else src.reason,
                    reason_en=f"{src.reason_en}{suffix_en}" if suffix_en and src.upgrades_from_owned not in src.reason_en else src.reason_en,
                    priority=round(score, 3),
                    already_owned=src.already_owned,
                    upgrade_status=src.upgrade_status,
                    upgrades_from_owned=src.upgrades_from_owned,
                    net_cost=src.net_cost,
                    target_heroes=list(src.target_heroes),
                )
            )
        return top_items

    def recommend(
        self,
        match: MatchState,
        default_core_build: list[dict[str, str | int]] | list[str] | None = None,
        upgrade_graph: dict[str, Any] | None = None,
        lane_opponent_heroes: list[str] | None = None,
        item_categories: dict[str, str] | None = None,
    ) -> list[ItemRecommendation]:
        """Generate balanced recommendations across all sections with upgrade & sustain awareness."""
        me = match.self_player
        if me is None:
            return []

        balance = self.analyze_build_balance(match, item_categories=item_categories)
        owned_display_by_lower = {i.strip().lower(): i.strip() for i in me.items if i.strip()}
        snowball_reports = self.compute_snowball_reports(match)
        snowball_by_hero = {r.hero_name: r for r in snowball_reports}
        lane_status, lane_diff, lane_opponents = self.evaluate_lane_status(
            match, lane_opponent_heroes=lane_opponent_heroes
        )

        recommendations: list[ItemRecommendation] = []

        # 1. Direct Matchup section
        if lane_opponents:
            lane_enemy_names = " / ".join(o.hero_name for o in lane_opponents)
            if match.match_minutes < 14.0:
                if lane_status == LaneStatus.BEHIND:
                    for idx, item in enumerate(self.rules.get("lane_defensive_items", [])):
                        rec = ItemRecommendation(
                            item_name=item["item_name"],
                            category=item["category"],
                            cost=int(item["cost"]),
                            section=RecommendationSection.DIRECT_MATCHUP,
                            reason=item["reason"].format(
                                item=item["item_name"],
                                lane_gap_str=_format_souls(abs(lane_diff)),
                                lane_enemy=lane_enemy_names,
                            ),
                            reason_en=item.get("reason_en", item["reason"]).format(
                                item=item["item_name"],
                                lane_gap_str_en=_format_souls_en(abs(lane_diff)),
                                lane_enemy=lane_enemy_names,
                            ),
                            priority=3.0 - idx * 0.2,
                            target_heroes=[o.hero_name for o in lane_opponents],
                        )
                        recommendations.append(self._apply_upgrade_fields(rec, owned_display_by_lower, upgrade_graph))
                elif lane_status == LaneStatus.SNOWBALLING:
                    for idx, item in enumerate(self.rules.get("lane_snowball_items", [])):
                        rec = ItemRecommendation(
                            item_name=item["item_name"],
                            category=item["category"],
                            cost=int(item["cost"]),
                            section=RecommendationSection.DIRECT_MATCHUP,
                            reason=item["reason"].format(
                                item=item["item_name"],
                                lane_lead=_format_souls(lane_diff),
                                lane_enemy=lane_enemy_names,
                            ),
                            reason_en=item.get("reason_en", item["reason"]).format(
                                item=item["item_name"],
                                lane_lead_en=_format_souls_en(lane_diff),
                                lane_enemy=lane_enemy_names,
                            ),
                            priority=2.9 - idx * 0.2,
                            target_heroes=[o.hero_name for o in lane_opponents],
                        )
                        recommendations.append(self._apply_upgrade_fields(rec, owned_display_by_lower, upgrade_graph))

            lane_weights, lane_heroes = self._collect_threat_weights(lane_opponents, snowball_by_hero)
            lane_counters = self._build_counter_recs(
                lane_weights,
                lane_heroes,
                RecommendationSection.DIRECT_MATCHUP,
                owned_display_by_lower,
                upgrade_graph,
                balance,
                min_weight_override=1.0,
            )
            already_direct = {r.item_name.lower() for r in recommendations}
            for lc in lane_counters:
                if lc.item_name.lower() not in already_direct:
                    recommendations.append(lc)
                    already_direct.add(lc.item_name.lower())
                if len([r for r in recommendations if r.section == RecommendationSection.DIRECT_MATCHUP]) >= 5:
                    break

        # 2. Global Threats section
        any_fed = any(r.is_fed for r in snowball_reports)
        if match.match_minutes >= self.settings.early_lane_minutes or any_fed:
            global_weights, global_heroes = self._collect_threat_weights(match.enemies, snowball_by_hero)
            global_counters = self._build_counter_recs(
                global_weights,
                global_heroes,
                RecommendationSection.GLOBAL_THREATS,
                owned_display_by_lower,
                upgrade_graph,
                balance,
            )
            recommendations.extend(global_counters[:4])

        # 3. Evolving Core Items section
        core_recs = self._build_evolving_core(
            me, match, default_core_build, owned_display_by_lower, upgrade_graph, balance
        )
        recommendations.extend(core_recs)

        # 4. Situational Items section (counters + sustain gap injection)
        situational_weights, situational_heroes = self._collect_threat_weights(match.enemies, snowball_by_hero)
        all_counters = self._build_counter_recs(
            situational_weights,
            situational_heroes,
            RecommendationSection.SITUATIONAL_ITEMS,
            owned_display_by_lower,
            upgrade_graph,
            balance,
        )
        already_global_or_core = {
            r.item_name.lower()
            for r in recommendations
            if r.section in {RecommendationSection.GLOBAL_THREATS, RecommendationSection.CORE_ITEMS}
        }
        if balance.needs_sustain and "fortitude" not in already_global_or_core and "fortitude" not in owned_display_by_lower:
            sustain_rec = ItemRecommendation(
                item_name="Fortitude",
                category="Vitality",
                cost=3200,
                section=RecommendationSection.SITUATIONAL_ITEMS,
                reason="Aucun objet de soin/sustain (0) : ajoute de la tenue en fight.",
                reason_en="No healing/sustain item (0): add fight sustain.",
                priority=2.45,
            )
            recommendations.append(self._apply_upgrade_fields(sustain_rec, owned_display_by_lower, upgrade_graph))
            already_global_or_core.add("fortitude")

        for rec in all_counters:
            if rec.item_name.lower() not in already_global_or_core:
                recommendations.append(rec)
                already_global_or_core.add(rec.item_name.lower())

        # 5. Balanced Top Priority section
        top_priority_recs = self._build_top_priority(recommendations, len(owned_display_by_lower), balance)
        return top_priority_recs + recommendations
