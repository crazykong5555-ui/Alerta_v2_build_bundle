const map = L.map('map').setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const alertList = document.getElementById('alertList');
const statsNode = document.getElementById('stats');
const minSevInput = document.getElementById('minSev');
const reloadBtn = document.getElementById('reloadBtn');

const params = new URLSearchParams(window.location.search);
const selectedLat = parseFloat(params.get('lat'));
const selectedLon = parseFloat(params.get('lon'));
const selectedTitle = params.get('title') || 'Punto destacado';

let currentLayer = null;
let selectedMarker = null;

function renderGeoJson(data) {
  if (currentLayer) {
    map.removeLayer(currentLayer);
  }
  if (selectedMarker) {
    map.removeLayer(selectedMarker);
    selectedMarker = null;
  }

  const features = (data && data.features) || [];
  currentLayer = L.geoJSON(features, {
    pointToLayer: (feature, latlng) => {
      const props = feature.properties || {};
      const sev = Number(props.severity || 0);
      const color = sev >= 8 ? '#dc2626' : sev >= 5 ? '#f59e0b' : '#22c55e';
      return L.circleMarker(latlng, {
        radius: 7,
        color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: 1
      }).bindPopup(`
        <strong>${props.title || 'Alerta'}</strong><br>
        Severidad: ${sev}<br>
        <a href="${props.link || '#'}" target="_blank">Abrir noticia</a>
      `);
    }
  }).addTo(map);

  if (!Number.isNaN(selectedLat) && !Number.isNaN(selectedLon)) {
    selectedMarker = L.circleMarker([selectedLat, selectedLon], {
      radius: 11,
      color: '#ff0000',
      fillColor: '#ff0000',
      fillOpacity: 1,
      weight: 2
    }).addTo(map).bindPopup(`<strong>${selectedTitle}</strong><br>Ubicación destacada desde la noticia`);
    map.flyTo([selectedLat, selectedLon], 6);
  } else if (features.length) {
    map.fitBounds(currentLayer.getBounds(), { padding: [30, 30] });
  }

  alertList.innerHTML = '';
  for (const feature of features) {
    const props = feature.properties || {};
    const item = document.createElement('li');
    item.textContent = `${props.title || 'Alerta'} (Sev ${props.severity || 0})`;
    item.addEventListener('click', () => {
      const coords = feature.geometry?.coordinates || [];
      if (coords.length >= 2) {
        map.flyTo([coords[1], coords[0]], 6);
      }
    });
    alertList.appendChild(item);
  }
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    if (data && !data.error) {
      statsNode.textContent = `Total: ${data.count} · Máx: ${data.max_severity}`;
    }
  } catch (err) {
    console.error('stats error', err);
  }
}

async function reloadGeoJson() {
  try {
    const res = await fetch('/api/geojson');
    const data = await res.json();
    if (data && data.features) {
      renderGeoJson(data);
    }
  } catch (err) {
    console.error('geojson error', err);
  }
}

reloadBtn.addEventListener('click', () => {
  reloadGeoJson();
  fetchStats();
});

minSevInput.addEventListener('change', async () => {
  const min = Number(minSevInput.value || 0);
  const res = await fetch('/api/geojson');
  const data = await res.json();
  const filtered = {
    type: 'FeatureCollection',
    features: (data.features || []).filter((f) => Number(f.properties?.severity || 0) >= min)
  };
  renderGeoJson(filtered);
});

reloadGeoJson();
fetchStats();
