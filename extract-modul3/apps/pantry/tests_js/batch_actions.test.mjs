import assert from "node:assert/strict";
import test from "node:test";
import {createActionKeyStore, locationExpiry, isAISuggestion, correctionConsent} from "../static/pantry/batch_actions.mjs";

test("a retry retains its operation key; a changed payload gets a new key", () => {
  let count = 0;
  const key = createActionKeyStore(() => String(++count));
  assert.equal(key("create", {quantity: 1}), "1");
  assert.equal(key("create", {quantity: 1}), "1");
  assert.equal(key("create", {quantity: 2}), "2");
  assert.equal(key("delete", {quantity: 2}), "3");
});

test("manual and label dates are never overwritten by a location preview", () => {
  for (const source of ["manual", "label"]) {
    assert.deepEqual(locationExpiry(source, "2026-10-06", {estimated_expires_on: "2027-01-01"}),
      {mode: "manual", date: "2026-10-06"});
  }
});

test("automatic dates use the server's conservative estimate", () => {
  assert.deepEqual(locationExpiry("estimate", "2026-10-08", {estimated_expires_on: "2026-10-06"}),
    {mode: "auto", date: "2026-10-06"});
});

test("legacy dates stay unchanged without falsely becoming manual dates", () => {
  assert.deepEqual(locationExpiry("legacy", "2026-10-08", {estimated_expires_on: "2027-01-01"}),
    {mode: "auto", date: "2026-10-08"});
});

test("cached AI remains labelled as AI; autofill alone is not consent", () => {
  assert.equal(isAISuggestion("ai_cache_perlu_periksa"), true);
  assert.equal(isAISuggestion("ai_perlu_periksa"), true);
  assert.equal(isAISuggestion("katalog"), false);
  assert.deepEqual(correctionConsent({suggestionMethod: "ai_perlu_periksa"}), {accepted: false, user_edited: false});
  assert.deepEqual(correctionConsent({}, true), {accepted: true, user_edited: false});
  assert.deepEqual(correctionConsent({userEdited: "true"}), {accepted: false, user_edited: true});
});
