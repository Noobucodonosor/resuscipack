(() => {
  const state = {
    overview: null,
    extractionStatus: null,
    statusTimerId: null,
    activeFilter: "frontier",
    currentNodeData: null,
    activeMode: "card",
  };

  function renderMath(container) {
    if (window.renderMathInElement && container) {
      window.renderMathInElement(container, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true },
        ],
        throwOnError: false,
      });
    }
  }

  async function fetchJson(url, options) {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(txt || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  async function loadOverview(selectNodeId) {
    const data = await fetchJson("/api/overview");
    state.overview = data;
    renderNodeStrip();
    updateGlobalStats();

    const targetId =
      selectNodeId ||
      (state.currentNodeData && state.currentNodeData.node.id) ||
      (data.frontier_nodes.length > 0 ? data.frontier_nodes[0].id : "numeri.quantita");
    await selectNode(targetId);
  }

  async function loadExtractionStatus() {
    if (state.statusTimerId) {
      clearTimeout(state.statusTimerId);
      state.statusTimerId = null;
    }
    try {
      const data = await fetchJson("/api/extraction_status");
      state.extractionStatus = data;
      updateGlobalStats();
      if (data.state === "running") {
        state.statusTimerId = setTimeout(loadExtractionStatus, 10000);
      }
    } catch (_err) {
      // Mantiene la UI operativa anche se lo stato live non è ancora disponibile
    }
  }

  function updateGlobalStats() {
    if (!state.overview) return;
    const masteredCount = state.overview.mastered_ids.length;
    const totalCount = state.overview.metadata.total_nodes;
    const ofa = state.overview.ofa_readiness;
    const statsEl = document.getElementById("compassStats");
    let text = `Padronanza: ${masteredCount}/${totalCount} · Gate OFA G00: ${ofa.ready_count}/${ofa.total_count}`;
    if (state.extractionStatus) {
      const es = state.extractionStatus;
      const booksStr = Number(es.books_active || 0).toLocaleString("it-IT");
      const extStr = Number(es.blocks_extracted || 0).toLocaleString("it-IT");
      const brStr = Number(es.validated_bridges || 0).toLocaleString("it-IT");
      text = `📚 ${booksStr} libri · Letti AI: ${extStr} · Ponti: ${brStr}`;
      if (es.state === "running" && es.live_wave) {
        const lw = es.live_wave;
        text += ` (⏳ Wave ${lw.wave || 1}: ${lw.blocks_completed || 0}/${lw.blocks_total_in_wave || 0})`;
      }
      text += ` · Padronanza: ${masteredCount}/${totalCount} · OFA: ${ofa.ready_count}/${ofa.total_count}`;
    }
    statsEl.textContent = text;
  }

  function renderNodeStrip() {
    if (!state.overview) return;
    const strip = document.getElementById("nodeStrip");
    strip.innerHTML = "";
    let list = [];
    if (state.activeFilter === "frontier") {
      list = state.overview.frontier_nodes;
    } else {
      const layerNum = Number(state.activeFilter);
      list = state.overview.nodes.filter((n) => n.layer === layerNum);
    }

    list.forEach((n) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const st = n.student_status || "not_started";
      const isCurrent = state.currentNodeData && state.currentNodeData.node.id === n.id;
      btn.className = `node-chip status-${st}${isCurrent ? " active" : ""}`;
      const cardIcon = n.has_card ? "📄 " : "";
      btn.textContent = `${cardIcon}${n.id} · ${n.title}`;
      btn.addEventListener("click", () => selectNode(n.id));
      strip.appendChild(btn);
    });
  }

  async function selectNode(nodeId) {
    const data = await fetchJson(`/api/node/${encodeURIComponent(nodeId)}`);
    state.currentNodeData = data;
    renderHeroCompass(data);
    renderNodeHeader(data);
    renderCardPanel(data);
    renderDrillPanel(data);
    renderHeroPanel(data);
    renderNodeStrip();
  }

  function renderHeroCompass(data) {
    const chainEl = document.getElementById("compassChain");
    chainEl.innerHTML = "";
    const label = document.createElement("span");
    label.textContent = "Traiettoria Hero: ";
    chainEl.appendChild(label);

    data.hero_compass.chain.forEach((step, idx) => {
      if (idx > 0) {
        const arrow = document.createElement("span");
        arrow.textContent = " → ";
        chainEl.appendChild(arrow);
      }
      const sp = document.createElement("span");
      sp.className = `compass-step${step.id === data.node.id ? " current" : ""}`;
      sp.textContent = `${step.id} (${step.title})`;
      sp.addEventListener("click", () => selectNode(step.id));
      chainEl.appendChild(sp);
    });

    if (data.hero_compass.target_gate_window) {
      const win = document.createElement("span");
      win.textContent = ` · [${data.hero_compass.target_gate_window}]`;
      chainEl.appendChild(win);
    }
  }

  function renderNodeHeader(data) {
    document.getElementById("nodeLayerBadge").textContent = data.node.layer_label;
    document.getElementById("nodeTitle").textContent = `${data.node.id} — ${data.node.title}`;
    document.getElementById("nodeDecision").textContent = data.node.decision || "";
    const st = data.progress.status || "not_started";
    document.getElementById("nodeStatusPill").textContent = `Stato: ${st}`;
  }

  function renderCardPanel(data) {
    const bridgesBox = document.getElementById("wrongBookBridgesBox");
    bridgesBox.innerHTML = "";
    if (data.wrong_book_bridges && data.wrong_book_bridges.length > 0) {
      data.wrong_book_bridges.forEach((br) => {
        const div = document.createElement("div");
        div.className = "bridge-card";
        const mappingItems = Object.entries(br.mapping || {})
          .map(([k, v]) => `<li><strong>${escapeHtml(k)}</strong> ↔ ${escapeHtml(v)}</li>`)
          .join("");
        const stepsItems = (br.chain_steps || [])
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("");
        div.innerHTML = `
          <h3>🧭 Ponte «Il Libro Sbagliato» (${escapeHtml(br.surface_domain)} · score ${br.score})</h3>
          <div><em>${escapeHtml(br.book_title)}</em> (p. ${br.page_start || "?"})</div>
          <ul>${mappingItems}</ul>
          <ol>${stepsItems}</ol>
          <button type="button" class="fn-trigger" data-block-pk="${br.block_pk}" data-quote="">
            Apri pagina originale [block_pk=${br.block_pk}]
          </button>
        `;
        bridgesBox.appendChild(div);
      });
    }

    const cardBody = document.getElementById("cardContent");
    const fnBox = document.getElementById("footnotesBox");
    fnBox.innerHTML = "";

    if (data.card) {
      cardBody.innerHTML = data.card.html;
      if (data.card.footnotes && data.card.footnotes.length > 0) {
        const h = document.createElement("h3");
        h.textContent = "Fonti Primarie Verificate (clicca per leggere la pagina nel libro a destra)";
        fnBox.appendChild(h);
        data.card.footnotes.forEach((fn) => {
          const row = document.createElement("div");
          row.className = "footnote-row";
          row.innerHTML = `
            <button type="button" class="fn-trigger" data-block-pk="${fn.block_pk}" data-quote="${escapeAttr(fn.quote)}">
              [^${fn.num}]
            </button>
            <span>«${escapeHtml(fn.quote)}» — <em>${escapeHtml(fn.source_label)}</em> <code>[${fn.block_uid}]</code></span>
          `;
          fnBox.appendChild(row);
        });
      }
      document.getElementById("governanceBadge").textContent =
        `Governance scheda: ${data.progress.card_governance || data.card.status} (6/6 Gate verificati)`;
    } else {
      cardBody.innerHTML = `
        <div class="drill-intro">
          <p><strong>Decisione di Progetto del Nodo:</strong> ${escapeHtml(data.node.decision || "")}</p>
          <p><strong>Archetipo Generatore (per il Libro Sbagliato):</strong> ${escapeHtml(data.node.generator_archetype || "Traguardo d'esame ufficiale SecAI.")}</p>
          <p>Usa la scheda <strong>⚡ Fast-Forward Diagnostico (SymPy)</strong> qui sopra per verificare e chiudere subito questo nodo se lo padroneggi già, oppure cerca passaggi nei 1.372 libri a destra.</p>
        </div>
      `;
      document.getElementById("governanceBadge").textContent =
        "Nodo attivo in modalità Fast-Forward Diagnostico (Wave 1–4 genera le schede dei soli Nodi Frontiera)";
    }

    wireBlockButtons(document.getElementById("panelCard"));
    renderMath(document.getElementById("panelCard"));
  }

  function renderDrillPanel(data) {
    const list = document.getElementById("drillList");
    list.innerHTML = "";
    (data.drills || []).forEach((d, idx) => {
      const box = document.createElement("div");
      box.className = "drill-card";
      box.innerHTML = `
        <div><strong>Quesito ${idx + 1}:</strong> ${escapeHtml(d.prompt)}</div>
        <div class="drill-row">
          <input type="text" placeholder="Scrivi risposta o formula algebrica…" id="ans-${idx}" />
          <button type="button" class="mode-btn active" id="sub-${idx}">Verifica SymPy</button>
        </div>
        <div class="drill-feedback" id="fb-${idx}"></div>
      `;
      list.appendChild(box);
      box.querySelector(`#sub-${idx}`).addEventListener("click", async () => {
        const val = box.querySelector(`#ans-${idx}`).value;
        const res = await fetchJson("/api/drill/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: data.node.id,
            drill_id: d.drill_id,
            expected: d.expected,
            student_answer: val,
          }),
        });
        const fb = box.querySelector(`#fb-${idx}`);
        fb.className = `drill-feedback ${res.grade.is_correct ? "ok" : "err"}`;
        fb.textContent = `${res.grade.is_correct ? "✓ " : "✗ "}${res.grade.feedback} — ${d.explanation}`;
        document.getElementById("nodeStatusPill").textContent = `Stato: ${res.progress.status}`;
        state.overview.mastered_ids = res.mastered_ids;
        state.overview.frontier_nodes = res.frontier_nodes;
        updateGlobalStats();
        renderNodeStrip();
      });
    });
  }

  function renderHeroPanel(data) {
    const box = document.getElementById("heroProofContainer");
    box.innerHTML = "";
    const heroText = data.node.hero_proof || data.node.diagnostic_prompt || "Supera il Fast-Forward SymPy per consolidare questo mattone.";
    const header = document.createElement("div");
    header.className = "drill-card";
    header.innerHTML = `<strong>Prova Osservabile dell'Hero:</strong> <p>${escapeHtml(heroText)}</p>`;
    box.appendChild(header);

    if (data.node.graph_spec_id === "abs_shifted_log") {
      const gDiv = document.createElement("div");
      gDiv.className = "drill-card";
      gDiv.innerHTML = `
        <h3>Verifica Grafico a Mano: $y = |\\ln(x - 2)| + 1$ (5 Invarianti SymPy)</h3>
        <p>Disegna la curva su carta senza tabella di punti, poi inserisci i 5 invarianti per sbloccare il confronto:</p>
        <div class="drill-row"><input id="gi-dom" placeholder="Estremo sinistro dominio (es. 2)" /><input id="gi-asym" placeholder="Asintoto verticale x = …" /></div>
        <div class="drill-row"><input id="gi-cx" placeholder="Ascissa cuspide x" /><input id="gi-cy" placeholder="Ordinata cuspide y" /></div>
        <div class="drill-row"><input id="gi-probe" placeholder="Valore y in x = 2 + e" /><input id="gi-left" placeholder="Ramo (2,3): decrescente/crescente" /><input id="gi-right" placeholder="Ramo (3,+inf): decrescente/crescente" /></div>
        <button type="button" class="mode-btn active" id="btnCheckGraph" style="margin-top:8px;">Valida Invarianti con SymPy</button>
        <div id="graphCheckResult" class="drill-feedback"></div>
      `;
      box.appendChild(gDiv);
      gDiv.querySelector("#btnCheckGraph").addEventListener("click", async () => {
        const res = await fetchJson("/api/hero/graph-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: data.node.id,
            spec_id: "abs_shifted_log",
            answers: {
              domain_lower_bound: gDiv.querySelector("#gi-dom").value,
              vertical_asymptote_x: gDiv.querySelector("#gi-asym").value,
              cusp_x: gDiv.querySelector("#gi-cx").value,
              cusp_y: gDiv.querySelector("#gi-cy").value,
              probe_y_at_2_plus_e: gDiv.querySelector("#gi-probe").value,
              left_branch: gDiv.querySelector("#gi-left").value,
              right_branch: gDiv.querySelector("#gi-right").value,
            },
          }),
        });
        const out = gDiv.querySelector("#graphCheckResult");
        out.className = `drill-feedback ${res.all_passed ? "ok" : "err"}`;
        out.textContent = `Invarianti corretti: ${res.passed_count}/${res.total_checks}${res.all_passed ? " — Grafico validato e salvato nel Portfolio!" : ""}`;
      });
    }

    if (data.node.rubric_id) {
      const rDiv = document.createElement("div");
      rDiv.className = "drill-card";
      rDiv.innerHTML = `
        <h3>Verifica Dimostrazione a Libro Chiuso (Rubrica Booleana <code>${escapeHtml(data.node.rubric_id)}</code>)</h3>
        <textarea class="proof-textarea" id="proofTextInput" placeholder="Scrivi qui tutti i passaggi logici della dimostrazione a libro chiuso…"></textarea>
        <button type="button" class="mode-btn active" id="btnCheckProof">Controlla Obblighi di Prova</button>
        <div id="proofCheckOutput"></div>
      `;
      box.appendChild(rDiv);
      rDiv.querySelector("#btnCheckProof").addEventListener("click", async () => {
        const res = await fetchJson("/api/hero/proof-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: data.node.id,
            rubric_id: data.node.rubric_id,
            proof_text: rDiv.querySelector("#proofTextInput").value,
          }),
        });
        const items = res.results
          .map((r) => `<li>${r.present ? "✅" : "❌"} <strong>${escapeHtml(r.label)}</strong>: ${escapeHtml(r.feedback)}</li>`)
          .join("");
        rDiv.querySelector("#proofCheckOutput").innerHTML = `<ul class="card-list">${items}</ul>`;
      });
    }

    const oaBox = document.getElementById("openAccessBox");
    oaBox.innerHTML = "";
    if (data.open_access_books && data.open_access_books.length > 0) {
      data.open_access_books.forEach((oa) => {
        const d = document.createElement("div");
        d.className = "wrong-book-callout";
        d.innerHTML = `
          <strong>📖 Protocollo Onestà Lacune (€0 Open-Access Drop-In):</strong>
          <div><em>${escapeHtml(oa.title)}</em> — ${escapeHtml(oa.authors)} (${escapeHtml(oa.license)})</div>
          <div>${escapeHtml(oa.rationale)} · <a href="${escapeAttr(oa.url)}" target="_blank" rel="noopener">Scarica fonte canonica gratuita</a></div>
        `;
        oaBox.appendChild(d);
      });
    }
    renderMath(box);
  }

  function wireBlockButtons(root) {
    root.querySelectorAll("[data-block-pk]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pk = Number(btn.getAttribute("data-block-pk"));
        const quote = btn.getAttribute("data-quote") || "";
        openBookBlock(pk, quote);
      });
    });
  }

  async function openBookBlock(blockPk, quote) {
    const qParam = quote ? `?quote=${encodeURIComponent(quote)}` : "";
    const blk = await fetchJson(`/api/block/${blockPk}${qParam}`);
    const reader = document.getElementById("bookReaderContainer");
    const authorLine = blk.author ? `${escapeHtml(blk.author)} · ` : "";
    reader.innerHTML = `
      <div class="reader-meta">
        <div><strong>${escapeHtml(blk.book_title)}</strong></div>
        <div>${authorLine}Pag. ${blk.page_start || "?"} · Dominio: <code>${escapeHtml(blk.surface_domain)}</code> · ID immutabile: <code>${escapeHtml(blk.block_uid)}</code> (<code>block_pk=${blk.block_pk}</code>)</div>
      </div>
      <div class="reader-nav">
        <button type="button" class="secondary-btn" id="btnPrevBlock" ${blk.prev_block_pk ? "" : "disabled"}>← Blocco Precedente</button>
        <button type="button" class="secondary-btn" id="btnNextBlock" ${blk.next_block_pk ? "" : "disabled"}>Blocco Successivo →</button>
      </div>
      <div class="reader-text" id="readerTextBody">${blk.highlighted_html}</div>
    `;
    if (blk.prev_block_pk) {
      reader.querySelector("#btnPrevBlock").addEventListener("click", () => openBookBlock(blk.prev_block_pk, ""));
    }
    if (blk.next_block_pk) {
      reader.querySelector("#btnNextBlock").addEventListener("click", () => openBookBlock(blk.next_block_pk, ""));
    }
    renderMath(reader.querySelector("#readerTextBody"));
    const mark = reader.querySelector("mark.verbatim-highlight");
    if (mark && mark.scrollIntoView) {
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function setMode(mode) {
    state.activeMode = mode;
    document.querySelectorAll(".mode-btn[data-mode]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    document.getElementById("panelCard").classList.toggle("hidden", mode !== "card");
    document.getElementById("panelDrill").classList.toggle("hidden", mode !== "drill");
    document.getElementById("panelHero").classList.toggle("hidden", mode !== "hero");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".layer-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".layer-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        state.activeFilter = tab.getAttribute("data-filter");
        renderNodeStrip();
      });
    });

    document.querySelectorAll(".mode-btn[data-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setMode(btn.getAttribute("data-mode")));
    });

    document.getElementById("btnFlagCard").addEventListener("click", async () => {
      if (!state.currentNodeData) return;
      const note = window.prompt("Quale passaggio o formula della scheda ti sembra avere un salto implicito?");
      if (!note || !note.trim()) return;
      await fetchJson("/api/card/flag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: state.currentNodeData.node.id, note }),
      });
      window.alert("Segnalazione registrata in student_state.db (non blocca lo studio).");
    });

    document.getElementById("librarySearchForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const q = document.getElementById("librarySearchInput").value.trim();
      const box = document.getElementById("searchResultsBox");
      if (!q) {
        box.classList.add("hidden");
        return;
      }
      const data = await fetchJson(`/api/search?q=${encodeURIComponent(q)}&limit=25`);
      box.classList.remove("hidden");
      if (!data.results || data.results.length === 0) {
        box.innerHTML = "<div>Nessun passaggio trovato.</div>";
        return;
      }
      box.innerHTML = "";
      data.results.forEach((hit) => {
        const item = document.createElement("div");
        item.className = "search-hit";
        item.innerHTML = `
          <div><strong>${escapeHtml(hit.book_title)}</strong> (p. ${hit.page_start || "?"})</div>
          <div>${hit.snippet_html || ""}</div>
        `;
        item.addEventListener("click", () => openBookBlock(hit.block_pk, ""));
        box.appendChild(item);
      });
    });

    loadOverview();
    loadExtractionStatus();
  });
})();
