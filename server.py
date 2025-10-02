from flask import Flask, request, render_template_string, jsonify
from datetime import datetime
import threading

app = Flask(__name__)

# ---------------- CONFIG ----------------
HOME_LAT = 21.01460257498693   # <-- theo yêu cầu bạn
HOME_LON = 105.82291951301539  # <-- theo yêu cầu bạn

# LATEST location
latest = {"lat": None, "lon": None, "time": None}

# TRACK history (in-memory)
track_history = []  # mỗi item: {"lat":float,"lon":float,"time":iso-string}

# Lock bảo vệ truy cập history
history_lock = threading.Lock()

# HTML + JS cho map (Leaflet)
MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>GPS Tracker Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
  <style>
    body, html, #map { height: 100%; margin: 0; padding: 0; }
    #controls {
      position: absolute; top: 8px; right: 8px; z-index:1000;
      background: rgba(255,255,255,0.95); padding:8px; border-radius:6px;
      box-shadow: 0 2px 6px rgba(0,0,0,0.2);
      font-family: Arial, sans-serif;
    }
    button { margin:2px; }
    #info { position: absolute; top:8px; left:8px; z-index:1000;
            background: rgba(255,255,255,0.9); padding:6px; border-radius:4px; font-family: Arial, sans-serif;}
  </style>
</head>
<body>
  <div id="info">
    <strong>Home:</strong> {{ home_lat }}, {{ home_lon }}<br/>
    <strong>Latest:</strong> <span id="latest">No data</span>
  </div>

  <div id="controls">
    <div>
      <button id="btnPlay">Play</button>
      <button id="btnPause">Pause</button>
      <button id="btnStop">Stop</button>
      <button id="btnClear">Clear</button>
    </div>
    <div style="margin-top:6px">
      Speed (ms/point): <input id="speed" type="number" value="700" style="width:80px"/>
    </div>
  </div>

  <div id="map"></div>

