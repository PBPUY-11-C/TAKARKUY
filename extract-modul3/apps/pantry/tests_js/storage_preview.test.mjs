import assert from "node:assert/strict";
import test from "node:test";
import { storagePreview } from "../static/pantry/storage_preview.mjs";

const storage = { options: {
  suhu_ruang: { estimated_expires_on: "2026-10-03", shelf_life_days: 2 },
  chiller: { estimated_expires_on: "2026-10-06", shelf_life_days: 5 },
  freezer: { estimated_expires_on: "2026-10-21", shelf_life_days: 20 },
}};

test("changing location immediately selects that location's server-calculated date", () => {
  assert.equal(storagePreview(storage, "chiller").estimated_expires_on, "2026-10-06");
  assert.equal(storagePreview(storage, "freezer").estimated_expires_on, "2026-10-21");
  assert.equal(storagePreview(storage, "suhu_ruang").estimated_expires_on, "2026-10-03");
});

test("blank location uses room temperature without changing the original dates", () => {
  assert.equal(storagePreview(storage, "").estimated_expires_on, "2026-10-03");
});

test("missing location data clears the preview instead of borrowing another location", () => {
  assert.equal(storagePreview(storage, "unknown").estimated_expires_on, "");
  assert.equal(storagePreview(undefined, "chiller").shelf_life_days, null);
  assert.match(storagePreview({options: {chiller: storage.options.chiller}}, "suhu_ruang").message, /belum tersedia/);
});
