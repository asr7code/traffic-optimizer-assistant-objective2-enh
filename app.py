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
st.title("🚦 Chandigarh Traffic Assistant – Smooth Movement Simulation")

# Autorefresh every 1 second
st_autorefresh(interval=1000, limit=None, key="smooth_sim")

# Load graph
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# Get only 4-way intersections
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

# Interpolate points between lat/lon
def interpolate_points(p1, p2, spacing=10):
    distance = geodesic(p1, p2).meters
    num_points = max(int(distance / spacing), 1)
    lats = np.linspace(p1[0], p2[0], num=num_points)
    lons = np.linspace(p1[1], p2[1], num=num_points)
    return list(zip(lats, lons))

# Sidebar inputs
st.sidebar.header("Setup")
start_lat = st.sidebar.number_input("Start Lat", value=30.7270)
start_lon = st.sidebar.number_input("Start Lon", value=76.7651)
end_lat = st.sidebar.number_input("End Lat", value=30.7165)
end_lon = st.sidebar.number_input("End Lon", value=76.7656)

if st.sidebar.button("▶️ Start Simulation"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig, dest, weight="length")
    raw_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    # Interpolate full path
    full_path = []
    for i in range(len(raw_coords) - 1):
        full_path += interpolate_points(raw_coords[i], raw_coords[i + 1])

    st.session_state.path = full_path
    st.session_state.pos_idx = 0
    st.session_state.speed = random.randint(30, 60)  # km/h
    st.session_state.intersections = get_4way_intersections(G)
    st.session_state.waiting = False
    st.session_state.running = True
    st.session_state.completed = False

# Run simulation
if st.session_state.get("running", False):
    path = st.session_state.path
    idx = st.session_state.pos_idx
    pos = path[idx]
    speed = st.session_state.speed
    speed_mps = speed / 3.6
    distance_per_tick = speed_mps  # ~1 sec tick

    # Advance if not waiting
    def get_nearest_light(pos, threshold=20):
        for loc in st.session_state.intersections:
            if geodesic(pos, loc).meters < threshold:
                return loc
        return None

    nearest_light = get_nearest_light(pos)
    phase = "None"

    if nearest_light:
        light = st.session_state.intersections[nearest_light]
        timer = light["timer"]
        phase = "Red" if timer < 30 else "Yellow" if timer < 35 else "Green"

        if phase == "Red":
            st.session_state.waiting = True
        elif st.session_state.waiting and phase != "Red":
            st.session_state.waiting = False

    if not st.session_state.waiting:
        # Move forward by distance
        steps_ahead = 1
        total_distance = 0
        while idx + steps_ahead < len(path):
            d = geodesic(path[idx], path[idx + steps_ahead]).meters
            if total_distance + d > distance_per_tick:
                break
            total_distance += d
            steps_ahead += 1

        st.session_state.pos_idx += steps_ahead

        if st.session_state.pos_idx >= len(path) - 1:
            st.session_state.running = False
            st.session_state.completed = True

    # Update signal timers
    for light in st.session_state.intersections.values():
        light["timer"] = (light["timer"] + 1) % 60

# Display map
if "path" in st.session_state:
    path = st.session_state.path
    idx = min(st.session_state.pos_idx, len(path) - 1)
    pos = path[idx]

    m = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(path, color="blue", weight=5).add_to(m)
    folium.Marker(path[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(path[-1], icon=folium.Icon(color="red"), popup="End").add_to(m)

    # Draw traffic lights
    for loc, data in st.session_state.intersections.items():
        timer = data["timer"]
        phase = "Red" if timer < 30 else "Yellow" if timer < 35 else "Green"
        color = "red" if phase == "Red" else "orange" if phase == "Yellow" else "green"
        folium.Marker(loc, icon=folium.Icon(color=color), popup=f"🚦 {phase}").add_to(m)

    folium.Marker(pos, icon=folium.Icon(color="purple", icon="car"), popup="🚗").add_to(m)
    st_folium(m, height=500, width=900)

    st.markdown("### 📊 Status")
    st.write(f"**Current Position:** {pos}")
    st.write(f"**Speed:** {st.session_state.speed} km/h")
    st.write(f"**Waiting at Red:** {st.session_state.waiting}")
    if st.session_state.completed:
        st.success("✅ Destination reached.")
