import {
  createSourceDrawerController,
  disciplineColor,
  initDialogLightDismissFallback,
  initMathRendering,
  safeSetHTML,
  withViewTransition,
} from "./editorial_shared.js";

(() => {
  initDialogLightDismissFallback();
  const sourceDrawer = createSourceDrawerController();

  const initialBookPkRaw = document.body.dataset.initialBookPk || "";
  const initialDiscipline = document.body.dataset.initialDiscipline || "";
  const PAGE_RENDER_BATCH = 60;

  let disciplinesList = [];
  let loadedBooks = [];
  let renderedCount = 0;
  let selectedBookPk = initialBookPkRaw ? Number(initialBookPkRaw) : 514;
  let activeDisciplineFilter = initialDiscipline;

  const tabBtns = [
    document.getElementById("tabCatalogBtn"),
    document.getElementById("tabMosaicBtn"),
    document.getElementById("tabSearchBtn"),
  ];
  const panels = [
    document.getElementById("panelCatalog"),
    document.getElementById("panelMosaic"),
    document.getElementById("panelSearch"),
  ];

  const searchInput = document.getElementById("atlasSearchInput");
  const primarySelect = document.getElementById("atlasPrimarySelect");
  const containsSelect = document.getElementById("atlasContainsSelect");
  const secondaryOnlyCb = document.getElementById("atlasSecondaryOnly");
  const includeNoiseCb = document.getElementById("atlasIncludeNoise");
  const catalogCountEl = document.getElementById("atlasCatalogCount");
  const bookListEl = document.getElementById("atlasBookList");
  const showMoreBtn = document.getElementById("atlasShowMoreBtn");
  const bookDetailEl = document.getElementById("atlasBookDetail");

  const mosaicSelect = document.getElementById("mosaicDisciplineSelect");
  const mosaicMinCovInput = document.getElementById("mosaicMinCov");
  const mosaicLoadBtn = document.getElementById("mosaicLoadBtn");
  const mosaicBox = document.getElementById("mosaicResultBox");

  const searchForm = document.getElementById("atlasSearchForm");
  const conceptQueryInput = document.getElementById("conceptQueryInput");
  const searchModeSelect = document.getElementById("conceptSearchMode");
  const modalFilterSelect = document.getElementById("conceptModalFilter");
  const conceptResultsBox = document.getElementById("conceptResultsBox");

  function switchTab(idx) {
    withViewTransition(() => {
      tabBtns.forEach((b, i) => {
        b.setAttribute("aria-selected", i === idx ? "true" : "false");
        panels[i].hidden = i !== idx;
      });
    }, null);
  }

  tabBtns.forEach((btn, idx) => {
    btn.addEventListener("click", () => switchTab(idx));
  });

  function buildSpectrumBar(spectrumItems) {
    const bar = document.createElement("div");
    bar.className = "spectrum-stack";
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", "Barra dello spettro percentuale per disciplina");
    for (let i = 0; i < spectrumItems.length && i < 8; i += 1) {
      const item = spectrumItems[i];
      if (Number(item.share_pct) <= 0.4) continue;
      const seg = document.createElement("span");
      seg.className = "spectrum-stack__seg";
      seg.style.width = `${item.share_pct}%`;
      seg.style.backgroundColor = disciplineColor(i);
      seg.title = `${item.label_it}: ${item.share_pct}%`;
      bar.appendChild(seg);
    }
    return bar;
  }

  function renderBookBatch(reset) {
    if (reset) {
      bookListEl.replaceChildren();
      renderedCount = 0;
    }
    const end = Math.min(loadedBooks.length, renderedCount + PAGE_RENDER_BATCH);
    for (let i = renderedCount; i < end; i += 1) {
      const b = loadedBooks[i];
      const card = document.createElement("button");
      card.type = "button";
      card.className = "atlas-book-card";
      if (b.book_pk === selectedBookPk) {
        card.setAttribute("aria-current", "true");
      }

      const titleEl = document.createElement("div");
      titleEl.className = "atlas-book-card__title";
      titleEl.textContent = b.title;

      const metaEl = document.createElement("div");
      metaEl.className = "atlas-book-card__meta";
      const parts = [];
      if (b.author) parts.push(b.author);
      if (b.year) parts.push(String(b.year));
      if (b.primary_discipline_label) parts.push(`Dominante: ${b.primary_discipline_label}`);
      if (b.target_coverage_pct !== null && b.target_coverage_pct !== undefined) {
        parts.push(`Copertura disciplina cercata: ${b.target_coverage_pct}%`);
      }
      metaEl.textContent = parts.join(" · ");

      card.appendChild(titleEl);
      card.appendChild(metaEl);
      if (Array.isArray(b.spectrum) && b.spectrum.length > 0) {
        card.appendChild(buildSpectrumBar(b.spectrum));
      }

      card.addEventListener("click", () => {
        selectedBookPk = b.book_pk;
        renderBookBatchState();
        openBookSpectrum(b.book_pk, containsSelect.value || activeDisciplineFilter);
      });
      bookListEl.appendChild(card);
    }
    renderedCount = end;
    showMoreBtn.hidden = renderedCount >= loadedBooks.length;
    if (!showMoreBtn.hidden) {
      showMoreBtn.textContent = `Mostra altri volumi (${renderedCount} di ${loadedBooks.length} caricati)`;
    }
  }

  function renderBookBatchState() {
    const cards = bookListEl.querySelectorAll(".atlas-book-card");
    cards.forEach((el, idx) => {
      const book = loadedBooks[idx];
      if (book && book.book_pk === selectedBookPk) {
        el.setAttribute("aria-current", "true");
      } else {
        el.removeAttribute("aria-current");
      }
    });
  }

  showMoreBtn.addEventListener("click", () => renderBookBatch(false));

  async function fetchCatalog() {
    catalogCountEl.textContent = "Caricamento opere dell'atlante…";
    const params = new URLSearchParams();
    if (searchInput.value.trim()) params.set("q", searchInput.value.trim());
    if (primarySelect.value) params.set("primary", primarySelect.value);
    if (containsSelect.value) params.set("contains", containsSelect.value);
    if (secondaryOnlyCb.checked) params.set("only_secondary", "1");
    if (includeNoiseCb.checked) params.set("include_noise", "1");

    const resp = await fetch(`/api/atlas/books?${params.toString()}`);
    if (!resp.ok) {
      catalogCountEl.textContent = "Impossibile caricare l'elenco delle opere.";
      return;
    }
    const data = await resp.json();
    loadedBooks = data.books || [];
    catalogCountEl.textContent = `${data.total.toLocaleString("it-IT")} volumi visibili su ${data.total_active_library.toLocaleString("it-IT")} opere attive in archivio.`;
    renderBookBatch(true);

    if (loadedBooks.length > 0 && !loadedBooks.some((b) => b.book_pk === selectedBookPk)) {
      selectedBookPk = loadedBooks[0].book_pk;
    }
  }

  async function openBookSpectrum(bookPk, preselectDiscipline = "") {
    bookDetailEl.replaceChildren();
    const loading = document.createElement("p");
    loading.textContent = "Caricamento spettro disciplinare…";
    bookDetailEl.appendChild(loading);

    const resp = await fetch(`/api/atlas/book/${encodeURIComponent(bookPk)}`);
    if (!resp.ok) {
      loading.textContent = "Spettro non disponibile per quest'opera.";
      return;
    }
    const spec = await resp.json();
    bookDetailEl.replaceChildren();

    const head = document.createElement("div");
    head.className = "stack-2";
    const h = document.createElement("h2");
    h.className = "source-drawer__title";
    h.textContent = spec.clean_title || spec.title;
    const meta = document.createElement("p");
    meta.className = "source-drawer__meta";
    meta.textContent = [spec.author, spec.year, `${spec.active_blocks_count || 0} blocchi di testo`].filter(Boolean).join(" · ");
    head.appendChild(h);
    head.appendChild(meta);
    bookDetailEl.appendChild(head);

    const discList = spec.disciplines || [];
    if (discList.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "Nessuna ripartizione disciplinare ancora registrata per questo documento.";
      bookDetailEl.appendChild(empty);
      return;
    }

    bookDetailEl.appendChild(buildSpectrumBar(discList));

    const help = document.createElement("p");
    help.className = "t-small muted";
    help.textContent = "Clicca qualsiasi disciplina per leggere i corrispondenti passaggi originali del volume.";
    bookDetailEl.appendChild(help);

    const rowsUl = document.createElement("ul");
    rowsUl.className = "spectrum-rows";
    const passagesBox = document.createElement("div");
    passagesBox.className = "passage-list";

    discList.forEach((d, idx) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "spectrum-row-item";
      const dot = document.createElement("span");
      dot.className = "spectrum-dot";
      dot.style.backgroundColor = disciplineColor(idx);
      const lbl = document.createElement("span");
      lbl.textContent = `${d.label_it} (${d.block_count} passaggi)`;
      const pct = document.createElement("span");
      pct.className = "spectrum-pct";
      pct.textContent = `${Number(d.share_pct).toFixed(1)}% · cop. ${Number(d.coverage_pct).toFixed(1)}%`;
      btn.appendChild(dot);
      btn.appendChild(lbl);
      btn.appendChild(pct);
      btn.addEventListener("click", () => loadBookPassagesForDiscipline(bookPk, d.macro_discipline, passagesBox));
      li.appendChild(btn);
      rowsUl.appendChild(li);
    });
    bookDetailEl.appendChild(rowsUl);
    bookDetailEl.appendChild(passagesBox);

    if (preselectDiscipline) {
      const match = discList.find(
        (d) =>
          d.macro_discipline === preselectDiscipline ||
          d.macro_discipline.indexOf(preselectDiscipline.toLowerCase()) !== -1,
      );
      if (match) {
        loadBookPassagesForDiscipline(bookPk, match.macro_discipline, passagesBox);
      }
    } else if (discList[0]) {
      loadBookPassagesForDiscipline(bookPk, discList[0].macro_discipline, passagesBox);
    }
  }

  async function loadBookPassagesForDiscipline(bookPk, discSlug, container) {
    container.replaceChildren();
    const waitP = document.createElement("p");
    waitP.className = "t-small muted";
    waitP.textContent = "Estrazione passaggi del volume in ordine di pagina…";
    container.appendChild(waitP);

    const resp = await fetch(`/api/atlas/book/${encodeURIComponent(bookPk)}/passages?discipline=${encodeURIComponent(discSlug)}`);
    if (!resp.ok) {
      waitP.textContent = "Passaggi non disponibili.";
      return;
    }
    const data = await resp.json();
    container.replaceChildren();

    const summary = document.createElement("h3");
    summary.className = "t-small";
    summary.textContent = `${data.discipline_label}: ${data.count} passaggi trovati nell'opera`;
    container.appendChild(summary);

    (data.passages || []).forEach((p) => {
      const card = document.createElement("article");
      card.className = "passage-item";
      const meta = document.createElement("div");
      meta.className = "passage-item__meta";
      const pg = p.printed_page || p.page_start;
      const metaParts = [pg ? `Pagina ${pg}` : "Sezione del volume"];
      if (p.section_title) metaParts.push(p.section_title);
      if (Array.isArray(p.places) && p.places.length > 0) metaParts.push(`Luoghi: ${p.places.join(", ")}`);
      meta.textContent = metaParts.join(" · ");

      const quote = document.createElement("p");
      quote.className = "passage-item__quote";
      quote.textContent = p.stmt ? `${p.stmt} — «${p.excerpt}»` : p.excerpt;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.textContent = "Apri pagina originale";
      btn.addEventListener("click", () => sourceDrawer.openBlock(p.block_pk, p.quote || p.excerpt));

      card.appendChild(meta);
      card.appendChild(quote);
      card.appendChild(btn);
      container.appendChild(card);
    });
  }

  async function runMosaic(discSlug) {
    mosaicSelect.value = discSlug;
    mosaicBox.replaceChildren();
    const wait = document.createElement("p");
    wait.textContent = "Ricostruzione della disciplina dalle opere non disciplinari…";
    mosaicBox.appendChild(wait);

    const minCov = mosaicMinCovInput.value || "0.5";
    const resp = await fetch(`/api/atlas/reconstruct/${encodeURIComponent(discSlug)}?min_coverage_pct=${encodeURIComponent(minCov)}`);
    if (!resp.ok) {
      wait.textContent = "Impossibile caricare il mosaico richiesto.";
      return;
    }
    const rep = await resp.json();
    mosaicBox.replaceChildren();

    const head = document.createElement("div");
    head.className = "stack-2";
    head.style.marginBottom = "var(--s-5)";
    const title = document.createElement("h2");
    title.textContent = `${rep.target_label_it} ricostruita dal basso`;
    const stats = document.createElement("p");
    stats.className = "t-lead muted";
    stats.textContent = `${rep.total_wrong_books} libri non primariamente dedicati a questa materia · ${rep.total_passages} passaggi verificati`;
    head.appendChild(title);
    head.appendChild(stats);
    if (Array.isArray(rep.top_places) && rep.top_places.length > 0) {
      const placesLine = document.createElement("p");
      placesLine.className = "t-small";
      placesLine.textContent = `Luoghi ricorrenti nei testi: ${rep.top_places.join(", ")}`;
      head.appendChild(placesLine);
    }
    mosaicBox.appendChild(head);

    const list = document.createElement("div");
    list.className = "passage-list";
    (rep.books || []).forEach((b) => {
      const wrap = document.createElement("article");
      wrap.className = "passage-item";
      const h3 = document.createElement("h3");
      h3.style.margin = "0";
      h3.textContent = `${b.clean_title || b.book_title}${b.author ? ` — ${b.author}` : ""}`;
      const info = document.createElement("p");
      info.className = "passage-item__meta";
      info.textContent = `Disciplina dominante del libro: ${b.primary_discipline_label || b.surface_domain} (${Number(b.primary_share_pct).toFixed(1)}%) · ${b.target_block_count} passaggi trovati (copertura ${Number(b.target_coverage_pct).toFixed(1)}%)`;
      const reason = document.createElement("p");
      reason.className = "t-small";
      reason.textContent = b.interdisciplinary_reason || "";
      wrap.appendChild(h3);
      wrap.appendChild(info);
      wrap.appendChild(reason);

      (b.passages || []).forEach((p) => {
        const sub = document.createElement("div");
        sub.style.paddingTop = "8px";
        sub.style.borderTop = "1px solid rgba(17, 17, 17, 0.08)";
        const q = document.createElement("p");
        q.className = "passage-item__quote";
        const loc = p.printed_page || p.page_start;
        q.textContent = `${loc ? `Pag. ${loc}: ` : ""}${p.best_stmt} — «${p.verbatim_quote}»`;
        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "btn btn--secondary";
        openBtn.style.marginTop = "6px";
        openBtn.textContent = "Apri pagina originale";
        openBtn.addEventListener("click", () => sourceDrawer.openBlock(p.block_pk, p.verbatim_quote));
        sub.appendChild(q);
        sub.appendChild(openBtn);
        wrap.appendChild(sub);
      });
      list.appendChild(wrap);
    });
    mosaicBox.appendChild(list);
  }

  async function runConceptSearch(queryText) {
    const q = String(queryText || "").trim();
    if (!q) return;
    conceptQueryInput.value = q;
    conceptResultsBox.replaceChildren();
    const wait = document.createElement("p");
    wait.textContent = "Ricerca nella memoria storica della biblioteca…";
    conceptResultsBox.appendChild(wait);

    const modeVal = searchModeSelect.value;
    if (modeVal === "fts") {
      const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=50`);
      if (!resp.ok) {
        wait.textContent = "Ricerca non disponibile.";
        return;
      }
      const data = await resp.json();
      conceptResultsBox.replaceChildren();
      const head = document.createElement("p");
      head.className = "t-small muted";
      head.textContent = `${data.count || 0} occorrenze trovate nei volumi per "${q}".`;
      conceptResultsBox.appendChild(head);

      const list = document.createElement("div");
      list.className = "passage-list";
      (data.results || []).forEach((hit) => {
        const card = document.createElement("article");
        card.className = "passage-item";
        const meta = document.createElement("div");
        meta.className = "passage-item__meta";
        const pg = hit.printed_page || hit.page_start;
        meta.textContent = `${hit.clean_book_title || hit.book_title}${hit.author ? ` · ${hit.author}` : ""}${pg ? ` · p. ${pg}` : ""}`;
        const snip = document.createElement("p");
        snip.className = "passage-item__quote";
        safeSetHTML(snip, hit.snippet_html || "");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn--secondary";
        btn.textContent = "Apri pagina originale";
        btn.addEventListener("click", () => sourceDrawer.openBlock(hit.block_pk, q));
        card.appendChild(meta);
        card.appendChild(snip);
        card.appendChild(btn);
        list.appendChild(card);
      });
      conceptResultsBox.appendChild(list);
      return;
    }

    const params = new URLSearchParams({ q });
    if (modalFilterSelect.value) params.set("mode", modalFilterSelect.value);
    const resp = await fetch(`/api/atlas/decompress?${params.toString()}`);
    if (!resp.ok) {
      wait.textContent = "Ricerca sinottica non riuscita.";
      return;
    }
    const rep = await resp.json();
    conceptResultsBox.replaceChildren();

    const info = document.createElement("p");
    info.className = "t-small muted";
    const spanTxt = Array.isArray(rep.chronological_span) && rep.chronological_span.length === 2 && rep.chronological_span[0] != null
      ? ` (${rep.chronological_span[0]}–${rep.chronological_span[1]})`
      : "";
    info.textContent = `${rep.total_entries || 0} passaggi ordinati nel tempo su ${rep.distinct_books || 0} opere distinte${spanTxt}.`;
    conceptResultsBox.appendChild(info);

    const list = document.createElement("div");
    list.className = "passage-list";
    (rep.timeline || []).forEach((ent) => {
      const card = document.createElement("article");
      card.className = "passage-item";
      const meta = document.createElement("div");
      meta.className = "passage-item__meta";
      const bits = [
        ent.when_label || (ent.sort_year != null ? String(ent.sort_year) : "Epoca moderna"),
        ent.mode_label_it || ent.mode,
        ent.clean_book_title || ent.book_title,
        Array.isArray(ent.who) && ent.who.length ? `Autori citati: ${ent.who.join(", ")}` : null,
      ].filter(Boolean);
      meta.textContent = bits.join(" · ");

      const body = document.createElement("p");
      body.className = "passage-item__quote";
      body.textContent = `${ent.stmt} — «${ent.verbatim_quote}»`;

      const extra = document.createElement("div");
      extra.className = "t-small muted";
      const extraBits = [];
      if (Array.isArray(ent.places) && ent.places.length) extraBits.push(`Luoghi: ${ent.places.join(", ")}`);
      if (ent.vs_dispute) extraBits.push(`In disaccordo con: ${ent.vs_dispute}`);
      extra.textContent = extraBits.join(" · ");

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.textContent = "Apri pagina originale";
      btn.addEventListener("click", () => sourceDrawer.openBlock(ent.block_pk, ent.verbatim_quote));

      card.appendChild(meta);
      card.appendChild(body);
      if (extra.textContent) card.appendChild(extra);
      card.appendChild(btn);
      initMathRendering(card);
      list.appendChild(card);
    });
    conceptResultsBox.appendChild(list);
  }

  let debounceTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(fetchCatalog, 180);
  });
  [primarySelect, containsSelect, secondaryOnlyCb, includeNoiseCb].forEach((el) => {
    el.addEventListener("change", fetchCatalog);
  });

  document.getElementById("shortcutMarconiBtn").addEventListener("click", () => {
    searchInput.value = "Marconi";
    primarySelect.value = "";
    containsSelect.value = "";
    secondaryOnlyCb.checked = false;
    selectedBookPk = 514;
    fetchCatalog().then(() => openBookSpectrum(514, "geografia_cartografia_territorio"));
  });

  document.getElementById("shortcutGeoSecondaryBtn").addEventListener("click", () => {
    searchInput.value = "";
    primarySelect.value = "";
    containsSelect.value = "geografia_cartografia_territorio";
    secondaryOnlyCb.checked = true;
    fetchCatalog();
  });

  document.getElementById("shortcutResetBtn").addEventListener("click", () => {
    searchInput.value = "";
    primarySelect.value = "";
    containsSelect.value = "";
    secondaryOnlyCb.checked = false;
    includeNoiseCb.checked = false;
    fetchCatalog();
  });

  mosaicLoadBtn.addEventListener("click", () => {
    if (mosaicSelect.value) runMosaic(mosaicSelect.value);
  });

  document.querySelectorAll("[data-mosaic-disc]").forEach((btn) => {
    btn.addEventListener("click", () => runMosaic(btn.dataset.mosaicDisc));
  });

  searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    runConceptSearch(conceptQueryInput.value);
  });

  document.querySelectorAll("[data-concept]").forEach((btn) => {
    btn.addEventListener("click", () => runConceptSearch(btn.dataset.concept));
  });

  async function bootstrap() {
    const resp = await fetch("/api/atlas/disciplines");
    if (resp.ok) {
      const payload = await resp.json();
      disciplinesList = payload.disciplines || [];
      disciplinesList.forEach((d) => {
        [primarySelect, containsSelect, mosaicSelect].forEach((sel) => {
          const opt = document.createElement("option");
          opt.value = d.slug;
          opt.textContent = `${d.label_it} (${d.total_books_count})`;
          sel.appendChild(opt);
        });
      });
    }

    if (initialDiscipline === "geografia" || initialDiscipline === "geografia_cartografia_territorio") {
      if (initialBookPkRaw) {
        await fetchCatalog();
        await openBookSpectrum(selectedBookPk, "geografia_cartografia_territorio");
        return;
      }
      await fetchCatalog();
      switchTab(1);
      await runMosaic("geografia_cartografia_territorio");
      return;
    }

    await fetchCatalog();
    await openBookSpectrum(selectedBookPk, initialDiscipline);
  }

  bootstrap();
})();