<script>
  const homeLat = {{ home_lat }};
  const homeLon = {{ home_lon }};

  // init map
  var map = L.map('map').setView([homeLat, homeLon], 16);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

  // Home icon (emoji)
  var homeIcon = L.divIcon({ html: "🏠", className: "home-icon", iconSize: [30,30] });
  L.marker([homeLat, homeLon], {icon: homeIcon}).addTo(map).bindPopup("Home");

  // Latest marker
  var latestMarker = null;

  function updateLatestMarker(lat, lon, timeStr) {
    if (!lat || !lon) return;
    if (latestMarker) {
      latestMarker.setLatLng([lat, lon]).setPopupContent("Latest: " + timeStr);
    } else {
      latestMarker = L.marker([lat, lon]).addTo(map).bindPopup("Latest: " + timeStr);
      latestMarker.openPopup();
    }
  }

  // Track polyline and markers
  var trackLine = L.polyline([], { weight: 4 }).addTo(map);
  var pointMarkers = []; // small markers for each track point
  var startMarker = null;
  var endMarker = null;

  // Playback moving marker
  var movingMarker = null;
  var playTimer = null;
  var isPlaying = false;
  var playPoints = [];
  var playIndex = 0;

  // Polling (auto refresh)
  var pollInterval = 5000;
  var pollId = null;
  var pollingEnabled = true;

  async function fetchStatus() {
    try {
      let r = await fetch("/api/status");
      if (!r.ok) return;
      let j = await r.json();
      if (j.latest && j.latest.lat && j.latest.lon) {
        document.getElementById("latest").innerText = j.latest.time + " (" + j.latest.lat.toFixed(6) + ", " + j.latest.lon.toFixed(6) + ")";
        updateLatestMarker(j.latest.lat, j.latest.lon, j.latest.time);
      }
    } catch(e){ console.error("status", e); }
  }

  async function fetchHistoryAndDraw() {
    try {
      let r = await fetch("/api/history");
      if (!r.ok) return;
      let arr = await r.json();
      // redraw polyline
      let latlngs = arr.map(p => [p.lat, p.lon]);
      trackLine.setLatLngs(latlngs);

      // remove old point markers
      pointMarkers.forEach(m => map.removeLayer(m));
      pointMarkers = [];

      // start & end markers
      if (startMarker) { map.removeLayer(startMarker); startMarker = null; }
      if (endMarker) { map.removeLayer(endMarker); endMarker = null; }

      if (arr.length > 0) {
        // create small markers and popups
        for (let i=0;i<arr.length;i++){
          let p = arr[i];
          let m = L.circleMarker([p.lat,p.lon], {radius:4}).addTo(map).bindPopup(p.time);
          pointMarkers.push(m);
        }
        // start = first (green), end = last (red)
        let first = arr[0], last = arr[arr.length-1];
        startMarker = L.circleMarker([first.lat, first.lon], {radius:7, color:'green', fill:true}).addTo(map).bindPopup("Start: " + first.time);
        endMarker = L.circleMarker([last.lat, last.lon], {radius:7, color:'red', fill:true}).addTo(map).bindPopup("End: " + last.time);
        // auto-fit map to track if not playing
        if (!isPlaying && latlngs.length>0) {
          try { map.fitBounds(trackLine.getBounds().pad(0.25)); } catch(e){}
        }
      }
    } catch(e){ console.error("history", e); }
  }

  function startPolling() {
    if (pollId) clearInterval(pollId);
    pollingEnabled = true;
    pollId = setInterval(()=>{ fetchStatus(); fetchHistoryAndDraw(); }, pollInterval);
    // initial
    fetchStatus(); fetchHistoryAndDraw();
  }
  function stopPolling() {
    pollingEnabled = false;
    if (pollId) { clearInterval(pollId); pollId = null; }
  }

  // Playback controls
  document.getElementById("btnPlay").addEventListener("click", () => {
    if (isPlaying) return;
    play();
  });
  document.getElementById("btnPause").addEventListener("click", () => {
    pausePlayback();
  });
  document.getElementById("btnStop").addEventListener("click", () => {
    stopPlayback();
  });
  document.getElementById("btnClear").addEventListener("click", async () => {
    if (!confirm("Clear all track history on server?")) return;
    try {
      let r = await fetch("/clear_history", { method: "POST" });
      if (r.ok) {
        alert("Cleared");
        fetchHistoryAndDraw();
      } else alert("Clear failed");
    } catch(e){ alert("Error: " + e); }
  });

  async function play() {
    stopPolling(); // pause polling while playing
    isPlaying = true;
    try {
      let r = await fetch("/api/history");
      if (!r.ok) { isPlaying=false; startPolling(); return; }
      playPoints = await r.json();
      if (!playPoints || playPoints.length===0) { alert("No points to play"); isPlaying=false; startPolling(); return; }
      playIndex = 0;
      // create movingMarker at first point if not exists
      if (!movingMarker) {
        movingMarker = L.marker([playPoints[0].lat, playPoints[0].lon]).addTo(map);
      }
      let speed = parseInt(document.getElementById("speed").value) || 700;
      playTimer = setInterval(()=> {
        if (playIndex >= playPoints.length) {
          // reached end
          pausePlayback();
          startPolling();
          isPlaying = false;
          return;
        }
        const p = playPoints[playIndex++];
        movingMarker.setLatLng([p.lat, p.lon]).bindPopup(p.time);
        map.panTo([p.lat, p.lon]);
      }, speed);
    } catch(e) {
      console.error("play error", e);
      isPlaying=false;
      startPolling();
    }
  }

  function pausePlayback() {
    if (playTimer) { clearInterval(playTimer); playTimer = null; }
    isPlaying = false;
    // do not restart polling automatically — user may press Stop or Play
  }

  function stopPlayback() {
    pausePlayback();
    if (movingMarker) { map.removeLayer(movingMarker); movingMarker = null; }
    playPoints = [];
    playIndex = 0;
    startPolling();
  }

  // initial start polling
  startPolling();
</script>
</body>
</html>
"""

# ROUTES
@app.route("/")
def home():
    return "Server is running. Use /update and /map."

@app.route("/update")
def update():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    track_flag = request.args.get("track", "0")
    if not lat or not lon:
        return "Missing lat/lon", 400
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except:
        return "Invalid lat/lon", 400

    now = datetime.utcnow().isoformat() + "Z"
    latest['lat'] = lat_f
    latest['lon'] = lon_f
    latest['time'] = now

    if track_flag == "1":
        with history_lock:
            track_history.append({"lat": lat_f, "lon": lon_f, "time": now})
            # hạn chế số điểm giữ trong RAM
            if len(track_history) > 5000:
                track_history.pop(0)

    return f"Updated location: ({lat},{lon}) at {now}"

@app.route("/map")
def map_view():
    return render_template_string(MAP_HTML, home_lat=HOME_LAT, home_lon=HOME_LON)

@app.route("/api/status")
def api_status():
    return jsonify({"latest": latest})

@app.route("/api/history")
def api_history():
    with history_lock:
        # trả về tối đa N điểm cuối (client sẽ vẽ)
        return jsonify(track_history[-2000:])

@app.route("/clear_history", methods=['GET', 'POST'])
def clear_history():
    with history_lock:
        track_history.clear()
    return jsonify({"ok": True, "msg": "history cleared"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
