import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.features import DivIcon
import requests
import pandas as pd
from shapely.geometry import shape, mapping

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Airbox Footprint Map", page_icon="📍", layout="wide")
st.title("Airbox Customer Footprint: Specialist Police Units")

# --- CACHED DATA FETCHING (GEOMETRY) ---
@st.cache_data
def get_police_data():
    police_url = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Police_Force_Areas_December_2023_EW_BGC/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson"
    country_url = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Countries_December_2023_Boundaries_UK_BGC/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson"
    
    all_features = []
    
    try:
        r_pol = requests.get(police_url, timeout=15)
        if r_pol.status_code == 200:
            all_features.extend(r_pol.json().get('features', []))
    except Exception as e:
        st.error(f"Failed to fetch EW Police data: {e}")

    try:
        r_country = requests.get(country_url, timeout=15)
        if r_country.status_code == 200:
            for feature in r_country.json().get('features', []):
                if feature['properties'].get('CTRY23NM') == 'Scotland':
                    feature['properties']['PFA23NM'] = "Police Scotland"
                    all_features.append(feature)
    except Exception as e:
        st.error(f"Failed to fetch Scotland data: {e}")

    processed_features = []
    for feature in all_features:
        name = feature['properties'].get("PFA23NM", "Unknown")
        geom = shape(feature['geometry'])
        
        # Simplify geometry for fast loading
        tolerance = 0.02 if name == "Police Scotland" else 0.002
        simplified_geom = geom.simplify(tolerance=tolerance, preserve_topology=True)
        feature['geometry'] = mapping(simplified_geom)
        
        centroid = simplified_geom.centroid
        feature['properties']['center_lon'] = centroid.x
        feature['properties']['center_lat'] = centroid.y
        
        processed_features.append(feature)

    processed_features.sort(key=lambda x: x['properties'].get("PFA23NM", ""))
    return processed_features

# --- CACHED DATA FETCHING (CSV FOOTPRINT) ---
@st.cache_data
def get_footprint_data():
    try:
        df = pd.read_csv("footprint.csv")
        df.columns = [c.strip().title() for c in df.columns]
        return df
    except FileNotFoundError:
        st.warning("⚠️ 'footprint.csv' not found. Displaying comprehensive sample data.")
        # Dummy data showcasing all 6 units
        return pd.DataFrame({
            "Force": [
                "Metropolitan Police", "Metropolitan Police", "Metropolitan Police", 
                "Greater Manchester", "Greater Manchester", "Police Scotland", "Avon and Somerset"
            ],
            "Unit": [
                "Roads Policing", "Public Order", "Firearms", 
                "Dogs Units", "Serious & Organised Crime", "Surveillance", "Public Order"
            ],
            "Status": [
                "Live", "In discussions", "Target", 
                "Target", "Live", "In discussions", "Live"
            ]
        })

features = get_police_data()
df_footprint = get_footprint_data()

# --- DEFINE STYLES & GRID OFFSETS ---
STATUS_STYLES = {
    "Live": {"color": "#2ecc71", "hex": "#2ecc71"},          # Green
    "In discussions": {"color": "#f1c40f", "hex": "#f1c40f"}, # Yellow
    "Target": {"color": "#e74c3c", "hex": "#e74c3c"}          # Red
}

# The 6 units are assigned specific lat/lon offsets to form a 2x3 grid over the region
UNIT_STYLES = {
    "Roads Policing":            {"icon": "🚓", "weight": 5.0, "dash": None,             "lat_offset": 0.04,  "lon_offset": 0.0},
    "Dogs Units":                {"icon": "🐕‍🦺", "weight": 4.0, "dash": '10, 10',         "lat_offset": 0.04,  "lon_offset": -0.15},
    "Public Order":              {"icon": "🛡️", "weight": 3.0, "dash": '2, 6',           "lat_offset": 0.04,  "lon_offset": 0.15},
    "Firearms":                  {"icon": "🎯", "weight": 2.5, "dash": '15, 5, 2, 5',    "lat_offset": -0.04, "lon_offset": 0.0},
    "Surveillance":              {"icon": "📡", "weight": 2.0, "dash": '20, 10',         "lat_offset": -0.04, "lon_offset": -0.15},
    "Serious & Organised Crime": {"icon": "🕵️", "weight": 1.5, "dash": '2, 4, 2, 8',     "lat_offset": -0.04, "lon_offset": 0.15}
}

# --- SIDEBAR UI ---
st.sidebar.header("Filter Pipeline")

# 1. Dedicated Toggles for Status
st.sidebar.subheader("Sales Status")
show_live = st.sidebar.checkbox("🟢 Show Live", value=True)
show_disc = st.sidebar.checkbox("🟡 Show In Discussions", value=True)
show_targ = st.sidebar.checkbox("🔴 Show Targets", value=True)

# Build the active status list based on toggles
active_statuses = []
if show_live: active_statuses.append("Live")
if show_disc: active_statuses.append("In discussions")
if show_targ: active_statuses.append("Target")

# 2. Multi-select for Units
st.sidebar.subheader("Specialist Units")
selected_units = st.sidebar.multiselect(
    "Select Unit Types:",
    options=list(UNIT_STYLES.keys()),
    default=list(UNIT_STYLES.keys()) # Select all by default
)

# --- FILTER DATA ---
filtered_df = df_footprint[
    (df_footprint['Status'].isin(active_statuses)) & 
    (df_footprint['Unit'].isin(selected_units))
]

# --- BUILD THE MAP ---
m = folium.Map(location=[54.5, -3.0], zoom_start=5.5, tiles="cartodbpositron")

for feature in features:
    force_name = feature['properties'].get("PFA23NM", "Unknown")
    
    # Check if this force exists in our filtered footprint data
    force_data = filtered_df[filtered_df['Force'] == force_name]
    
    if not force_data.empty:
        center_lon = feature['properties']['center_lon']
        center_lat = feature['properties']['center_lat']
        
        # Iterate through each active unit for this specific force
        for _, row in force_data.iterrows():
            unit = row['Unit'].strip()
            status = row['Status'].strip()
            
            if unit in UNIT_STYLES and status in STATUS_STYLES:
                u_style = UNIT_STYLES[unit]
                s_style = STATUS_STYLES[status]
                
                # 1. Add Colored Boundary
                folium.GeoJson(
                    feature,
                    style_function=lambda x, c=s_style['color'], w=u_style['weight'], d=u_style['dash']: {
                        'fillColor': c, 'color': c, 'weight': w, 'dashArray': d, 'fillOpacity': 0.03 
                    },
                    tooltip=f"{u_style['icon']} {force_name}: {unit} ({status})"
                ).add_to(m)
                
                # 2. Add Colored Glowing Emoji using Grid Offsets
                glow = s_style['hex']
                html_icon = f'''
                    <div style="font-size: 20px; text-shadow: 
                        -1.5px -1.5px 0 {glow}, 1.5px -1.5px 0 {glow}, 
                        -1.5px 1.5px 0 {glow}, 1.5px 1.5px 0 {glow};">
                        {u_style["icon"]}
                    </div>
                '''
                
                folium.Marker(
                    location=[center_lat + u_style['lat_offset'], center_lon + u_style['lon_offset']],
                    icon=DivIcon(icon_size=(30, 30), icon_anchor=(15, 15), html=html_icon),
                    tooltip=f"{force_name}: {unit} ({status})"
                ).add_to(m)

# --- RENDER MAP IN STREAMLIT ---
st_folium(m, width=1200, height=700, returned_objects=[])