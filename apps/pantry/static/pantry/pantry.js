import { needsGeminiFallback, parseReceiptText } from "./receipt_parser.mjs";
import { storagePreview } from "./storage_preview.mjs";
import { createActionKeyStore, locationExpiry, isAISuggestion, correctionConsent } from "./batch_actions.mjs";

const fileInput = document.getElementById("receipt-file");
const preview = document.getElementById("receipt-preview");
const receiptName = document.getElementById("receipt-name");
const receiptCount = document.getElementById("receipt-count");
const scanProgress = document.getElementById("scan-progress");
const scanFeedback = document.getElementById("scan-feedback");
const receiptDate = document.getElementById("receipt-date");
const draftEmpty = document.getElementById("draft-empty");
const draftTableWrap = document.getElementById("draft-table-wrap");
const draftRows = document.getElementById("draft-rows");
const draftCount = document.getElementById("draft-count");
const saveDraftButton = document.getElementById("save-draft");
const manualForm = document.getElementById("manual-form");
const manualFeedback = document.getElementById("manual-feedback");
const csrfToken = document.querySelector('[name="csrfmiddlewaretoken"]').value;
const geminiFallbackEnabled = fileInput.dataset.geminiFallback === "true";
let previewUrl = null;
let workerPromise = null;
let hasUploaded = false;
let scanVersion = 0;

function feedback(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function draftElements() {
  return [...draftRows.querySelectorAll("tr[data-draft]")];
}

function refreshDraftCount() {
  const count = draftElements().length;
  draftCount.textContent = `${count} bahan`;
  receiptCount.textContent = `${count} Item Terdeteksi`;
  draftTableWrap.hidden = !count;
  draftEmpty.hidden = !!count;
  draftEmpty.querySelector("p").textContent = hasUploaded
    ? "Belum ada bahan yang terbaca. Coba unggah struk lain atau tambah baris manual."
    : "Belum ada struk yang diunggah. Unggah struk untuk mendeteksi bahan makanan secara otomatis.";
}

function addControlCell(row, control) {
  const cell = document.createElement("td");
  cell.append(control);
  row.append(cell);
}

function addInput(row, field, type, value, label) {
  const input = document.createElement("input");
  input.dataset.field = field;
  input.type = type;
  input.value = value || "";
  input.required = true;
  input.setAttribute("aria-label", label);
  if (type === "number") {
    input.min = field === "shelf_life_days" ? "1" : "0.001";
    input.step = field === "shelf_life_days" ? "1" : "0.001";
    if (field === "shelf_life_days") input.max = "3650";
  }
  if (field === "name") input.maxLength = 255;
  addControlCell(row, input);
}

function addSelect(row, field, sourceId, value, label) {
  const source = document.getElementById(sourceId);
  const select = document.createElement("select");
  select.dataset.field = field;
  select.required = true;
  select.setAttribute("aria-label", label);
  for (const option of source.options) select.append(option.cloneNode(true));
  select.value = value || "";
  addControlCell(row, select);
}

function addDraftRow(item = {}) {
  const row = document.createElement("tr");
  row.dataset.draft = "";
  row.dataset.originalName = item.raw || item.name || "";
  if (item.rawLine) row.title = `Teks struk: ${item.rawLine}`;
  addInput(row, "name", "text", item.name, "Nama bahan");
  const nameInput = row.querySelector('[data-field="name"]');
  const suggestion = document.createElement("div");
  suggestion.className = "name-suggestion";
  suggestion.hidden = true;
  nameInput.parentElement.append(suggestion);
  const confirmation = document.createElement("label");
  confirmation.className = "name-suggestion";
  confirmation.hidden = true;
  const accepted = document.createElement("input");
  accepted.type = "checkbox";
  accepted.className = "confirm-name";
  confirmation.append(accepted, document.createTextNode(" Nama ini sudah saya periksa (opsional)"));
  nameInput.parentElement.append(confirmation);
  if (item.method === "ai_foto_perlu_periksa") {
    if (item.ingredient_code) row.dataset.ingredientCode = item.ingredient_code;
    row.dataset.suggestionMethod = item.method;
    suggestion.textContent = `Dibaca dengan AI dari “${row.dataset.originalName}”. Periksa dan ubah jika keliru.`;
    suggestion.hidden = false;
    confirmation.hidden = false;
  }
  nameInput.addEventListener("input", () => {
    row.dataset.userEdited = "true";
    delete row.dataset.ingredientCode;
    delete row.dataset.location;
    delete row.dataset.minDays;
    suggestion.hidden = true;
    accepted.checked = false;
    confirmation.hidden = true;
  });
  addInput(row, "quantity", "number", item.quantity, "Jumlah bahan");
  addSelect(row, "unit", "ocr-unit-options", item.unit, "Satuan bahan");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-row";
  remove.textContent = "Hapus";
  remove.setAttribute("aria-label", `Hapus baris ${item.name || "bahan"}`);
  remove.addEventListener("click", () => {
    row.remove();
    refreshDraftCount();
  });
  addControlCell(row, remove);
  draftRows.append(row);
  refreshDraftCount();
  return row;
}

async function suggestRows(rows, version, allowLLM = true) {
  const draft = draftElements();
  try {
    const response = await fetch("/modul2/suggestions/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      credentials: "same-origin",
      body: JSON.stringify({ names: rows.map((row) => row.raw || row.name), allow_llm: allowLLM }),
    });
    if (!response.ok) return;
    const data = await response.json();
    if (version !== scanVersion) return;
    data.suggestions.forEach((result, index) => {
      const row = draft[index];
      if (!row || !row.isConnected || !result.suggested_name || row.dataset.originalName !== result.raw_name) return;
      const nameInput = row.querySelector('[data-field="name"]');
      // A late response must not overwrite a correction the user has already typed.
      if (row.dataset.userEdited || nameInput.value !== result.raw_name) return;
      const box = row.querySelector(".name-suggestion");
      const details = result.storage
        ? ` · ${result.storage.location === "chiller" ? "Kulkas" : "Suhu ruang"} · referensi ${result.storage.min_days}–${result.storage.max_days} hari sejak ${result.storage.starting_event === "mulai_disimpan" ? "mulai disimpan" : "dibeli"}`
        : " · acuan masa simpan suhu ruang belum tersedia";
      nameInput.value = result.suggested_name;
      row.dataset.ingredientCode = result.ingredient_code;
      row.dataset.suggestionMethod = result.method;
      const aiLabel = isAISuggestion(result.method) ? " dengan AI" : "";
      box.textContent = result.raw_name === result.suggested_name
        ? `Cocok dengan katalog${aiLabel}${details}`
        : `Diperbaiki otomatis${aiLabel} dari “${result.raw_name}”${details}. Periksa dan ubah jika keliru.`;
      box.hidden = false;
      row.querySelector(".confirm-name").parentElement.hidden = false;
    });
  } catch (_) {
    // OCR and manual correction still work when recommendation service is unavailable.
  }
}

