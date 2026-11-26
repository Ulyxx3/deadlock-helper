import { FormEvent, useEffect, useState } from "react";
import type {
  AllItemsResponse,
  CompanionSnapshot,
  ItemRecommendation,
  RankedShopItem,
  RecommendationSectionName,
  UiLang,
} from "./types";

const UI_TEXT: Record<
  UiLang,
  {
    liveActive: string;
    manualMode: string;
    pseudoLabel: string;
    testImage: string;
    analyzing: string;
    resetMatch: string;
    overlayOn: string;
    overlayOff: string;
    waitingTitle: string;
    waitingBodyPre: string;
    waitingBodyPost: string;
    notSet: string;
    testNow: string;
    timer: string;
    yourHero: string;
    soulsUnit: string;
    slotMissing: string;
    slotMissingHint: string;
    inventoryLabel: string;
    slotsLabel: string;
    owned: string;
    evolved: string;
    upgrade: string;
    fromItem: string;
    lanePinHint: string;
    laneBadge: string;
    topPriorityTitle: string;
    deadSpectator: string;
    balanceDamageWarn: string;
    balanceSustainWarn: string;
    balanceDefenseWarn: string;
    allItemsBtn: string;
    modalTitle: string;
    modalSub: string;
    searchPlaceholder: string;
    allFilter: string;
    hideOwned: string;
    upgradesOnly: string;
    loadingAllItems: string;
    noMatchingItems: string;
    bdLabels: {
      meta: string;
      counter: string;
      upgrade: string;
      balance: string;
      phase: string;
    };
    emptySection: string;
    sections: Record<RecommendationSectionName, string>;
  }
