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
    "p", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "figure", "img",
    "table", "tbody", "tr", "td", "th", "strong", "em", "code", "sup", "button",
    "span", "mark", "br",
  ];
  const attributes = [
    "class", "src", "alt", "width", "height", "loading", "type", "title",
    "aria-label", "data-note", "data-block-pk", "data-quote",
  ];
  if ("setHTML" in Element.prototype) {
    try {
      el.setHTML(htmlString, { sanitizer: { elements, attributes } });
      return;
    } catch (_err) {
      // fallback se la configurazione locale differisce dalle specifiche browser
    }
  }
  el.innerHTML = htmlString;
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

  async function openBlock(blockPk, quoteText = "") {
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
