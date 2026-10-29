
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const script = readFileSync(
  new URL(
    "../../../apps/pantry/static/pantry/receipt_guide.js",
    import.meta.url,
  ),
  "utf8",
);

class MockElement {
  constructor() {
    this.listeners = {};
    this.attributes = {};
    this.open = false;
    this.focused = false;
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  focus() { this.focused = true; document.activeElement = this; }
  trigger(name, event = {}) {
    return this.listeners[name]?.({
      target: this,
      currentTarget: this,
      preventDefault() {
        this.defaultPrevented = true;
      },
      ...event,
    });
  }
}

class MockDialog extends MockElement {
  constructor() {
    super();
    this.closeButton = new MockElement();
    this.closeButton.dataset = { guideClose: "" };
  }
  querySelectorAll(selector) { if (selector === "[data-guide-close]") return [this.closeButton]; return []; }
  showModal() { this.open = true; }
  close() { this.open = false; this.trigger("close"); }
}

function setup({ withDialog = true, withOpener = true } = {}) {
  const dialog = withDialog ? new MockDialog() : null;
  const opener = withOpener ? new MockElement() : null;

  globalThis.document = {
    activeElement: null,
    getElementById(id) { if (id === "receipt-guide-dialog") return dialog; if (id === "receipt-guide-open") return opener; return null; }
  };
  runInNewContext(script, { document });
  return { dialog, opener };
}

// karna ga ada dianggapnya bener
test("The guide modal does not open automatically", () => {
  const { dialog, opener } = setup();

  assert.equal(dialog.open, false);
  assert.equal(opener.getAttribute("aria-expanded"), null);
  assert.equal(typeof opener.listeners.click, "function"); // Memastikan tombol buat bukanya ada
});

test("Clicking the guide button opens the modal and updates aria-expanded", () => {
  const { dialog, opener } = setup();

  opener.trigger("click");

  assert.equal(dialog.open, true);
  assert.equal(opener.getAttribute("aria-expanded"), "true");
});

test("Clicking the close button closes the modal and restores focus", () => {
  const { dialog, opener } = setup();

  opener.trigger("click");
  dialog.closeButton.trigger("click");

  assert.equal(dialog.open, false);
  assert.equal(opener.getAttribute("aria-expanded"), "false");
  assert.equal(opener.focused, true);
});

test("Clicking the backdrop closes the modal", () => {
  const { dialog, opener } = setup();

  opener.trigger("click");

  dialog.trigger("mousedown", { target: dialog });
  dialog.trigger("click", { target: dialog });

  assert.equal(dialog.open, false);
  assert.equal(opener.getAttribute("aria-expanded"), "false");
});

test("Clicking inside the dialog does not close the modal", () => {
  const { dialog, opener } = setup();
  const content = new MockElement();

  opener.trigger("click");

  dialog.trigger("mousedown", { target: content });
  dialog.trigger("click", { target: content });

  assert.equal(dialog.open, true);
});