> = {
  fr: {
    liveActive: "TAB Live (VAC-Safe)",
    manualMode: "Mode Manuel",
    pseudoLabel: "Pseudo",
    testImage: "Tester image.png",
    analyzing: "Analyse...",
    resetMatch: "Reset",
    overlayOn: "2nd Écran",
    overlayOff: "Overlay",
    waitingTitle: "En attente du tableau des scores (TAB)",
    waitingBodyPre: "Renseigne ton pseudo en jeu ci-dessus (",
    waitingBodyPost: "), puis maintiens TAB dans Deadlock pour analyser les 12 héros et les âmes.",
    notSet: "non défini",
    testNow: "Tester sur images/image.png",
    timer: "CHRONO",
    yourHero: "TON HÉROS",
    soulsUnit: "âmes",
    slotMissing: "SLOT NON DÉTECTÉ",
    slotMissingHint: "Pseudo exact requis",
    inventoryLabel: "Inventaire",
    slotsLabel: "slots",
    owned: "✔ ACHETÉ",
    evolved: "✔ ÉVOLUÉ",
    upgrade: "⬆ AMÉLIO",
    fromItem: "depuis",
    lanePinHint: "Cliquer sur un ennemi pour cibler ton matchup de lane",
    laneBadge: "LANE",
    topPriorityTitle: "🔥 Priorité absolue",
    deadSpectator: "☠ Mort / Spectateur (inventaire figé)",
    balanceDamageWarn: "Manque de dégâts",
    balanceSustainWarn: "Manque de soin / sustain",
    balanceDefenseWarn: "Aucune défense Vitality",
    allItemsBtn: "📊 Tous les items (%)",
    modalTitle: "Classement complet des items",
    modalSub: "items analysés selon ta partie",
    searchPlaceholder: "Rechercher un item...",
    allFilter: "Tous",
    hideOwned: "Masquer achetés",
    upgradesOnly: "⬆ Améliorations",
    loadingAllItems: "Calcul des scores...",
    noMatchingItems: "Aucun item ne correspond aux filtres.",
    bdLabels: {
      meta: "Méta",
      counter: "Contre",
      upgrade: "Amélio",
      balance: "Équilibre",
      phase: "Phase",
    },
    emptySection: "Aucune alerte prioritaire.",
    sections: {
      "Priorité absolue": "Priorité absolue",
      "Matchup direct": "Matchup direct",
      "Menaces globales": "Menaces globales",
      "Items Core": "Items Core",
      "Items Situationnels": "Situationnels",
    },
  },
  en: {
    liveActive: "TAB Live (VAC-Safe)",
    manualMode: "Manual Mode",
    pseudoLabel: "Player",
    testImage: "Test image.png",
    analyzing: "Scanning...",
    resetMatch: "Reset",
    overlayOn: "2nd Screen",
    overlayOff: "Overlay",
    waitingTitle: "Waiting for Scoreboard (TAB)",
    waitingBodyPre: "Enter your in-game name above (",
    waitingBodyPost: "), then hold TAB in Deadlock to scan all 12 heroes & souls.",
    notSet: "not set",
    testNow: "Test on images/image.png",
    timer: "TIMER",
    yourHero: "YOUR HERO",
    soulsUnit: "souls",
    slotMissing: "SLOT NOT FOUND",
    slotMissingHint: "Check exact player name",
    inventoryLabel: "Inventory",
    slotsLabel: "slots",
    owned: "✔ OWNED",
    evolved: "✔ EVOLVED",
    upgrade: "⬆ UPGRADE",
    fromItem: "from",
    lanePinHint: "Click an enemy to pin your direct lane matchup",
    laneBadge: "LANE",
    topPriorityTitle: "🔥 Top Priority",
    deadSpectator: "☠ Dead / Spectating (inventory locked)",
    balanceDamageWarn: "Low damage items",
    balanceSustainWarn: "Missing healing / sustain",
    balanceDefenseWarn: "No Vitality defense",
    allItemsBtn: "📊 All Items (%)",
    modalTitle: "Full Shop Item Ranking",
    modalSub: "items scored for this match",
    searchPlaceholder: "Search item...",
    allFilter: "All",
    hideOwned: "Hide owned",
    upgradesOnly: "⬆ Upgrades only",
    loadingAllItems: "Scoring all items...",
    noMatchingItems: "No items match current filters.",
    bdLabels: {
      meta: "Meta",
      counter: "Counter",
      upgrade: "Upgrade",
      balance: "Balance",
      phase: "Phase",
    },
    emptySection: "No urgent counter needed.",
    sections: {
      "Priorité absolue": "Top Priority",
      "Matchup direct": "Direct Matchup",
      "Menaces globales": "Global Threats",
      "Items Core": "Core Items",
      "Items Situationnels": "Situational",
    },
  },
};

const COLUMN_SECTIONS: RecommendationSectionName[] = [
  "Matchup direct",
  "Menaces globales",
  "Items Core",
  "Items Situationnels",
];

function formatNumber(amount: number, lang: UiLang): string {
  return amount.toLocaleString(lang === "fr" ? "fr-FR" : "en-US");
}

function categoryClass(category: string): string {
  const c = category.toLowerCase();
  if (c.includes("weapon")) return "cat-weapon";
  if (c.includes("vitality")) return "cat-vitality";
  if (c.includes("spirit")) return "cat-spirit";
  return "cat-core";
}