function showDraftItems(rows, {photoAttempted = false, photoSucceeded = false} = {}) {
  draftRows.replaceChildren();
  rows.forEach(addDraftRow);
  if (rows.length && !photoSucceeded) suggestRows(rows, scanVersion, !photoAttempted);
  refreshDraftCount();
  return rows.length;
}

async function readWithGemini(file) {
  const form = new FormData();
  form.append("image", file);
  const response = await fetch("/modul2/ocr-fallback/", {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
    credentials: "same-origin",
    body: form,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Pemindaian cadangan gagal.");
  if (!Array.isArray(data.items)) throw new Error("Hasil pemindaian cadangan tidak valid.");
  return data.items;
}

async function prepareReceiptImage(file, enhance = false) {
  if (typeof createImageBitmap !== "function") return { image: file, width: null };
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
    const widthBefore = bitmap.width;
    if (!enhance && widthBefore >= 600) return { image: file, width: widthBefore };
    const scale = Math.max(1, Math.min(1400 / bitmap.width, 6000 / bitmap.height, 6));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = width + 32;
    canvas.height = height + 32;
    const context = canvas.getContext("2d");
    if (!context) return { image: file, width: widthBefore };
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.filter = "grayscale(1) contrast(1.3)";
    context.drawImage(bitmap, 16, 16, width, height);
    const enlarged = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    return { image: enlarged || file, width: widthBefore };
  } catch (_) {
    // Canvas conversion is optional; do not block OCR if a browser cannot do it.
    return { image: file, width: bitmap?.width || null };
  } finally {
    bitmap?.close();
  }
}

async function getWorker() {
  if (!window.Tesseract) throw new Error("Pustaka OCR gagal dimuat. Periksa koneksi internet lalu muat ulang halaman.");
  if (!workerPromise) {
    workerPromise = window.Tesseract.createWorker(["ind", "eng"], 1, {
      logger: (event) => {
        if (event.status === "recognizing text") {
          scanProgress.textContent = `Memindai struk… ${Math.round((event.progress || 0) * 100)}%`;
        }
      },
    }).catch((error) => {
      workerPromise = null;
      throw error;
    });
  }
  return workerPromise;
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) {
    feedback(scanFeedback, "Pilih gambar JPG, PNG, atau WebP berukuran maksimal 10 MB.", true);
    return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
  preview.hidden = false;
  receiptName.textContent = `Struk: ${file.name}`;
  scanVersion += 1;
  hasUploaded = true;
  draftRows.replaceChildren();
  refreshDraftCount();
  feedback(scanFeedback, "Menyiapkan pemindaian…");
  scanProgress.textContent = "Memuat mesin OCR…";
  fileInput.disabled = true;
  try {
    const prepared = await prepareReceiptImage(file);
    let rawText = "";
    let confidence = null;
    let ocrError = null;
    try {
      const worker = await getWorker();
      const result = await worker.recognize(prepared.image);
      rawText = result.data.text || "";
      confidence = result.data.confidence;
      let parsedCount = parseReceiptText(rawText).length;
      if (parsedCount < 2 || needsGeminiFallback(confidence, parsedCount)) {
        const retryImage = prepared.image === file
          ? (await prepareReceiptImage(file, true)).image
          : file;
        if (retryImage !== prepared.image) {
          try {
            scanProgress.textContent = "Mencoba pembacaan kedua…";
            const retry = await worker.recognize(retryImage);
            const retryText = retry.data.text || "";
            const retryCount = parseReceiptText(retryText).length;
            const retryConfidence = retry.data.confidence;
            if (retryCount > parsedCount || (retryCount === parsedCount && Number.isFinite(retryConfidence)
              && (!Number.isFinite(confidence) || retryConfidence > confidence))) {
              rawText = retryText;
              parsedCount = retryCount;
              confidence = retryConfidence;
            }
          } catch (_) {
            // Keep the first OCR result when an optional second pass fails.
          }
        }
      }
    } catch (error) {
      ocrError = error;
    }
    let rows = parseReceiptText(rawText);
    let usedGemini = false;
    let photoAttempted = false;
    let fallbackEmpty = false;
    let fallbackError = null;
    if (geminiFallbackEnabled && (ocrError || needsGeminiFallback(confidence, rows.length))) {
      photoAttempted = true;
      scanProgress.textContent = "Mencoba pembacaan cadangan dengan AI…";
      try {
        const aiRows = await readWithGemini(file);
        if (aiRows.length) {
          rows = aiRows;
          usedGemini = true;
        } else {
          fallbackEmpty = true;
        }
      } catch (error) {
        fallbackError = error;
      }
    }
    if (ocrError && !usedGemini) throw ocrError;
    const found = showDraftItems(rows, {photoAttempted, photoSucceeded: usedGemini});
    if (usedGemini) {
      feedback(scanFeedback, `${found} calon bahan dibaca ulang dengan AI. Periksa nama, jumlah, dan satuannya sebelum menyimpan.`);
    } else if (fallbackError) {
      feedback(scanFeedback, `${fallbackError.message} ${found ? `${found} hasil OCR awal masih tersedia untuk diperiksa.` : "Tambahkan baris manual atau coba foto lain."}`, !found);
    } else if (fallbackEmpty) {
      feedback(scanFeedback, found
        ? `AI belum menemukan bahan tambahan; ${found} hasil OCR awal masih tersedia untuk diperiksa.`
        : "OCR dan AI belum menemukan bahan. Coba foto lain atau tambah baris manual.", !found);
    } else if (Number.isFinite(confidence) && confidence < 80 && found) {
      feedback(scanFeedback, `Pembacaan struk kurang yakin (${Math.round(confidence)}%). Periksa ${found} calon bahan dengan teliti.`);
    } else if (prepared.width && prepared.width < 600) {
      feedback(scanFeedback, found
        ? `Foto kecil (${prepared.width} piksel) telah dipindai; ${found} calon bahan ditemukan. Periksa nama, jumlah, dan satuannya.`
        : rawText.trim()
          ? `Sebagian teks terbaca, tetapi barang belum dikenali. Lebar foto hanya ${prepared.width} piksel; coba foto asli yang lebih tajam.`
          : `Teks belum terbaca dari foto ${prepared.width} piksel. Gunakan foto asli, bukan gambar pratinjau kecil.`,
      !found);
    } else if (!found) {
      feedback(scanFeedback, rawText.trim()
        ? "Teks struk terbaca, tetapi baris barang belum dikenali. Coba foto yang lebih terang dan lurus."
        : "Teks struk belum terbaca. Coba foto yang lebih terang, fokus, dan memenuhi bingkai.", true);
    } else {
      feedback(scanFeedback, `${found} calon bahan ditemukan. Periksa dan koreksi baris yang keliru.`);
    }
    scanProgress.textContent = "Pemindaian selesai. Tidak ada item yang disimpan otomatis.";
  } catch (error) {
    feedback(scanFeedback, `Pemindaian gagal: ${error.message}. Kamu masih bisa menambah baris secara manual.`, true);
    scanProgress.textContent = "Pemindaian belum berhasil.";
  } finally {
    fileInput.disabled = false;
    fileInput.value = "";
  }
});

