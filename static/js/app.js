/**
 * Rockola kiosk UI — 1280×800 táctil.
 * Sin librerías externas. WebSockets + teclado virtual + cola.
 */

(() => {
  "use strict";

  const MAX_DURATION = 600;

  const els = {
    credits: document.getElementById("credits-count"),
    creditsPanel: document.getElementById("credits-panel"),
    searchInput: document.getElementById("search-input"),
    searchBtn: document.getElementById("search-btn"),
    topBtn: document.getElementById("top-btn"),
    results: document.getElementById("results"),
    resultsPane: document.querySelector(".results-pane"),
    resultsTitle: document.getElementById("results-title"),
    queueList: document.getElementById("queue-list"),
    queuePane: document.getElementById("queue-panel"),
    state: document.getElementById("player-state"),
    nowTitle: document.getElementById("now-title"),
    hint: document.getElementById("status-hint"),
    toast: document.getElementById("toast"),
    keyboard: document.getElementById("keyboard"),
  };

  let credits = 0;
  let shift = false;
  let searching = false;
  let toastTimer = 0;
  let keyboardTarget = true;

  // Escala el layout 1280×800 para llenar la pantalla táctil real
  function fitKioskToScreen() {
    const root = document.getElementById("scale-root");
    const kiosk = document.getElementById("kiosk");
    if (!root || !kiosk) return;
    const sw = window.innerWidth || 1280;
    const sh = window.innerHeight || 800;
    const scale = Math.min(sw / 1280, sh / 800);
    const ox = Math.max(0, (sw - 1280 * scale) / 2);
    const oy = Math.max(0, (sh - 800 * scale) / 2);
    kiosk.style.transformOrigin = "top left";
    kiosk.style.transform = `translate(${ox}px, ${oy}px) scale(${scale})`;
  }

  document.body.classList.add("lite");
  fitKioskToScreen();
  window.addEventListener("resize", fitKioskToScreen);
  window.addEventListener("orientationchange", fitKioskToScreen);

  // ---------------------------------------------------------------------------
  // Bloqueo kiosk
  // ---------------------------------------------------------------------------

  const blockEvent = (e) => {
    e.preventDefault();
    e.stopPropagation();
    return false;
  };

  document.addEventListener("contextmenu", blockEvent, true);
  document.addEventListener("selectstart", blockEvent, true);
  document.addEventListener("dragstart", blockEvent, true);
  document.addEventListener("copy", blockEvent, true);
  document.addEventListener("cut", blockEvent, true);
  document.addEventListener("paste", blockEvent, true);

  window.addEventListener(
    "keydown",
    (e) => {
      const key = e.key;
      const blocked =
        key === "F5" ||
        key === "F11" ||
        key === "F12" ||
        key === "Escape" ||
        (e.altKey && (key === "F4" || key === "Tab")) ||
        (e.ctrlKey &&
          ["r", "R", "w", "W", "n", "N", "t", "T", "u", "U", "p", "P", "s", "S"].includes(
            key
          )) ||
        (e.ctrlKey && e.shiftKey && ["i", "I", "j", "J", "c", "C"].includes(key));

      // El teclado físico no debe escribir en el input (usamos virtual)
      if (document.activeElement === els.searchInput && !blocked) {
        e.preventDefault();
        return;
      }

      if (blocked) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
    true
  );

  // ---------------------------------------------------------------------------
  // Toast / créditos UI
  // ---------------------------------------------------------------------------

  function showToast(message, isError = false) {
    els.toast.hidden = false;
    els.toast.textContent = message;
    els.toast.classList.toggle("error", isError);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.hidden = true;
    }, 2800);
  }

  function setCredits(value) {
    const next = Number(value) || 0;
    const changed = next !== credits;
    credits = next;
    els.credits.textContent = String(credits);
    if (changed) {
      els.creditsPanel.classList.remove("pulse");
      // reflow para reiniciar animación
      void els.creditsPanel.offsetWidth;
      els.creditsPanel.classList.add("pulse");
      setTimeout(() => els.creditsPanel.classList.remove("pulse"), 220);
    }
    els.hint.textContent =
      credits > 0
        ? "Toca una canción elegible para añadirla a la cola"
        : "Inserta fichas para seleccionar canciones";
  }

  function setState(state) {
    const label = String(state || "idle").toUpperCase();
    els.state.textContent = label;
  }

  function setNowPlaying(track, state) {
    if (track && track.titulo) {
      els.nowTitle.textContent = track.titulo;
      return;
    }
    if (String(state).toLowerCase() === "idle") {
      els.nowTitle.textContent = "Música de ambiente";
    } else {
      els.nowTitle.textContent = "—";
    }
  }

  // ---------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------

  async function refreshCredits() {
    try {
      const res = await fetch("/api/credits");
      const data = await res.json();
      setCredits(data.creditos_disponibles);
    } catch (_) {
      /* offline momentáneo */
    }
  }

  async function refreshQueue() {
    try {
      const res = await fetch("/api/queue");
      const data = await res.json();
      applyQueuePayload(data);
    } catch (_) {
      /* ignore */
    }
  }

  function applyQueuePayload(data) {
    setState(data.state);
    setNowPlaying(data.current, data.state);
    renderQueue(data.queue || []);
    if (data.mpv_available === false) {
      els.hint.textContent = "Instala mpv (winget install shinchiro.mpv) y reinicia el servidor";
    }
  }

  async function doSearch() {
    const query = els.searchInput.value.trim();
    if (!query || searching) return;
    searching = true;
    els.resultsTitle.textContent = `Buscando “${query}”…`;
    els.resultsPane.classList.remove("is-empty");
    els.results.innerHTML =
      '<div class="empty-hint" style="display:block;position:relative;padding:28px">Buscando…</div>';
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: 8 }),
      });
      const data = await res.json();
      els.resultsTitle.textContent = `Resultados · “${query}”`;
      renderResults(data.results || [], { mode: "search" });
    } catch (_) {
      els.resultsTitle.textContent = "Búsqueda";
      showToast("No se pudo buscar. Revisa la conexión.", true);
      renderResults([]);
    } finally {
      searching = false;
    }
  }

  async function loadTop() {
    els.resultsTitle.textContent = "🔥 Las Más Sonadas";
    try {
      const res = await fetch("/api/top");
      const data = await res.json();
      const items = (data.top || []).map((item, index) => ({
        ...item,
        // Temas ya sonados se consideran seleccionables
        elegible: true,
        duration_formatted: item.reproducciones
          ? `${item.reproducciones} plays`
          : "",
        _rank: index + 1,
      }));
      renderResults(items, { mode: "top" });
    } catch (_) {
      showToast("No se pudo cargar el ranking.", true);
    }
  }

  async function enqueueSong(item) {
    if (!item) return;
    const elegible =
      item.elegible === true ||
      (item.duration_seconds != null && item.duration_seconds <= MAX_DURATION);

    if (!elegible) {
      showToast("Supera 10 min — no se puede seleccionar", true);
      return;
    }
    if (credits < 1) {
      showToast("No hay fichas disponibles", true);
      return;
    }

    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_youtube: item.id_youtube,
          titulo: item.titulo,
          miniatura: item.miniatura || "",
          duration_seconds: item.duration_seconds ?? 0,
        }),
      });
      const data = await res.json();
      if (data.creditos_disponibles != null) {
        setCredits(data.creditos_disponibles);
      }
      if (!data.ok) {
        const msg =
          data.detail ||
          (data.error === "no_credits"
            ? "No hay fichas disponibles"
            : "No se pudo encolar la canción");
        showToast(msg, true);
        return;
      }
      if (data.queue) renderQueue(data.queue);
      if (data.state) setState(data.state);
      showToast(`Añadida: ${item.titulo}`);
    } catch (_) {
      showToast("Error al añadir a la cola", true);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  function renderResults(items, { mode } = { mode: "search" }) {
    els.results.innerHTML = "";
    const list = Array.isArray(items) ? items : [];
    els.resultsPane.classList.toggle("is-empty", list.length === 0);

    for (const item of list) {
      const durationSec =
        item.duration_seconds != null ? Number(item.duration_seconds) : null;
      const elegible =
        mode === "top"
          ? true
          : item.elegible === true ||
            (durationSec != null && durationSec <= MAX_DURATION);
      const blocked = !elegible;

      const card = document.createElement("article");
      card.className = "card" + (blocked ? " disabled" : "");
      card.dataset.id = item.id_youtube || "";

      const thumb = document.createElement("div");
      thumb.className = "card-thumb";
      if (item.miniatura) {
        thumb.style.backgroundImage = `url("${item.miniatura}")`;
      }

      if (item.duration_formatted) {
        const dur = document.createElement("span");
        dur.className = "card-duration";
        dur.textContent = item.duration_formatted;
        thumb.appendChild(dur);
      }

      if (blocked) {
        const badge = document.createElement("div");
        badge.className = "badge-blocked";
        badge.textContent = "Supera 10 min";
        thumb.appendChild(badge);
      }

      const body = document.createElement("div");
      body.className = "card-body";

      const title = document.createElement("div");
      title.className = "card-title";
      title.textContent = item.titulo || item.id_youtube || "Sin título";

      const meta = document.createElement("div");
      meta.className = "card-meta";
      if (mode === "top" && item._rank) {
        meta.textContent = `#${item._rank} · ${item.reproducciones || 0} reproducciones`;
      } else {
        meta.textContent = elegible ? "Toca para seleccionar" : "No disponible";
      }

      body.appendChild(title);
      body.appendChild(meta);
      card.appendChild(thumb);
      card.appendChild(body);

      if (!blocked) {
        card.addEventListener("click", () => enqueueSong(item));
      }

      els.results.appendChild(card);
    }
  }

  function renderQueue(queue) {
    const list = Array.isArray(queue) ? queue : [];
    els.queueList.innerHTML = "";
    els.queuePane.classList.toggle("is-empty", list.length === 0);

    list.forEach((item, index) => {
      const li = document.createElement("li");

      const num = document.createElement("span");
      num.className = "queue-num";
      num.textContent = String(index + 1);

      const song = document.createElement("span");
      song.className = "queue-song";
      song.textContent = item.titulo || item.id_youtube || "Canción";

      li.appendChild(num);
      li.appendChild(song);
      els.queueList.appendChild(li);
    });
  }

  // ---------------------------------------------------------------------------
  // Teclado táctil virtual
  // ---------------------------------------------------------------------------

  const KB_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ"],
    ["⇧", "z", "x", "c", "v", "b", "n", "m", "⌫"],
    ["ESPACIO", "BUSCAR"],
  ];

  function buildKeyboard() {
    const rows = els.keyboard.querySelectorAll(".kb-row");
    rows.forEach((rowEl) => {
      rowEl.innerHTML = "";
      const idx = Number(rowEl.dataset.row) - 1;
      const keys = KB_ROWS[idx] || [];
      keys.forEach((key) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "kb-key";
        btn.dataset.key = key;

        if (key === "ESPACIO") {
          btn.classList.add("wide", "space");
          btn.textContent = "espacio";
        } else if (key === "BUSCAR") {
          btn.classList.add("wide", "accent");
          btn.textContent = "Buscar";
        } else if (key === "⌫") {
          btn.classList.add("wide", "danger");
          btn.textContent = "⌫";
        } else if (key === "⇧") {
          btn.classList.add("wide", "accent");
          btn.textContent = "⇧";
        } else {
          btn.textContent = shift && /[a-zñ]/.test(key) ? key.toUpperCase() : key;
        }

        btn.addEventListener("click", () => onKey(key));
        rowEl.appendChild(btn);
      });
    });
  }

  function onKey(key) {
    keyboardTarget = true;
    els.searchInput.classList.add("active");

    if (key === "⇧") {
      shift = !shift;
      buildKeyboard();
      return;
    }
    if (key === "⌫") {
      els.searchInput.value = els.searchInput.value.slice(0, -1);
      return;
    }
    if (key === "ESPACIO") {
      els.searchInput.value += " ";
      return;
    }
    if (key === "BUSCAR") {
      doSearch();
      return;
    }

    const ch = shift && /[a-zñ]/.test(key) ? key.toUpperCase() : key;
    if (els.searchInput.value.length < 80) {
      els.searchInput.value += ch;
    }
    if (shift && /[a-zñ]/i.test(key)) {
      shift = false;
      buildKeyboard();
    }
  }

  // ---------------------------------------------------------------------------
  // WebSocket tiempo real
  // ---------------------------------------------------------------------------

  function connectSocket() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (_) {
        return;
      }

      if (data.type === "credits" || data.type === "snapshot") {
        if (data.creditos_disponibles != null) setCredits(data.creditos_disponibles);
      }
      if (data.type === "state") setState(data.state);
      if (data.type === "track") setNowPlaying(data.current, els.state.textContent);
      if (data.type === "queue") renderQueue(data.queue || []);
      if (data.type === "error" && data.detail) {
        showToast(data.detail, true);
      }
      if (data.type === "snapshot") {
        applyQueuePayload(data);
        if (data.mpv_available === false) {
          showToast("Instala mpv para oír/ver el vídeo (winget install shinchiro.mpv)", true);
        }
      }
    };

    ws.onclose = () => setTimeout(connectSocket, 2000);
    ws.onerror = () => {
      try {
        ws.close();
      } catch (_) {
        /* ignore */
      }
    };
  }

  // ---------------------------------------------------------------------------
  // Eventos UI
  // ---------------------------------------------------------------------------

  els.searchBtn.addEventListener("click", doSearch);
  els.topBtn.addEventListener("click", loadTop);
  els.searchInput.addEventListener("click", () => {
    keyboardTarget = true;
    els.searchInput.classList.add("active");
  });

  buildKeyboard();
  renderResults([]);
  refreshCredits();
  refreshQueue();
  connectSocket();
  loadTop();
})();
