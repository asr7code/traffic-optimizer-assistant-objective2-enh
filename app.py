import streamlit as st
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import numpy as np
import random

st.set_page_config(layout="wide")
st.title("🚦 Chandigarh Traffic Assistant – Optimized & Smooth Simulation")

# Auto-refresh every second
st_autorefresh(interval=1000, limit=None, key="refresh")

# Load once and cache
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# 4-way intersection traffic lights
def get_4way_intersections(G):
    lights = {}
    for node in G.nodes:
        if len(list(G.neighbors(node))) >= 4:
            y, x = G.nodes[node]['y'], G.nodes[node]['x']
            lights[(y, x)] = {
                "timer": random.randint(0, 59),
                "green_start": 35,
                "green_end": 59
            }
    return lights

# Interpolate points between two lat/lon with lower density
def interpolate_points(p1, p2, spacing=15):
    distance = geodesic(p1, p2).meters
    if distance < spacing:
        return [p1, p2]
    num_points = min(int(distance / spacing), 10)
    lats = np.linspace(p1[0], p2[0], num=num_points)
    lons = np.linspace(p1[1], p2[1], num=num_points)
    return list(zip(lats, lons))

# Sidebar input
st.sidebar.header("Route Setup")
start_lat = st.sidebar.number_input("Start Latitude", value=30.7270)
start_lon = st.sidebar.number_input("Start Longitude", value=76.7651)
end_lat = st.sidebar.number_input("End Latitude", value=30.7165)
end_lon = st.sidebar.number_input("End Longitude", value=76.7656)

if st.sidebar.button("▶️ Start Simulation"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig, dest, weight="length")
    raw_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    # 🧠 Interpolate lightly
    full_path = []
    for i in range(len(raw_coords) - 1):
        full_path += interpolate_points(raw_coords[i], raw_coords[i + 1])
        if len(full_path) > 300:
            break  # 🚀 Limit for performance

    st.session_state.path = full_path
    st.session_state.pos_idx = 0
    st.session_state.speed = random.randint(30, 50)
    st.session_state.waiting = False
    st.session_state.completed = False
    st.session_state.intersections = get_4way_intersections(G)
    st.session_state.trail = []

# Simulation logic
if st.session_state.get("path") and not st.session_state.get("completed", False):
    path = st.session_state.path
    idx = st.session_state.pos_idx
    pos = path[idx]
    speed = st.session_state.speed
    distance_per_sec = speed / 3.6

    # Nearest light
    def get_nearest_light(pos, threshold=25):
        for loc in st.session_state.intersections:
            if geodesic(pos, loc).meters < threshold:
                return loc
        return None

    nearest_light = get_nearest_light(pos)
    if nearest_light:
        timer = st.session_state.intersections[nearest_light]["timer"]
        phase = "Red" if timer < 30 else "Yellow" if timer < 35 else "Green"
        if phase == "Red":
            st.session_state.waiting = True
        elif st.session_state.waiting and phase != "Red":
            st.session_state.waiting = False
    else:
        phase = "None"

    if not st.session_state.waiting:
        steps = 1
        total = 0
        while idx + steps < len(path):
            d = geodesic(path[idx + steps - 1], path[idx + steps]).meters
            if total + d > distance_per_sec:
                break
            total += d
            steps += 1

        st.session_state.pos_idx += steps
        if st.session_state.pos_idx >= len(path) - 1:
            st.session_state.completed = True

    # Trail (last 3)
    st.session_state.trail.append(pos)
    if len(st.session_state.trail) > 3:
        st.session_state.trail.pop(0)

    # Update lights
    for light in st.session_state.intersections.values():
        light["timer"] = (light["timer"] + 1) % 60

# Map display
if st.session_state.get("path"):
    path = st.session_state.path
    idx = min(st.session_state.pos_idx, len(path) - 1)
    pos = path[idx]

    m = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(path, color="blue", weight=3).add_to(m)
    folium.Marker(path[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(path[-1], icon=folium.Icon(color="red"), popup="End").add_to(m)

    # Traffic lights
    for loc, data in st.session_state.intersections.items():
        t = data["timer"]
        phase = "Red" if t < 30 else "Yellow" if t < 35 else "Green"
        color = "red" if phase == "Red" else "orange" if phase == "Yellow" else "green"
        folium.CircleMarker(loc, radius=5, color=color, fill=True, fill_opacity=0.8,
                            popup=f"{phase} [{t}s]").add_to(m)

    # Trail
    for tpos in st.session_state.trail:
        folium.CircleMarker(tpos, radius=3, color="purple", fill=True, fill_opacity=0.5).add_to(m)

    # Car
    folium.Marker(pos, icon=folium.Icon(color="blue", icon="car"), popup="🚗").add_to(m)
    st_folium(m, height=500, width=900)

    st.markdown("### 📊 Car Info")
    st.write(f"**Position:** {pos}")
    st.write(f"**Speed:** {speed} km/h")
    st.write(f"**Waiting:** {st.session_state.waiting}")
    st.write(f"**Light Phase:** {phase}")
    if st.session_state.completed:
        st.success("✅ Reached destination.")
