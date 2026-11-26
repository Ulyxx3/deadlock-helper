export type RecommendationSectionName =
  | "Priorité absolue"
  | "Matchup direct"
  | "Menaces globales"
  | "Items Core"
  | "Items Situationnels";

export type UiLang = "fr" | "en";

export type UpgradeStatus = "new" | "upgrade_ready" | "owned" | "evolved";

export interface DetectedItem {
  name: string;
  name_fr?: string;
  icon_url: string | null;
}

export interface PlayerSnapshot {
  slot_index: number;
  team: "amber_hand" | "sapphire_flame";
  hero_name: string;
  player_name: string;
  souls: number;
  is_self: boolean;
  items: DetectedItem[];
}

export interface SnowballReport {
  hero_name: string;
  souls: number;
  souls_gap_vs_avg: number;
  snowball_score: number;
  is_fed: boolean;
  key_items: string[];
}

export interface ItemRecommendation {
  item_name: string;
  item_name_fr?: string;
  category: string;
  cost: number;
  net_cost?: number;
  reason: string;
  reason_en?: string;
  priority: number;
  already_owned: boolean;
  upgrade_status?: UpgradeStatus;
  upgrades_from_owned?: string | null;
  upgrades_from_owned_fr?: string | null;
  target_heroes?: string[];
  icon_url: string | null;
}

export interface BuildBalance {
  weapon_count: number;
  spirit_count: number;
  vitality_count: number;
  sustain_count: number;
  needs_damage: boolean;
  needs_sustain: boolean;
  needs_defense: boolean;
}

export interface CompanionSnapshot {
  status: "waiting_for_tab" | "ready";
  source: "idle" | "live_tab" | "test_image";
  live_enabled: boolean;
  player_pseudo: string | null;
  self_is_dead?: boolean;
  pinned_lane_opponents?: string[];
  inventory_slots_used?: number;
  inventory_slots_max?: number;
  build_balance?: BuildBalance | null;
  updated_at: number;
  match_minutes: number;
  match_timer_display: string;
  lane_status: "snowballing" | "even" | "behind";
  team_totals: {
    amber_hand: number;
    sapphire_flame: number;
  };
  self_player: {
    slot_index: number;
    hero_name: string;
    player_name: string;
    team: "amber_hand" | "sapphire_flame";
    souls: number;
    items: DetectedItem[];
  } | null;
  players: PlayerSnapshot[];
  snowball_reports: SnowballReport[];
  sections: Record<RecommendationSectionName, ItemRecommendation[]>;
}

export interface ScoreBreakdown {
  meta: number;
  counter: number;
  upgrade: number;
  balance: number;
  phase: number;
}

export interface RankedShopItem {
  item_name: string;
  item_name_fr?: string;
  category: string;
  tier: number;
  cost: number;
  net_cost: number;
  score_pct: number;
  upgrade_status: UpgradeStatus;
  upgrades_from_owned?: string | null;
  upgrades_from_owned_fr?: string | null;
  already_owned: boolean;
  target_heroes: string[];
  reason: string;
  reason_en?: string;
  icon_url: string | null;
  breakdown: ScoreBreakdown;
}

export interface AllItemsResponse {
  status: "waiting_for_tab" | "ready";
  match_timer_display?: string;
  total_items: number;
  items: RankedShopItem[];
}
