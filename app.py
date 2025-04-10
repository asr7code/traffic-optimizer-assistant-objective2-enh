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
st.title("🚦 Chandigarh Traffic Assistant – Independent Lights Simulation")

# Auto-refresh every 1 second
st_autorefresh(interval=1000, limit=None, key="sim_refresh")

# Load graph
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# Detect 4-way intersections
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

# Store traffic lights with individual timers
if "intersections" not in st.session_state:
    st.session_state.intersections = get_4way_intersections(G)

# Sidebar
st.sidebar.header("Simulation Setup")
start_lat = st.sidebar.number_input("Start Latitude", value=30.7270)
start_lon = st.sidebar.number_input("Start Longitude", value=76.7651)
end_lat = st.sidebar.number_input("End Latitude", value=30.7165)
end_lon = st.sidebar.number_input("End Longitude", value=76.7656)

if st.sidebar.button("▶️ Start Simulation"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig, dest, weight='length')
    coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    st.session_state.route = coords
    st.session_state.index = 0
    st.session_state.speed = np.random.randint(30, 61)
    st.session_state.running = True
    st.session_state.waiting = False
    st.session_state.completed = False

# Simulation logic
if st.session_state.get("running", False):
    coords = st.session_state.route
    i = st.session_state.index
    pos = coords[i]
    next_pos = coords[i + 1] if i + 1 < len(coords) else coords[-1]
    dist = geodesic(pos, next_pos).meters
    speed = st.session_state.speed
    speed_mps = speed / 3.6
    eta = dist / speed_mps

    # Closest signal (within 40m)
    def get_nearest_light(pos, threshold=40):
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

        # Red light logic
        if dist < 50 and phase == "Red":
            st.session_state.waiting = True
        elif st.session_state.waiting and phase != "Red":
            st.session_state.waiting = False

    # Speed suggestion logic
    def suggest_speed(d, timer):
        for s in range(20, 101, 5):
            t = d / (s / 3.6)
            arrival = (timer + t) % 60
            if arrival >= 35:
                return s
        return 25

    if nearest_light:
        suggested = suggest_speed(dist, st.session_state.intersections[nearest_light]["timer"])
        if suggested != speed:
            st.session_state.speed = suggested

    if not st.session_state.waiting:
        st.session_state.index += 1
        if st.session_state.index >= len(coords) - 1:
            st.session_state.completed = True
            st.session_state.running = False

    # Update all signal timers
    for light in st.session_state.intersections.values():
        light["timer"] = (light["timer"] + 1) % 60

# Display map
if "route" in st.session_state:
    coords = st.session_state.route
    idx = min(st.session_state.index, len(coords) - 1)
    pos = coords[idx]

    m = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(coords, color="blue", weight=5).add_to(m)
    folium.Marker(coords[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(coords[-1], icon=folium.Icon(color="red"), popup="End").add_to(m)

    # Traffic lights (colored markers)
    for loc, data in st.session_state.intersections.items():
        phase = "Red" if data["timer"] < 30 else "Yellow" if data["timer"] < 35 else "Green"
        color = "red" if phase == "Red" else "orange" if phase == "Yellow" else "green"
        folium.Marker(loc, icon=folium.Icon(color=color), popup=f"🚦 {phase}").add_to(m)

    folium.Marker(pos, icon=folium.Icon(color="purple", icon="car"), popup="🚗 Car").add_to(m)
    st_folium(m, height=500, width=900)

    st.markdown("### 📊 Simulation Status")
    st.write(f"**Car Position:** {pos}")
    st.write(f"**Step Index:** {idx}")
    st.write(f"**Speed:** {st.session_state.speed} km/h")
    st.write(f"**Waiting at Red Light:** {st.session_state.waiting}")
    if st.session_state.completed:
        st.success("✅ Simulation complete.")
