import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time
import logging

# ==============================
# API KEYS
# ==============================
GOOGLE_API_KEY = st.secrets["google_api_key"]
TOMTOM_API_KEY = st.secrets.get("tomtom_api_key", "")

# ==============================
# UTILITY FUNCTIONS
# ==============================

def extract_brand_name(station_name):
    """Extract brand name from station name"""
    if not station_name or station_name == "Unknown":
        return "Unknown"
    
    # Common EV charging brands
    brands = {
        'tesla': 'Tesla',
        'supercharger': 'Tesla',
        'chargepoint': 'ChargePoint',
        'ionity': 'Ionity',
        'pod point': 'Pod Point',
        'podpoint': 'Pod Point',
        'ecotricity': 'Ecotricity',
        'bp pulse': 'BP Pulse',
        'bp': 'BP Pulse',
        'shell': 'Shell Recharge',
        'gridserve': 'Gridserve',
        'instavolt': 'InstaVolt',
        'osprey': 'Osprey Charging',
        'charge your car': 'Charge Your Car',
        'rolec': 'Rolec',
        'chargemaster': 'Chargemaster',
        'polar': 'Polar Network',
        'source london': 'Source London',
        'ev-box': 'EVBox',
        'fastned': 'Fastned',
        'mer': 'MER',
        'newmotion': 'NewMotion'
    }
    
    name_lower = station_name.lower()
    
    # Check for brand matches
    for brand_key, brand_name in brands.items():
        if brand_key in name_lower:
            return brand_name
    
    # If no known brand found, try to extract first word(s)
    words = station_name.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    elif len(words) == 1:
        return words[0]
    
    return "Other"

def create_pie_chart_data(brands_dict):
    """Create pie chart data for market share analysis"""
    if not brands_dict:
        return None
    
    try:
        import matplotlib.pyplot as plt
        import io
        import base64
        
        # Create the pie chart
        fig, ax = plt.subplots(figsize=(8, 6))
        
        labels = list(brands_dict.keys())
        sizes = list(brands_dict.values())
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9']
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors[:len(labels)])
        
        # Enhance appearance
        ax.set_title('EV Charging Network Market Share', fontsize=14, fontweight='bold', pad=20)
        
        # Make percentage text bold and larger
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
        
        # Equal aspect ratio ensures that pie is drawn as a circle
        ax.axis('equal')
        
        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300, facecolor='white')
        buffer.seek(0)
        
        # Convert to base64 for display
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close(fig)
        
        return img_base64
    except Exception as e:
        st.warning(f"Could not create pie chart: {e}")
        return None

@st.cache_data
def get_postcode_info(lat, lon):
    """Get postcode information using postcodes.io API"""
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = r.json()
        if data.get("status") == 200 and data["result"]:
            res = data["result"][0]
            return res.get("postcode","N/A"), res.get("admin_ward","N/A"), res.get("admin_district","N/A")
    except Exception as e:
        st.warning(f"Postcode API error: {e}")
    return "N/A","N/A","N/A"

