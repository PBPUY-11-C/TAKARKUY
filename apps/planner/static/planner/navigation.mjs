let lastPage = null;
let afterSwap = () => {};

export function onSwap(callback) { afterSwap = callback; }

export function navigate(url) {
  const destination = new URL(url, window.location.origin);
  if (destination.pathname === window.location.pathname && destination.search === window.location.search) {
    window.location.hash = destination.hash;
    window.location.reload();
  } else {
    window.location.assign(url);
  }
}

export function canSwap() {
  return Boolean(window.DOMParser && window.history?.pushState && document.getElementById("main"));
}

// Fetch a planner page and replace only <main>, so actions finish without a full reload.
export async function swap(url, options = {}, record = true) {
  if (!canSwap()) return false;
  const target = new URL(url, window.location.origin);
  let response;
  let html;
  try {
    response = await fetch(target, { credentials: "same-origin", ...options, headers: { Accept: "text/html" } });
    if (!(response.headers.get("content-type") || "").includes("text/html")) return false;
    html = await response.text();
  } catch { return false; }
  const page = new DOMParser().parseFromString(html, "text/html");
  const next = page.getElementById("main");
  if (!next?.querySelector(".planner-form")) return false;
  document.querySelectorAll("dialog[open]").forEach((open) => open.close());
  document.getElementById("main").replaceWith(document.adoptNode(next));
  document.title = page.title;
  if (record && (!options.method || response.redirected)) {
    const landed = new URL(response.url || target);
    landed.hash = target.hash;
    if (landed.href !== window.location.href) window.history.pushState({ planner: true }, "", landed);
  }
  lastPage = window.location.pathname + window.location.search;
  afterSwap();
  globalThis.TakarKuyImages?.bind(document.getElementById("main"));
  const anchor = window.location.hash && document.querySelector(window.location.hash);
  if (anchor && anchor.tagName !== "DIALOG") anchor.scrollIntoView({ block: "start" });
  else if (!anchor) window.scrollTo({ top: 0 });
  return true;
}

export async function visit(url, message) {
  if (await swap(url)) {
    if (message) globalThis.TakarKuy?.toast(message);
    return;
  }
  if (message) globalThis.TakarKuy?.flash(message);
  navigate(url);
}

// Back/forward and a[data-swap] links reuse swap() instead of reloading the page.
export function bindNavigation() {
  lastPage = window.location.pathname + window.location.search;
  window.addEventListener?.("popstate", async () => {
    if (window.location.pathname + window.location.search === lastPage) return;
    if (!(await swap(window.location.href, {}, false))) window.location.reload();
  });
  document.addEventListener?.("click", async (event) => {
    const link = event.target.closest?.("a[data-swap]");
    if (!link || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!canSwap()) return;
    event.preventDefault();
    if (!(await swap(link.href))) window.location.assign(link.href);
  });
}
