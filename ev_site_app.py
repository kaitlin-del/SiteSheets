import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time
import io

# API KEYS
GOOGLE_API_KEY = st.secrets["google_api_key"]
TOMTOM_API_KEY = st.secrets.get("tomtom_api_key", "")

# UTILITY FUNCTIONS

def classify_charger_power(name, rating=None):
    """Classify EV charger by power rating into Fast, Rapid, or Ultra Rapid"""
    import re
    power_kw = None
    
    if rating and isinstance(rating, (int, float)):
        power_kw = rating
    else:
        name_str = str(name).lower()
        kw_match = re.search(r'(\d+)\s*kw', name_str)
        if kw_match:
            power_kw = int(kw_match.group(1))
    
    if power_kw:
        if power_kw <= 22:
            return "Fast (≤22kW)"
        elif power_kw <= 50:
            return "Rapid (23-50kW)"
        elif power_kw <= 150:
            return "Rapid (51-150kW)"
        else:
            return "Ultra Rapid (>150kW)"
    
    name_lower = name.lower()
    if any(keyword in name_lower for keyword in ["ultra", "ultra-rapid", "350kw", "300kw"]):
        return "Ultra Rapid (>150kW)"
    elif any(keyword in name_lower for keyword in ["rapid", "dc", "fast dc", "ccs", "chademo", "supercharger"]):
        return "Rapid (23-150kW)"
    elif any(keyword in name_lower for keyword in ["fast", "ac", "type 2", "7kw", "22kw"]):
        return "Fast (≤22kW)"
    else:
        return "Unknown"

def extract_brand_name(station_name):
    """Extract brand name from station name"""
    if not station_name or station_name == "Unknown":
        return "Unknown"
    
    brands = {
        'tesla': 'Tesla', 'supercharger': 'Tesla', 'chargepoint': 'ChargePoint',
        'ionity': 'Ionity', 'pod point': 'Pod Point', 'podpoint': 'Pod Point',
        'ecotricity': 'Ecotricity', 'bp pulse': 'BP Pulse', 'bp': 'BP Pulse',
        'shell': 'Shell Recharge', 'gridserve': 'Gridserve', 'instavolt': 'InstaVolt',
        'osprey': 'Osprey Charging', 'charge your car': 'Charge Your Car',
        'rolec': 'Rolec', 'chargemaster': 'Chargemaster', 'polar': 'Polar Network',
        'source london': 'Source London', 'ev-box': 'EVBox', 'fastned': 'Fastned',
        'mer': 'MER', 'newmotion': 'NewMotion'
    }
    
    name_lower = station_name.lower()
    for brand_key, brand_name in brands.items():
        if brand_key in name_lower:
            return brand_name
    
    words = station_name.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    elif len(words) == 1:
        return words[0]
    return "Other"

def create_bar_chart_data(brands_dict):
    """Create bar chart data for market share analysis sorted by proportion"""
    if not brands_dict:
        return None
    try:
        import matplotlib.pyplot as plt
        import io
        import base64
        
        sorted_brands = sorted(brands_dict.items(), key=lambda x: x[1])
        labels = [item[0] for item in sorted_brands]
        counts = [item[1] for item in sorted_brands]
        total = sum(counts)
        proportions = [(c/total)*100 for c in counts]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9']
        bars = ax.barh(labels, proportions, color=colors[:len(labels)])
        
        ax.set_xlabel('Percentage (%)', fontsize=12, fontweight='bold')
        ax.set_title('EV Charging Network Market Share (Ascending)', fontsize=14, fontweight='bold', pad=20)
        ax.grid(axis='x', alpha=0.3, linestyle='--')
        
        for i, (bar, prop) in enumerate(zip(bars, proportions)):
            ax.text(prop + 0.5, i, f'{prop:.1f}%', va='center', fontsize=9)
        
        plt.tight_layout()
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300, facecolor='white')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)
        return img_base64
    except Exception as e:
        st.warning(f"Could not create bar chart: {e}")
        return None

def create_csv_template():
    """Create a CSV template for batch processing"""
    template_data = {
        "latitude": [51.5074, 51.5155, 51.5203],
        "longitude": [-0.1278, -0.0922, -0.0740],
        "fast_chargers": [2, 4, 3],
        "rapid_chargers": [2, 1, 2],
        "ultra_chargers": [1, 0, 1]
    }
    df_template = pd.DataFrame(template_data)
    return df_template.to_csv(index=False).encode('utf-8')

@st.cache_data
def get_elevation_data(lat, lon):
    """Get elevation data using Google Maps Elevation API"""
    try:
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        params = {"locations": f"{lat},{lon}", "key": GOOGLE_API_KEY}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                elevation = data["results"][0].get("elevation")
                return round(elevation, 2) if elevation is not None else "N/A"
    except Exception as e:
        st.warning(f"Elevation API error: {e}")
    return "N/A"

def get_aerial_view_url(lat, lon, zoom=18, size="600x400"):
    """Generate Google Maps Static API URL for aerial view with marker"""
    return (f"https://maps.googleapis.com/maps/api/staticmap"
            f"?center={lat},{lon}&zoom={zoom}&size={size}"
            f"&maptype=satellite"
            f"&markers=color:red%7Clabel:📍%7C{lat},{lon}"
            f"&key={GOOGLE_API_KEY}")

def get_embed_map_html(lat, lon, mode="place"):
    """Generate Google Maps Embed API HTML iframe"""
    if mode == "place":
        src = f"https://www.google.com/maps/embed/v1/place?key={GOOGLE_API_KEY}&q={lat},{lon}&zoom=15"
    else:  # satellite
        src = f"https://www.google.com/maps/embed/v1/view?key={GOOGLE_API_KEY}&center={lat},{lon}&zoom=18&maptype=satellite"
    
    return f'<iframe width="100%" height="450" frameborder="0" style="border:0" src="{src}" allowfullscreen></iframe>'

@st.cache_data
def get_postcode_info(lat, lon):
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = r.json()
        if data.get("status") == 200 and data["result"]:
            res = data["result"][0]
            return {
                "postcode": res.get("postcode", "N/A"),
                "admin_ward": res.get("admin_ward", "N/A"),
                "admin_district": res.get("admin_district", "N/A"),
                "admin_county": res.get("admin_county", "N/A"),
                "parish": res.get("parish", "N/A"),
                "parliamentary_constituency": res.get("parliamentary_constituency", "N/A"),
                "ccg": res.get("ccg", "N/A"),
                "ced": res.get("ced", "N/A"),
                "nuts": res.get("nuts", "N/A"),
                "lsoa": res.get("lsoa", "N/A"),
                "msoa": res.get("msoa", "N/A"),
                "region": res.get("region", "N/A"),
                "country": res.get("country", "N/A")
            }
    except Exception as e:
        st.warning(f"Postcode API error: {e}")
    return {
        "postcode": "N/A", "admin_ward": "N/A", "admin_district": "N/A",
        "admin_county": "N/A", "parish": "N/A", "parliamentary_constituency": "N/A",
        "ccg": "N/A", "ced": "N/A", "nuts": "N/A", "lsoa": "N/A", "msoa": "N/A",
        "region": "N/A", "country": "N/A"
    }

