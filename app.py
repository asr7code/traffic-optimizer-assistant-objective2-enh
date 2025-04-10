import streamlit as st
from streamlit_folium import st_folium
import folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import time
import numpy as np

st.set_page_config(layout="wide")
st.title("🚦 Chandigarh Traffic Assistant – Full Auto Simulation")

# Load road graph
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# Define traffic lights (static dummy ones for now)
intersections = {
    "ISBT Sector 43": (30.7165, 76.7656),
    "Madhya Marg & Jan Marg": (30.7415, 76.7680),
    "Sector 17 Plaza": (30.7399, 76.7821),
    "PGI Chowk": (30.7625, 76.7662),
    "Sector 35": (30.7270, 76.7651),
}

# Set parameters
speed_limit = 60  # Max vehicle speed
green_start = 35  # green starts at 35s
green_end = 59    # green ends at 59s
cycle_duration = 60

# Sidebar inputs
st.sidebar.header("Simulation Setup")
start_lat = st.sidebar.number_input("Start Latitude", value=30.7270, format="%.5f")
start_lon = st.sidebar.number_input("Start Longitude", value=76.7651, format="%.5f")
end_lat = st.sidebar.number_input("Destination Latitude", value=30.7165, format="%.5f")
end_lon = st.sidebar.number_input("Destination Longitude", value=76.7656, format="%.5f")

if st.sidebar.button("▶️ Start Simulation"):
    # Compute route
    orig_node = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig_node, dest_node, weight='length')
    route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    st.session_state.route = route_coords
    st.session_state.index = 0
    st.session_state.speed = np.random.randint(30, 61)  # initial random speed km/h
    st.session_state.time = 0  # start of signal cycle
    st.session_state.waiting = False
    st.session_state.simulation_running = True

# Run simulation loop
if st.session_state.get("simulation_running", False):

    route_coords = st.session_state.route
    index = st.session_state.index
    current_pos = route_coords[index]
    next_pos = route_coords[index + 1] if index + 1 < len(route_coords) else route_coords[-1]
    speed = st.session_state.speed
    time_in_cycle = st.session_state.time

    distance = geodesic(current_pos, next_pos).meters
    speed_mps = speed / 3.6
    eta = distance / speed_mps

    # Traffic light logic
    arrival_cycle = (time_in_cycle + eta) % cycle_duration
    if arrival_cycle < 30:
        phase = "Red"
    elif arrival_cycle < 35:
        phase = "Yellow"
    else:
        phase = "Green"

    # Handle red light stop
    if phase == "Red" and distance < 50:  # approaching red
        st.session_state.waiting = True
        st.warning("🚦 Red light ahead. Stopping car...")
    elif st.session_state.waiting and phase != "Red":
        st.success("🟢 Green light! Resuming...")
        st.session_state.waiting = False

    # Advance car if not waiting
    if not st.session_state.waiting:
        st.session_state.index += 1
        if st.session_state.index >= len(route_coords) - 1:
            st.success("✅ Destination reached.")
            st.session_state.simulation_running = False

    # Adjust speed dynamically
    def suggest_speed(distance, current_cycle):
        for s in range(20, 101, 5):
            t = distance / (s / 3.6)
            predicted = (current_cycle + t) % 60
            if predicted >= green_start:
                return s
        return speed_limit

    new_speed = suggest_speed(distance, time_in_cycle)
    if new_speed != speed:
        st.info(f"⚙️ Adjusting speed from {speed} to {new_speed} km/h")
        st.session_state.speed = new_speed

    # Update signal cycle time
    st.session_state.time = (st.session_state.time + 1) % cycle_duration

    # Display Map
    m = folium.Map(location=current_pos, zoom_start=15)
    folium.PolyLine(route_coords, color="blue", weight=5).add_to(m)
    folium.Marker(route_coords[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(route_coords[-1], icon=folium.Icon(color="red"), popup="Destination").add_to(m)
    for name, loc in intersections.items():
        folium.Marker(loc, icon=folium.Icon(color="orange", icon="exclamation-sign"), popup=name).add_to(m)
    folium.Marker(current_pos, icon=folium.Icon(color="purple", icon="car"), popup="🚗 Car").add_to(m)

    st_data = st_folium(m, height=500, width=900)

    st.markdown("### 📊 Live Simulation Data")
    st.write(f"**Current Position:** `{current_pos}`")
    st.write(f"**Next Point:** `{next_pos}`")
    st.write(f"**Speed:** `{speed} km/h`")
    st.write(f"**Distance to next:** `{distance:.1f} m`")
    st.write(f"**ETA to next:** `{eta:.1f} sec`")
    st.write(f"**Signal Phase at Arrival:** `{phase}` at `{arrival_cycle:.1f}` sec")

    # Refresh every second
    time.sleep(1)
    st.experimental_rerun()
