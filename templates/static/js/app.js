// Visor Leaflet para alerts.geojson
let map;
let markersLayer;

document.addEventListener("DOMContentLoaded", () => {
    map = L.map("map").setView([10, -75], 3);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors",
    }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);

    document.getElementById("reloadBtn").addEventListener("click", loadAlerts);
    document.getElementById("minSev").addEventListener("change", renderAlerts);

    loadAlerts();
    loadStats();
});

async function loadAlerts() {
    try {
        const r = await fetch("/api/geojson");
        const data = await r.json();
        window.__alerts = data.features || [];
        renderAlerts();
    } catch (e) {
        console.error("Error cargando alertas:", e);
    }
}

async function loadStats() {
    try {
        const r = await fetch("/api/stats");
        const s = await r.json();
        document.getElementById("stats").textContent =
            `${s.count} alertas · sev media ${(s.avg_severity || 0).toFixed(1)} · max ${s.max_severity || 0}`;
    } catch (e) {
        document.getElementById("stats").textContent = "Sin estadísticas";
    }
}

function colorForSeverity(sev) {
    sev = +sev || 0;
    if (sev >= 8) return "#c0392b";
    if (sev >= 6) return "#e74c3c";
    if (sev >= 4) return "#e67e22";
    if (sev >= 2) return "#f1c40f";
    return "#2ecc71";
}

function renderAlerts() {
    const minSev = +document.getElementById("minSev").value || 0;
    const features = (window.__alerts || []).filter(f => {
        const sev = +(f.properties?.severity || 0);
        return sev >= minSev;
    });

    // Marcadores
    markersLayer.clearLayers();
    const bounds = [];
    features.forEach(f => {
        const [lon, lat] = f.geometry?.coordinates || [null, null];
        if (lon == null || lat == null) return;
        const sev = +(f.properties?.severity || 0);
        const marker = L.circleMarker([lat, lon], {
            radius: 6 + sev,
            color: colorForSeverity(sev),
            fillColor: colorForSeverity(sev),
            fillOpacity: 0.7,
            weight: 2,
        }).bindPopup(`
            <strong>${escapeHtml(f.properties?.title || "Sin título")}</strong><br>
            <small>${escapeHtml(f.properties?.summary || "").slice(0, 200)}</small><br>
            <em>Severidad: ${sev}</em><br>
            ${f.properties?.link ? `<a href="${f.properties.link}" target="_blank">Fuente</a>` : ""}
        `);
        marker.addTo(markersLayer);
        bounds.push([lat, lon]);
    });

    if (bounds.length) {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 6 });
    }

    // Sidebar
    const list = document.getElementById("alertList");
    list.innerHTML = "";
    if (!features.length) {
        list.innerHTML = "<li class='meta'>Sin alertas con este filtro</li>";
        return;
    }
    features.forEach((f, idx) => {
        const p = f.properties || {};
        const sev = +(p.severity || 0);
        const li = document.createElement("li");
        li.dataset.sev = sev;
        li.dataset.idx = idx;
        li.innerHTML = `
            <span class="sev">${sev}</span>
            <span class="title">${escapeHtml(p.title || "Sin título")}</span>
            <div class="meta">
                ${p.scraped_at ? new Date(p.scraped_at).toLocaleString() : ""}
            </div>
        `;
        li.addEventListener("click", () => {
            const [lon, lat] = f.geometry?.coordinates || [0, 0];
            map.flyTo([lat, lon], 7, { duration: 1.0 });
            markersLayer.eachLayer(layer => {
                const ll = layer.getLatLng();
                if (ll.lat === lat && ll.lng === lon) layer.openPopup();
            });
        });
        list.appendChild(li);
    });
}

function escapeHtml(s) {
    return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