@st.cache_data
def get_geocode_details(lat, lon):
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/geocode/json", 
                         params={"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY}, timeout=10)
        data = r.json()
        if data.get("status")=="OK" and data.get("results"):
            comps = data["results"][0]["address_components"]
            details = {}
            for c in comps:
                types = c.get("types",[])
                if "route" in types: details["street"]=c["long_name"]
                if "street_number" in types: details["street_number"]=c["long_name"]
                if "neighborhood" in types: details["neighbourhood"]=c["long_name"]
                if "locality" in types: details["city"]=c["long_name"]
                if "administrative_area_level_2" in types: details["county"]=c["long_name"]
                if "administrative_area_level_1" in types: details["region"]=c["long_name"]
                if "postal_code" in types: details["postcode"]=c["long_name"]
                if "country" in types: details["country"]=c["long_name"]
            details["formatted_address"]=data["results"][0].get("formatted_address")
            return details
    except Exception as e:
        st.warning(f"Geocoding API error: {e}")
    return {}

@st.cache_data
def get_street_view_data(lat: float, lon: float, fov: int = 90, pitch: int = 0):
    meta_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    meta_params = {"location": f"{lat},{lon}", "key": GOOGLE_API_KEY}
    try:
        meta = requests.get(meta_url, params=meta_params, timeout=10).json()
        has_sv = meta.get("status") == "OK"
    except Exception:
        has_sv = False

    maps_pano_link = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
    
    if has_sv:
        headings = {"North (0°)": 0, "East (90°)": 90, "South (180°)": 180, "West (270°)": 270}
        image_urls = {}
        for direction, heading in headings.items():
            img_url = (
                "https://maps.googleapis.com/maps/api/streetview"
                f"?size=640x400&location={lat},{lon}&fov={fov}&pitch={pitch}&heading={heading}&key={GOOGLE_API_KEY}"
            )
            image_urls[direction] = img_url
        return {"image_urls": image_urls, "maps_link": maps_pano_link, "has_street_view": True}
    else:
        return {"image_urls": {}, "maps_link": maps_pano_link, "has_street_view": False}

def google_maps_search_link(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

def google_maps_dir_link(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

@st.cache_data
def get_ev_charging_stations(lat, lon, radius=1000):
    ev_stations = []
    try:
        search_terms = ["electric vehicle charging station", "EV charging", "Tesla Supercharger", "ChargePoint", "Ionity"]
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        all_results = []
        
        type_params = {"location": f"{lat},{lon}", "radius": radius, "type": "gas_station", 
                      "keyword": "electric vehicle charging", "key": GOOGLE_API_KEY}
        response = requests.get(url, params=type_params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                all_results.extend(data.get("results", []))
        time.sleep(0.1)
        
        for term in search_terms:
            keyword_params = {"location": f"{lat},{lon}", "radius": radius, "keyword": term, "key": GOOGLE_API_KEY}
            response = requests.get(url, params=keyword_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    all_results.extend(data.get("results", []))
            time.sleep(0.1)
        
        unique_places = {}
        for place in all_results:
            place_id = place.get("place_id")
            if place_id and place_id not in unique_places:
                name = place.get("name", "").lower()
                types = place.get("types", [])
                ev_keywords = ["electric", "ev", "charging", "tesla", "chargepoint", "ionity", "pod point", "ecotricity"]
                if any(keyword in name for keyword in ev_keywords) or "electric_vehicle_charging_station" in types:
                    geometry = place.get("geometry", {})
                    location = geometry.get("location", {})
                    unique_places[place_id] = {
                        "place_id": place_id, "name": place.get("name", "Unknown"),
                        "latitude": location.get("lat"), "longitude": location.get("lng"),
                        "geometry": geometry
                    }
        
        for place_id, basic_info in unique_places.items():
            try:
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {"place_id": place_id, 
                                "fields": "name,rating,formatted_address,photos,types,geometry,opening_hours,formatted_phone_number",
                                "key": GOOGLE_API_KEY}
                details_response = requests.get(details_url, params=details_params, timeout=10)
                if details_response.status_code == 200:
                    details_data = details_response.json()
                    if details_data.get("status") == "OK":
                        result = details_data.get("result", {})
                        photo_url = None
                        photos = result.get("photos", [])
                        if photos:
                            photo_reference = photos[0].get("photo_reference")
                            if photo_reference:
                                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_API_KEY}"
                        geometry = result.get("geometry", basic_info.get("geometry", {}))
                        location = geometry.get("location", {})
                        ev_station = {
                            "name": result.get("name", basic_info.get("name", "Unknown")),
                            "rating": result.get("rating", "N/A"),
                            "address": result.get("formatted_address", "N/A"),
                            "photo_url": photo_url,
                            "phone": result.get("formatted_phone_number", "N/A"),
                            "types": result.get("types", []),
                            "place_id": place_id,
                            "latitude": location.get("lat", basic_info.get("latitude")),
                            "longitude": location.get("lng", basic_info.get("longitude")),
                            "geometry": geometry
                        }
                        if ev_station["latitude"] and ev_station["longitude"]:
                            ev_stations.append(ev_station)
                time.sleep(0.1)
            except Exception:
                if basic_info.get("latitude") and basic_info.get("longitude"):
                    ev_stations.append(basic_info)
    except Exception as e:
        st.warning(f"Error searching for EV stations: {e}")
    return ev_stations

PLACE_TYPES_FOR_STATS = ["restaurant", "cafe", "shopping_mall", "supermarket", "hospital",
                         "pharmacy", "bank", "atm", "lodging", "gas_station"]

@st.cache_data
def get_nearby_amenities(lat, lon, radius=500):
    amenities_summary_list = []
    counts = {t: 0 for t in PLACE_TYPES_FOR_STATS}
    total_hits = 0

    try:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        for place_type in PLACE_TYPES_FOR_STATS:
            params = {"location": f"{lat},{lon}", "radius": radius, "type": place_type, "key": GOOGLE_API_KEY}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    results = data.get("results", [])
                    shown = 0
                    for place in results:
                        name = place.get("name", "Unknown")
                        rating = place.get("rating", "N/A")
                        name_lower = name.lower()
                        ev_keywords = ["electric", "ev", "charging", "tesla", "chargepoint"]
                        if any(keyword in name_lower for keyword in ev_keywords):
                            continue
                        if shown < 3:
                            display_type = place_type.replace("_", " ").title()
                            amenity_info = f"{name} ({display_type})"
                            if rating != "N/A":
                                amenity_info += f" ⭐{rating}"
                            amenities_summary_list.append(amenity_info)
                            shown += 1
                        counts[place_type] += 1
                        total_hits += 1
            time.sleep(0.1)

        summary = "; ".join(amenities_summary_list[:15]) if amenities_summary_list else "None nearby"
        proportions = {}
        if total_hits > 0:
            proportions = {t: round((counts[t] / total_hits) * 100.0, 2) for t in counts}
        else:
            proportions = {t: 0.0 for t in counts}

        return {"summary": summary, "counts": counts, "proportions": proportions, "total_found": total_hits}
    except Exception as e:
        st.warning(f"Places API error: {e}")
        return {"summary": f"Error retrieving amenities: {str(e)}", 
               "counts": {t: 0 for t in PLACE_TYPES_FOR_STATS},
               "proportions": {t: 0.0 for t in PLACE_TYPES_FOR_STATS}, "total_found": 0}

@st.cache_data
def get_road_info_google_roads(lat, lon):
    road_info = {"snapped_road_name": "Unknown", "snapped_road_type": "Unknown",
                "nearest_road_name": "Unknown", "nearest_road_type": "Unknown", "place_id": None}
    try:
        snap_url = "https://roads.googleapis.com/v1/snapToRoads"
        snap_params = {"path": f"{lat},{lon}", "interpolate": "true", "key": GOOGLE_API_KEY}
        snap_response = requests.get(snap_url, params=snap_params, timeout=10)
        if snap_response.status_code == 200:
            snap_data = snap_response.json()
            if "snappedPoints" in snap_data and snap_data["snappedPoints"]:
                snapped_point = snap_data["snappedPoints"][0]
                place_id = snapped_point.get("placeId")
                if place_id:
                    road_info["place_id"] = place_id
                    place_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    place_params = {"place_id": place_id, "fields": "name,types,geometry,formatted_address", "key": GOOGLE_API_KEY}
                    place_response = requests.get(place_url, params=place_params, timeout=10)
                    if place_response.status_code == 200:
                        place_data = place_response.json()
                        if place_data.get("status") == "OK":
                            result = place_data.get("result", {})
                            road_info["snapped_road_name"] = result.get("name", "Unknown Road")
                            place_types = result.get("types", [])
                            road_info["snapped_road_type"] = classify_road_type(place_types, road_info["snapped_road_name"])
        
        if road_info["snapped_road_name"] == "Unknown":
            try:
                geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
                geocode_params = {"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY}
                geocode_response = requests.get(geocode_url, params=geocode_params, timeout=10)
                if geocode_response.status_code == 200:
                    geocode_data = geocode_response.json()
                    if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                        components = geocode_data["results"][0].get("address_components", [])
                        for component in components:
                            types = component.get("types", [])
                            if "route" in types:
                                fallback_road_name = component.get("long_name", "Unknown Road")
                                fallback_road_type = classify_road_type_from_name(fallback_road_name)
                                road_info["snapped_road_name"] = fallback_road_name
                                road_info["snapped_road_type"] = fallback_road_type
                                road_info["nearest_road_name"] = fallback_road_name
                                road_info["nearest_road_type"] = fallback_road_type
                                break
            except Exception:
                pass
    except Exception as e:
        st.warning(f"Google Roads API error: {e}")
    return road_info

def classify_road_type(place_types, road_name=""):
    if "highway" in place_types:
        return "Highway"
    elif "primary" in place_types:
        return "Primary Road"
    elif "secondary" in place_types:
        return "Secondary Road"
    elif "tertiary" in place_types:
        return "Tertiary Road"
    elif "residential" in place_types:
        return "Residential Street"
    elif "service" in place_types:
        return "Service Road"
    elif "trunk" in place_types:
        return "Trunk Road"
    elif "route" in place_types:
        return "Route"
    else:
        return classify_road_type_from_name(road_name)

def classify_road_type_from_name(road_name):
    if not road_name or road_name == "Unknown Road":
        return "Local Road"
    road_name_lower = road_name.lower()
    if any(keyword in road_name_lower for keyword in ["motorway", "m1", "m25", "m2", "m3", "m4", "m5", "m6"]):
        return "Motorway"
    elif road_name_lower.startswith("a") and len(road_name) > 1 and road_name[1:].split()[0].isdigit():
        return "A Road"
    elif road_name_lower.startswith("b") and len(road_name) > 1 and road_name[1:].split()[0].isdigit():
        return "B Road"
    elif any(keyword in road_name_lower for keyword in ["dual carriageway", "bypass"]):
        return "Dual Carriageway"
    elif any(keyword in road_name_lower for keyword in ["street", "road", "avenue", "lane", "drive", "close", "way"]):
        return "Local Road"
    elif any(keyword in road_name_lower for keyword in ["roundabout", "circus"]):
        return "Roundabout"
    else:
        return "Local Road"

@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326","epsg:27700")

def convert_to_british_grid(lat, lon):
    transformer = get_transformer()
    try:
        e, n = transformer.transform(lat, lon)
        return round(e), round(n)
    except Exception as e:
        st.warning(f"Coordinate transformation error: {e}")
        return None, None

def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    return round(total_kw / 0.95, 2)

def get_tomtom_traffic(lat, lon):
    if not TOMTOM_API_KEY:
        return {"speed": None, "freeFlow": None, "congestion": "N/A"}
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"point": f"{lat},{lon}", "key": TOMTOM_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            flow = r.json().get("flowSegmentData", {})
            speed, freeflow = flow.get("currentSpeed"), flow.get("freeFlowSpeed")
            if speed and freeflow and freeflow > 0:
                ratio = speed / freeflow
                if ratio > 0.85:
                    level = "Low"
                elif ratio > 0.6:
                    level = "Medium"
                else:
                    level = "High"
                return {"speed": speed, "freeFlow": freeflow, "congestion": level}
    except Exception as e:
        st.warning(f"TomTom API error: {e}")
    return {"speed": None, "freeFlow": None, "congestion": "N/A"}

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw,
                 competitor_radius: int = 1000, amenities_radius: int = 500):
    with st.spinner(f"Processing site at {lat}, {lon}..."):
        result = {
            "latitude": lat, "longitude": lon, "easting": None, "northing": None,
            "elevation": "N/A", "postcode": "N/A", "ward": "N/A", "district": "N/A",
            "admin_county": "N/A", "parish": "N/A", "parliamentary_constituency": "N/A",
            "ccg": "N/A", "ced": "N/A", "nuts": "N/A", "lsoa": "N/A", "msoa": "N/A",
            "postcode_region": "N/A", "postcode_country": "N/A",
            "street": "N/A", "street_number": "N/A", "neighbourhood": "N/A", "city": "N/A",
            "county": "N/A", "region": "N/A", "country": "N/A", "formatted_address": "N/A",
            "fast_chargers": fast, "rapid_chargers": rapid, "ultra_chargers": ultra,
            "required_kva": 0, "traffic_speed": None, "traffic_freeflow": None,
            "traffic_congestion": "N/A", "amenities": "N/A", "amenities_summary": "N/A",
            "amenities_counts": {t: 0 for t in PLACE_TYPES_FOR_STATS},
            "amenities_proportions": {t: 0.0 for t in PLACE_TYPES_FOR_STATS},
            "amenities_total": 0, "snapped_road_name": "Unknown", "snapped_road_type": "Unknown",
            "nearest_road_name": "Unknown", "nearest_road_type": "Unknown", "place_id": None,
            "competitor_ev_count": 0, "competitor_ev_names": "None", "ev_stations_details": [],
            "street_view_image_urls": {}, "street_view_maps_link": None,
            "google_maps_link": None, "google_maps_dir_link": None, "has_street_view": False,
            "aerial_view_url": None, "competitor_radius": competitor_radius, 
            "amenities_radius": amenities_radius
        }
        try:
            easting, northing = convert_to_british_grid(lat, lon)
            result["easting"] = easting
            result["northing"] = northing
            result["required_kva"] = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
            
            elevation = get_elevation_data(lat, lon)
            result["elevation"] = elevation
            
            result["aerial_view_url"] = get_aerial_view_url(lat, lon)
            
            # PRIORITY 1: Get address and postcode from Google Geocoding API (PRIMARY SOURCE)
            geo = get_geocode_details(lat, lon)
            result.update({k: geo.get(k, "N/A") for k in ["street", "street_number", "neighbourhood", 
                          "city", "county", "region", "country", "formatted_address", "postcode"]})
            
            # Store Google's postcode separately to ensure it's not overwritten
            google_postcode = geo.get("postcode", "N/A")
            
            # PRIORITY 2: Get UK administrative data from postcodes.io (ONLY for ward, district, etc.)
            postcode_data = get_postcode_info(lat, lon)
            # Only update UK administrative fields, NOT the postcode or address
            result["ward"] = postcode_data["admin_ward"]
            result["district"] = postcode_data["admin_district"]
            result["admin_county"] = postcode_data["admin_county"]
            result["parish"] = postcode_data["parish"]
            result["parliamentary_constituency"] = postcode_data["parliamentary_constituency"]
            result["ccg"] = postcode_data["ccg"]
            result["ced"] = postcode_data["ced"]
            result["nuts"] = postcode_data["nuts"]
            result["lsoa"] = postcode_data["lsoa"]
            result["msoa"] = postcode_data["msoa"]
            result["postcode_region"] = postcode_data["region"]
            result["postcode_country"] = postcode_data["country"]
            
            # CRITICAL: Always keep Google's postcode as the final value
            result["postcode"] = google_postcode

            traffic = get_tomtom_traffic(lat, lon)
            result.update({"traffic_speed": traffic["speed"], "traffic_freeflow": traffic["freeFlow"],
                          "traffic_congestion": traffic["congestion"]})

            amenities_data = get_nearby_amenities(lat, lon, amenities_radius)
            result.update({"amenities": amenities_data["summary"], "amenities_summary": amenities_data["summary"],
                          "amenities_counts": amenities_data["counts"], 
                          "amenities_proportions": amenities_data["proportions"],
                          "amenities_total": amenities_data["total_found"]})

            ev_stations = get_ev_charging_stations(lat, lon, competitor_radius)
            result.update({"competitor_ev_count": len(ev_stations),
                          "competitor_ev_names": "; ".join([s["name"] for s in ev_stations]) if ev_stations else "None",
                          "ev_stations_details": ev_stations})

            road_info = get_road_info_google_roads(lat, lon)
            result.update({k: road_info.get(k, "Unknown") for k in ["snapped_road_name", "snapped_road_type",
                          "nearest_road_name", "nearest_road_type", "place_id"]})

            sv = get_street_view_data(lat, lon)
            result.update({"street_view_image_urls": sv.get("image_urls", {}),
                          "street_view_maps_link": sv.get("maps_link"),
                          "has_street_view": sv.get("has_street_view", False),
                          "google_maps_link": google_maps_search_link(lat, lon),
                          "google_maps_dir_link": google_maps_dir_link(lat, lon)})

        except Exception as e:
            st.warning(f"Error processing some data for site {lat}, {lon}: {e}")
        return result

# MAP FUNCTIONS

def add_google_traffic_layer(m):
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Traffic", overlay=True, control=True).add_to(m)

def add_google_satellite_layers(m):
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Satellite", overlay=False, control=True, show=False).add_to(m)
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=y&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Hybrid", overlay=False, control=True, show=False).add_to(m)

def create_single_map(site, show_traffic=False, show_competitors=True):
    m = folium.Map(location=[site["latitude"], site["longitude"]], zoom_start=15,
                  tiles="OpenStreetMap", attr="OpenStreetMap")
    
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Google Maps", overlay=False, control=True, show=True).add_to(m)
    add_google_satellite_layers(m)

    popup_content = f"""
    <b>📍 {site.get('formatted_address', 'Unknown Address')}</b><br>
    <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
    <b>📏 Elevation:</b> {site.get('elevation','N/A')} m<br>
    <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
    <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
    <b>⚡ Competitor EVs:</b> {site.get('competitor_ev_count', 0)}<br>
    <b>🏪 Nearby:</b> {site.get('amenities_summary','N/A')[:100]}{'...' if len(str(site.get('amenities_summary',''))) > 100 else ''}<br>
    <a href="{site.get('google_maps_link','')}" target="_blank">🗺️ Open in Google Maps</a> &nbsp;|&nbsp;
    <a href="{site.get('street_view_maps_link','')}" target="_blank">🚶 Open Street View</a>
    """
    folium.Marker([site["latitude"], site["longitude"]], popup=folium.Popup(popup_content, max_width=350),
                 tooltip="🔋 EV Charging Site", icon=folium.Icon(color="pink", icon="bolt", prefix="fa")).add_to(m)

    if show_competitors:
        for station in site.get('ev_stations_details', []):
            try:
                if station.get('latitude') and station.get('longitude'):
                    ev_popup = f"""
                    <b>⚡ {station.get('name', 'Unknown EV Station')}</b><br>
                    <b>Rating:</b> {station.get('rating', 'N/A')}<br>
                    <b>Address:</b> {station.get('address', 'N/A')}<br>
                    <b>Phone:</b> {station.get('phone', 'N/A')}<br>
                    <a href="{google_maps_search_link(station['latitude'], station['longitude'])}" target="_blank">🗺️ Open in Google Maps</a>
                    """
                    folium.Marker([station['latitude'], station['longitude']], popup=folium.Popup(ev_popup, max_width=300),
                                tooltip=f"⚡ Competitor: {station.get('name', 'EV Station')}",
                                icon=folium.Icon(color="red", icon="flash", prefix="fa")).add_to(m)
            except:
                continue

    if show_traffic:
        add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_sites_only_map(sites, show_traffic=False):
    if not sites:
        return None
    valid_sites = [s for s in sites if s.get("latitude") and s.get("longitude")]
    if not valid_sites:
        return None
    center_lat = sum(s["latitude"] for s in valid_sites) / len(valid_sites)
    center_lon = sum(s["longitude"] for s in valid_sites) / len(valid_sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="OpenStreetMap", attr="OpenStreetMap")
    
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Google Maps", overlay=False, control=True, show=True).add_to(m)
    add_google_satellite_layers(m)

    for i, site in enumerate(valid_sites):
        popup_content = f"""
        <b>📍 Site {i+1}:</b> {site.get('formatted_address','Unknown Address')}<br>
        <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
        <b>📏 Elevation:</b> {site.get('elevation','N/A')} m<br>
        <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
        <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
        <b>🏪 Nearby:</b> {site.get('amenities_summary','N/A')[:100]}{'...' if len(str(site.get('amenities_summary',''))) > 100 else ''}<br>
        <a href="{site.get('google_maps_link','')}" target="_blank">🗺️ Open in Google Maps</a> &nbsp;|&nbsp;
        <a href="{site.get('street_view_maps_link','')}" target="_blank">🚶 Open Street View</a>
        """
        folium.Marker([site["latitude"], site["longitude"]], popup=folium.Popup(popup_content, max_width=350),
                     tooltip=f"🔋 EV Site {i+1}", icon=folium.Icon(color="pink", icon="bolt", prefix="fa")).add_to(m)
    if show_traffic:
        add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites, show_traffic=False):
    if not sites:
        return None
    valid_sites = [s for s in sites if s.get("latitude") and s.get("longitude")]
    if not valid_sites:
        return None
    center_lat = sum(s["latitude"] for s in valid_sites) / len(valid_sites)
    center_lon = sum(s["longitude"] for s in valid_sites) / len(valid_sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="OpenStreetMap", attr="OpenStreetMap")
    
    folium.TileLayer(tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
                    attr="Google", name="Google Maps", overlay=False, control=True, show=True).add_to(m)
    add_google_satellite_layers(m)

    for i, site in enumerate(valid_sites):
        popup_content = f"""
        <b>📍 Site {i+1}:</b> {site.get('formatted_address','Unknown Address')}<br>
        <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
        <b>📏 Elevation:</b> {site.get('elevation','N/A')} m<br>
        <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
        <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
        <b>⚡ Competitor EVs:</b> {site.get('competitor_ev_count', 0)}<br>
        <b>🏪 Nearby:</b> {site.get('amenities_summary','N/A')[:100]}{'...' if len(str(site.get('amenities_summary',''))) > 100 else ''}<br>
        <a href="{site.get('google_maps_link','')}" target="_blank">🗺️ Open in Google Maps</a> &nbsp;|&nbsp;
        <a href="{site.get('street_view_maps_link','')}" target="_blank">🚶 Open Street View</a>
        """
        folium.Marker([site["latitude"], site["longitude"]], popup=folium.Popup(popup_content, max_width=350),
                     tooltip=f"🔋 EV Site {i+1}", icon=folium.Icon(color="pink", icon="bolt", prefix="fa")).add_to(m)

        for station in site.get('ev_stations_details', []):
            try:
                if station.get('latitude') and station.get('longitude'):
                    ev_popup = f"""
                    <b>⚡ {station.get('name', 'Unknown EV Station')}</b><br>
                    <b>Near Site:</b> {i+1}<br>
                    <b>Rating:</b> {station.get('rating', 'N/A')}<br>
                    <b>Address:</b> {station.get('address', 'N/A')}<br>
                    <b>Phone:</b> {station.get('phone', 'N/A')}<br>
                    <a href="{google_maps_search_link(station['latitude'], station['longitude'])}" target="_blank">🗺️ Open in Google Maps</a>
                    """
                    folium.Marker([station['latitude'], station['longitude']], popup=folium.Popup(ev_popup, max_width=300),
                                tooltip=f"⚡ Competitor: {station.get('name', 'EV Station')}",
                                icon=folium.Icon(color="red", icon="flash", prefix="fa")).add_to(m)
            except:
                continue
    if show_traffic:
        add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

# STREAMLIT APP
st.set_page_config(page_title="EV Site Selection Guide", page_icon="🔋", layout="wide")
st.title("🔋Believ Site Selection Guide")
st.markdown("*Comprehensive site guide for EV charging infrastructure planning*")

with st.sidebar:
    st.header("⚙️ Settings")
    st.subheader("Charger Power Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22, min_value=1, max_value=200, 
                              help="Power rating for fast chargers. Please use 31kW for Etrel chargers")
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60, min_value=1, max_value=350, 
                               help="Power rating for rapid chargers")
    ultra_kw = st.number_input("Ultra Rapid Charger Power (kW)", value=150, min_value=1, max_value=400, 
                               help="Power rating for ultra rapid chargers")

    st.subheader("Radius Settings")
    competitor_radius = st.number_input("Competitor Search Radius (m)", value=1000, min_value=100, 
                                       max_value=5000, step=100, help="Radius to search for nearby EV charging competitors")
    amenities_radius = st.number_input("Amenities Search Radius (m)", value=500, min_value=100, 
                                      max_value=2000, step=50, help="Radius to search for nearby amenities")

    st.subheader("Map Settings")
    show_traffic_single = st.checkbox("Show Traffic Layer (Single Site)", value=False)
    show_traffic_batch = st.checkbox("Show Traffic Layer (Batch Maps)", value=False)

tab1, tab2 = st.tabs(["📍 Single Site Analysis", "📁 Batch Processing"])

with tab1:
    st.subheader("🔍 Analyse Single Site")
    col1, col2 = st.columns(2)
    with col1:
        lat = st.text_input("Latitude", value="51.5074", help="Enter latitude in decimal degrees")
        lon = st.text_input("Longitude", value="-0.1278", help="Enter longitude in decimal degrees")
    with col2:
        fast = st.number_input("Fast Chargers", min_value=0, value=2, help=f"Number of {fast_kw}kW chargers")
        rapid = st.number_input("Rapid Chargers", min_value=0, value=2, help=f"Number of {rapid_kw}kW chargers")
        ultra = st.number_input("Ultra Chargers", min_value=0, value=1, help=f"Number of {ultra_kw}kW chargers")

    if st.button("🔍 Analyse Site", type="primary"):
        try:
            lat_float, lon_float = float(lat), float(lon)
            if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                st.error("Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180.")
            else:
                site = process_site(lat_float, lon_float, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw,
                                  competitor_radius=competitor_radius, amenities_radius=amenities_radius)
                st.session_state["single_site"] = site
                st.success("✅ Site analysis completed!")
        except ValueError:
            st.error("Invalid coordinate format. Please enter numeric values.")
        except Exception as e:
            st.error(f"Error analysing site: {e}")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]

        link_cols = st.columns(3)
        with link_cols[0]:
            if site.get("google_maps_link"):
                st.link_button("🗺️ Open in Google Maps", site["google_maps_link"])
        with link_cols[1]:
            if site.get("google_maps_dir_link"):
                st.link_button("📍 Directions", site["google_maps_dir_link"])
        with link_cols[2]:
            if site.get("street_view_maps_link"):
                st.link_button("🚶 Open Street View", site["street_view_maps_link"])

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Required kVA", site.get("required_kva", "N/A"))
        with col2:
            st.metric("Elevation (m)", site.get("elevation", "N/A"))
        with col3:
            st.metric("Road Type", site.get("snapped_road_type", "Unknown"))
        with col4:
            st.metric("Traffic Level", site.get("traffic_congestion", "N/A"))
        with col5:
            st.metric("Competitor EVs", site.get("competitor_ev_count", 0))

        st.subheader("📋 Detailed Site Information")
        detail_tabs = st.tabs(["🏠 Location", "🔌 Power", "🛣️ Road Info", "🚦 Traffic", 
                              "🏪 Amenities", "📊 Amenities Mix", "⚡ EV Competitors", 
                              "🗺️ Site Map", "🛰️ Aerial View", "🚶 Street View"])

        with detail_tabs[0]:
            st.write(f"**Address:** {site.get('formatted_address', 'N/A')}")
            st.write(f"**Postcode:** {site.get('postcode', 'N/A')}")
            st.write(f"**Ward:** {site.get('ward', 'N/A')}")
            st.write(f"**District:** {site.get('district', 'N/A')}")
            st.write(f"**County:** {site.get('admin_county', 'N/A')}")
            st.write(f"**Parish:** {site.get('parish', 'N/A')}")
            st.write(f"**Parliamentary Constituency:** {site.get('parliamentary_constituency', 'N/A')}")
            st.write(f"**CCG:** {site.get('ccg', 'N/A')}")
            st.write(f"**CED:** {site.get('ced', 'N/A')}")
            st.write(f"**NUTS:** {site.get('nuts', 'N/A')}")
            st.write(f"**LSOA:** {site.get('lsoa', 'N/A')}")
            st.write(f"**MSOA:** {site.get('msoa', 'N/A')}")
            st.write(f"**Region:** {site.get('postcode_region', 'N/A')}")
            st.write(f"**Country:** {site.get('postcode_country', 'N/A')}")
            st.write(f"**Elevation:** {site.get('elevation', 'N/A')} meters above sea level")
            st.write(f"**British Grid:** {site.get('easting', 'N/A')}, {site.get('northing', 'N/A')}")

        with detail_tabs[1]:
            st.write(f"**Fast Chargers:** {site.get('fast_chargers', 0)} × {fast_kw}kW")
            st.write(f"**Rapid Chargers:** {site.get('rapid_chargers', 0)} × {rapid_kw}kW")
            st.write(f"**Ultra Chargers:** {site.get('ultra_chargers', 0)} × {ultra_kw}kW")
            st.write(f"**Total Required kVA:** {site.get('required_kva', 'N/A')}")

        with detail_tabs[2]:
            st.write(f"**Snapped Road Name:** {site.get('snapped_road_name', 'Unknown')}")
            st.write(f"**Snapped Road Type:** {site.get('snapped_road_type', 'Unknown')}")
            st.write(f"**Nearest Road Name:** {site.get('nearest_road_name', 'Unknown')}")
            st.write(f"**Nearest Road Type:** {site.get('nearest_road_type', 'Unknown')}")
            if site.get('place_id'):
                st.write(f"**Google Place ID:** {site['place_id']}")

        with detail_tabs[3]:
            st.write(f"**Congestion Level:** {site.get('traffic_congestion', 'N/A')}")
            if site.get('traffic_speed'):
                st.write(f"**Current Speed:** {site['traffic_speed']} mph")
                st.write(f"**Free Flow Speed:** {site['traffic_freeflow']} mph")

        with detail_tabs[4]:
            st.write(f"**Nearby Amenities:** {site.get('amenities_summary', 'N/A')}")

        with detail_tabs[5]:
            st.write("**Amenities proportions (% of all nearby results found):**")
            props = site.get("amenities_proportions", {})
            if props:
                prop_df = pd.DataFrame([{"Amenity": k.replace("_", " ").title(), "Proportion %": v}
                                       for k, v in props.items()]).sort_values("Proportion %", ascending=False)
                st.dataframe(prop_df, use_container_width=True)
            st.caption(f"Total amenities found: {site.get('amenities_total', 0)} within {site.get('amenities_radius', 0)}m")

        with detail_tabs[6]:
            st.write(f"**Number of Competitor EV Stations:** {site.get('competitor_ev_count', 0)}")
            st.write(f"**Competitor Names:** {site.get('competitor_ev_names', 'None')}")
            ev_stations = site.get('ev_stations_details', [])
            if ev_stations:
                col_comp1, col_comp2 = st.columns(2)
                with col_comp1:
                    st.subheader("🔍 Detailed Competitor Information")
                    for i, station in enumerate(ev_stations):
                        charger_type = classify_charger_power(station.get('name', ''), station.get('rating'))
                        with st.expander(f"⚡ {station.get('name', f'EV Station {i+1}')} - {charger_type}"):
                            st.write(f"**Charger Type:** {charger_type}")
                            st.write(f"**Rating:** {station.get('rating', 'N/A')}")
                            st.write(f"**Address:** {station.get('address', 'N/A')}")
                            st.write(f"**Phone:** {station.get('phone', 'N/A')}")
                            st.write(f"**Coordinates:** {station.get('latitude', 'N/A')}, {station.get('longitude', 'N/A')}")
                            if station.get('latitude') and station.get('longitude'):
                                st.link_button("🗺️ Open in Google Maps", 
                                             google_maps_search_link(station['latitude'], station['longitude']))
                            if station.get('photo_url'):
                                try:
                                    st.image(station['photo_url'], caption=station.get('name', 'EV Station'), width=220)
                                except:
                                    st.write("📷 Photo unavailable")
                            else:
                                st.write("📷 No photo available")
                with col_comp2:
                    st.subheader("📊 Competitor Market Share")
                    competitor_brands = {}
                    charger_types = {}
                    for station in ev_stations:
                        name = station.get('name', 'Unknown')
                        competitor_brands[extract_brand_name(name)] = competitor_brands.get(extract_brand_name(name), 0) + 1
                        charger_type = classify_charger_power(name, station.get('rating'))
                        charger_types[charger_type] = charger_types.get(charger_type, 0) + 1
                    
                    if competitor_brands:
                        brand_df = pd.DataFrame([{"Brand": k, "Count": v, "Percentage": f"{(v/len(ev_stations)*100):.1f}%"}
                                                for k, v in sorted(competitor_brands.items(), key=lambda x: x[1], reverse=True)])
                        st.dataframe(brand_df, use_container_width=True)
                        bar_chart = create_bar_chart_data(competitor_brands)
                        if bar_chart:
                            st.image(f"data:image/png;base64,{bar_chart}")
                    
                    if charger_types:
                        st.write("**Charger Type Distribution:**")
                        charger_df = pd.DataFrame([{"Charger Type": k, "Count": v, "Percentage": f"{(v/len(ev_stations)*100):.1f}%"}
                                                  for k, v in sorted(charger_types.items(), key=lambda x: x[1], reverse=True)])
                        st.dataframe(charger_df, use_container_width=True)

        with detail_tabs[7]:
            st.write("**Interactive Site Map:**")
            map_cols = st.columns([3, 2])
            with map_cols[0]:
                map_view_type = st.radio("Select Map View:", ["Site Only", "Site + Competitors"], 
                                        horizontal=True, key="single_site_map_toggle")
            with map_cols[1]:
                use_embed_map = st.checkbox("Use Google Maps Embed", value=False, key="single_embed_toggle",
                                           help="Toggle between interactive Folium map and Google Maps Embed")
            
            if use_embed_map:
                st.components.v1.html(get_embed_map_html(site["latitude"], site["longitude"], mode="place"), height=450)
            else:
                show_competitors_map = (map_view_type == "Site + Competitors")
                site_map = create_single_map(site, show_traffic_single, show_competitors=show_competitors_map)
                st_folium(site_map, width=700, height=500)

        with detail_tabs[8]:
            st.write("**Satellite Aerial View:**")
            if site.get("aerial_view_url"):
                st.image(site["aerial_view_url"], caption=f"Aerial View: {site.get('formatted_address', 'Site Location')}", 
                        use_container_width=True)
                st.caption("High-resolution satellite imagery from Google Maps")
                
                use_embed_aerial = st.checkbox("Use Interactive Google Maps Embed (Satellite)", value=False, 
                                              key="single_aerial_embed", help="View in interactive satellite mode")
                if use_embed_aerial:
                    st.components.v1.html(get_embed_map_html(site["latitude"], site["longitude"], mode="satellite"), height=450)
            else:
                st.info("Aerial view not available for this location.")

        with detail_tabs[9]:
            if site.get("has_street_view") and site.get("street_view_image_urls"):
                st.write("**Street View - 4 Directional Views:**")
                image_urls = site.get("street_view_image_urls", {})
                row1_col1, row1_col2 = st.columns(2)
                row2_col1, row2_col2 = st.columns(2)
                directions = list(image_urls.items())
                if len(directions) >= 1:
                    with row1_col1:
                        st.image(directions[0][1], caption=directions[0][0], use_container_width=True)
                if len(directions) >= 2:
                    with row1_col2:
                        st.image(directions[1][1], caption=directions[1][0], use_container_width=True)
                if len(directions) >= 3:
                    with row2_col1:
                        st.image(directions[2][1], caption=directions[2][0], use_container_width=True)
                if len(directions) >= 4:
                    with row2_col2:
                        st.image(directions[3][1], caption=directions[3][0], use_container_width=True)
            else:
                st.info("Street View is not available for this location.")
            if site.get("street_view_maps_link"):
                st.link_button("🚶 Open Interactive Street View in Google Maps", site["street_view_maps_link"])

        st.subheader("📥 Export Data")
        export_data = {
            "Latitude": site["latitude"], 
            "Longitude": site["longitude"],
            "Easting": site.get("easting", "N/A"), 
            "Northing": site.get("northing", "N/A"),
            "Elevation (m)": site.get("elevation", "N/A"),
            "Postcode": site.get("postcode", "N/A"),
            "Address": site.get("formatted_address", "N/A"),
            "Street": site.get("street", "N/A"),
            "Street Number": site.get("street_number", "N/A"),
            "City": site.get("city", "N/A"),
            "County": site.get("county", "N/A"),
            "Region": site.get("region", "N/A"),
            "Country": site.get("country", "N/A"),
            "Ward": site.get("ward", "N/A"), 
            "District": site.get("district", "N/A"),
            "Admin County": site.get("admin_county", "N/A"), 
            "Parish": site.get("parish", "N/A"),
            "Parliamentary Constituency": site.get("parliamentary_constituency", "N/A"),
            "CCG": site.get("ccg", "N/A"), 
            "CED": site.get("ced", "N/A"),
            "NUTS": site.get("nuts", "N/A"), 
            "LSOA": site.get("lsoa", "N/A"),
            "MSOA": site.get("msoa", "N/A"), 
            "Postcode Region": site.get("postcode_region", "N/A"),
            "Postcode Country": site.get("postcode_country", "N/A"),
            "Fast Chargers": site.get("fast_chargers", 0), 
            "Rapid Chargers": site.get("rapid_chargers", 0),
            "Ultra Chargers": site.get("ultra_chargers", 0), 
            "Required kVA": site.get("required_kva", "N/A"),
            "Road Name": site.get("snapped_road_name", "Unknown"), 
            "Road Type": site.get("snapped_road_type", "Unknown"),
            "Traffic Congestion": site.get("traffic_congestion", "N/A"),
            "Competitor EV Count": site.get("competitor_ev_count", 0),
            "Competitor Names": site.get("competitor_ev_names", "None"),
            "Amenities Total": site.get("amenities_total", 0),
            "Amenities Summary": site.get("amenities_summary", "N/A"),
            "Google Maps Link": site.get("google_maps_link", ""),
            "Street View Link": site.get("street_view_maps_link", ""),
            "Aerial View Link": site.get("aerial_view_url", "")
        }
        df_export = pd.DataFrame([export_data])
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download Site Data as CSV", data=csv,
                          file_name=f"ev_site_{site['latitude']}_{site['longitude']}.csv", mime="text/csv")

