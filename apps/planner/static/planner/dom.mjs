// Format angka ke rupiah dengan pemisah ribuan lokal Indonesia, mis. "Rp 150.000".
export const rupiah = (value) => "Rp " + Number(value).toLocaleString("id-ID");

// Membuat elemen DOM dengan class dan teks opsional; teks diisi lewat textContent agar aman dari HTML.
export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Mengambil token CSRF Django dari input csrfmiddlewaretoken di halaman.
export const csrfToken = () => document.querySelector('[name="csrfmiddlewaretoken"]').value;