function ItemCard({
  item,
  lang,
  t,
  compactCard = false,
}: {
  item: ItemRecommendation;
  lang: UiLang;
  t: (typeof UI_TEXT)["fr"];
  compactCard?: boolean;
}) {
  const displayName = lang === "fr" ? item.item_name_fr || item.item_name : item.item_name;
  const displayReason = lang === "fr" ? item.reason : item.reason_en || item.reason;
  const status = item.upgrade_status || (item.already_owned ? "owned" : "new");
  const isDone = status === "owned" || status === "evolved";
  const isUpgrade = status === "upgrade_ready";
  const price = item.net_cost !== undefined && isUpgrade ? item.net_cost : item.cost;
  const fromName =
    lang === "fr"
      ? item.upgrades_from_owned_fr || item.upgrades_from_owned
      : item.upgrades_from_owned;

  return (
    <article
      className={`item-card ${categoryClass(item.category)} ${isDone ? "is-owned" : ""} ${
        isUpgrade ? "is-upgrade" : ""
      } ${compactCard ? "priority-card" : ""}`}
    >
      <div className="item-icon-wrap">
        {item.icon_url ? (
          <img
            src={item.icon_url}
            alt={displayName}
            className="item-icon"
            loading="lazy"
          />
        ) : (
          <div className="item-icon-fallback">{displayName.slice(0, 2)}</div>
        )}
      </div>

      <div className="item-body">
        <div className="item-header">
          <strong className="item-title" title={displayName}>
            {displayName}
          </strong>
          <div className="item-badges">
            {status === "evolved" ? (
              <span className="owned-pill">{t.evolved}</span>
            ) : status === "owned" ? (
              <span className="owned-pill">{t.owned}</span>
            ) : isUpgrade ? (
              <>
                <span className="upgrade-pill" title={fromName ? `${t.fromItem} ${fromName}` : ""}>
                  {t.upgrade}
                </span>
                <span className="cost-pill">{formatNumber(price, lang)}</span>
              </>
            ) : (
              <span className="cost-pill">{formatNumber(price, lang)}</span>
            )}
          </div>
        </div>
        <p className="item-reason">{displayReason}</p>
      </div>
    </article>
  );
}

