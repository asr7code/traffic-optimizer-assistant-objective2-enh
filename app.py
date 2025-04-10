import streamlit as st
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import numpy as np

st.set_page_config(layout="wide")
st.title("🚦 Chandigarh Traffic Assistant – Auto Simulation with 4-Way Lights")

# Autorefresh every second (1000 ms)
st_autorefresh(interval=1000, limit=None, key="auto_sim")

# Load graph
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# Detect only 4-way intersections for lights
def get_4way_intersections(G):
    four_way = {}
    for node in G.nodes:
        if len(list(G.neighbors(node))) >= 4:
            y, x = G.nodes[node]['y'], G.nodes[node]['x']
            name = f"Intersection at ({y:.4f}, {x:.4f})"
            four_way[name] = (y, x)
    return four_way

intersections = get_4way_intersections(G)

green_start = 35
cycle_duration = 60

# Sidebar
st.sidebar.header("Setup")
start_lat = st.sidebar.number_input("Start Lat", value=30.7270, format="%.5f")
start_lon = st.sidebar.number_input("Start Lon", value=76.7651, format="%.5f")
end_lat = st.sidebar.number_input("End Lat", value=30.7165, format="%.5f")
end_lon = st.sidebar.number_input("End Lon", value=76.7656, format="%.5f")

# Start
if st.sidebar.button("▶️ Start Simulation"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig, dest, weight="length")
    coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    st.session_state.route = coords
    st.session_state.index = 0
    st.session_state.speed = np.random.randint(30, 61)
    st.session_state.timer = 0
    st.session_state.waiting = False
    st.session_state.running = True

# Simulation logic
if st.session_state.get("running", False):
    route = st.session_state.route
    i = st.session_state.index
    speed = st.session_state.speed
    time_in_cycle = st.session_state.timer

    if i >= len(route) - 1:
        st.success("✅ Reached destination.")
        st.session_state.running = False
    else:
        pos = route[i]
        next_pos = route[i + 1]
        dist = geodesic(pos, next_pos).meters
        speed_mps = speed / 3.6
        eta = dist / speed_mps
        arrival = (time_in_cycle + eta) % 60
        phase = "Red" if arrival < 30 else "Yellow" if arrival < 35 else "Green"

        # Closest light ahead
        def is_near_light(loc, intersections, threshold=40):
            for name, iloc in intersections.items():
                if geodesic(loc, iloc).meters < threshold:
                    return True
            return False

        near_light = is_near_light(pos, intersections)

        if near_light and phase == "Red":
            st.session_state.waiting = True
            st.warning("🚗 Stopped at red light...")
        elif st.session_state.waiting and phase != "Red":
            st.session_state.waiting = False
            st.success("🟢 Green light! Resuming...")

        # Speed Suggestion
        def suggest_speed(d, t):
            for s in range(20, 101, 5):
                arrival = (t + d / (s / 3.6)) % 60
                if arrival >= green_start:
                    return s
            return 25

        suggested = suggest_speed(dist, time_in_cycle)
        if suggested != speed:
            st.info(f"⚙️ Adjusting speed to {suggested} km/h")
            st.session_state.speed = suggested

        # Move if not waiting
        if not st.session_state.waiting:
            st.session_state.index += 1

        # Increment timer
        st.session_state.timer = (time_in_cycle + 1) % 60

# Show map
if "route" in st.session_state:
    coords = st.session_state.route
    idx = min(st.session_state.index, len(coords) - 1)
    pos = coords[idx]

    m = folium.Map(location=pos, zoom_start=15)
    folium.PolyLine(coords, color="blue").add_to(m)
    folium.Marker(coords[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(coords[-1], icon=folium.Icon(color="red"), popup="End").add_to(m)

    for name, loc in intersections.items():
        folium.Marker(loc, icon=folium.Icon(color="orange", icon="exclamation-sign"), popup=name).add_to(m)

    folium.Marker(pos, icon=folium.Icon(color="purple", icon="car"), popup="🚗").add_to(m)
    st_folium(m, height=500, width=900)

    st.markdown("### 📊 Status")
    st.write(f"**Position:** {pos}")
    st.write(f"**Index:** {idx}")
    st.write(f"**Speed:** {st.session_state.speed} km/h")
    st.write(f"**Signal Time:** {st.session_state.timer} s")
    st.write(f"**Waiting at Red:** {st.session_state.waiting}")
