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
        # Clean up column names in case of stray spaces
        df.columns = [c.strip().title() for c in df.columns]
        return df
    except FileNotFoundError:
        st.warning("⚠️ 'footprint.csv' not found in repository. Displaying sample data.")
        # Fallback dummy data
        return pd.DataFrame({
            "Force": ["Metropolitan Police", "Metropolitan Police", "Greater Manchester", "Greater Manchester", "Police Scotland", "Avon and Somerset"],
            "Unit": ["Roads", "Public Order", "Roads", "Dogs", "Dogs", "Public Order"],
            "Status": ["Live", "In discussions", "Live", "Target", "Target", "Live"]
        })

features = get_police_data()
df_footprint = get_footprint_data()

# --- DEFINE STYLES ---
STATUS_STYLES = {
    "Live": {"color": "#2ecc71", "hex": "#2ecc71"},          # Green
    "In discussions": {"color": "#f1c40f", "hex": "#f1c40f"}, # Yellow/Amber
    "Target": {"color": "#e74c3c", "hex": "#e74c3c"}          # Red
}

UNIT_STYLES = {
    "Roads": {"icon": "🚓", "weight": 5, "dash": None, "lon_offset": 0.0},
    "Dogs": {"icon": "🐕‍🦺", "weight": 3.5, "dash": '10, 8', "lon_offset": -0.15},
    "Public Order": {"icon": "🛡️", "weight": 2, "dash": '3, 6', "lon_offset": 0.15}
}

# --- SIDEBAR UI ---
st.sidebar.header("Filter Pipeline")

st.sidebar.subheader("Sales Status")
selected_statuses = st.sidebar.multiselect(
    "Select Account Status:",
    options=list(STATUS_STYLES.keys()),
    default=["Live", "In discussions", "Target"]
)

st.sidebar.subheader("Specialist Units")
selected_units = st.sidebar.multiselect(
    "Select Unit Types:",
    options=list(UNIT_STYLES.keys()),
    default=["Roads", "Dogs", "Public Order"]
)

# --- FILTER DATA ---
# Filter the pandas dataframe based on sidebar selections
filtered_df = df_footprint[
    (df_footprint['Status'].isin(selected_statuses)) & 
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
                        'fillColor': c, 'color': c, 'weight': w, 'dashArray': d, 'fillOpacity': 0.05 
                    },
                    tooltip=f"{u_style['icon']} {force_name}: {unit} ({status})"
                ).add_to(m)
                
                # 2. Add Colored Glowing Emoji
                # Using CSS text-shadow to create a colored border around the emoji
                glow = s_style['hex']
                html_icon = f'''
                    <div style="font-size: 20px; text-shadow: 
                        -1.5px -1.5px 0 {glow}, 1.5px -1.5px 0 {glow}, 
                        -1.5px 1.5px 0 {glow}, 1.5px 1.5px 0 {glow};">
                        {u_style["icon"]}
                    </div>
                '''
                
                folium.Marker(
                    location=[center_lat, center_lon + u_style['lon_offset']],
                    icon=DivIcon(icon_size=(30, 30), icon_anchor=(15, 15), html=html_icon),
                    tooltip=f"{force_name}: {unit} ({status})"
                ).add_to(m)

# --- RENDER MAP IN STREAMLIT ---
st_folium(m, width=1200, height=700, returned_objects=[])