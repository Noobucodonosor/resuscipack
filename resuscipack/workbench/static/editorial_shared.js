/* Utility condivise tra /libro e /atlante: modale nativo <dialog>, sanitizzazione sicura e View Transitions. */

export const SPECTRUM_PALETTE = [
  "#0369a1",
  "#0f766e",
  "#b45309",
  "#2d6a4f",
  "#b93815",
  "#334155",
  "#9a3412",
  "#4d7c0f",
];

export function disciplineColor(index) {
  return SPECTRUM_PALETTE[index % SPECTRUM_PALETTE.length];
}

export function initDialogLightDismissFallback() {
  if ("closedBy" in HTMLDialogElement.prototype) {
    return;
  }
  const outside = (e, dialog) => {
    const r = dialog.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  document.querySelectorAll('dialog[closedby="any"]').forEach((dialog) => {
    let pressedOutside = false;
    dialog.addEventListener("pointerdown", (e) => {
      pressedOutside = outside(e, dialog);
    });
    dialog.addEventListener("pointerup", (e) => {
      if (pressedOutside && outside(e, dialog)) {
        dialog.close();
      }
      pressedOutside = false;
    });
  });
}

export function safeSetHTML(el, htmlString) {
  if (!el) return;
  const elements = [
    "p", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "figure", "figcaption", "img",
    "table", "tbody", "thead", "tr", "td", "th", "strong", "em", "code", "pre", "sup",
    "button", "span", "mark", "br", "hr", "div", "aside", "details", "summary", "a",
    "svg", "g", "path", "rect", "circle", "line", "text", "polygon", "polyline",
    "defs", "marker", "tspan",
  ];
  const attributes = [
    "class", "id", "src", "href", "alt", "width", "height", "loading", "type", "title",
    "aria-label", "aria-hidden", "data-note", "data-block-pk", "data-quote",
    "viewbox", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx",
    "fill", "stroke", "stroke-width", "stroke-dasharray", "text-anchor",
    "font-size", "transform", "marker-end", "points",
  ];
  if ("setHTML" in Element.prototype) {
    try {
      el.setHTML(htmlString, { sanitizer: { elements, attributes } });
      return;
    } catch (_err) {
      // fallback se la configurazione locale differisce dalle specifiche browser
    }
  }
  const allowedTags = new Set(elements.map((t) => t.toUpperCase()));
  const allowedAttrs = new Set(attributes.map((a) => a.toLowerCase()));
  const parsed = new DOMParser().parseFromString(String(htmlString || ""), "text/html");
  const cleanNode = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      return document.createTextNode(node.textContent || "");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const tag = node.tagName.toUpperCase();
    if (!allowedTags.has(tag)) {
      const frag = document.createDocumentFragment();
      Array.from(node.childNodes).forEach((ch) => {
        const cleaned = cleanNode(ch);
        if (cleaned) frag.appendChild(cleaned);
      });
      return frag;
    }
    const out = document.createElement(node.tagName.toLowerCase());
    Array.from(node.attributes).forEach((attr) => {
      const name = attr.name.toLowerCase();
      if (!allowedAttrs.has(name)) return;
      if (name === "src" && /^\s*javascript:/i.test(attr.value)) return;
      out.setAttribute(attr.name, attr.value);
    });
    Array.from(node.childNodes).forEach((ch) => {
      const cleaned = cleanNode(ch);
      if (cleaned) out.appendChild(cleaned);
    });
    return out;
  };
  el.replaceChildren();
  Array.from(parsed.body.childNodes).forEach((ch) => {
    const cleaned = cleanNode(ch);
    if (cleaned) el.appendChild(cleaned);
  });
}

export function withViewTransition(updateDomFn, focusElementId) {
  const focusTarget = () => {
    if (!focusElementId) return;
    const node = document.getElementById(focusElementId);
    if (node && typeof node.focus === "function") {
      node.focus({ preventScroll: false });
    }
  };
  if (typeof document.startViewTransition !== "function") {
    Promise.resolve(updateDomFn()).finally(focusTarget);
    return;
  }
  const transition = document.startViewTransition(() => updateDomFn());
  transition.finished.finally(focusTarget);
}

