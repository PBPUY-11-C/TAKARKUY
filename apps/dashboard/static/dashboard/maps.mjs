export function validPoint(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}
export function distanceKm(a, b) {
  const rad = value => value * Math.PI / 180;
  const dLat = rad(b[0] - a[0]), dLon = rad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}
export function rankedPlaces(places, origin) {
  return places.map(place => ({...place, distance: origin && validPoint(place.lat, place.lon)
    ? distanceKm(origin, [place.lat, place.lon]) : null})).sort((a,b) => (a.distance ?? Infinity) - (b.distance ?? Infinity));
}
export function searchPayload(form) {
  // GPS is deliberately never part of this payload.
  return {region: form.region.value.trim(), kind: form.kind.value, online: Boolean(form.online?.checked)};
}
export function safeURL(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null; } catch { return null; }
}
export function placeLink(place) {
  if (validPoint(place.lat, place.lon)) return `https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lon}#map=17/${place.lat}/${place.lon}`;
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(`${place.name} ${place.address}`)}`;
}