@st.cache_data
def get_geocode_details(lat, lon):
    """Get detailed geocoding information from Google Maps"""
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
                if "neighborhood" in types: details["neighborhood"]=c["long_name"]
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
def get_ev_charging_stations(lat, lon, radius=1000):
    """Get EV charging stations specifically"""
    ev_stations = []
    
    try:
        search_terms = [
            "electric vehicle charging station",
            "EV charging",
            "Tesla Supercharger",
            "ChargePoint",
            "Ionity"
        ]
        
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        all_results = []
        
        # Method 1: Type-based search
        type_params = {
            "location": f"{lat},{lon}",
            "radius": radius,
            "type": "gas_station",
            "keyword": "electric vehicle charging",
            "key": GOOGLE_API_KEY
        }
        
        response = requests.get(url, params=type_params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                all_results.extend(data.get("results", []))
        
        time.sleep(0.1)
        
        # Method 2: Keyword searches
        for term in search_terms:
            keyword_params = {
                "location": f"{lat},{lon}",
                "radius": radius,
                "keyword": term,
                "key": GOOGLE_API_KEY
            }
            
            response = requests.get(url, params=keyword_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    all_results.extend(data.get("results", []))
            
            time.sleep(0.1)
        
        # Remove duplicates based on place_id
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
                        "place_id": place_id,
                        "name": place.get("name", "Unknown"),
                        "latitude": location.get("lat"),
                        "longitude": location.get("lng"),
                        "geometry": geometry
                    }
        
        # Get detailed information for each EV station
        for place_id, basic_info in unique_places.items():
            try:
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {
                    "place_id": place_id,
                    "fields": "name,rating,formatted_address,photos,types,geometry,opening_hours,formatted_phone_number",
                    "key": GOOGLE_API_KEY
                }
                
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
                
            except Exception as e:
                st.warning(f"Error getting EV station details: {e}")
                if basic_info.get("latitude") and basic_info.get("longitude"):
                    ev_stations.append(basic_info)
    
    except Exception as e:
        st.warning(f"Error searching for EV stations: {e}")
    
    return ev_stations

@st.cache_data
def get_nearby_amenities(lat, lon, radius=500):
    """Get nearby amenities using Google Places API (excluding EV stations)"""
    amenities = []
    
    place_types = [
        "restaurant", "cafe", "shopping_mall", "supermarket", "hospital", 
        "pharmacy", "bank", "atm", "lodging", "gas_station"
    ]
    
    try:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        
        for place_type in place_types:
            params = {
                "location": f"{lat},{lon}",
                "radius": radius,
                "type": place_type,
                "key": GOOGLE_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK":
                    results = data.get("results", [])
                    
                    for place in results[:3]:
                        name = place.get("name", "Unknown")
                        rating = place.get("rating", "N/A")
                        
                        name_lower = name.lower()
                        ev_keywords = ["electric", "ev", "charging", "tesla", "chargepoint"]
                        if any(keyword in name_lower for keyword in ev_keywords):
                            continue
                        
                        display_type = place_type.replace("_", " ").title()
                        
                        amenity_info = f"{name} ({display_type})"
                        if rating != "N/A":
                            amenity_info += f" ⭐{rating}"
                            
                        amenities.append(amenity_info)
                
                elif data.get("status") == "ZERO_RESULTS":
                    continue
                else:
                    st.warning(f"Places API error for {place_type}: {data.get('status')}")
            
            else:
                st.warning(f"HTTP error {response.status_code} for {place_type}")
            
            time.sleep(0.1)
        
        return "; ".join(amenities[:15]) if amenities else "None nearby"
        
    except Exception as e:
        st.warning(f"Places API error: {e}")
        return f"Error retrieving amenities: {str(e)}"

@st.cache_data
def get_road_info_google_roads(lat, lon):
    """Get road information using Google Roads API"""
    road_info = {
        "snapped_road_name": "Unknown",
        "snapped_road_type": "Unknown",
        "nearest_road_name": "Unknown", 
        "nearest_road_type": "Unknown",
        "place_id": None
    }
    
    try:
        snap_url = "https://roads.googleapis.com/v1/snapToRoads"
        snap_params = {
            "path": f"{lat},{lon}",
            "interpolate": "true",
            "key": GOOGLE_API_KEY
        }
        
        snap_response = requests.get(snap_url, params=snap_params, timeout=10)
        
        if snap_response.status_code == 200:
            snap_data = snap_response.json()
            
            if "snappedPoints" in snap_data and snap_data["snappedPoints"]:
                snapped_point = snap_data["snappedPoints"][0]
                place_id = snapped_point.get("placeId")
                
                if place_id:
                    road_info["place_id"] = place_id
                    
                    place_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    place_params = {
                        "place_id": place_id,
                        "fields": "name,types,geometry,formatted_address",
                        "key": GOOGLE_API_KEY
                    }
                    
                    place_response = requests.get(place_url, params=place_params, timeout=10)
                    
                    if place_response.status_code == 200:
                        place_data = place_response.json()
                        
                        if place_data.get("status") == "OK":
                            result = place_data.get("result", {})
                            road_info["snapped_road_name"] = result.get("name", "Unknown Road")
                            
                            place_types = result.get("types", [])
                            road_info["snapped_road_type"] = classify_road_type(place_types, road_info["snapped_road_name"])
        
        # Fallback: Use reverse geocoding if APIs fail
        if road_info["snapped_road_name"] == "Unknown":
            try:
                geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
                geocode_params = {
                    "latlng": f"{lat},{lon}",
                    "key": GOOGLE_API_KEY
                }
                
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
                
            except Exception as e:
                st.warning(f"Geocoding fallback error: {e}")
            
    except Exception as e:
        st.warning(f"Google Roads API error: {e}")
    
    return road_info

def classify_road_type(place_types, road_name=""):
    """Classify road type based on Google Places API types and road name"""
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
    """Classify road type based on road name patterns (UK-focused)"""
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
    """Get coordinate transformer for British National Grid"""
    return Transformer.from_crs("epsg:4326","epsg:27700")

def convert_to_british_grid(lat, lon):
    """Convert WGS84 coordinates to British National Grid"""
    transformer = get_transformer()
    try:
        e, n = transformer.transform(lat, lon)
        return round(e), round(n)
    except Exception as e:
        st.warning(f"Coordinate transformation error: {e}")
        return None, None

def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    """Calculate required kVA capacity"""
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    return round(total_kw / 0.95, 2)

def get_tomtom_traffic(lat, lon):
    """Get traffic information from TomTom API"""
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
    """Process a single site and gather all information"""
    with st.spinner(f"Processing site at {lat}, {lon}..."):
        result = {
            "latitude": lat,
            "longitude": lon,
            "easting": None,
            "northing": None,
            "postcode": "N/A",
            "ward": "N/A",
            "district": "N/A",
            "street": "N/A",
            "street_number": "N/A",
            "neighborhood": "N/A",
            "city": "N/A",
            "county": "N/A",
            "region": "N/A",
            "country": "N/A",
            "formatted_address": "N/A",
            "fast_chargers": fast,
            "rapid_chargers": rapid,
            "ultra_chargers": ultra,
            "required_kva": 0,
            "traffic_speed": None,
            "traffic_freeflow": None,
            "traffic_congestion": "N/A",
            "amenities": "N/A",
            "snapped_road_name": "Unknown",
            "snapped_road_type": "Unknown",
            "nearest_road_name": "Unknown",
            "nearest_road_type": "Unknown",
            "place_id": None,
            "competitor_ev_count": 0,
            "competitor_ev_names": "None",
            "ev_stations_details": []
        }
        
        try:
            easting, northing = convert_to_british_grid(lat, lon)
            result["easting"] = easting
            result["northing"] = northing
            
            kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
            result["required_kva"] = kva
            
            postcode, ward, district = get_postcode_info(lat, lon)
            result["postcode"] = postcode
            result["ward"] = ward
            result["district"] = district
            
            geo = get_geocode_details(lat, lon)
            result.update({
                "street": geo.get("street", "N/A"),
                "street_number": geo.get("street_number", "N/A"),
                "neighborhood": geo.get("neighborhood", "N/A"),
                "city": geo.get("city", "N/A"),
                "county": geo.get("county", "N/A"),
                "region": geo.get("region", "N/A"),
                "country": geo.get("country", "N/A"),
                "formatted_address": geo.get("formatted_address", "N/A")
            })
            
            traffic = get_tomtom_traffic(lat, lon)
            result.update({
                "traffic_speed": traffic["speed"],
                "traffic_freeflow": traffic["freeFlow"],
                "traffic_congestion": traffic["congestion"]
            })
            
            amenities = get_nearby_amenities(lat, lon, amenities_radius)
            result["amenities"] = amenities
            
            ev_stations = get_ev_charging_stations(lat, lon, competitor_radius)
            ev_count = len(ev_stations)
            ev_names = [station["name"] for station in ev_stations]
            ev_names_str = "; ".join(ev_names) if ev_names else "None"
            
            result.update({
                "competitor_ev_count": ev_count,
                "competitor_ev_names": ev_names_str,
                "ev_stations_details": ev_stations,
                "competitor_radius": competitor_radius,
                "amenities_radius": amenities_radius
            })
            
            road_info = get_road_info_google_roads(lat, lon)
            result.update({
                "snapped_road_name": road_info.get("snapped_road_name", "Unknown"),
                "snapped_road_type": road_info.get("snapped_road_type", "Unknown"),
                "nearest_road_name": road_info.get("nearest_road_name", "Unknown"),
                "nearest_road_type": road_info.get("nearest_road_type", "Unknown"),
                "place_id": road_info.get("place_id")
            })
            
        except Exception as e:
            st.warning(f"Error processing some data for site {lat}, {lon}: {e}")
        
        return result

# ==============================
# MAP FUNCTIONS
# ==============================

def add_google_traffic_layer(m):
    """Add Google Traffic layer to folium map"""
    folium.TileLayer(
        tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Traffic",
        name="Traffic",
        overlay=True,
        control=True
    ).add_to(m)

def create_single_map(site, show_traffic=False):
    """Create a map for a single site"""
    m = folium.Map(
        location=[site["latitude"], site["longitude"]], 
        zoom_start=15,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", 
        attr="Google Maps"
    )
    
    popup_content = f"""
    <b>📍 {site.get('formatted_address', 'Unknown Address')}</b><br>
    <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
    <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
    <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
    <b>⚡ Competitor EVs:</b> {site.get('competitor_ev_count', 0)}<br>
    <b>🏪 Nearby:</b> {site.get('amenities','N/A')[:100]}{'...' if len(str(site.get('amenities',''))) > 100 else ''}
    """
    
    folium.Marker(
        [site["latitude"], site["longitude"]], 
        popup=folium.Popup(popup_content, max_width=350),
        tooltip="🔋 EV Charging Site",
        icon=folium.Icon(color="pink", icon="bolt", prefix="fa")
    ).add_to(m)
    
    ev_stations = site.get('ev_stations_details', [])
    for i, station in enumerate(ev_stations):
        try:
            station_lat = station.get('latitude')
            station_lng = station.get('longitude')
            
            if station_lat and station_lng:
                ev_popup = f"""
                <b>⚡ {station.get('name', 'Unknown EV Station')}</b><br>
                <b>Rating:</b> {station.get('rating', 'N/A')}<br>
                <b>Address:</b> {station.get('address', 'N/A')}<br>
                <b>Phone:</b> {station.get('phone', 'N/A')}
                """
                
                folium.Marker(
                    [station_lat, station_lng],
                    popup=folium.Popup(ev_popup, max_width=300),
                    tooltip=f"⚡ Competitor: {station.get('name', 'EV Station')}",
                    icon=folium.Icon(color="red", icon="flash", prefix="fa")
                ).add_to(m)
        except Exception as e:
            st.warning(f"Error adding EV station marker: {e}")
            continue
    
    if show_traffic:
        add_google_traffic_layer(m)
    
    folium.LayerControl().add_to(m)
    return m

def create_sites_only_map(sites, show_traffic: bool = False):
    """Create a map showing only the proposed sites (no competitors)"""
    if not sites:
        return None
        
    valid_sites = [s for s in sites if s.get("latitude") and s.get("longitude")]
    if not valid_sites:
        return None
        
    center_lat = sum(s["latitude"] for s in valid_sites) / len(valid_sites)
    center_lon = sum(s["longitude"] for s in valid_sites) / len(valid_sites)
    
    m = folium.Map(
        location=[center_lat, center_lon], 
        zoom_start=8,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", 
        attr="Google Maps"
    )
    
    for i, site in enumerate(valid_sites):
        popup_content = f"""
        <b>📍 Site {i+1}:</b> {site.get('formatted_address','Unknown Address')}<br>
        <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
        <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
        <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
        <b>🏪 Nearby:</b> {site.get('amenities','N/A')[:100]}{'...' if len(str(site.get('amenities',''))) > 100 else ''}
        """
        
        folium.Marker(
            [site["latitude"], site["longitude"]], 
            popup=folium.Popup(popup_content, max_width=350),
            tooltip=f"🔋 EV Site {i+1}",
            icon=folium.Icon(color="pink", icon="bolt", prefix="fa")
        ).add_to(m)
    if show_traffic:
        add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites, show_traffic=False):
    """Create a map for multiple sites with competitors"""
    if not sites:
        return None
        
    valid_sites = [s for s in sites if s.get("latitude") and s.get("longitude")]
    if not valid_sites:
        return None
        
    center_lat = sum(s["latitude"] for s in valid_sites) / len(valid_sites)
    center_lon = sum(s["longitude"] for s in valid_sites) / len(valid_sites)
    
    m = folium.Map(
        location=[center_lat, center_lon], 
        zoom_start=8,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", 
        attr="Google Maps"
    )
    
    for i, site in enumerate(valid_sites):
        popup_content = f"""
        <b>📍 Site {i+1}:</b> {site.get('formatted_address','Unknown Address')}<br>
        <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
        <b>🛣️ Road:</b> {site.get('snapped_road_name','N/A')} ({site.get('snapped_road_type','N/A')})<br>
        <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
        <b>⚡ Competitor EVs:</b> {site.get('competitor_ev_count', 0)}<br>
        <b>🏪 Nearby:</b> {site.get('amenities','N/A')[:100]}{'...' if len(str(site.get('amenities',''))) > 100 else ''}
        """
        
        folium.Marker(
            [site["latitude"], site["longitude"]], 
            popup=folium.Popup(popup_content, max_width=350),
            tooltip=f"🔋 EV Site {i+1}",
            icon=folium.Icon(color="pink", icon="bolt", prefix="fa")
        ).add_to(m)
        
        ev_stations = site.get('ev_stations_details', [])
        for j, station in enumerate(ev_stations):
            try:
                station_lat = station.get('latitude')
                station_lng = station.get('longitude')
                
                if station_lat and station_lng:
                    ev_popup = f"""
                    <b>⚡ {station.get('name', 'Unknown EV Station')}</b><br>
                    <b>Near Site:</b> {i+1}<br>
                    <b>Rating:</b> {station.get('rating', 'N/A')}<br>
                    <b>Address:</b> {station.get('address', 'N/A')}<br>
                    <b>Phone:</b> {station.get('phone', 'N/A')}
                    """
                    
                    folium.Marker(
                        [station_lat, station_lng],
                        popup=folium.Popup(ev_popup, max_width=300),
                        tooltip=f"⚡ Competitor: {station.get('name', 'EV Station')}",
                        icon=folium.Icon(color="red", icon="flash", prefix="fa")
                    ).add_to(m)
            except Exception as e:
                continue
    
    if show_traffic:
        add_google_traffic_layer(m)
    
    folium.LayerControl().add_to(m)
    return m

# ==============================
# STREAMLIT APP
# ==============================

st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")

st.title("🔋 EV Charger Site Generator (CPO Edition)")
st.markdown("*Comprehensive site analysis for EV charging infrastructure planning with competitor analysis*")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("Charger Power Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22, min_value=1, max_value=200, help="Power rating for fast chargers. Note: please put 31kW for Etrel chargers")
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60, min_value=1, max_value=350, help="Power rating for rapid chargers")
    ultra_kw = st.number_input("Ultra Rapid Charger Power (kW)", value=150, min_value=1, max_value=400, help="Power rating for ultra rapid chargers")
    
    st.subheader("Radius Settings")
    competitor_radius = st.number_input(
        "Competitor Search Radius (m)", value=1000, min_value=100, max_value=5000, step=100,
        help="Radius to search for nearby EV charging competitors"
    )
    amenities_radius = st.number_input(
        "Amenities Search Radius (m)", value=500, min_value=100, max_value=2000, step=50,
        help="Radius to search for nearby amenities"
    )
    
    st.subheader("Map Settings")
    show_traffic_single = st.checkbox("Show Traffic Layer (Single Site)", value=False)
    show_traffic_batch = st.checkbox("Show Traffic Layer (Batch Maps)", value=False)
    
    # API status section removed per request

# Main tabs
tab1, tab2 = st.tabs(["📍 Single Site Analysis", "📁 Batch Processing"])

# --- SINGLE SITE ---
with tab1:
    st.subheader("🔍 Analyze Single Site")
    
    col1, col2 = st.columns(2)
    
    with col1:
        lat = st.text_input("Latitude", value="51.5074", help="Enter latitude in decimal degrees")
        lon = st.text_input("Longitude", value="-0.1278", help="Enter longitude in decimal degrees")
    
    with col2:
        fast = st.number_input("Fast Chargers", min_value=0, value=2, help=f"Number of {fast_kw}kW chargers")
        rapid = st.number_input("Rapid Chargers", min_value=0, value=2, help=f"Number of {rapid_kw}kW chargers")
        ultra = st.number_input("Ultra Chargers", min_value=0, value=1, help=f"Number of {ultra_kw}kW chargers")

    if st.button("🔍 Analyze Site", type="primary"):
        try:
            lat_float, lon_float = float(lat), float(lon)
            if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                st.error("Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180.")
            else:
                site = process_site(
                    lat_float, lon_float,
                    fast, rapid, ultra,
                    fast_kw, rapid_kw, ultra_kw,
                    competitor_radius=competitor_radius,
                    amenities_radius=amenities_radius
                )
                st.session_state["single_site"] = site
                st.success("✅ Site analysis completed!")
        except ValueError:
            st.error("Invalid coordinate format. Please enter numeric values.")
        except Exception as e:
            st.error(f"Error analyzing site: {e}")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Required kVA", site.get("required_kva", "N/A"))
        with col2:
            st.metric("Snapped Road Type", site.get("snapped_road_type", "Unknown"))
        with col3:
            st.metric("Traffic Level", site.get("traffic_congestion", "N/A"))
        with col4:
            ev_count = site.get("competitor_ev_count", 0)
            st.metric("Competitor EVs", ev_count)
        
        # Detailed information
        st.subheader("📋 Detailed Site Information")
        
        detail_tabs = st.tabs(["🏠 Location", "🔌 Power", "🛣️ Road Info", "🚦 Traffic", "🏪 Amenities", "⚡ EV Competitors", "🗺️ Site Map"])
        
        with detail_tabs[0]:
            st.write(f"**Address:** {site.get('formatted_address', 'N/A')}")
            st.write(f"**Postcode:** {site.get('postcode', 'N/A')}")
            st.write(f"**Ward:** {site.get('ward', 'N/A')}")
            st.write(f"**District:** {site.get('district', 'N/A')}")
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
            st.write(f"**Nearby Amenities:** {site.get('amenities', 'N/A')}")
        
        with detail_tabs[5]:
            st.write(f"**Number of Competitor EV Stations:** {site.get('competitor_ev_count', 0)}")
            st.write(f"**Competitor Names:** {site.get('competitor_ev_names', 'None')}")
            
            ev_stations = site.get('ev_stations_details', [])
            if ev_stations:
                col_comp1, col_comp2 = st.columns(2)
                
                with col_comp1:
                    st.subheader("🔍 Detailed Competitor Information")
                    for i, station in enumerate(ev_stations):
                        with st.expander(f"⚡ {station.get('name', f'EV Station {i+1}')}"):
                            st.write(f"**Rating:** {station.get('rating', 'N/A')}")
                            st.write(f"**Address:** {station.get('address', 'N/A')}")
                            st.write(f"**Phone:** {station.get('phone', 'N/A')}")
                            st.write(f"**Coordinates:** {station.get('latitude', 'N/A')}, {station.get('longitude', 'N/A')}")
                            
                            if station.get('photo_url'):
                                try:
                                    st.image(station['photo_url'], caption=station.get('name', 'EV Station'), width=200)
                                except:
                                    st.write("📷 Photo unavailable")
                            else:
                                st.write("📷 No photo available")
                
                with col_comp2:
                    st.subheader("📊 Competitor Market Share")
                    
                    competitor_brands = {}
                    for station in ev_stations:
                        name = station.get('name', 'Unknown')
                        brand = extract_brand_name(name)
                        competitor_brands[brand] = competitor_brands.get(brand, 0) + 1
                    
                    if competitor_brands:
                        total_stations = sum(competitor_brands.values())
                        
                        st.write("**Market Share Distribution:**")
                        for brand, count in competitor_brands.items():
                            percentage = (count / total_stations) * 100
                            st.write(f"**{brand}**: {count} stations ({percentage:.1f}%)")
                            st.progress(percentage / 100)
                        
                        st.write("**Visual Breakdown:**")
                        try:
                            pie_chart_img = create_pie_chart_data(competitor_brands)
                            if pie_chart_img:
                                st.markdown(f'<img src="data:image/png;base64,{pie_chart_img}" style="width:100%">', unsafe_allow_html=True)
                            else:
                                chart_df = pd.DataFrame({
                                    'Brand': list(competitor_brands.keys()),
                                    'Stations': list(competitor_brands.values())
                                })
                                st.bar_chart(chart_df.set_index('Brand'), use_container_width=True)
                        except Exception as e:
                            st.warning(f"Could not create pie chart: {e}")
                            chart_df = pd.DataFrame({
                                'Brand': list(competitor_brands.keys()),
                                'Stations': list(competitor_brands.values())
                            })
                            st.bar_chart(chart_df.set_index('Brand'), use_container_width=True)
            else:
                st.info("No competitor EV charging stations found nearby.")
        
        with detail_tabs[6]:
            map_tabs = st.tabs(["🗺️ Site Only", "🗺️ Site + Competitors"])
            
            with map_tabs[0]:
                st.markdown("*Pink marker: Your proposed site*")
                only_map = create_sites_only_map([site], show_traffic_single)
                if only_map:
                    st_folium(only_map, width=700, height=500, key="single_site_only_map", returned_objects=["last_object_clicked"]) 
                else:
                    st.error("Unable to create site-only map.")
            
            with map_tabs[1]:
                st.markdown("*Pink marker: Your proposed site | Red markers: Competitor EV stations*")
                full_map = create_single_map(site, show_traffic_single)
                st_folium(full_map, width=700, height=500, key="single_site_full_map", returned_objects=["last_object_clicked"]) 

# --- BATCH PROCESSING ---
with tab2:
    st.subheader("📁 Batch Processing")
    st.markdown("Upload a CSV file with the required columns to analyze multiple sites at once.")
    
    uploaded = st.file_uploader(
        "Upload CSV file", 
        type="csv",
        help="Required columns: latitude, longitude, fast, rapid, ultra"
    )
    
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            
            st.subheader("📊 Data Preview")
            st.write("**File Structure:**")
            st.write(f"Rows: {len(df)}, Columns: {len(df.columns)}")
            st.write(f"Columns: {', '.join(df.columns.tolist())}")
            
            if len(df) > 0:
                st.write("**Sample Data (First 3 rows):**")
                for i in range(min(3, len(df))):
                    row_data = []
                    for col in df.columns:
                        row_data.append(f"{col}: {df.iloc[i][col]}")
                    st.write(f"Row {i+1}: {' | '.join(row_data[:5])}")
            
            required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
            missing_cols = required_cols - set(df.columns)
            
            if missing_cols:
                st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                st.info("Required columns: latitude, longitude, fast, rapid, ultra")
            else:
                st.success(f"✅ CSV file loaded successfully! Found {len(df)} sites to process.")
                
                if st.button("🚀 Process All Sites", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results = []
                    
                    for i, row in df.iterrows():
                        try:
                            status_text.text(f"Processing site {i+1}/{len(df)}: ({row['latitude']}, {row['longitude']})")
                            site = process_site(
                                float(row["latitude"]), 
                                float(row["longitude"]),
                                int(row.get("fast", 0)), 
                                int(row.get("rapid", 0)), 
                                int(row.get("ultra", 0)),
                                fast_kw, rapid_kw, ultra_kw
                            )
                            results.append(site)
                        except Exception as e:
                            st.warning(f"Error processing row {i+1}: {e}")
                            results.append({
                                "latitude": row.get("latitude"),
                                "longitude": row.get("longitude"),
                                "error": str(e)
                            })
                        
                        progress_bar.progress((i + 1) / len(df))
                    
                    status_text.text("✅ Batch processing completed!")
                    st.session_state["batch_results"] = results

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")

    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        
        st.subheader("📊 Batch Analysis Results")
        
        successful_results = [r for r in results if "error" not in r]
        failed_results = [r for r in results if "error" in r]
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Sites", len(results))
        with col2:
            st.metric("Successful", len(successful_results))
        with col3:
            if successful_results:
                avg_kva = sum(r.get("required_kva", 0) for r in successful_results) / len(successful_results)
                st.metric("Avg kVA", f"{avg_kva:.1f}")
            else:
                st.metric("Avg kVA", "N/A")
        with col4:
            if successful_results:
                avg_competitors = sum(r.get("competitor_ev_count", 0) for r in successful_results) / len(successful_results)
                st.metric("Avg Competitors", f"{avg_competitors:.1f}")
            else:
                st.metric("Avg Competitors", "N/A")
        
        # For large datasets, skip detailed display
        if len(successful_results) > 50:
            st.info(f"📊 Large dataset detected ({len(successful_results)} sites). Download options available below.")
            
            if successful_results:
                st.subheader("🗺️ Site Maps")
                
                map_col1, map_col2 = st.columns(2)
                
                with map_col1:
                    st.markdown("**Sites Only Map**")
                    st.markdown("*Pink markers: Your proposed EV sites*")
                    sites_map = create_sites_only_map(successful_results, show_traffic_batch)
                    if sites_map:
                        st_folium(sites_map, width=350, height=400, key="sites_only_map")
                    else:
                        st.error("Unable to create sites map.")
                
                with map_col2:
                    st.markdown("**Sites + Competitors Map**")
                    st.markdown("*Pink markers: Your sites | Red markers: Competitors*")
                    full_map = create_batch_map(successful_results, show_traffic=show_traffic_batch)
                    if full_map:
                        st_folium(full_map, width=350, height=400, key="full_batch_map")
                    else:
                        st.error("Unable to create full map.")
        
        else:
            # For smaller datasets, show full interface
            if successful_results:
                st.subheader("📋 Detailed Batch Analysis")
                
                batch_tabs = st.tabs(["🗺️ Sites Only", "🗺️ Sites + Competitors", "⚡ EV Competition"])
                
                with batch_tabs[0]:
                    st.markdown("*Pink markers: Your proposed EV sites*")
                    sites_map = create_sites_only_map(successful_results, show_traffic_batch)
                    if sites_map:
                        st_folium(sites_map, width=700, height=500, key="batch_sites_only")
                    else:
                        st.error("Unable to create sites map.")
                
                with batch_tabs[1]:
                    st.markdown("*Pink markers: Your proposed EV sites | Red markers: Competitor EV stations*")
                    batch_map = create_batch_map(successful_results, show_traffic=show_traffic_batch)
                    if batch_map:
                        st_folium(batch_map, width=700, height=500, key="batch_full_map")
                    else:
                        st.error("Unable to create map.")
                
                with batch_tabs[2]:
                    st.write("**⚡ EV Competition Analysis**")
                    
                    comp_col1, comp_col2, comp_col3 = st.columns(3)
                    
                    total_competitors = sum(r.get("competitor_ev_count", 0) for r in successful_results)
                    sites_with_competitors = sum(1 for r in successful_results if r.get("competitor_ev_count", 0) > 0)
                    max_competitors_site = max(successful_results, key=lambda x: x.get("competitor_ev_count", 0))
                    max_competitors = max_competitors_site.get("competitor_ev_count", 0)
                    
                    with comp_col1:
                        st.metric("Total Competitors Found", total_competitors)
                    with comp_col2:
                        st.metric("Sites with Competitors", sites_with_competitors)
                    with comp_col3:
                        st.metric("Max Competitors (Single Site)", max_competitors)
                    
                    if total_competitors > 0:
                        st.write("**📊 Overall Market Share Analysis**")
                        
                        all_competitors = {}
                        for result in successful_results:
                            ev_stations = result.get('ev_stations_details', [])
                            if isinstance(ev_stations, list):
                                for station in ev_stations:
                                    if isinstance(station, dict):
                                        name = station.get('name', 'Unknown')
                                        brand = extract_brand_name(name)
                                        all_competitors[brand] = all_competitors.get(brand, 0) + 1
                        
                        if all_competitors:
                            total_stations = sum(all_competitors.values())
                            st.write("**Market Share Distribution:**")
                            for brand, count in all_competitors.items():
                                percentage = (count / total_stations) * 100
                                st.write(f"**{brand}**: {count} stations ({percentage:.1f}%)")
                                st.progress(percentage / 100)
                            
                            st.write("**Visual Breakdown:**")
                            try:
                                pie_chart_img = create_pie_chart_data(all_competitors)
                                if pie_chart_img:
                                    st.markdown(f'<img src="data:image/png;base64,{pie_chart_img}" style="width:100%">', unsafe_allow_html=True)
                                else:
                                    df_market = pd.DataFrame({
                                        'Brand': list(all_competitors.keys()),
                                        'Total Stations': list(all_competitors.values())
                                    }).sort_values('Total Stations', ascending=False)
                                    st.bar_chart(df_market.set_index('Brand'), use_container_width=True)
                            except Exception as e:
                                st.warning(f"Could not create pie chart: {e}")
                                df_market = pd.DataFrame({
                                    'Brand': list(all_competitors.keys()),
                                    'Total Stations': list(all_competitors.values())
                                }).sort_values('Total Stations', ascending=False)
                                st.bar_chart(df_market.set_index('Brand'), use_container_width=True)
        
        if failed_results:
            st.subheader("⚠️ Failed Sites")
            for i, failed in enumerate(failed_results):
                st.write(f"**Site {i+1}:** {failed.get('latitude', 'N/A')}, {failed.get('longitude', 'N/A')} - {failed.get('error', 'Unknown error')}")
        
        if successful_results:
            st.subheader("📥 Download Results")
            
            download_data = []
            for i, site in enumerate(successful_results):
                try:
                    download_data.append({
                        'Site_Number': i + 1,
                        'Latitude': site.get('latitude', ''),
                        'Longitude': site.get('longitude', ''),
                        'Address': str(site.get('formatted_address', '')),
                        'Postcode': str(site.get('postcode', '')),
                        'Ward': str(site.get('ward', '')),
                        'District': str(site.get('district', '')),
                        'Fast_Chargers': int(site.get('fast_chargers', 0)),
                        'Rapid_Chargers': int(site.get('rapid_chargers', 0)),
                        'Ultra_Chargers': int(site.get('ultra_chargers', 0)),
                        'Required_kVA': float(site.get('required_kva', 0)),
                        'Snapped_Road_Name': str(site.get('snapped_road_name', '')),
                        'Snapped_Road_Type': str(site.get('snapped_road_type', '')),
                        'Traffic_Congestion': str(site.get('traffic_congestion', '')),
                        'Traffic_Speed_mph': str(site.get('traffic_speed', '')),
                        'Competitor_EV_Count': int(site.get('competitor_ev_count', 0)),
                        'Competitor_EV_Names': str(site.get('competitor_ev_names', '')),
                        'Amenities': str(site.get('amenities', '')),
                        'British_Grid_Easting': str(site.get('easting', '')),
                        'British_Grid_Northing': str(site.get('northing', ''))
                    })
                except Exception as e:
                    st.warning(f"Error preparing site {i+1} for download: {e}")
                    download_data.append({
                        'Site_Number': i + 1,
                        'Latitude': site.get('latitude', ''),
                        'Longitude': site.get('longitude', ''),
                        'Address': 'Error processing data',
                        'Error': str(e)
                    })
            
            try:
                df_download = pd.DataFrame(download_data)
                csv_data = df_download.to_csv(index=False)
                
                st.write(f"**Download includes {len(download_data)} sites with {len(df_download.columns)} data columns**")
                
                st.download_button(
                    label="📥 Download Complete Analysis CSV",
                    data=csv_data,
                    file_name=f"ev_site_batch_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_csv_batch"
                )
                
                simplified_data = []
                for i, site in enumerate(successful_results):
                    simplified_data.append({
                        'Site': i + 1,
                        'Lat': site.get('latitude', ''),
                        'Lon': site.get('longitude', ''),
                        'Address': str(site.get('formatted_address', ''))[:100],
                        'kVA': site.get('required_kva', 0),
                        'Road_Type': str(site.get('snapped_road_type', '')),
                        'Traffic': str(site.get('traffic_congestion', '')),
                        'Competitors': site.get('competitor_ev_count', 0)
                    })
                
                df_simple = pd.DataFrame(simplified_data)
                csv_simple = df_simple.to_csv(index=False)
                
                st.download_button(
                    label="📥 Download Summary CSV (Essential Data Only)",
                    data=csv_simple,
                    file_name=f"ev_site_summary_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_simple_batch"
                )
                
            except Exception as e:
                st.error(f"Error creating CSV download: {e}")
        else:
            st.info("No successful results to download.")
    
    else:
        st.info("👆 Upload a CSV file to start batch processing.")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        <p>🔋 EV Charger Site Generator v3.0 | Built with Streamlit</p>
        <p>Powered by Google Maps API (Roads, Places, Geocoding), TomTom Traffic API, and Postcodes.io</p>
        <p>✨ Now with EV competitor analysis and enhanced road information</p>
    </div>
    """, 
    unsafe_allow_html=True
)
