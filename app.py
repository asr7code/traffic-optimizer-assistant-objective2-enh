import streamlit as st
from streamlit_folium import st_folium
import folium
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import numpy as np

st.set_page_config(layout="wide")
st.title("🚦 Chandigarh Traffic Assistant – Step-by-Step Simulation")

# Load road graph
@st.cache_resource
def load_graph():
    return ox.load_graphml("chandigarh.graphml")

G = load_graph()

# Dummy Traffic Lights
intersections = {
    "ISBT Sector 43": (30.7165, 76.7656),
    "Madhya Marg & Jan Marg": (30.7415, 76.7680),
    "Sector 17 Plaza": (30.7399, 76.7821),
    "PGI Chowk": (30.7625, 76.7662),
    "Sector 35": (30.7270, 76.7651),
}

green_start = 35
cycle_duration = 60

# Sidebar Input
st.sidebar.header("Setup")
start_lat = st.sidebar.number_input("Start Latitude", value=30.7270, format="%.5f")
start_lon = st.sidebar.number_input("Start Longitude", value=76.7651, format="%.5f")
end_lat = st.sidebar.number_input("End Latitude", value=30.7165, format="%.5f")
end_lon = st.sidebar.number_input("End Longitude", value=76.7656, format="%.5f")

if st.sidebar.button("🚦 Start Simulation"):
    orig_node = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.distance.nearest_nodes(G, end_lon, end_lat)
    route = nx.shortest_path(G, orig_node, dest_node, weight="length")
    route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    st.session_state.route = route_coords
    st.session_state.index = 0
    st.session_state.speed = np.random.randint(30, 61)
    st.session_state.time = 0
    st.session_state.waiting = False

# Next Step Button
if st.button("➡️ Next Step"):
    if 'route' in st.session_state:
        route_coords = st.session_state.route
        index = st.session_state.index
        if index < len(route_coords) - 1:
            curr_pos = route_coords[index]
            next_pos = route_coords[index + 1]
            dist = geodesic(curr_pos, next_pos).meters
            speed = st.session_state.speed
            time_now = st.session_state.time
            eta = dist / (speed / 3.6)
            arrival = (time_now + eta) % cycle_duration
            phase = "Red" if arrival < 30 else "Yellow" if arrival < 35 else "Green"

            # Red light logic
            if phase == "Red" and dist < 50:
                st.session_state.waiting = True
            elif st.session_state.waiting and phase != "Red":
                st.session_state.waiting = False

            # Suggest speed
            def suggest_speed(d, cycle):
                for s in range(20, 101, 5):
                    t = d / (s / 3.6)
                    arrive = (cycle + t) % 60
                    if arrive >= green_start:
                        return s
                return 25

            new_speed = suggest_speed(dist, time_now)
            st.session_state.speed = new_speed

            if not st.session_state.waiting:
                st.session_state.index += 1
            st.session_state.time = (time_now + 1) % 60

# Draw Map
if 'route' in st.session_state:
    route_coords = st.session_state.route
    idx = min(st.session_state.index, len(route_coords) - 1)
    current_pos = route_coords[idx]

    m = folium.Map(location=current_pos, zoom_start=15)
    folium.PolyLine(route_coords, color="blue", weight=5).add_to(m)
    folium.Marker(route_coords[0], icon=folium.Icon(color="green"), popup="Start").add_to(m)
    folium.Marker(route_coords[-1], icon=folium.Icon(color="red"), popup="Destination").add_to(m)

    for name, loc in intersections.items():
        folium.Marker(loc, icon=folium.Icon(color="orange", icon="exclamation-sign"), popup=name).add_to(m)

    folium.Marker(current_pos, icon=folium.Icon(color="purple", icon="car"), popup="🚗 Car").add_to(m)
    st_data = st_folium(m, height=500, width=900)

    st.markdown("### 📊 Car Status")
    st.write(f"**Current Position:** {current_pos}")
    st.write(f"**Step Index:** {idx}")
    st.write(f"**Speed:** {st.session_state.speed} km/h")
    st.write(f"**Signal Time:** {st.session_state.time} s")
    st.write(f"**Waiting at Red Light:** {st.session_state.waiting}")
