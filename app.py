import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import numpy as np
import random
import time

st.set_page_config(layout="wide")
st.title("🚦 Traffic Optimizer Assistant – Auto Simulation (Objective 2)")

@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

@st.cache_data
def get_major_signals(G, max_signals=20):
    major_types = {"primary", "secondary", "trunk", "motorway"}
    signal_nodes = []

    for node in G.nodes:
        neighbors = list(G.neighbors(node))
        if len(neighbors) >= 4:
            hw_types = []
            for nbr in neighbors:
                for key in G.get_edge_data(node, nbr):
                    hw = G.get_edge_data(node, nbr)[key].get("highway")
                    if isinstance(hw, list):
                        hw_types += hw
                    elif hw:
                        hw_types.append(hw)
            if any(h in major_types for h in hw_types):
                signal_nodes.append(node)

    signals = {}
    count = 0
    for node in signal_nodes:
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
    points = int(distance / spacing)
    lats = np.linspace(p1[0], p2[0], points)
    lons = np.linspace(p1[1], p2[1], points)
    return list(zip(lats, lons))

def get_nearest_signal(pos, signals, threshold=100):
    nearest = None
    min_dist = float("inf")
    for loc in signals:
        dist = geodesic(pos, loc).meters
        if dist < threshold and dist < min_dist:
            nearest = loc
            min_dist = dist
    return nearest, min_dist if nearest else None

# Reset
if st.button("🔁 Reset"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

G = load_graph()

# Select route
if "clicks" not in st.session_state:
    st.session_state.clicks = []
    st.session_state.start = None
    st.session_state.end = None
    st.session_state.simulating = False

st.markdown("### 🗺️ Select Start and End Points")
m = folium.Map(location=[30.73, 76.77], zoom_start=14)
if st.session_state.get("start"):
    folium.Marker(st.session_state.start, icon=folium.Icon(color="green")).add_to(m)
if st.session_state.get("end"):
    folium.Marker(st.session_state.end, icon=folium.Icon(color="red")).add_to(m)

map_data = st_folium(m, height=400, width=900)
if map_data and map_data.get("last_clicked"):
    click = (map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"])
    if len(st.session_state.clicks) < 2:
        st.session_state.clicks.append(click)
        if len(st.session_state.clicks) == 1:
            st.session_state.start = click
        else:
            st.session_state.end = click

# Build path
if st.session_state.get("start") and st.session_state.get("end") and "path" not in st.session_state:
    orig = ox.distance.nearest_nodes(G, st.session_state.start[1], st.session_state.start[0])
    dest = ox.distance.nearest_nodes(G, st.session_state.end[1], st.session_state.end[0])
    route = nx.shortest_path(G, orig, dest, weight="length")
    coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    path = []
    for i in range(len(coords) - 1):
        path += interpolate_points(coords[i], coords[i+1])
        if len(path) > 300:
            break

    st.session_state.path = path
    st.session_state.idx = 0
    st.session_state.speed = random.randint(30, 50)
    st.session_state.lights = get_major_signals(G)
    st.session_state.trail = []
    st.session_state.done = False
    st.session_state.simulating = True
    st.session_state.suggestion = ""

# Simulation loop
if st.session_state.get("simulating", False):
    path = st.session_state.path
    idx = st.session_state.idx
    speed = st.session_state.speed
    dps = speed / 3.6
    lights = st.session_state.lights
    pos = path[min(idx, len(path)-1)]

    near_light, dist = get_nearest_signal(pos, lights)
    suggestion = "🚘 Maintain current speed"

    if near_light:
        timer = lights[near_light]["timer"]
        phase = "Red" if timer < 30 else "Yellow" if timer < 35 else "Green"
        time_left = (30 if phase == "Red" else 35 if phase == "Yellow" else 60) - timer

        st.session_state.signal_info = {
            "location": near_light,
            "phase": phase,
            "time_left": time_left,
            "distance": int(dist)
        }

        if phase == "Red" and dist < dps * 2:
            suggestion = "🛑 Slow Down – Red ahead"
            st.session_state.waiting = True
        elif phase == "Green" and dist < dps * 2:
            suggestion = "✅ Speed Up – Green!"
            st.session_state.waiting = False
        else:
            suggestion = "🚘 Hold speed"
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
        st.session_state.idx = idx + steps
        if st.session_state.idx >= len(path):
            st.session_state.done = True
            st.session_state.simulating = False

    # update signal timers
    for l in lights.values():
        l["timer"] = (l["timer"] + 1) % 60

    st.session_state.trail.append(pos)
    if len(st.session_state.trail) > 5:
        st.session_state.trail.pop(0)

    # map
    m2 = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(path, color="blue", weight=3).add_to(m2)
    folium.Marker(path[0], icon=folium.Icon(color="green")).add_to(m2)
    folium.Marker(path[-1], icon=folium.Icon(color="red")).add_to(m2)

    for loc, data in lights.items():
        t = data["timer"]
        phase = "Red" if t < 30 else "Yellow" if t < 35 else "Green"
        color = "red" if phase == "Red" else "orange" if phase == "Yellow" else "green"
        folium.CircleMarker(loc, radius=6, color=color, fill=True, popup=f"{phase} [{t}s]").add_to(m2)

    for t in st.session_state.trail:
        folium.CircleMarker(t, radius=4, color="purple", fill=True).add_to(m2)

    folium.Marker(pos, icon=folium.Icon(color="blue", icon="car")).add_to(m2)
    st_folium(m2, height=500, width=900)

    # dashboard
    st.markdown("### 📊 Status")
    st.write(f"**Speed:** {speed} km/h")
    st.write(f"**Advice:** {suggestion}")

    if st.session_state.get("signal_info"):
        info = st.session_state["signal_info"]
        st.info(f"🚦 Signal: **{info['phase']}**, ⏳ Time left: **{info['time_left']}s**, 📏 Distance: **{info['distance']} m**")

    time.sleep(1)
    st.experimental_rerun()

elif st.session_state.get("done"):
    st.success("🎉 Simulation completed. Destination reached!")
