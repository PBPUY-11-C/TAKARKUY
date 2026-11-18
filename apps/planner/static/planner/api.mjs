import { csrfToken } from "./dom.mjs";

// Pesan error yang mudah dipahami user berdasarkan kode status HTTP (CSRF, login, 404, server).
export function failureMessage(status) {
  if (status === 403) return "Sesi keamanan halaman kedaluwarsa. Muat ulang halaman lalu coba lagi.";
  if (status === 401 || status === 302) return "Sesi login berakhir. Masuk lagi lalu coba kembali.";
  if (status === 404) return "Rencana tidak ditemukan atau sudah diganti. Muat ulang halaman.";
  if (status >= 500) return `Server sedang bermasalah (kode ${status}). Coba lagi sebentar lagi.`;
  return `Request belum berhasil (kode ${status}). Muat ulang halaman.`;
}

// GET jika tanpa data, POST JSON dengan token CSRF jika ada data; mengembalikan body JSON atau melempar error yang terbaca.
export async function request(url, data) {
  const options = { credentials: "same-origin", headers: { Accept: "application/json" } };
  if (data !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.headers["X-CSRFToken"] = csrfToken();
    options.body = JSON.stringify(data);
  }
  const response = await fetch(url, options);
  let body;
  try { body = await response.json(); } catch { throw new Error(failureMessage(response.status)); }
  if (!response.ok) throw new Error(body.error || "Request belum berhasil.");
  return body;
}
