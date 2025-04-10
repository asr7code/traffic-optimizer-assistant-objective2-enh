import streamlit as st
from streamlit_folium import st_folium
import folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import numpy as np
import random

st.set_page_config(layout="wide")
st.title("🚦 Traffic Optimizer Assistant – Signal Phase + Timer Simulation")

@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

@st.cache_data
def get_top_signals(G, max_signals=20):
    major_types = {"primary", "secondary", "trunk", "motorway"}
    signal_candidates = []

    for node in G.nodes:
        neighbors = list(G.neighbors(node))
        if len(neighbors) >= 4:
            types = []
            for nbr in neighbors:
                edge_data = G.get_edge_data(node, nbr)
                for key in edge_data:
                    edge = edge_data[key]
                    if "highway" in edge:
                        hw = edge["highway"]
                        types += hw if isinstance(hw, list) else [hw]
            if any(t in major_types for t in types):
                signal_candidates.append(node)

    center_nodes = list(nx.closeness_centrality(G).items())
    center_nodes.sort(key=lambda x: x[1], reverse=True)
    signals = {}
    count = 0
    for node, _ in center_nodes:
        if node in signal_candidates:
            y, x = G.nodes[node]['y'], G.nodes[node]['x']
            signals[(y, x)] = {
                "timer": random.randint(0, 59),
                "green_start": 35,
                "green_end": 59
            }
            count += 1
            if count >= max_signals:
                break
    return signals

def interpolate_points(p1, p2, spacing=15):
    distance = geodesic(p1, p2).meters
    if distance < spacing:
        return [p1, p2]
    num_points = min(int(distance / spacing), 10)
    lats = np.linspace(p1[0], p2[0], num=num_points)
    lons = np.linspace(p1[1], p2[1], num=num_points)
    return list(zip(lats, lons))

def get_nearest_light(pos, lights, threshold=80):
    nearest = None
    min_dist = float('inf')
    for loc in lights:
        dist = geodesic(pos, loc).meters
        if dist < threshold and dist < min_dist:
            nearest = loc
            min_dist = dist
    return nearest, min_dist if nearest else None

