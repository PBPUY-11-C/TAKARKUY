import assert from "node:assert/strict";
import { test } from "node:test";
import { parseReceiptText } from "../static/pantry/receipt_parser.mjs";

test("reads a simple item with explicit weight and skips total", () => {
  assert.deepEqual(parseReceiptText("DAGING AYAM FILLET 350 GR 24.500\nTOTAL 24.500"), [
    { rawLine: "DAGING AYAM FILLET 350 GR 24.500", name: "DAGING AYAM FILLET", quantity: "350", unit: "g" },
  ]);
});

test("keeps package count without inventing its unit", () => {
  const rows = parseReceiptText("SEDAAP KARI SPC75 160 2.590 414.400\nHEMAT -62.400\nULTRA PLN 1L 6 16.990 101.940");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].quantity, "160");
  assert.equal(rows[0].unit, "");
  assert.equal(rows[1].name, "ULTRA PLN 1L");
  assert.equal(rows[1].quantity, "6");
});

test("maps printed packaging units to the simplified pantry unit", () => {
  const rows = parseReceiptText("TEMPE 2 PAPAN 8.000\nTAHU 1 KOTAK 6.000");
  assert.deepEqual(rows.map(({ quantity, unit }) => [quantity, unit]), [["2", "pack"], ["1", "pack"]]);
});

test("does not guess missing quantity and ignores receipt metadata", () => {
  const rows = parseReceiptText("PT LION SUPER INDO\nTanggal: 06-06-97\nBAYAM HIJAU 4.500\nSubtotal 4.500");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, "BAYAM HIJAU");
  assert.equal(rows[0].quantity, "");
});

test("keeps an item with a clear quantity and unit when OCR misses its price", () => {
  assert.deepEqual(parseReceiptText("BAYAM HIJAU 1 IKAT\nTOTAL 8.000"), [
    { rawLine: "BAYAM HIJAU 1 IKAT", name: "BAYAM HIJAU", quantity: "1", unit: "ikat" },
  ]);
});

test("keeps a supermarket item with quantity when its price is unreadable", () => {
  assert.deepEqual(parseReceiptText("SEDAAP KARI SPC75 160\nPT LION SUPER INDO"), [
    { rawLine: "SEDAAP KARI SPC75 160", name: "SEDAAP KARI SPC75", quantity: "160", unit: "" },
  ]);
});

test("reads item rows from the large supermarket receipt without tax or discounts", () => {
  const rows = parseReceiptText(`DESKRIPSI QTY HARGA TOTAL
SEDAAP KARI SPC75 160 2.590 414.400
HEMAT -62.400
ULTRA PLN 1L 6 16.990 101.940
INDOMI GORENG BW/ 160 2.600 416.000
Sub Total (Termasuk PPN) 1.002.500
Pembayaran-UOB MASTER ELE 1.002.500`);
  assert.deepEqual(rows.map(({ name, quantity }) => [name, quantity]), [
    ["SEDAAP KARI SPC75", "160"], ["ULTRA PLN 1L", "6"], ["INDOMI GORENG BW", "160"],
  ]);
});

test("ignores tax summary rows on the busy-background receipt", () => {
  const rows = parseReceiptText(`LACT T/PASTE T&CF 2 16.990 33.980
NUVO FAMILY NAT/P 1 16.590 16.590
HEMAT -16.990
BKP 105.140 POT.BRG 35.120
DPP 63.081 PPN 6.939
TOTAL 70.000`);
  assert.deepEqual(rows.map(({ name, quantity }) => [name, quantity]), [
    ["LACT T/PASTE T&CF", "2"], ["NUVO FAMILY NAT/P", "1"],
  ]);
});
