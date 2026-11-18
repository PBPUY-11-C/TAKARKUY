// True jika lat/lon berupa angka hingga dalam rentang koordinat bumi.
export function validPoint(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}
// Jarak garis lurus (haversine) dalam km antara dua titik [lat, lon].
export function distanceKm(a, b) {
  // Konversi derajat ke radian.
  const rad = value => value * Math.PI / 180;
  const dLat = rad(b[0] - a[0]), dLon = rad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}
// Menambahkan jarak dari origin ke tiap tempat lalu mengurutkan; tempat tanpa jarak di urutan akhir.
export function rankedPlaces(places, origin) {
  return places.map(place => ({...place, distance: origin && validPoint(place.lat, place.lon)
    ? distanceKm(origin, [place.lat, place.lon]) : null})).sort((a,b) => (a.distance ?? Infinity) - (b.distance ?? Infinity));
}
// Payload pencarian berdasarkan nama wilayah dari input form.
export function regionPayload(form) {
  return {region: form.region.value.trim()};
}
// Payload lokasi yang dibulatkan ke 2 desimal (±1 km) sebelum dikirim ke server.
export function pointPayload(lat, lon) {
  return {lat: Math.round(lat * 100) / 100, lon: Math.round(lon * 100) / 100};
}
// Mengembalikan URL ternormalisasi hanya jika protokolnya https, selain itu null.
export function safeURL(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null; } catch { return null; }
}
// Tautan OpenStreetMap ke titik tempat, atau pencarian nama + alamat jika titiknya tidak valid.
export function placeLink(place) {
  if (validPoint(place.lat, place.lon)) return `https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lon}#map=17/${place.lat}/${place.lon}`;
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(`${place.name} ${place.address}`)}`;
}
