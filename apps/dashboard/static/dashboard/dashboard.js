import {validPoint, rankedPlaces, searchPayload, safeURL, placeLink} from './maps.mjs';

const dialog = document.querySelector('#market-dialog');
if (dialog) {
  const form = document.querySelector('#market-form'), output = document.querySelector('#market-results');
  const message = document.querySelector('#market-message'), mapBox = document.querySelector('#market-map');
  const curated = JSON.parse(document.querySelector('#map-places').textContent);
  const config = JSON.parse(document.querySelector('#map-config').textContent);
  let places = [], origin = null, sequence = 0, controller = null, map = null, layer = null, leafletPromise = null;
  function reset() { sequence++; controller?.abort(); origin = null; layer?.clearLayers(); form.querySelector('[type=submit]').disabled = false; }
  dialog.addEventListener('close', reset);
  document.querySelector('#close-market').addEventListener('click', () => dialog.close());
  function addLink(parent, label, url) {
    const safe = safeURL(url); if (!safe) return;
    const a = document.createElement('a'); a.textContent = label; a.href = safe;
    a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.append(a);
  }
  function renderList() {
    output.replaceChildren();
    for (const place of rankedPlaces(places, origin)) {
      const li = document.createElement('li'), text = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = place.name;
      const address = document.createElement('small'); address.textContent = place.address || place.region;
      const info = document.createElement('small'); info.textContent = `${place.kind === 'market' ? 'Pasar' : 'Bank sampah'}${place.distance === null ? '' : ` · ±${place.distance.toFixed(1)} km (garis lurus)`}`;
      text.append(title, address, info);
      if (!validPoint(place.lat, place.lon)) {
        const note = document.createElement('small'); note.textContent = 'Titik belum diverifikasi'; text.append(note);
      }
      addLink(text, 'Sumber', place.source_url); li.append(text); addLink(li, 'Buka peta ↗', placeLink(place)); output.append(li);
    }
    if (!places.length) {
      const li = document.createElement('li'); li.className = 'empty'; li.textContent = 'Data belum tersedia di wilayah ini.'; output.append(li);
    }
  }
  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (!leafletPromise) leafletPromise = new Promise((resolve, reject) => {
      const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      css.integrity = 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY='; css.crossOrigin = 'anonymous'; document.head.append(css);
      const script = document.createElement('script'); script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.integrity = 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo='; script.crossOrigin = 'anonymous';
      const timer = setTimeout(() => reject(new Error('Peta tidak tersedia. Daftar tempat tetap bisa dipakai.')), 7000);
      script.onload = () => { clearTimeout(timer); window.L ? resolve(window.L) : reject(new Error('Peta tidak tersedia.')); };
      script.onerror = () => { clearTimeout(timer); reject(new Error('Peta tidak tersedia. Daftar tempat tetap bisa dipakai.')); };
      document.head.append(script);
    });
    return leafletPromise;
  }
  async function drawMap(current) {
    try {
      const L = await loadLeaflet(); if (current !== sequence || !dialog.open) return;
      mapBox.hidden = false;
      if (!map) {
        map = L.map(mapBox).setView([-7.20055, 107.90340], 11);
        if (!safeURL(config.tiles)) throw new Error('Penyedia peta tidak valid.');
        L.tileLayer(config.tiles, {maxZoom: 18, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'})
          .on('tileerror', () => { message.textContent = 'Peta tidak tersedia. Gunakan daftar tempat di bawah.'; }).addTo(map);
        layer = L.layerGroup().addTo(map);
      }
      layer.clearLayers(); const points = [];
      for (const place of places) {
        if (!validPoint(place.lat, place.lon)) continue;
        const point = [place.lat, place.lon], popup = document.createElement('strong'); popup.textContent = place.name;
        L.circleMarker(point, {radius: 7, color: '#007452'}).bindPopup(popup).addTo(layer); points.push(point);
      }
      if (origin) { L.circleMarker(origin, {radius: 7, color: '#357cc0'}).bindPopup('Lokasi Anda').addTo(layer); points.push(origin); }
      if (points.length) map.fitBounds(points, {padding: [24,24], maxZoom: 14});
      map.invalidateSize();
    } catch (error) { if (current === sequence && dialog.open) message.textContent = error.message; }
  }
  function localSearch() {
    const region = form.elements.region.value.trim().toLowerCase().replace(/^(kota|kabupaten)\s+/, ''), kind = form.elements.kind.value;
    places = curated.places.filter(p => `${p.region} ${p.address}`.toLowerCase().includes(region) && (kind === 'all' || p.kind === kind));
    renderList();
  }
  document.querySelector('#open-market').addEventListener('click', () => {
    dialog.showModal(); message.textContent = ''; localSearch(); drawMap(++sequence);
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); const current = ++sequence; controller?.abort(); const pending = new AbortController(); controller = pending;
    const button = form.querySelector('[type=submit]'); button.disabled = true; message.textContent = 'Mencari…';
    const timer = setTimeout(() => pending.abort(), 20000);
    try {
      const response = await fetch(dialog.dataset.url, {method: 'POST', credentials: 'same-origin', signal: pending.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify(searchPayload(form.elements))});
      let data;
      try { data = await response.json(); }
      catch { throw new Error('Sesi atau layanan tidak tersedia. Muat ulang halaman.'); }
      if (current !== sequence || !dialog.open) return;
      if (!response.ok) throw new Error(data.error || 'Pencarian gagal.');
      places = data.places; message.textContent = data.message || (data.source === 'osm' ? 'Data OpenStreetMap · belum tentu lengkap.' : 'Data kurasi');
      renderList(); drawMap(current);
    } catch (error) {
      if (current !== sequence || !dialog.open) return;
      localSearch(); message.textContent = error.name === 'AbortError' ? 'Pencarian terlalu lama. Menampilkan data kurasi.' : error.message;
    } finally { clearTimeout(timer); if (current === sequence || !dialog.open) button.disabled = false; }
  });
  document.querySelector('#locate-market').addEventListener('click', () => {
    if (!navigator.geolocation) { message.textContent = 'Lokasi tidak didukung. Gunakan pencarian wilayah.'; return; }
    const current = sequence;
    navigator.geolocation.getCurrentPosition(position => {
      if (!dialog.open || current !== sequence) return;
      const {latitude, longitude} = position.coords;
      if (!validPoint(latitude, longitude)) return;
      origin = [latitude, longitude]; renderList(); drawMap(current);
      message.textContent = 'Jarak hanya dihitung untuk tempat bertitik terverifikasi di daftar ini.';
    }, () => { if (dialog.open && current === sequence) message.textContent = 'Lokasi tidak tersedia. Cari wilayah secara manual.'; },
    {enableHighAccuracy: false, timeout: 8000, maximumAge: 0});
  });
}