document.getElementById("add-draft-row").addEventListener("click", () => {
  const row = addDraftRow();
  row.querySelector('[data-field="name"]').focus();
});

const actionKey = createActionKeyStore();

async function saveItems(items, source) {
  const response = await fetch("/modul2/items/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
    credentials: "same-origin",
    body: JSON.stringify({ source, items, operation_key: actionKey(`create-${source}`, {source, items}) }),
  });
  const data = await response.json().catch(() => {
    throw new Error("Sesi tidak valid atau server sedang bermasalah. Muat ulang halaman lalu coba lagi.");
  });
  if (!response.ok) {
    const firstRow = Object.values(data.rows || {})[0] || {};
    const firstFieldErrors = Object.values(firstRow)[0] || [];
    throw new Error(firstFieldErrors[0]?.message || data.error || "Gagal menyimpan bahan.");
  }
  return data;
}

saveDraftButton.addEventListener("click", async () => {
  const rows = draftElements();
  if (!rows.length) {
    feedback(scanFeedback, "Belum ada bahan untuk disimpan.", true);
    return;
  }
  for (const row of rows) {
    const invalid = [...row.querySelectorAll("input, select")].find((control) => !control.checkValidity());
    if (invalid) {
      invalid.reportValidity();
      feedback(scanFeedback, "Lengkapi nama, jumlah, dan satuan setiap baris.", true);
      return;
    }
  }
  const items = rows.map((row) => Object.fromEntries(
    [...row.querySelectorAll("[data-field]")].map((control) => [control.dataset.field, control.value])
  ));
  if (receiptDate.value && !receiptDate.checkValidity()) {
    receiptDate.reportValidity();
    return;
  }
  items.forEach((item, index) => {
    const row = rows[index];
    item.original_name = row.dataset.originalName || "";
    Object.assign(item, correctionConsent(row.dataset, row.querySelector(".confirm-name")?.checked));
    if (row.dataset.ingredientCode) {
      item.ingredient_code = row.dataset.ingredientCode;
    }
    if (receiptDate.value) item.starting_on = receiptDate.value;
  });
  saveDraftButton.disabled = true;
  feedback(scanFeedback, "Menyimpan stok…");
  try {
    await saveItems(items, "ocr");
    window.location.reload();
  } catch (error) {
    feedback(scanFeedback, error.message, true);
    saveDraftButton.disabled = false;
  }
});

manualForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!manualForm.reportValidity()) return;
  const item = Object.fromEntries(new FormData(manualForm).entries());
  delete item.csrfmiddlewaretoken;
  const submit = manualForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  feedback(manualFeedback, "Menyimpan stok…");
  try {
    await saveItems([item], "manual");
    window.location.reload();
  } catch (error) {
    feedback(manualFeedback, error.message, true);
    submit.disabled = false;
  }
});

const pantryStorage = JSON.parse(document.getElementById("pantry-storage-data").textContent);
document.querySelectorAll("[data-pantry-item]").forEach((row) => {
  const button = row.querySelector(".save-pantry-details");
  const deleteButton = row.querySelector(".delete-pantry-item");
  const rowFeedback = row.querySelector(".row-feedback");
  const locationInput = row.querySelector("[data-pantry-location]");
  const expiryInput = row.querySelector("[data-pantry-expiry]");
  const storageFeedback = row.querySelector("[data-storage-feedback]");
  const sourceInput = row.querySelector("[data-expiry-source]");
  let expiryMode = "";
  locationInput.addEventListener("change", () => {
    const estimate = storagePreview(pantryStorage[row.dataset.pantryItem], locationInput.value);
    const change = locationExpiry(sourceInput.value, expiryInput.value, estimate);
    expiryMode = change.mode;
    expiryInput.value = change.date;
    storageFeedback.textContent = estimate.message;
    feedback(rowFeedback, "Perkiraan diperbarui. Tekan Simpan untuk menyimpan perubahan.");
  });
  expiryInput.addEventListener("input", () => {
    expiryMode = "manual";
    if (sourceInput.value !== "label") sourceInput.value = "manual";
    storageFeedback.textContent = "Tanggal diisi manual; utamakan label kemasan.";
  });
  sourceInput.addEventListener("change", () => {
    expiryMode = sourceInput.value === "estimate" ? "auto" : "manual";
  });
  row.querySelector("[data-edit-name]").addEventListener("input", () => {
    row.querySelector("[data-edit-ingredient]").value = "";
  });
  button.addEventListener("click", async () => {
    const location = locationInput.value;
    if (!expiryInput.checkValidity()) {
      expiryInput.reportValidity();
      return;
    }
    button.disabled = true;
    locationInput.disabled = true;
    expiryInput.disabled = true;
    feedback(rowFeedback, "Menyimpan…");
    const changes = {
      location, estimated_expires_on: expiryInput.value, expiry_mode: expiryMode,
      expiry_source: sourceInput.value, version: Number(row.dataset.version),
      name: row.querySelector("[data-edit-name]").value,
      quantity: row.querySelector("[data-edit-quantity]").value,
      unit: row.querySelector("[data-edit-unit]").value,
      category: row.querySelector("[data-edit-category]").value,
      ingredient_code: row.querySelector("[data-edit-ingredient]").value,
      pack_weight_g: row.querySelector("[data-edit-weight]").value,
    };
    try {
      const response = await fetch(`/modul2/items/${row.dataset.pantryItem}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        credentials: "same-origin",
        body: JSON.stringify({ ...changes, operation_key: actionKey(`edit-${row.dataset.pantryItem}`, changes) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Gagal menyimpan perubahan.");
      row.dataset.version = data.version;
      sourceInput.value = data.expiry_source;
      locationInput.value = data.location;
      expiryInput.value = data.estimated_expires_on;
      storageFeedback.textContent = data.message;
      expiryMode = "";
      feedback(rowFeedback, "Tersimpan");
    } catch (error) {
      feedback(rowFeedback, error.message || "Gagal menyimpan perubahan.", true);
    } finally {
      button.disabled = false;
      locationInput.disabled = false;
      expiryInput.disabled = false;
    }
  });
  row.querySelector(".pantry-history").addEventListener("click", async () => {
    const output = row.querySelector("[data-history-output]");
    try {
      const response = await fetch(`/modul2/items/${row.dataset.pantryItem}/movements/`, {credentials: "same-origin"});
      const data = await response.json();
      if (!response.ok) throw new Error("Riwayat tidak tersedia.");
      output.replaceChildren(...data.movements.map((entry) => {
        const line = document.createElement("p");
        line.textContent = `${new Date(entry.created_at).toLocaleString("id-ID")} · ${entry.kind}: ${entry.before} → ${entry.after}`;
        return line;
      }));
      output.hidden = !output.hidden;
    } catch (error) { feedback(rowFeedback, error.message, true); }
  });
  deleteButton.addEventListener("click", async () => {
    if (!window.confirm(`Hapus ${deleteButton.dataset.itemName} dari stok pantry?`)) return;
    deleteButton.disabled = true;
    feedback(rowFeedback, "Menghapus…");
    try {
      const response = await fetch(`/modul2/items/${row.dataset.pantryItem}/delete/`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        credentials: "same-origin",
        body: JSON.stringify({ version: Number(row.dataset.version), operation_key: actionKey(`delete-${row.dataset.pantryItem}`, {version: Number(row.dataset.version)}) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Gagal menghapus bahan.");
      row.remove();
      if (!document.querySelector("[data-pantry-item]")) window.location.reload();
    } catch (error) {
      feedback(rowFeedback, error.message || "Gagal menghapus bahan.", true);
      deleteButton.disabled = false;
    }
  });
});

document.getElementById("stock-recipes-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const output = document.getElementById("stock-recipes-output");
  button.disabled = true;
  try {
    const servings = document.getElementById("stock-recipe-servings").value;
    const response = await fetch(`/modul2/recipes/?servings=${encodeURIComponent(servings)}`, {credentials: "same-origin"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Tidak dapat membaca kecocokan stok.");
    if (!data.recipes.length) output.textContent = "Belum ada menu cocok. Hubungkan bahan ke katalog dan lengkapi berat/tanggal stok jika diketahui.";
    else output.replaceChildren(...data.recipes.map((recipe) => {
      const line = document.createElement("p");
      line.textContent = `${recipe.name} · ${recipe.complete ? "Bahan cukup" : "Sebagian bahan tersedia"}${recipe.instructions_pending_review ? " · langkah memasak belum dipublikasikan" : ""}`;
      return line;
    }));
  } catch (error) { output.textContent = error.message; }
  finally { button.disabled = false; }
});

window.addEventListener("pagehide", () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  if (workerPromise) workerPromise.then((worker) => worker.terminate()).catch(() => {});
});