# 🔁 Reset Button
if st.button("🔁 Reset"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

# 🗺️ Route Selection
if "clicks" not in st.session_state:
    st.session_state.clicks = []
    st.session_state.start = None
    st.session_state.end = None

st.markdown("### 🗺️ Click to Set Start & Destination")
m = folium.Map(location=[30.73, 76.77], zoom_start=14)
if st.session_state.get("start"):
    folium.Marker(st.session_state.start, icon=folium.Icon(color="green")).add_to(m)
if st.session_state.get("end"):
    folium.Marker(st.session_state.end, icon=folium.Icon(color="red")).add_to(m)

map_data = st_folium(m, height=400, width=900)
if map_data and map_data.get("last_clicked"):
    coord = (map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"])
    if len(st.session_state.clicks) < 2:
        st.session_state.clicks.append(coord)
        if len(st.session_state.clicks) == 1:
            st.session_state.start = coord
        elif len(st.session_state.clicks) == 2:
            st.session_state.end = coord

# 🛣️ Route Generation
if st.session_state.get("start") and st.session_state.get("end") and "path" not in st.session_state:
    orig = ox.distance.nearest_nodes(G, st.session_state.start[1], st.session_state.start[0])
    dest = ox.distance.nearest_nodes(G, st.session_state.end[1], st.session_state.end[0])
    route = nx.shortest_path(G, orig, dest, weight="length")
    raw_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    full_path = []
    for i in range(len(raw_coords) - 1):
        full_path += interpolate_points(raw_coords[i], raw_coords[i + 1])
        if len(full_path) > 300:
            break

    st.session_state.path = full_path
    st.session_state.lights = get_top_signals(G)
    st.session_state.idx = 0
    st.session_state.speed = random.randint(30, 60)
    st.session_state.waiting = False
    st.session_state.trail = []
    st.session_state.done = False
    st.session_state.suggestion = ""
    st.success("✅ Route ready! Click ➡️ Next Step to simulate.")

# 🚗 Step-by-Step Simulation
if st.button("➡️ Next Step") and st.session_state.get("path") and not st.session_state.get("done", False):
    path = st.session_state.get("path", [])
    idx = st.session_state.get("idx", 0)
    pos = path[min(idx, len(path) - 1)]
    speed = st.session_state.get("speed", 30)
    dps = speed / 3.6
    lights = st.session_state.get("lights", {})

    nearest, dist = get_nearest_light(pos, lights)
    if nearest:
        timer = lights[nearest]["timer"]
        phase = "Red" if timer < 30 else "Yellow" if timer < 35 else "Green"
        time_left = (30 if phase == "Red" else 35 if phase == "Yellow" else 60) - timer
        st.session_state.signal_info = {
            "location": nearest,
            "phase": phase,
            "distance": int(dist),
            "time_left": time_left
        }

        if phase == "Red" and dist < (dps * 2):
            st.session_state.suggestion = f"🛑 Slow Down - Red in {int(dist)}m"
        elif phase == "Green" and dist < (dps * 2):
            st.session_state.suggestion = f"✅ Maintain - Green in {int(dist)}m"
        else:
            st.session_state.suggestion = "🚘 Drive steady"

        if phase == "Red" and dist < 25:
            st.session_state.waiting = True
        elif phase != "Red":
            st.session_state.waiting = False

    if not st.session_state.get("waiting", False):
        steps = 1
        total = 0
        while idx + steps < len(path):
            d = geodesic(path[idx + steps - 1], path[idx + steps]).meters
            if total + d > dps:
                break
            total += d
            steps += 1
        st.session_state.idx += steps
        if st.session_state.idx >= len(path) - 1:
            st.session_state.done = True
            st.success("🎉 Destination Reached!")

    for l in lights.values():
        l["timer"] = (l["timer"] + 1) % 60

    st.session_state.trail.append(pos)
    if len(st.session_state.trail) > 3:
        st.session_state.trail.pop(0)

# 🗺️ Map Display
if st.session_state.get("path"):
    path = st.session_state.get("path", [])
    idx = min(st.session_state.get("idx", 0), len(path)-1)
    pos = path[idx]
    lights = st.session_state.get("lights", {})

    m2 = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(path, color="blue", weight=3).add_to(m2)
    folium.Marker(path[0], icon=folium.Icon(color="green")).add_to(m2)
    folium.Marker(path[-1], icon=folium.Icon(color="red")).add_to(m2)

    for loc, data in lights.items():
        t = data["timer"]
        ph = "Red" if t < 30 else "Yellow" if t < 35 else "Green"
        color = "red" if ph == "Red" else "orange" if ph == "Yellow" else "green"
        folium.CircleMarker(loc, radius=6, color=color, fill=True, popup=f"{ph} [{t}s]").add_to(m2)

    for tpos in st.session_state.get("trail", []):
        folium.CircleMarker(tpos, radius=3, color="purple", fill=True).add_to(m2)

    folium.Marker(pos, icon=folium.Icon(color="blue", icon="car"), popup="🚗").add_to(m2)
    st_folium(m2, height=500, width=900)

    # 🧠 Simulation Info
    st.markdown("### 📊 Driving Info")
    st.write(f"**Speed:** {speed} km/h")
    st.write(f"**Advice:** {st.session_state.get('suggestion', '')}")
    if st.session_state.get("signal_info"):
        info = st.session_state.signal_info
        st.info(f"🛑 Next Signal: **{info['phase']}**, ⏳ Time Left: **{info['time_left']}s**, 📏 Distance: **{info['distance']} m**")
    if st.session_state.get("done"):
        st.success("✅ Trip Completed.")
