const TRANSLATIONS = {
  fr: {
    navFeatures: "Fonctionnalités",
    navInstall: "Installation",
    navArch: "Architecture",
    navFaq: "FAQ",
    heroBadge: "100 % Externe • Zéro Lecture Mémoire • VAC-Safe",
    heroTitle: "Le companion temps réel pour adapter chaque item dans Deadlock.",
    heroSub:
      "Analyse instantanée lorsque tu maintiens TAB : lecture des âmes, détection des 12 héros même avec des skins personnalisés, calcul du Snowball ennemi et suivi complet de l'arbre d'améliorations sur ton second écran.",
    ctaInstall: "Installer en 2 min",
    ctaRepo: "Voir sur GitHub",
    mockPrioTitle: "🔥 Priorité absolue",
    mockUpgradeDesc: "Améliore Longue portée (0 slot en plus)",
    mockUpgradeBadge: "⬆ AMÉLIO 1 600",
    mockThreatDesc: "Contre Pocket (+5 000), Bebop, Seven",
    mockOwnedDesc: "Déjà détecté dans ton inventaire",
    mockOwnedBadge: "✔ ACHETÉ",
    featuresTitle: "Conçu pour de vraies parties de Deadlock",
    f1Title: "🛡 100 % VAC-Safe & Événementiel",
    f1Desc:
      "Aucune lecture mémoire ni injection DLL. L'OCR ne s'exécute que lorsque tu maintiens TAB (via mss + RapidOCR ONNX), gardant 0 % de charge CPU en combat.",
    f2Title: "🎨 Compatible DeadlockModManager",
    f2Desc:
      "Les mods de skins remplacent les portraits : le tracker lit donc le nom textuel des 12 héros (FR/EN + fuzzy matching) et le verrouille pour toute la partie.",
    f3Title: "⬆ Arbre d'améliorations & 12 slots",
    f3Desc:
      "Exploite le graphe officiel des composants pour repérer les améliorations gratuites en slots (⬆ AMÉLIO + coût net) et masquer les T1 obsolètes en late game.",
    f4Title: "📈 Snowball & Contres Multi-héros",
    f4Desc:
      "Détecte les ennemis fed par l'écart d'âmes à la moyenne et leurs spikes. Chaque counter liste tous les héros adverses qu'il neutralise.",
    f5Title: "🎯 Matchup direct & Priorité absolue",
    f5Desc:
      "Épingle tes adversaires de lane en 1 clic et suis la barre Priorité absolue pour connaître les 3–4 meilleurs achats immédiats.",
    f6Title: "🌐 Second Écran, Overlay & FR/EN",
    f6Desc:
      "Interface 4 colonnes sans scroll sur 1080p, mode Overlay compact, et switch instantané entre Français et Anglais (noms officiels Deadlock API inclus).",
    installTitle: "Installation & Lancement rapide (Windows)",
    s1Title: "1. Cloner et installer",
    s2Title: "2. Lancer le Companion",
    s2Note:
      "Ouvre ensuite http://127.0.0.1:8765 sur ton second écran, entre ton pseudo une fois et appuie sur TAB en jeu.",
    copyBtn: "Copier",
    copiedBtn: "Copié ✔",
    archTitle: "Architecture du pipeline temps réel",
    p1: "Écoute OS pynput + capture ciblée mss",
    p2: "RapidOCR (âmes/chrono/héros) + ItemMatcher (6×2 & 2×6)",
    p3: "deadlock-api.com + Snowball + Arbre d'améliorations",
    p4: "FastAPI WS /ws → React 4 colonnes (FR/EN)",
    docArchLink: "📘 Documentation Architecture",
    docCalibLink: "🎯 Guide de Calibration ROIs",
    docFaqLink: "❓ Documentation FAQ",
    faqTitle: "Questions fréquentes",
    q1: "Est-ce 100 % sans risque vis-à-vis du VAC ?",
    a1: "Oui. Aucune lecture mémoire (RPM), aucune DLL injectée et aucun fichier du jeu modifié. L'application analyse uniquement les pixels de ton écran quand tu appuies sur TAB.",
    q2: "Ça fonctionne avec des skins DeadlockModManager ?",
    a2: "Oui : la détection des héros ne dépend pas des portraits (qui peuvent être moddés), mais de l'OCR du nom de héros sous la carte avec correction fuzzy FR/EN.",
    q3: "Comment aligner les zones sur un autre format d'écran ?",
    a3: "Lance --image capture.png --dump-rois data/debug_captures pour visualiser les boîtes générées et ajuste les coordonnées normalisées dans backend/config/rois.json.",
    q4: "Pourquoi Valve GSI n'est-il pas utilisé ?",
    a4: "Valve n'a pas encore publié de Game State Integration pour Deadlock. Le code inclut déjà une interface abstraite MatchDataProvider prête pour le jour où il sera disponible.",
    footerNote: "MIT License • Projet open-source communautaire non affilié à Valve Corporation.",
  },
  en: {
    navFeatures: "Features",
    navInstall: "Install",
    navArch: "Architecture",
    navFaq: "FAQ",
    heroBadge: "100% External • Zero Memory Reading • VAC-Safe",
    heroTitle: "Real-time Deadlock companion to adapt your build every match.",
    heroSub:
      "Instant scan whenever you hold TAB: extracts souls, identifies all 12 heroes even with custom mod skins, tracks enemy Snowball, and evolves your upgrade tree on a second screen.",
    ctaInstall: "Install in 2 min",
    ctaRepo: "View on GitHub",
    mockPrioTitle: "🔥 Top Priority",
    mockUpgradeDesc: "Upgrades Long Range (0 extra slot)",
    mockUpgradeBadge: "⬆ UPGRADE 1,600",
    mockThreatDesc: "Vs Pocket (+5,000), Bebop, Seven",
    mockOwnedDesc: "Already detected in your inventory",
    mockOwnedBadge: "✔ OWNED",
    featuresTitle: "Built for real Deadlock matches",
    f1Title: "🛡 100% VAC-Safe & Event-Driven",
    f1Desc:
      "Zero memory reading or DLL injection. OCR runs only when holding TAB (mss + RapidOCR ONNX), keeping ~0% CPU overhead during fights.",
    f2Title: "🎨 DeadlockModManager Skin-Proof",
    f2Desc:
      "Custom skins replace hero portraits—so the tracker OCRs the text hero names (FR/EN + fuzzy matching) and locks them for the entire match.",
    f3Title: "⬆ Upgrade Tree & 12-Slot Aware",
    f3Desc:
      "Uses Deadlock's official component graph to highlight slot-free upgrades (⬆ UPGRADE + net cost) and filter obsolete T1 items in late game.",
    f4Title: "📈 Snowball & Multi-Hero Counters",
    f4Desc:
      "Flags fed enemies by soul lead over lobby average and power spikes. Every counter lists all enemy heroes it shuts down.",
    f5Title: "🎯 Direct Matchup & Top Priority",
    f5Desc:
      "Pin your direct lane opponents in 1 click and follow the Top Priority strip for the 3–4 highest-impact immediate purchases.",
    f6Title: "🌐 Second Screen, Overlay & FR/EN",
    f6Desc:
      "Zero-scroll 4-column layout at 1080p, compact Overlay toggle, and instant French / English switching with official Deadlock API item names.",
    installTitle: "Installation & Quickstart (Windows)",
    s1Title: "1. Clone & install",
    s2Title: "2. Start the Companion",
    s2Note:
      "Then open http://127.0.0.1:8765 on your second screen, enter your in-game name once, and hold TAB in Deadlock.",
    copyBtn: "Copy",
    copiedBtn: "Copied ✔",
    archTitle: "Real-Time Pipeline Architecture",
    p1: "OS TAB listener (pynput) + targeted mss capture",
    p2: "RapidOCR (souls/clock/heroes) + ItemMatcher (6×2 & 2×6)",
    p3: "deadlock-api.com + Snowball + Upgrade graph",
    p4: "FastAPI WS /ws → 4-column React UI (FR/EN)",
    docArchLink: "📘 Architecture Docs",
    docCalibLink: "🎯 ROI Calibration Guide",
    docFaqLink: "❓ FAQ Docs",
    faqTitle: "Frequently Asked Questions",
    q1: "Is this 100% safe from VAC bans?",
    a1: "Yes. No memory reading (RPM), no DLL injection, and no game file edits. It only captures screen pixels when you hold TAB.",
    q2: "Does it work with DeadlockModManager custom skins?",
    a2: "Yes: hero detection never relies on portraits. It reads the hero name text with FR/EN fuzzy matching.",
    q3: "How do I calibrate ROIs for ultrawide or HUD changes?",
    a3: "Run --image screenshot.png --dump-rois data/debug_captures to inspect the boxes and adjust normalized coordinates in backend/config/rois.json.",
    q4: "Why isn't Valve GSI used?",
    a4: "Valve has not exposed Game State Integration for Deadlock yet. The codebase already includes an abstract MatchDataProvider ready for future GSI support.",
    footerNote: "MIT License • Unofficial community open-source project, not affiliated with Valve Corporation.",
  },
};