with tab2:
    st.subheader("📁 Batch Site Processing")
    st.write("Upload a CSV file with columns: latitude, longitude, fast_chargers, rapid_chargers, ultra_chargers")
    
    template_csv = create_csv_template()
    st.download_button(
        label="📥 Download Template CSV",
        data=template_csv,
        file_name="ev_sites_template.csv",
        mime="text/csv",
        help="Download a sample CSV template with the correct format"
    )
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        try:
            df_input = pd.read_csv(uploaded_file)
            required_cols = ["latitude", "longitude", "fast_chargers", "rapid_chargers", "ultra_chargers"]
            
            if not all(col in df_input.columns for col in required_cols):
                st.error(f"CSV must contain columns: {', '.join(required_cols)}")
            else:
                st.write(f"✅ Loaded {len(df_input)} sites from CSV")
                st.dataframe(df_input.head(), use_container_width=True)
                
                if st.button("🚀 Process All Sites", type="primary"):
                    results = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for idx, row in df_input.iterrows():
                        status_text.text(f"Processing site {idx + 1} of {len(df_input)}...")
                        try:
                            site_result = process_site(float(row["latitude"]), float(row["longitude"]),
                                                      int(row["fast_chargers"]), int(row["rapid_chargers"]),
                                                      int(row["ultra_chargers"]), fast_kw, rapid_kw, ultra_kw,
                                                      competitor_radius=competitor_radius, amenities_radius=amenities_radius)
                            results.append(site_result)
                        except Exception as e:
                            st.warning(f"Error processing site {idx + 1}: {e}")
                        progress_bar.progress((idx + 1) / len(df_input))
                    
                    status_text.text("✅ Processing complete!")
                    st.session_state["batch_results"] = results
                    st.success(f"Successfully processed {len(results)} sites!")
        except Exception as e:
            st.error(f"Error reading CSV file: {e}")
    
    if "batch_results" in st.session_state and st.session_state["batch_results"]:
        results = st.session_state["batch_results"]
        
        st.subheader("📊 Batch Results Summary")
        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("Total Sites", len(results))
        with summary_cols[1]:
            total_kva = sum(r.get("required_kva", 0) for r in results)
            st.metric("Total kVA", f"{total_kva:.2f}")
        with summary_cols[2]:
            total_competitors = sum(r.get("competitor_ev_count", 0) for r in results)
            st.metric("Total Competitors", total_competitors)
        with summary_cols[3]:
            avg_competitors = total_competitors / len(results) if results else 0
            st.metric("Avg Competitors/Site", f"{avg_competitors:.1f}")
        
        st.subheader("🗺️ All Sites Map")
        map_cols = st.columns([3, 2])
        with map_cols[0]:
            map_type = st.radio("Select Map Type:", ["Sites Only", "Sites with Competitors"], horizontal=True)
        with map_cols[1]:
            use_embed_batch = st.checkbox("Use Google Maps Embed", value=False, key="batch_embed_toggle",
                                         help="Toggle between interactive Folium map and Google Maps Embed")
        
        if use_embed_batch:
            if results:
                first_site = results[0]
                st.components.v1.html(get_embed_map_html(first_site["latitude"], first_site["longitude"], mode="place"), height=600)
                st.info("Google Maps Embed shows the first site location. Use Folium map to view all sites together.")
        else:
            if map_type == "Sites Only":
                batch_map = create_sites_only_map(results, show_traffic_batch)
            else:
                batch_map = create_batch_map(results, show_traffic_batch)
            
            if batch_map:
                st_folium(batch_map, width=900, height=600)
        
        st.subheader("🛰️ Aerial Views (All Sites)")
        show_aerial_views = st.checkbox("Show Aerial Views for All Sites", value=False, key="batch_aerial_toggle")
        
        if show_aerial_views:
            st.info("Displaying satellite imagery for all processed sites")
            cols_per_row = 2
            for i in range(0, len(results), cols_per_row):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(results):
                        site = results[i + j]
                        with cols[j]:
                            st.write(f"**Site {i+j+1}:** {site.get('formatted_address', 'Unknown')}")
                            if site.get("aerial_view_url"):
                                st.image(site["aerial_view_url"], use_container_width=True)
                            else:
                                st.info("Aerial view not available")
        
        st.subheader("📥 Export Batch Results")
        export_rows = []
        for site in results:
            export_rows.append({
                "Latitude": site["latitude"], 
                "Longitude": site["longitude"],
                "Easting": site.get("easting", "N/A"), 
                "Northing": site.get("northing", "N/A"),
                "Elevation (m)": site.get("elevation", "N/A"),
                "Postcode": site.get("postcode", "N/A"),
                "Address": site.get("formatted_address", "N/A"),
                "Street": site.get("street", "N/A"),
                "Street Number": site.get("street_number", "N/A"),
                "City": site.get("city", "N/A"),
                "County": site.get("county", "N/A"),
                "Region": site.get("region", "N/A"),
                "Country": site.get("country", "N/A"),
                "Ward": site.get("ward", "N/A"), 
                "District": site.get("district", "N/A"),
                "Admin County": site.get("admin_county", "N/A"), 
                "Parish": site.get("parish", "N/A"),
                "Parliamentary Constituency": site.get("parliamentary_constituency", "N/A"),
                "CCG": site.get("ccg", "N/A"), 
                "CED": site.get("ced", "N/A"),
                "NUTS": site.get("nuts", "N/A"), 
                "LSOA": site.get("lsoa", "N/A"),
                "MSOA": site.get("msoa", "N/A"), 
                "Postcode Region": site.get("postcode_region", "N/A"),
                "Postcode Country": site.get("postcode_country", "N/A"),
                "Fast Chargers": site.get("fast_chargers", 0), 
                "Rapid Chargers": site.get("rapid_chargers", 0),
                "Ultra Chargers": site.get("ultra_chargers", 0), 
                "Required kVA": site.get("required_kva", "N/A"),
                "Road Name": site.get("snapped_road_name", "Unknown"), 
                "Road Type": site.get("snapped_road_type", "Unknown"),
                "Traffic Congestion": site.get("traffic_congestion", "N/A"),
                "Competitor EV Count": site.get("competitor_ev_count", 0),
                "Competitor Names": site.get("competitor_ev_names", "None"),
                "Amenities Total": site.get("amenities_total", 0),
                "Amenities Summary": site.get("amenities_summary", "N/A"),
                "Google Maps Link": site.get("google_maps_link", ""),
                "Street View Link": site.get("street_view_maps_link", ""),
                "Aerial View Link": site.get("aerial_view_url", "")
            })
        
        df_batch_export = pd.DataFrame(export_rows)
        csv_batch = df_batch_export.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download Batch Results as CSV", data=csv_batch,
                          file_name="ev_batch_site_analysis.csv", mime="text/csv")
        
        st.subheader("📈 Batch Analysis")
        analysis_tabs = st.tabs(["Road Type Distribution", "Traffic Analysis", "Competitor Analysis", 
                                 "Amenities Analysis", "Elevation Analysis"])
        
        with analysis_tabs[0]:
            road_types = {}
            for site in results:
                road_type = site.get("snapped_road_type", "Unknown")
                road_types[road_type] = road_types.get(road_type, 0) + 1
            
            road_df = pd.DataFrame([
                {"Road Type": k, "Count": v, "Percentage": f"{(v/len(results)*100):.1f}%"}
                for k, v in sorted(road_types.items(), key=lambda x: x[1], reverse=True)
            ])
            st.dataframe(road_df, use_container_width=True)
        
        with analysis_tabs[1]:
            traffic_levels = {}
            for site in results:
                traffic = site.get("traffic_congestion", "N/A")
                traffic_levels[traffic] = traffic_levels.get(traffic, 0) + 1
            
            traffic_df = pd.DataFrame([
                {"Traffic Level": k, "Count": v, "Percentage": f"{(v/len(results)*100):.1f}%"}
                for k, v in sorted(traffic_levels.items(), key=lambda x: x[1], reverse=True)
            ])
            st.dataframe(traffic_df, use_container_width=True)
        
        with analysis_tabs[2]:
            st.write("**Competitor Statistics:**")
            comp_stats_col1, comp_stats_col2, comp_stats_col3 = st.columns(3)
            with comp_stats_col1:
                sites_with_comps = sum(1 for s in results if s.get("competitor_ev_count", 0) > 0)
                st.metric("Sites with Competitors", sites_with_comps)
            with comp_stats_col2:
                sites_without_comps = len(results) - sites_with_comps
                st.metric("Sites without Competitors", sites_without_comps)
            with comp_stats_col3:
                max_comps = max((s.get("competitor_ev_count", 0) for s in results), default=0)
                st.metric("Max Competitors at One Site", max_comps)
            
            all_brands = {}
            all_charger_types = {}
            for site in results:
                for station in site.get('ev_stations_details', []):
                    brand = extract_brand_name(station.get('name', 'Unknown'))
                    all_brands[brand] = all_brands.get(brand, 0) + 1
                    
                    charger_type = classify_charger_power(station.get('name', ''), station.get('rating'))
                    all_charger_types[charger_type] = all_charger_types.get(charger_type, 0) + 1
            
            if all_brands:
                st.write("**Overall Competitor Brand Distribution:**")
                brand_df = pd.DataFrame([
                    {"Brand": k, "Total Count": v, "Percentage": f"{(v/sum(all_brands.values())*100):.1f}%"}
                    for k, v in sorted(all_brands.items(), key=lambda x: x[1], reverse=True)
                ])
                st.dataframe(brand_df, use_container_width=True)
                
                bar_chart = create_bar_chart_data(all_brands)
                if bar_chart:
                    st.image(f"data:image/png;base64,{bar_chart}")
            
            if all_charger_types:
                st.write("**Overall Charger Type Distribution:**")
                charger_type_df = pd.DataFrame([
                    {"Charger Type": k, "Total Count": v, "Percentage": f"{(v/sum(all_charger_types.values())*100):.1f}%"}
                    for k, v in sorted(all_charger_types.items(), key=lambda x: x[1], reverse=True)
                ])
                st.dataframe(charger_type_df, use_container_width=True)
                
                charger_bar_chart = create_bar_chart_data(all_charger_types)
                if charger_bar_chart:
                    st.image(f"data:image/png;base64,{charger_bar_chart}")
        
        with analysis_tabs[3]:
            st.write("**Average Amenities per Site Type:**")
            avg_amenities = {t: 0 for t in PLACE_TYPES_FOR_STATS}
            for site in results:
                counts = site.get("amenities_counts", {})
                for t in PLACE_TYPES_FOR_STATS:
                    avg_amenities[t] += counts.get(t, 0)
            
            for t in avg_amenities:
                avg_amenities[t] = round(avg_amenities[t] / len(results), 2) if results else 0
            
            amenities_df = pd.DataFrame([
                {"Amenity Type": k.replace("_", " ").title(), "Average Count per Site": v}
                for k, v in sorted(avg_amenities.items(), key=lambda x: x[1], reverse=True)
            ])
            st.dataframe(amenities_df, use_container_width=True)
            
            st.write("**Total Amenities Distribution:**")
            total_amenities_list = [s.get("amenities_total", 0) for s in results]
            if total_amenities_list:
                avg_col, max_col, min_col = st.columns(3)
                with avg_col:
                    st.metric("Average Total Amenities per Site", f"{sum(total_amenities_list)/len(total_amenities_list):.1f}")
                with max_col:
                    st.metric("Max Amenities at One Site", max(total_amenities_list))
                with min_col:
                    st.metric("Min Amenities at One Site", min(total_amenities_list))
        
        with analysis_tabs[4]:
            st.write("**Elevation Analysis:**")
            elevation_values = [s.get("elevation") for s in results if s.get("elevation") != "N/A" and s.get("elevation") is not None]
            
            if elevation_values:
                elev_col1, elev_col2, elev_col3 = st.columns(3)
                with elev_col1:
                    st.metric("Average Elevation", f"{sum(elevation_values)/len(elevation_values):.2f} m")
                with elev_col2:
                    st.metric("Max Elevation", f"{max(elevation_values):.2f} m")
                with elev_col3:
                    st.metric("Min Elevation", f"{min(elevation_values):.2f} m")
                
                st.write("**Elevation by Site:**")
                elevation_df = pd.DataFrame([
                    {"Site": i+1, "Address": s.get("formatted_address", "Unknown")[:50], 
                     "Elevation (m)": s.get("elevation", "N/A")}
                    for i, s in enumerate(results)
                ])
                st.dataframe(elevation_df, use_container_width=True)
            else:
                st.info("No elevation data available for the processed sites.")

st.markdown("---")
st.markdown("**🔋 Believ Site Selection Guide** | Built with Streamlit | © 2025")