function AllItemsModal({
  data,
  loading,
  lang,
  t,
  onClose,
}: {
  data: AllItemsResponse | null;
  loading: boolean;
  lang: UiLang;
  t: (typeof UI_TEXT)["fr"];
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const [catFilter, setCatFilter] = useState<"ALL" | "Weapon" | "Vitality" | "Spirit">("ALL");
  const [tierFilter, setTierFilter] = useState<number>(0);
  const [hideOwned, setHideOwned] = useState(false);
  const [upgradesOnly, setUpgradesOnly] = useState(false);

  const items: RankedShopItem[] = data?.items ?? [];
  const q = search.trim().toLowerCase();
  const filtered = items.filter((item) => {
    if (catFilter !== "ALL" && item.category !== catFilter) return false;
    if (tierFilter !== 0 && item.tier !== tierFilter) return false;
    if (hideOwned && item.already_owned) return false;
    if (upgradesOnly && item.upgrade_status !== "upgrade_ready") return false;
    if (q) {
      const en = item.item_name.toLowerCase();
      const fr = (item.item_name_fr || "").toLowerCase();
      if (!en.includes(q) && !fr.includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h2>{t.modalTitle}</h2>
            <span className="modal-sub">
              {filtered.length}/{items.length} {t.modalSub}
              {data?.match_timer_display ? ` • ${data.match_timer_display}` : ""}
            </span>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-filters">
          <input
            type="text"
            className="modal-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t.searchPlaceholder}
          />

          <div className="filter-group">
            {(["ALL", "Weapon", "Vitality", "Spirit"] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                className={`filter-pill ${catFilter === cat ? "active" : ""}`}
                onClick={() => setCatFilter(cat)}
              >
                {cat === "ALL" ? t.allFilter : cat}
              </button>
            ))}
          </div>

          <div className="filter-group">
            {[0, 1, 2, 3, 4].map((tier) => (
              <button
                key={tier}
                type="button"
                className={`filter-pill ${tierFilter === tier ? "active" : ""}`}
                onClick={() => setTierFilter(tier)}
              >
                {tier === 0 ? t.allFilter : `T${tier}`}
              </button>
            ))}
          </div>

          <label className="toggle-check">
            <input
              type="checkbox"
              checked={hideOwned}
              onChange={(e) => setHideOwned(e.target.checked)}
            />
            <span>{t.hideOwned}</span>
          </label>

          <label className="toggle-check">
            <input
              type="checkbox"
              checked={upgradesOnly}
              onChange={(e) => setUpgradesOnly(e.target.checked)}
            />
            <span>{t.upgradesOnly}</span>
          </label>
        </div>

        <div className="ranked-list">
          {loading && items.length === 0 ? (
            <p className="empty-note">{t.loadingAllItems}</p>
          ) : filtered.length === 0 ? (
            <p className="empty-note">{t.noMatchingItems}</p>
          ) : (
            filtered.map((item, idx) => {
              const displayName =
                lang === "fr" ? item.item_name_fr || item.item_name : item.item_name;
              const displayReason =
                lang === "fr" ? item.reason : item.reason_en || item.reason;
              const pctClass =
                item.score_pct >= 75 ? "high" : item.score_pct >= 50 ? "mid" : "low";
              const bdEntries = (
                [
                  ["meta", item.breakdown.meta],
                  ["counter", item.breakdown.counter],
                  ["upgrade", item.breakdown.upgrade],
                  ["balance", item.breakdown.balance],
                  ["phase", item.breakdown.phase],
                ] as const
              ).filter(([, val]) => val !== 0);

              return (
                <div
                  key={item.item_name}
                  className={`ranked-row ${categoryClass(item.category)} ${
                    item.already_owned ? "is-owned" : ""
                  }`}
                >
                  <span className="rank-num">#{idx + 1}</span>
                  <div className="item-icon-wrap">
                    {item.icon_url ? (
                      <img
                        src={item.icon_url}
                        alt={displayName}
                        className="item-icon"
                        loading="lazy"
                      />
                    ) : (
                      <div className="item-icon-fallback">{displayName.slice(0, 2)}</div>
                    )}
                  </div>

                  <div className="ranked-main">
                    <div className="ranked-top">
                      <strong className="ranked-name">{displayName}</strong>
                      <span className="tier-tag">T{item.tier}</span>
                      {item.upgrade_status === "evolved" ? (
                        <span className="owned-pill">{t.evolved}</span>
                      ) : item.upgrade_status === "owned" ? (
                        <span className="owned-pill">{t.owned}</span>
                      ) : item.upgrade_status === "upgrade_ready" ? (
                        <>
                          <span className="upgrade-pill">{t.upgrade}</span>
                          <span className="cost-pill">{formatNumber(item.net_cost, lang)}</span>
                        </>
                      ) : (
                        <span className="cost-pill">{formatNumber(item.cost, lang)}</span>
                      )}
                    </div>
                    <p className="ranked-reason">{displayReason}</p>
                    <div className="breakdown-pills">
                      {bdEntries.map(([key, val]) => (
                        <span key={key} className={`bd-pill ${val < 0 ? "neg" : ""}`}>
                          {t.bdLabels[key]} {val > 0 ? `+${val}` : val}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="ranked-score-col">
                    <span className={`pct-value ${pctClass}`}>{item.score_pct}%</span>
                    <div className="pct-bar-track">
                      <div
                        className="pct-bar-fill"
                        style={{ width: `${item.score_pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [snapshot, setSnapshot] = useState<CompanionSnapshot | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [pseudoInput, setPseudoInput] = useState("");
  const [compactMode, setCompactMode] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showAllItemsModal, setShowAllItemsModal] = useState(false);
  const [allItemsData, setAllItemsData] = useState<AllItemsResponse | null>(null);
  const [allItemsLoading, setAllItemsLoading] = useState(false);
  const [lang, setLang] = useState<UiLang>(() => {
    const saved = window.localStorage.getItem("deadlock_helper_lang");
    return saved === "en" ? "en" : "fr";
  });

  const t = UI_TEXT[lang];

  const toggleLang = () => {
    setLang((prev) => {
      const next: UiLang = prev === "fr" ? "en" : "fr";
      window.localStorage.setItem("deadlock_helper_lang", next);
      return next;
    });
  };

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;

    const loadInitial = async () => {
      try {
        const res = await fetch("/api/state");
        if (res.ok && active) {
          const data: CompanionSnapshot = await res.json();
          setSnapshot(data);
          if (data.player_pseudo) {
            setPseudoInput(data.player_pseudo);
          }
        }
      } catch {
        // WebSocket retry will populate state once backend is up
      }
    };

    const connectWs = () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${proto}//${window.location.host}/ws`);
      socket.onopen = () => {
        if (active) setWsConnected(true);
      };
      socket.onmessage = (evt) => {
        if (!active) return;
        const data: CompanionSnapshot = JSON.parse(evt.data);
        setSnapshot(data);
        if (data.player_pseudo) {
          setPseudoInput((prev) => prev || data.player_pseudo || "");
        }
      };
      socket.onclose = () => {
        if (!active) return;
        setWsConnected(false);
        retryTimer = window.setTimeout(connectWs, 1500);
      };
    };

    void loadInitial();
    connectWs();

    return () => {
      active = false;
      if (retryTimer) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!showAllItemsModal) return;
    let active = true;
    const fetchAll = async () => {
      setAllItemsLoading(true);
      try {
        const res = await fetch("/api/all-items");
        if (res.ok && active) {
          setAllItemsData(await res.json());
        }
      } finally {
        if (active) setAllItemsLoading(false);
      }
    };
    void fetchAll();

    const onKeyDown = (evt: KeyboardEvent) => {
      if (evt.key === "Escape") setShowAllItemsModal(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      active = false;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [showAllItemsModal, snapshot?.updated_at]);

  const handleSavePseudo = async (e: FormEvent) => {
    e.preventDefault();
    if (!pseudoInput.trim()) return;
    setBusyAction("pseudo");
    setErrorMsg(null);
    try {
      const res = await fetch("/api/player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: pseudoInput.trim() }),
      });
      if (!res.ok) throw new Error("Failed to save player name");
      const data: CompanionSnapshot = await res.json();
      setSnapshot(data);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setBusyAction(null);
    }
  };

  const handleToggleLaneEnemy = async (heroName: string) => {
    const current = snapshot?.pinned_lane_opponents ?? [];
    const exists = current.some((h) => h.toLowerCase() === heroName.toLowerCase());
    const next = exists
      ? current.filter((h) => h.toLowerCase() !== heroName.toLowerCase())
      : [...current, heroName].slice(-2);
    try {
      const res = await fetch("/api/lane-opponents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ heroes: next }),
      });
      if (res.ok) {
        setSnapshot(await res.json());
      }
    } catch {
      // ignore transient network errors
    }
  };

  const handleTestImage = async () => {
    setBusyAction("image");
    setErrorMsg(null);
    try {
      const res = await fetch("/api/test-image", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "images/image.png not found");
      }
      const data: CompanionSnapshot = await res.json();
      setSnapshot(data);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Image scan failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleResetMatch = async () => {
    setBusyAction("reset");
    setErrorMsg(null);
    try {
      const res = await fetch("/api/reset-match", { method: "POST" });
      if (res.ok) {
        setSnapshot(await res.json());
      }
    } finally {
      setBusyAction(null);
    }
  };

  const amberTotal = snapshot?.team_totals.amber_hand ?? 0;
  const sapphireTotal = snapshot?.team_totals.sapphire_flame ?? 0;
  const sumSouls = Math.max(1, amberTotal + sapphireTotal);
  const amberPct = Math.round((amberTotal / sumSouls) * 100);
  const slotsUsed = snapshot?.inventory_slots_used ?? snapshot?.self_player?.items.length ?? 0;
  const slotsMax = snapshot?.inventory_slots_max ?? 12;
  const pinnedLanes = new Set(
    (snapshot?.pinned_lane_opponents ?? []).map((h) => h.toLowerCase())
  );
  const topPriorityItems = snapshot?.sections["Priorité absolue"] ?? [];

  return (
    <div className={`app-shell ${compactMode ? "compact-mode" : ""}`}>
      <header className="topbar">
        <div className="brand-block">
          <span className={`live-dot ${wsConnected ? "online" : "offline"}`} />
          <h1>DEADLOCK HELPER</h1>
          <span className="sub-tag">
            {snapshot?.live_enabled ? t.liveActive : t.manualMode}
          </span>
        </div>

        <form className="pseudo-form" onSubmit={handleSavePseudo}>
          <label htmlFor="pseudo-input">{t.pseudoLabel}</label>
          <input
            id="pseudo-input"
            type="text"
            value={pseudoInput}
            onChange={(e) => setPseudoInput(e.target.value)}
            placeholder="Ulyxx3"
          />
          <button type="submit" disabled={busyAction !== null}>
            OK
          </button>
        </form>

        <div className="actions-bar">
          <button
            type="button"
            className="btn-accent"
            onClick={handleTestImage}
            disabled={busyAction !== null}
          >
            {busyAction === "image" ? t.analyzing : t.testImage}
          </button>
          <button
            type="button"
            onClick={() => setShowAllItemsModal(true)}
            disabled={!snapshot || snapshot.status !== "ready"}
          >
            {t.allItemsBtn}
          </button>
          <button
            type="button"
            onClick={handleResetMatch}
            disabled={busyAction !== null}
          >
            {t.resetMatch}
          </button>
          <button
            type="button"
            className={compactMode ? "btn-active" : ""}
            onClick={() => setCompactMode((v) => !v)}
          >
            {compactMode ? t.overlayOn : t.overlayOff}
          </button>
          <button
            type="button"
            className="btn-lang"
            onClick={toggleLang}
            title="Switch FR / EN"
          >
            {lang === "fr" ? "FR 🇫🇷" : "EN 🇬🇧"}
          </button>
        </div>
      </header>

      {errorMsg && <div className="error-banner">{errorMsg}</div>}

      {!snapshot || snapshot.status === "waiting_for_tab" ? (
        <main className="waiting-panel">
          <div className="waiting-card">
            <h2>{t.waitingTitle}</h2>
            <p>
              {t.waitingBodyPre}
              <strong>{snapshot?.player_pseudo || t.notSet}</strong>
              {t.waitingBodyPost}
            </p>
            <button type="button" className="btn-accent" onClick={handleTestImage}>
              {t.testNow}
            </button>
          </div>
        </main>
      ) : (
        <main className="dashboard">
          <section className="hud-strip">
            <div className="summary-pills">
              <div className="stat-pill">
                <span className="label">{t.timer}</span>
                <strong>{snapshot.match_timer_display}</strong>
              </div>

              {snapshot.self_player ? (
                <div className="stat-pill">
                  <span className="label">{t.yourHero}</span>
                  <strong>
                    {snapshot.self_player.hero_name}{" "}
                    <span className="souls-text">
                      {formatNumber(snapshot.self_player.souls, lang)} {t.soulsUnit}
                    </span>
                  </strong>
                </div>
              ) : (
                <div className="stat-pill warn">
                  <span className="label">{t.slotMissing}</span>
                  <strong>{t.slotMissingHint}</strong>
                </div>
              )}

              <span className={`slots-pill ${slotsUsed >= 10 ? "slots-tight" : ""}`}>
                {slotsUsed}/{slotsMax} {t.slotsLabel}
              </span>

              {snapshot.self_is_dead && (
                <span className="dead-pill">{t.deadSpectator}</span>
              )}

              {snapshot.build_balance && (
                <div className="balance-pills">
                  <span
                    className={`bal-pill ${snapshot.build_balance.needs_damage ? "bal-warn" : ""}`}
                    title={snapshot.build_balance.needs_damage ? t.balanceDamageWarn : "Weapon"}
                  >
                    ⚔ {snapshot.build_balance.weapon_count}
                  </span>
                  <span
                    className={`bal-pill ${snapshot.build_balance.needs_damage ? "bal-warn" : ""}`}
                    title={snapshot.build_balance.needs_damage ? t.balanceDamageWarn : "Spirit"}
                  >
                    ✨ {snapshot.build_balance.spirit_count}
                  </span>
                  <span
                    className={`bal-pill ${snapshot.build_balance.needs_defense ? "bal-warn" : ""}`}
                    title={snapshot.build_balance.needs_defense ? t.balanceDefenseWarn : "Vitality"}
                  >
                    🛡 {snapshot.build_balance.vitality_count}
                  </span>
                  <span
                    className={`bal-pill ${snapshot.build_balance.needs_sustain ? "bal-warn" : ""}`}
                    title={snapshot.build_balance.needs_sustain ? t.balanceSustainWarn : "Sustain"}
                  >
                    🩸 {snapshot.build_balance.sustain_count}
                    {snapshot.build_balance.needs_sustain ? " ⚠" : ""}
                  </span>
                </div>
              )}

              <div className="team-bar-box">
                <div className="team-bar-labels">
                  <span className="amber-text">Amber {formatNumber(amberTotal, lang)}</span>
                  <span className="sapphire-text">Sapphire {formatNumber(sapphireTotal, lang)}</span>
                </div>
                <div className="team-bar-track">
                  <div className="team-bar-amber" style={{ width: `${amberPct}%` }} />
                </div>
              </div>
            </div>

            {snapshot.self_player && snapshot.self_player.items.length > 0 && (
              <div className="inventory-inline">
                <span className="strip-title">{t.inventoryLabel}:</span>
                <div className="inventory-chips">
                  {snapshot.self_player.items.map((item) => {
                    const label = lang === "fr" ? item.name_fr || item.name : item.name;
                    return (
                      <div key={item.name} className="inv-chip" title={label}>
                        {item.icon_url && <img src={item.icon_url} alt={label} />}
                        <span>{label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>

          {snapshot.snowball_reports.length > 0 && (
            <section className="snowball-strip" title={t.lanePinHint}>
              {snapshot.snowball_reports.map((rep, i) => {
                const isLane = pinnedLanes.has(rep.hero_name.toLowerCase());
                return (
                  <button
                    type="button"
                    key={`${rep.hero_name}-${i}`}
                    onClick={() => handleToggleLaneEnemy(rep.hero_name)}
                    className={`snowball-card ${rep.is_fed ? "is-fed" : ""} ${
                      isLane ? "is-lane" : ""
                    }`}
                  >
                    <div className="snowball-top">
                      <strong>{rep.hero_name}</strong>
                      <div className="snowball-flags">
                        {isLane && <span className="lane-badge">{t.laneBadge}</span>}
                        {rep.is_fed && <span className="fed-badge">FED</span>}
                      </div>
                    </div>
                    <div className="snowball-meta">
                      <span className="souls-text">{formatNumber(rep.souls, lang)}</span>
                      <span className={rep.souls_gap_vs_avg >= 0 ? "gap-pos" : "gap-neg"}>
                        {rep.souls_gap_vs_avg >= 0 ? "+" : ""}
                        {formatNumber(rep.souls_gap_vs_avg, lang)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </section>
          )}

          {topPriorityItems.length > 0 && (
            <section className="priority-strip">
              <div className="priority-header">
                <h2>{t.topPriorityTitle}</h2>
              </div>
              <div className="priority-grid">
                {topPriorityItems.map((item) => (
                  <ItemCard
                    key={`prio-${item.item_name}`}
                    item={item}
                    lang={lang}
                    t={t}
                    compactCard
                  />
                ))}
              </div>
            </section>
          )}

          <section className="recommendations-grid">
            {COLUMN_SECTIONS.map((key) => {
              const items = snapshot.sections[key] ?? [];
              return (
                <div key={key} className="rec-panel">
                  <div className="panel-header">
                    <h2>{t.sections[key]}</h2>
                    <span className="count-badge">{items.length}</span>
                  </div>
                  <div className="panel-list">
                    {items.length === 0 ? (
                      <p className="empty-note">{t.emptySection}</p>
                    ) : (
                      items.map((item) => (
                        <ItemCard
                          key={`${key}-${item.item_name}`}
                          item={item}
                          lang={lang}
                          t={t}
                        />
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </section>
        </main>
      )}

      {showAllItemsModal && (
        <AllItemsModal
          data={allItemsData}
          loading={allItemsLoading}
          lang={lang}
          t={t}
          onClose={() => setShowAllItemsModal(false)}
        />
      )}
    </div>
  );
}