function applyLanguage(lang) {
  const dict = TRANSLATIONS[lang] || TRANSLATIONS.fr;
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key && dict[key]) {
      el.textContent = dict[key];
    }
  });
  const btn = document.getElementById("lang-toggle");
  if (btn) {
    btn.textContent = lang === "fr" ? "FR 🇫🇷" : "EN 🇬🇧";
  }
}

let currentLang = localStorage.getItem("deadlock_docs_lang") === "en" ? "en" : "fr";
applyLanguage(currentLang);

const toggleBtn = document.getElementById("lang-toggle");
if (toggleBtn) {
  toggleBtn.addEventListener("click", () => {
    currentLang = currentLang === "fr" ? "en" : "fr";
    localStorage.setItem("deadlock_docs_lang", currentLang);
    applyLanguage(currentLang);
  });
}

document.querySelectorAll(".copy-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const targetId = btn.getAttribute("data-copy");
    const codeEl = targetId ? document.getElementById(targetId) : null;
    if (!codeEl) return;
    try {
      await navigator.clipboard.writeText(codeEl.textContent || "");
      btn.textContent = TRANSLATIONS[currentLang].copiedBtn;
      setTimeout(() => {
        btn.textContent = TRANSLATIONS[currentLang].copyBtn;
      }, 1600);
    } catch {
      // Clipboard blocked in restricted context
    }
  });
});
