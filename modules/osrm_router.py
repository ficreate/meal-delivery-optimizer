import requests
import json
import os
import math
import time

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'osrm_cache.json')

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    2点間の球面直線距離（km）を計算
    """
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def haversine_fallback(lat1, lon1, lat2, lon2):
    dist_direct = haversine_distance(lat1, lon1, lat2, lon2)
    dist = dist_direct * 1.45
    duration_min = (dist / 18.0) * 60.0
    return dist, duration_min, [[lat1, lon1], [lat2, lon2]]

def has_highway_steps(steps):
    keywords = ['名神', '第二京阪', '阪神高速', '京滋バイパス', '有料', 'インター', 'IC', 'JCT', 'ランプ', 'motorway', 'tollway', 'Expressway']
    for step in steps:
        name = step.get('name', '')
        ref = step.get('ref', '')
        for kw in keywords:
            if kw in name or kw in ref:
                return True
    return False

def get_road_route_chunk(coords_list, avoid_highways=True):
    """
    coords_list: list of (lat, lng) tuples. Max ~40 per chunk to avoid URL length limit.
    avoid_highways: If True, avoids motorways/expressways/IC ramps.
    Returns: (total_dist_km, total_duration_min, list_of_[lat, lng]_for_geometry)
    """
    if len(coords_list) <= 1:
        return 0.0, 0.0, coords_list

    # OSRM expects lng,lat format separated by ';'
    coords_str = ";".join([f"{lng:.6f},{lat:.6f}" for lat, lng in coords_list])
    cache_key = f"{coords_str}_avoid_{avoid_highways}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=true"

    cache = load_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        return cached['dist_km'], cached['dur_min'], cached['geometry']

    try:
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data.get('code') == 'Ok' and len(data.get('routes', [])) > 0:
                route = data['routes'][0]
                
                # Check if route uses highways
                steps = []
                for leg in route.get('legs', []):
                    steps.extend(leg.get('steps', []))

                is_highway_used = has_highway_steps(steps)

                # If highway is detected and avoid_highways is requested, calculate piecewise with intermediate waypoints
                if is_highway_used and avoid_highways and len(coords_list) > 2:
                    sub_d = 0.0
                    sub_t = 0.0
                    sub_geom = []
                    for k in range(len(coords_list) - 1):
                        pA = coords_list[k]
                        pB = coords_list[k+1]
                        d_k, t_k, g_k = get_two_points_avoid_highway(pA, pB)
                        sub_d += d_k
                        sub_t += t_k
                        if sub_geom:
                            sub_geom.extend(g_k[1:])
                        else:
                            sub_geom.extend(g_k)
                    
                    cache[cache_key] = {
                        'dist_km': round(sub_d, 2),
                        'dur_min': round(sub_t, 1),
                        'geometry': sub_geom
                    }
                    save_cache(cache)
                    return round(sub_d, 2), round(sub_t, 1), sub_geom

                dist_km = round(route['distance'] / 1000.0, 2)
                dur_min = round(route['duration'] / 60.0, 1)
                
                geojson_coords = route['geometry']['coordinates']
                lat_lng_geom = [[pt[1], pt[0]] for pt in geojson_coords]

                cache[cache_key] = {
                    'dist_km': dist_km,
                    'dur_min': dur_min,
                    'geometry': lat_lng_geom
                }
                save_cache(cache)
                return dist_km, dur_min, lat_lng_geom
    except Exception as e:
        pass

    # Fallback to pairwise haversine if API fails
    tot_d = 0.0
    tot_t = 0.0
    full_geom = []
    for i in range(len(coords_list) - 1):
        d, t, geom = haversine_fallback(coords_list[i][0], coords_list[i][1], coords_list[i+1][0], coords_list[i+1][1])
        tot_d += d
        tot_t += t
        full_geom.extend(geom)
    return round(tot_d, 2), round(tot_t, 1), full_geom

def get_two_points_avoid_highway(pA, pB):
    """
    Routes between two points while strictly avoiding expressways/highways/ramps.
    Tries normal route first; if highway detected, tries micro-offsets to snap to surface streets.
    """
    offsets = [
        (0.0, 0.0),
        (-0.0006, 0.0),  # ~65m south (away from elevated expressway)
        (0.0006, 0.0),   # ~65m north
        (0.0, 0.0006),   # ~55m east
        (0.0, -0.0006),  # ~55m west
    ]

    for dLatA, dLngA in offsets:
        for dLatB, dLngB in offsets:
            curA = (pA[0] + dLatA, pA[1] + dLngA)
            curB = (pB[0] + dLatB, pB[1] + dLngB)
            coords_str = f"{curA[1]:.6f},{curA[0]:.6f};{curB[1]:.6f},{curB[0]:.6f}"
            url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=true"
            try:
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('code') == 'Ok' and len(data.get('routes', [])) > 0:
                        route = data['routes'][0]
                        steps = []
                        for leg in route.get('legs', []):
                            steps.extend(leg.get('steps', []))
                        
                        if not has_highway_steps(steps):
                            geojson_coords = route['geometry']['coordinates']
                            return round(route['distance'] / 1000.0, 2), round(route['duration'] / 60.0, 1), [[pt[1], pt[0]] for pt in geojson_coords]
            except Exception:
                pass

    return haversine_fallback(pA[0], pA[1], pB[0], pB[1])

def get_complete_course_road_route(locations_lat_lng, chunk_size=35, avoid_highways=True):
    """
    Splits large route into overlapping chunks to fetch full OSRM road geometry.
    locations_lat_lng: [depot, cust1, cust2, ..., depot]
    avoid_highways: boolean to avoid expressways/toll roads.
    """
    total_dist_km = 0.0
    total_dur_min = 0.0
    full_road_geometry = []
    
    n = len(locations_lat_lng)
    if n <= 1:
        return 0.0, 0.0, locations_lat_lng

    i = 0
    while i < n - 1:
        chunk = locations_lat_lng[i:min(i + chunk_size, n)]
        d_km, dur_m, geom = get_road_route_chunk(chunk, avoid_highways=avoid_highways)
        total_dist_km += d_km
        total_dur_min += dur_m
        if full_road_geometry:
            full_road_geometry.extend(geom[1:])
        else:
            full_road_geometry.extend(geom)
        
        i += (len(chunk) - 1)

    return round(total_dist_km, 2), round(total_dur_min, 1), full_road_geometry
