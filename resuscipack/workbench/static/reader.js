import {
  createSourceDrawerController,
  initDialogLightDismissFallback,
  initMathRendering,
  safeSetHTML,
  withViewTransition,
} from "./editorial_shared.js";

(() => {
  initDialogLightDismissFallback();
  const sourceDrawer = createSourceDrawerController();

  const bodyEl = document.body;
  let currentVolumeId = bodyEl.dataset.initialVolume || "vol1_ofa";
  let currentSlug = bodyEl.dataset.initialSlug || "dall_ovvio_al_numero";
  let volumesCache = [];
  let ofaLoaded = false;

  const tocDesktop = document.getElementById("tocDesktopContainer");
  const tocMobile = document.getElementById("tocMobileContainer");
  const tocDrawer = document.getElementById("tocDrawer");
  const openTocBtn = document.getElementById("openTocBtn");

  const volLabelEl = document.getElementById("chapterVolumeLabel");
  const headingEl = document.getElementById("chapterHeading");
  const subtitleEl = document.getElementById("chapterSubtitle");
  const proseEl = document.getElementById("chapterProse");

  const apparatusCountEl = document.getElementById("apparatusSummaryCount");
  const apparatusBox = document.getElementById("apparatusContainer");
  const practiceCountEl = document.getElementById("practiceSummaryCount");
  const practiceBox = document.getElementById("practiceContainer");
  const ofaDetails = document.getElementById("ofaQuestionsDetails");
  const ofaBox = document.getElementById("ofaQuestionsContainer");

  const prevChapterBtn = document.getElementById("prevChapterBtn");
  const nextChapterBtn = document.getElementById("nextChapterBtn");

  const openManualProbeBtn = document.getElementById("openManualProbeBtn");
  const probeDrawer = document.getElementById("probeDrawer");
  const probeManualForm = document.getElementById("probeManualForm");
  const probeQueryInput = document.getElementById("probeQueryInput");
  const probeBridgeTags = document.getElementById("probeBridgeTags");
  const probeResultsBox = document.getElementById("probeResultsBox");
  const selectionProbeBar = document.getElementById("selectionProbeBar");
  const selectionProbeBtn = document.getElementById("selectionProbeBtn");
  let lastSelectedText = "";

  function renderTocInto(container) {
    if (!container) return;
    container.replaceChildren();
    volumesCache.forEach((vol) => {
      const wrap = document.createElement("section");
      wrap.className = "toc-volume";
      const h = document.createElement("h3");
      h.className = "toc-volume__title";
      h.textContent = `${vol.short_title} — ${vol.title}`;
      wrap.appendChild(h);

      const ul = document.createElement("ul");
      ul.className = "toc-list";
      vol.chapters.forEach((ch) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "toc-link";
        if (ch.volume_id === currentVolumeId && ch.slug === currentSlug) {
          btn.setAttribute("aria-current", "true");
        }
        const numSpan = document.createElement("span");
        numSpan.className = "toc-link__num";
        numSpan.textContent = `${ch.chapter_number}.`;
        const titleSpan = document.createElement("span");
        titleSpan.textContent = ch.title;
        btn.appendChild(numSpan);
        btn.appendChild(titleSpan);
        btn.addEventListener("click", () => {
          if (tocDrawer && tocDrawer.open) {
            tocDrawer.close();
          }
          navigateToChapter(ch.volume_id, ch.slug, true);
        });
        li.appendChild(btn);
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
      container.appendChild(wrap);
    });
  }

  function renderApparatus(data) {
    apparatusBox.replaceChildren();
    const fnCount = (data.footnotes || []).length;
    apparatusCountEl.textContent = `${fnCount} fonti verificate`;

    // 1. Verificato sul testo
    const g1 = document.createElement("div");
    g1.className = "apparatus-group apparatus-band";
    const h1 = document.createElement("h3");
    h1.textContent = "Verificato sul testo";
    g1.appendChild(h1);
    const list1 = document.createElement("ul");
    list1.className = "footnote-list";
    (data.footnotes || []).forEach((fn) => {
      const li = document.createElement("li");
      li.className = "footnote-item";
      const quoteLine = document.createElement("p");
      quoteLine.className = "t-small";
      quoteLine.textContent = `${fn.num}. «${fn.quote}» — ${fn.source_label}`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary footnote-open-btn";
      btn.textContent = `Apri pagina della fonte ${fn.num}`;
      btn.addEventListener("click", () => sourceDrawer.openBlock(fn.block_pk, fn.quote));
      li.appendChild(quoteLine);
      li.appendChild(btn);
      list1.appendChild(li);
    });
    g1.appendChild(list1);
    apparatusBox.appendChild(g1);

    // 2. Ricostruzione matematica / editoriale
    if (Array.isArray(data.ricostruzione) && data.ricostruzione.length > 0) {
      const g2 = document.createElement("div");
      g2.className = "apparatus-group apparatus-band apparatus-band--recon";
      const h2 = document.createElement("h3");
      h2.textContent = "Ricostruzione matematica";
      g2.appendChild(h2);
      const ul2 = document.createElement("ul");
      ul2.className = "book-list";
      data.ricostruzione.forEach((line) => {
        const li = document.createElement("li");
        li.textContent = line;
        ul2.appendChild(li);
      });
      g2.appendChild(ul2);
      initMathRendering(g2);
      apparatusBox.appendChild(g2);
    }

    // 3. Esercizi originali & tracce
    if (Array.isArray(data.esercizi_originali) && data.esercizi_originali.length > 0) {
      const g3 = document.createElement("div");
      g3.className = "apparatus-group apparatus-band apparatus-band--orig";
      const h3 = document.createElement("h3");
      h3.textContent = "Tracce di verifica degli esercizi a libro chiuso";
      g3.appendChild(h3);
      const ul3 = document.createElement("ul");
      ul3.className = "book-list";
      data.esercizi_originali.forEach((line) => {
        const li = document.createElement("li");
        li.textContent = line;
        ul3.appendChild(li);
      });
      g3.appendChild(ul3);
      initMathRendering(g3);
      apparatusBox.appendChild(g3);
    }
  }

  function renderPractice(data) {
    practiceBox.replaceChildren();
    const drills = data.drills || [];
    practiceCountEl.textContent = `${drills.length} esercizi simbolici`;

    drills.forEach((drill, idx) => {
      const card = document.createElement("div");
      card.className = "drill-card";
      const topic = document.createElement("p");
      topic.className = "t-small muted";
      topic.textContent = `${drill.topic_title || "Verifica simbolica"} · Quesito ${idx + 1}`;
      const prompt = document.createElement("p");
      prompt.textContent = drill.prompt;

      const form = document.createElement("form");
      form.className = "drill-form";
      const inputId = `drill-input-${idx}`;
      const label = document.createElement("label");
      label.htmlFor = inputId;
      label.className = "t-small";
      label.textContent = "Risposta";
      const input = document.createElement("input");
      input.id = inputId;
      input.type = "text";
      input.required = true;
      input.className = "practice-input";
      input.placeholder = "Scrivi espressione o valore…";

      const btn = document.createElement("button");
      btn.type = "submit";
      btn.className = "btn btn--primary";
      btn.textContent = "Verifica risposta";

      const status = document.createElement("p");
      status.className = "drill-feedback";
      status.setAttribute("role", "status");

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const ans = input.value.trim();
        if (!ans) return;
        status.textContent = "Verifica in corso…";
        const resp = await fetch("/api/drill/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: drill.node_id,
            drill_id: drill.drill_id,
            expected: drill.expected,
            student_answer: ans,
          }),
        });
        const out = await resp.json();
        if (out.grade && out.grade.is_correct) {
          status.className = "drill-feedback drill-feedback--ok";
          status.textContent = `✓ Corretto: ${out.grade.feedback || "espressione equivalente accettata."}`;
        } else {
          status.className = "drill-feedback drill-feedback--err";
          status.textContent = `× Da rivedere: ${(out.grade && out.grade.feedback) || "ricontrolla i passaggi e riprova."}`;
        }
      });

      form.appendChild(label);
      form.appendChild(input);
      form.appendChild(btn);
      card.appendChild(topic);
      card.appendChild(prompt);
      card.appendChild(form);
      card.appendChild(status);
      initMathRendering(card);
      practiceBox.appendChild(card);
    });

    if (data.proof_rubric) {
      const pr = data.proof_rubric;
      const box = document.createElement("form");
      box.className = "drill-card";
      const h = document.createElement("h3");
      h.textContent = pr.title;
      const p = document.createElement("p");
      p.textContent = pr.prompt;
      const ta = document.createElement("textarea");
      ta.className = "practice-textarea";
      ta.required = true;
      ta.placeholder = "Scrivi tutti i passaggi della dimostrazione…";
      const btn = document.createElement("button");
      btn.type = "submit";
      btn.className = "btn btn--primary";
      btn.textContent = "Controlla dimostrazione";
      const resEl = document.createElement("div");
      resEl.className = "stack-2";

      box.addEventListener("submit", async (e) => {
        e.preventDefault();
        const resp = await fetch("/api/hero/proof-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: pr.node_id,
            rubric_id: pr.id,
            proof_text: ta.value,
          }),
        });
        const out = await resp.json();
        resEl.replaceChildren();
        const summary = document.createElement("p");
        summary.className = out.all_passed ? "drill-feedback drill-feedback--ok" : "drill-feedback drill-feedback--err";
        summary.textContent = out.all_passed
          ? `✓ Dimostrazione completa (${out.passed_count} criteri verificati).`
          : `× Passaggi completi: ${out.passed_count} su ${out.total_lemmas}. Rivedi i punti mancanti:`;
        resEl.appendChild(summary);
        (out.results || []).forEach((item) => {
          const li = document.createElement("p");
          li.className = "t-small";
          li.textContent = `${item.present ? "✓" : "×"} ${item.label}${!item.present && item.missing_hint ? ` — ${item.missing_hint}` : ""}`;
          resEl.appendChild(li);
        });
      });

      box.appendChild(h);
      box.appendChild(p);
      box.appendChild(ta);
      box.appendChild(btn);
      box.appendChild(resEl);
      practiceBox.appendChild(box);
    }

    if (data.graph_invariant) {
      const gi = data.graph_invariant;
      const gform = document.createElement("form");
      gform.className = "drill-card";
      const h = document.createElement("h3");
      h.textContent = gi.title;
      const p = document.createElement("p");
      p.textContent = gi.prompt;
      gform.appendChild(h);
      gform.appendChild(p);

      (gi.fields || []).forEach((fld) => {
        const row = document.createElement("div");
        row.className = "atlas-field";
        const lbl = document.createElement("label");
        lbl.htmlFor = `gi-${fld.name}`;
        lbl.textContent = fld.label;
        row.appendChild(lbl);
        if (Array.isArray(fld.options)) {
          const sel = document.createElement("select");
          sel.id = `gi-${fld.name}`;
          sel.name = fld.name;
          sel.className = "atlas-select";
          fld.options.forEach((opt) => {
            const o = document.createElement("option");
            o.value = opt;
            o.textContent = opt;
            sel.appendChild(o);
          });
          row.appendChild(sel);
        } else {
          const inp = document.createElement("input");
          inp.id = `gi-${fld.name}`;
          inp.name = fld.name;
          inp.type = "text";
          inp.required = true;
          inp.className = "practice-input";
          inp.placeholder = fld.placeholder || "";
          row.appendChild(inp);
        }
        gform.appendChild(row);
      });

      const btn = document.createElement("button");
      btn.type = "submit";
      btn.className = "btn btn--primary";
      btn.textContent = "Verifica invarianti";
      const gStatus = document.createElement("p");
      gStatus.className = "drill-feedback";
      gStatus.setAttribute("role", "status");

      gform.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(gform);
        const answers = Object.fromEntries(fd.entries());
        const resp = await fetch("/api/hero/graph-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ node_id: gi.node_id, spec_id: gi.id, answers }),
        });
        const out = await resp.json();
        gStatus.className = out.all_passed ? "drill-feedback drill-feedback--ok" : "drill-feedback drill-feedback--err";
        gStatus.textContent = out.all_passed
          ? `✓ Tutti i ${out.passed_count} invarianti sono verificati.`
          : `× Verificati ${out.passed_count} su ${out.total_checks} invarianti: controlla dominio, cuspide o rami.`;
      });

      gform.appendChild(btn);
      gform.appendChild(gStatus);
      practiceBox.appendChild(gform);
    }
  }

  async function ensureOfaBank(show) {
    if (!ofaDetails) return;
    ofaDetails.hidden = !show;
    if (!show || ofaLoaded) return;
    const resp = await fetch("/api/books/ofa-questions");
    if (!resp.ok) return;
    const data = await resp.json();
    ofaLoaded = true;
    ofaBox.replaceChildren();
    const list = document.createElement("div");
    list.className = "passage-list";
    (data.questions || []).forEach((q) => {
      const card = document.createElement("div");
      card.className = "passage-item";
      const meta = document.createElement("div");
      meta.className = "passage-item__meta";
      meta.textContent = `Quesito ${q.index} · ${q.book_title}${q.page ? ` · p. ${q.page}` : ""}`;
      const txt = document.createElement("p");
      txt.className = "passage-item__quote";
      txt.textContent = q.question_excerpt;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.textContent = "Apri pagina d'esame";
      btn.addEventListener("click", () => sourceDrawer.openBlock(q.block_pk, q.question_excerpt));
      card.appendChild(meta);
      card.appendChild(txt);
      card.appendChild(btn);
      list.appendChild(card);
    });
    initMathRendering(list);
    ofaBox.appendChild(list);
  }

  async function loadChapter(volumeId, slug) {
    const resp = await fetch(`/api/books/${encodeURIComponent(volumeId)}/${encodeURIComponent(slug)}`);
    if (!resp.ok) {
      headingEl.textContent = "Capitolo non trovato";
      return;
    }
    const data = await resp.json();
    currentVolumeId = data.volume_id;
    currentSlug = data.slug;
    document.title = `resuscipack: ${data.title}`;

    withViewTransition(() => {
      volLabelEl.textContent = `${data.volume_short_title} — ${data.volume_title} · Capitolo ${data.chapter_number}`;
      headingEl.textContent = data.title;
      subtitleEl.textContent = data.subtitle || "";
      safeSetHTML(proseEl, data.html || "");
      initMathRendering(proseEl);

      proseEl.querySelectorAll("button.fn-trigger").forEach((btn) => {
        btn.addEventListener("click", () => {
          sourceDrawer.openBlock(btn.dataset.blockPk, btn.dataset.quote || "");
        });
      });

      renderApparatus(data);
      renderPractice(data);
      renderTocInto(tocDesktop);
      renderTocInto(tocMobile);
      ensureOfaBank(Boolean(data.has_ofa_bank));

      if (data.prev_chapter) {
        prevChapterBtn.hidden = false;
        prevChapterBtn.textContent = `← Cap. ${data.prev_chapter.chapter_number}: ${data.prev_chapter.title}`;
        prevChapterBtn.onclick = () => navigateToChapter(data.prev_chapter.volume_id, data.prev_chapter.slug, true);
      } else {
        prevChapterBtn.hidden = true;
      }

      if (data.next_chapter) {
        nextChapterBtn.hidden = false;
        nextChapterBtn.textContent = `Cap. ${data.next_chapter.chapter_number}: ${data.next_chapter.title} →`;
        nextChapterBtn.onclick = () => navigateToChapter(data.next_chapter.volume_id, data.next_chapter.slug, true);
      } else {
        nextChapterBtn.hidden = true;
      }
    }, "chapterHeading");
  }

  function navigateToChapter(volumeId, slug, pushHistory) {
    const nextUrl = `/libro/${encodeURIComponent(volumeId)}/${encodeURIComponent(slug)}`;
    if (pushHistory && window.location.pathname !== nextUrl) {
      window.history.pushState({ volumeId, slug }, "", nextUrl);
    }
    window.scrollTo({ top: 0 });
    loadChapter(volumeId, slug);
  }

  window.addEventListener("popstate", (ev) => {
    if (ev.state && ev.state.volumeId && ev.state.slug) {
      loadChapter(ev.state.volumeId, ev.state.slug);
    }
  });

  if (openTocBtn && tocDrawer) {
    openTocBtn.addEventListener("click", () => {
      tocDrawer.showModal();
    });
  }

  function renderProbeGroup(title, items) {
    const sec = document.createElement("section");
    sec.className = "apparatus-group";
    const h = document.createElement("h3");
    h.textContent = `${title} (${items.length})`;
    sec.appendChild(h);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "t-small muted";
      empty.textContent = "Nessun passaggio corrispondente in questa fascia.";
      sec.appendChild(empty);
      return sec;
    }
    const list = document.createElement("div");
    list.className = "passage-list";
    items.forEach((hit) => {
      const card = document.createElement("article");
      card.className = "passage-item";
      const meta = document.createElement("div");
      meta.className = "passage-item__meta";
      const who = hit.actors && hit.actors.length ? hit.actors.join(", ") : (hit.author || "");
      const parts = [hit.book_title];
      if (who) parts.push(who);
      if (hit.when) parts.push(hit.when);
      meta.textContent = parts.join(" · ");

      const stmt = document.createElement("p");
      stmt.className = "passage-item__quote";
      stmt.textContent = hit.stmt || "";

      const quote = document.createElement("blockquote");
      quote.className = "t-small muted";
      quote.textContent = hit.verbatim_quote ? `«${hit.verbatim_quote}»` : "";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.textContent = "Apri pagina originale";
      btn.addEventListener("click", () => {
        if (probeDrawer && probeDrawer.open) probeDrawer.close();
        sourceDrawer.openBlock(hit.block_pk, hit.verbatim_quote || "");
      });

      card.appendChild(meta);
      card.appendChild(stmt);
      if (hit.verbatim_quote) card.appendChild(quote);
      card.appendChild(btn);
      list.appendChild(card);
    });
    sec.appendChild(list);
    return sec;
  }

  async function runLiveProbe(queryText) {
    const q = String(queryText || "").trim();
    if (!probeDrawer || !probeResultsBox) return;
    if (probeQueryInput) probeQueryInput.value = q;
    if (!probeDrawer.open) probeDrawer.showModal();
    if (!q) {
      probeBridgeTags.replaceChildren();
      probeResultsBox.textContent = "Scrivi o seleziona un sintagma o un'intera frase dal capitolo.";
      return;
    }
    probeResultsBox.textContent = "Ricerca nei volumi della biblioteca…";
    const resp = await fetch("/api/probe/selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: q,
        chapter_context: headingEl ? headingEl.textContent || "" : "",
        limit: 10,
      }),
    });
    if (!resp.ok) {
      probeResultsBox.textContent = "Impossibile interrogare la biblioteca in questo momento.";
      return;
    }
    const data = await resp.json();
    probeBridgeTags.replaceChildren();
    (data.bridges || []).forEach((br) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "quick-pill";
      b.textContent = `Ponte: ${br.concept}`;
      b.addEventListener("click", () => runLiveProbe(br.concept));
      probeBridgeTags.appendChild(b);
    });

    probeResultsBox.replaceChildren();
    const summary = document.createElement("p");
    summary.className = "t-small muted";
    summary.textContent = data.mode === "proposition_trial"
      ? `Confronto su proposizione · termini chiave: ${(data.terms || []).join(", ")}`
      : `Sonda di sintagma · termini chiave: ${(data.terms || []).join(", ")}`;
    probeResultsBox.appendChild(summary);
    probeResultsBox.appendChild(renderProbeGroup("Conferme e definizioni", data.confirmations || []));
    probeResultsBox.appendChild(renderProbeGroup("Tesi rivali e obiezioni", data.rivals || []));
  }

  function updateSelectionProbeBar() {
    if (!selectionProbeBar || !proseEl) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      selectionProbeBar.hidden = true;
      return;
    }
    const text = sel.toString().trim();
    if (text.length < 4 || text.length > 420) {
      selectionProbeBar.hidden = true;
      return;
    }
    const anchor = sel.anchorNode;
    if (!anchor || !proseEl.contains(anchor)) {
      selectionProbeBar.hidden = true;
      return;
    }
    lastSelectedText = text;
    selectionProbeBar.hidden = false;
  }

  if (proseEl) {
    proseEl.addEventListener("mouseup", () => setTimeout(updateSelectionProbeBar, 10));
    proseEl.addEventListener("keyup", () => setTimeout(updateSelectionProbeBar, 10));
  }
  document.addEventListener("selectionchange", () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      if (selectionProbeBar) selectionProbeBar.hidden = true;
    }
  });
  if (selectionProbeBtn) {
    selectionProbeBtn.addEventListener("click", () => {
      if (selectionProbeBar) selectionProbeBar.hidden = true;
      runLiveProbe(lastSelectedText);
    });
  }
  if (openManualProbeBtn) {
    openManualProbeBtn.addEventListener("click", () => {
      const selText = (window.getSelection()?.toString() || "").trim();
      runLiveProbe(selText || lastSelectedText);
    });
  }
  if (probeManualForm) {
    probeManualForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      runLiveProbe(probeQueryInput ? probeQueryInput.value : "");
    });
  }

  async function bootstrap() {
    const resp = await fetch("/api/books");
    if (resp.ok) {
      const catalog = await resp.json();
      volumesCache = catalog.volumes || [];
    }
    await loadChapter(currentVolumeId, currentSlug);
  }

  bootstrap();
})();
