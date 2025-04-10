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
st.title("🚦 Chandigarh Traffic Assistant – Final Version (Click + Reset)")

if st.session_state.get("simulation_started", False):
    st_autorefresh(interval=1000, limit=None, key="tick")

@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# ✅ Smart signal placement
def get_major_road_intersections(G):
    major_types = {"primary", "secondary", "trunk", "motorway"}
    lights = {}
    for node in G.nodes:
        neighbors = list(G.neighbors(node))
        if len(neighbors) >= 4:
            tags = []
            for nbr in neighbors:
                data = G.get_edge_data(node, nbr)
                for key in data:
                    edge = data[key]
                    if 'highway' in edge:
                        hw = edge['highway']
                        tags += hw if isinstance(hw, list) else [hw]
            if any(tag in major_types for tag in tags):
                y, x = G.nodes[node]['y'], G.nodes[node]['x']
                lights[(y, x)] = {
                    "timer": random.randint(0, 59),
                    "green_start": 35,
                    "green_end": 59
                }
    return lights

def interpolate_points(p1, p2, spacing=15):
    distance = geodesic(p1, p2).meters
    if distance < spacing:
        return [p1, p2]
    num_points = min(int(distance / spacing), 10)
    lats = np.linspace(p1[0], p2[0], num=num_points)
    lons = np.linspace(p1[1], p2[1], num=num_points)
    return list(zip(lats, lons))

# 🧹 Reset button
if st.button("🔁 Reset Simulation"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

# 🗺️ Clickable map to set route
if "clicks" not in st.session_state:
    st.session_state.clicks = []
    st.session_state.start = None
    st.session_state.end = None

st.markdown("### 🗺️ Click once for Start, again for Destination")

m = folium.Map(location=[30.73, 76.77], zoom_start=14)

# Draw selected points
if st.session_state.start:
    folium.Marker(st.session_state.start, icon=folium.Icon(color="green"), popup="Start").add_to(m)
if st.session_state.end:
    folium.Marker(st.session_state.end, icon=folium.Icon(color="red"), popup="End").add_to(m)

# Show route
if "path" in st.session_state:
    folium.PolyLine(st.session_state.path, color="blue", weight=3).add_to(m)

# Show map
map_data = st_folium(m, height=450, width=900)

# Handle clicks
if map_data and map_data.get("last_clicked"):
    latlng = map_data["last_clicked"]
    coord = (latlng["lat"], latlng["lng"])
    if len(st.session_state.clicks) < 2:
        st.session_state.clicks.append(coord)
        if len(st.session_state.clicks) == 1:
            st.session_state.start = coord
        elif len(st.session_state.clicks) == 2:
            st.session_state.end = coord

# Generate route
if st.session_state.start and st.session_state.end and "path" not in st.session_state:
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
    st.session_state.intersections = get_major_road_intersections(G)
    st.session_state.pos_idx = 0
    st.success(f"✅ Route ready with {len(st.session_state.intersections)} smart signals.")

# 🚦 Start sim button
if st.button("▶️ Start Simulation") and "path" in st.session_state:
    st.session_state.simulation_started = True
    st.session_state.speed = random.randint(30, 50)
    st.session_state.waiting = False
    st.session_state.trail = []
    st.session_state.completed = False
    st.success("🚗 Simulation started")

# 🚗 Run simulation
if st.session_state.get("simulation_started", False) and not st.session_state.get("completed", False):
    path = st.session_state.path
    idx = st.session_state.pos_idx
    pos = path[min(idx, len(path)-1)]  # ✅ avoid crash if idx exceeds
    speed = st.session_state.speed
    distance_per_sec = speed / 3.6

    def get_nearest_light(pos, threshold=25):
        for loc in st.session_state.intersections:
            if geodesic(pos, loc).meters < threshold:
                return loc
        return None

    nearest_light = get_nearest_light(pos)
    if nearest_light:
        t = st.session_state.intersections[nearest_light]["timer"]
        phase = "Red" if t < 30 else "Yellow" if t < 35 else "Green"
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

    for light in st.session_state.intersections.values():
        light["timer"] = (light["timer"] + 1) % 60

    st.session_state.trail.append(pos)
    if len(st.session_state.trail) > 3:
        st.session_state.trail.pop(0)

    # Redraw simulation map
    m2 = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(path, color="blue", weight=3).add_to(m2)
    folium.Marker(path[0], icon=folium.Icon(color="green"), popup="Start").add_to(m2)
    folium.Marker(path[-1], icon=folium.Icon(color="red"), popup="End").add_to(m2)

    for loc, data in st.session_state.intersections.items():
        t = data["timer"]
        phase = "Red" if t < 30 else "Yellow" if t < 35 else "Green"
        color = "red" if phase == "Red" else "orange" if phase == "Yellow" else "green"
        folium.CircleMarker(loc, radius=6, color=color, fill=True, fill_opacity=0.8,
                            popup=f"{phase} [{t}s]").add_to(m2)

    for tpos in st.session_state.trail:
        folium.CircleMarker(tpos, radius=3, color="purple", fill=True, fill_opacity=0.5).add_to(m2)

    folium.Marker(pos, icon=folium.Icon(color="blue", icon="car"), popup="🚗").add_to(m2)
    st_folium(m2, height=500, width=900)

    st.markdown("### 📊 Car Info")
    st.write(f"**Position:** {pos}")
    st.write(f"**Speed:** {speed} km/h")
    st.write(f"**Waiting:** {st.session_state.waiting}")
    st.write(f"**Signal Phase:** {phase}")
    if st.session_state.get("completed"):
        st.success("✅ Destination Reached.")