export function initMathRendering(container) {
  if (typeof window.renderMathInElement === "function" && container) {
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

export function createSourceDrawerController() {
  const dialog = document.getElementById("sourceDrawer");
  const titleEl = document.getElementById("sourceDrawerTitle");
  const metaEl = document.getElementById("sourceDrawerMeta");
  const tagsEl = document.getElementById("sourceDrawerDisciplines");
  const bodyEl = document.getElementById("sourceDrawerBody");
  const figuresEl = document.getElementById("sourceDrawerFigures");
  const prevBtn = document.getElementById("sourcePrevBtn");
  const nextBtn = document.getElementById("sourceNextBtn");
  const atlasLink = document.getElementById("sourceOpenInAtlasLink");

  let currentPrevPk = null;
  let currentNextPk = null;

  async function openBlock(blockPk, quoteText = "", sourceLabel = "") {
    if (!dialog || !blockPk) return;
    if (!dialog.open) {
      dialog.showModal();
    }
    titleEl.textContent = "Caricamento pagina originale…";
    metaEl.textContent = "";
    tagsEl.replaceChildren();
    bodyEl.textContent = "";
    figuresEl.replaceChildren();
    prevBtn.disabled = true;
    nextBtn.disabled = true;

    const isStaticMode = document.body?.dataset?.staticMode === "true";
    if (isStaticMode) {
      titleEl.textContent = sourceLabel || "Fonte verificata del corpus";
      metaEl.textContent = "Citazione verificata · Vista Libro pubblica (pagina integrale consultabile nel workbench locale)";
      if (atlasLink) atlasLink.hidden = true;
      bodyEl.replaceChildren();
      const bq = document.createElement("blockquote");
      bq.className = "verbatim-highlight";
      bq.style.padding = "0.85rem 1rem";
      bq.style.borderRadius = "8px";
      bq.textContent = quoteText ? `«${quoteText}»` : "Citazione registrata nell'apparato del capitolo.";
      bodyEl.appendChild(bq);
      const note = document.createElement("p");
      note.className = "t-small muted";
      note.style.marginTop = "0.9rem";
      note.textContent = "Nella distribuzione pubblica statica i volumi coperti da copyright non sono redistribuiti: ogni nota mostra l'estratto verificato e il riferimento bibliografico esatto.";
      bodyEl.appendChild(note);
      initMathRendering(bodyEl);
      return;
    }

    const qs = quoteText ? `?quote=${encodeURIComponent(quoteText)}` : "";
    const resp = await fetch(`/api/block/${encodeURIComponent(blockPk)}${qs}`);
    if (!resp.ok) {
      titleEl.textContent = "Pagina non disponibile";
      bodyEl.textContent = "Impossibile recuperare il passaggio richiesto dal catalogo locale.";
      return;
    }
    const data = await resp.json();
    titleEl.textContent = data.clean_book_title || data.book_title || "Opera originale";

    const metaParts = [];
    if (data.author) metaParts.push(data.author);
    if (data.year) metaParts.push(String(data.year));
    const pageDisplay = data.printed_page || data.page_start;
    if (pageDisplay) metaParts.push(`pagina ${pageDisplay}`);
    if (data.section_title) metaParts.push(data.section_title);
    metaEl.textContent = metaParts.join(" · ");

    tagsEl.replaceChildren();
    if (Array.isArray(data.disciplines)) {
      data.disciplines.forEach((d) => {
        const pill = document.createElement("span");
        pill.className = "tag-pill";
        pill.textContent = d.label_it || d.slug;
        tagsEl.appendChild(pill);
      });
    }

    safeSetHTML(bodyEl, data.highlighted_html || "");
    initMathRendering(bodyEl);

    figuresEl.replaceChildren();
    if (Array.isArray(data.figures)) {
      data.figures.forEach((fig) => {
        const img = document.createElement("img");
        img.src = fig.url;
        img.alt = `Tavola dell'opera alla pagina ${fig.page || ""}`;
        img.loading = "lazy";
        figuresEl.appendChild(img);
      });
    }

    currentPrevPk = data.prev_block_pk || null;
    currentNextPk = data.next_block_pk || null;
    prevBtn.disabled = !currentPrevPk;
    nextBtn.disabled = !currentNextPk;

    if (atlasLink && data.book_pk) {
      atlasLink.href = `/atlante/libro/${data.book_pk}`;
      atlasLink.hidden = false;
    }
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentPrevPk) openBlock(currentPrevPk, "");
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (currentNextPk) openBlock(currentNextPk, "");
    });
  }

  return { openBlock };
}
