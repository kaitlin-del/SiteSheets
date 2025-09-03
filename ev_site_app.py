
import streamlit as st
import pandas as pd
import requests
from pyproj import Transformer
import folium
from streamlit_folium import st_folium

# --- CONFIG ---
WHAT3WORDS_API_KEY = "YOUR_W3W_API_KEY"  #61WM1GK9

# --- FUNCTIONS ---
def convert_to_easting_northing(lat, lon):
    transformer = Transformer.from_crs("epsg:4326", "epsg:27700")
    easting, northing = transformer.transform(lat, lon)
    return round(easting), round(northing)


def get_postcode_info(lat, lon):
    res = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}").json()
    if res.get("status") == 200 and res["result"]:
        result = res["result"][0]
        return result["postcode"], result["admin_ward"], result["admin_district"]
    return "N/A", "N/A", "N/A"

def get_street_name(lat, lon):
    res = requests.get("https://nominatim.openstreetmap.org/reverse", params={
        "format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1
    }, headers={"User-Agent": "EV-Site-App"}).json()
    return res.get("address", {}).get("road", "Unknown")

def calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    kva = round(total_kw / 0.9, 2)
    return kva

# --- STREAMLIT APP ---

st.set_page_config(page_title="EV Charger Site Sheet Generator", layout="wide")
st.title("🔋⚡ EV Charger Site Sheet Generator")

tab1, tab2 = st.tabs(["Single Site", "Batch Upload"])

with tab1:
    st.subheader("📍 Input Coordinates")
    lat = st.number_input("Latitude", format="%.6f")
    lon = st.number_input("Longitude", format="%.6f")

    st.subheader("⚡ Charger Configuration")
    fast_kw = st.number_input("Fast kW (Default 22)", value=22)
    rapid_kw = st.number_input("Rapid kW (Default 60)", value=60)
    ultra_kw = st.number_input("Ultra-Rapid kW (Default 150)", value=150)

    fast = st.number_input("Fast Chargers", 0, 20, 0)
    rapid = st.number_input("Rapid Chargers", 0, 20, 0)
    ultra = st.number_input("Ultra-Rapid Chargers", 0, 20, 0)

    if st.button("Process Site"):
        easting, northing = convert_to_easting_northing(lat, lon)
        postcode, ward, district = get_postcode_info(lat, lon)
        street = get_street_name(lat, lon)
        kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)

        site_data = {
            "Latitude": lat,
            "Longitude": lon,
            "Easting": easting,
            "Northing": northing,
            "Postcode": postcode,
            "Ward": ward,
            "District": district,
            "Street": street,
            "Fast Chargers": fast,
            "Rapid Chargers": rapid,
            "Ultra Chargers": ultra,
            "Required kVA": kva,
        }

        st.markdown("### ✅ Site Details")
        for k, v in site_data.items():
            st.write(f"**{k}**: {v}")

        # Map
        m = folium.Map(location=[lat, lon], zoom_start=16)
        folium.Marker([lat, lon], popup=f"EV Site: {street}").add_to(m)
        st_data = st_folium(m, width=700, height=400)

        df = pd.DataFrame([site_data])
        st.download_button("📥 Download Site Info (CSV)", df.to_csv(index=False), file_name="ev_site.csv")

with tab2:
    st.subheader("📁 Upload CSV with Columns: latitude, longitude, fast, rapid, ultra")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

    fast_kw = st.number_input("Fast kW (Batch)", value=22, key="fast_batch")
    rapid_kw = st.number_input("Rapid kW (Batch)", value=60, key="rapid_batch")
    ultra_kw = st.number_input("Ultra-Rapid kW (Batch)", value=150, key="ultra_batch")

    if uploaded_file:
        df_input = pd.read_csv(uploaded_file)
        output = []

        for _, row in df_input.iterrows():
            lat, lon = row["latitude"], row["longitude"]
            f, r, u = int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0))
            e, n = convert_to_easting_northing(lat, lon)
            postcode, ward, district = get_postcode_info(lat, lon)
            street = get_street_name(lat, lon)
            kva = calculate_kva(f, r, u, fast_kw, rapid_kw, ultra_kw)

            output.append({
                "Latitude": lat,
                "Longitude": lon,
                "Easting": e,
                "Northing": n,
                "Postcode": postcode,
                "Ward": ward,
                "District": district,
                "Street": street,
                "Fast Chargers": f,
                "Rapid Chargers": r,
                "Ultra Chargers": u,
                "Required kVA": kva,
            })

        df_out = pd.DataFrame(output)
        st.dataframe(df_out)
        st.download_button("📥 Download Results", df_out.to_csv(index=False), file_name="batch_results.csv")
