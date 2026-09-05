import math
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from modules.osrm_router import get_complete_course_road_route

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

def calculate_single_course_stats(course_df, depot_loc, house_svc, bldg_svc, dep_h, dep_m, break_min, avg_speed_kmh=18.0):
    if course_df.empty:
        return 0, 0, [], 0, "09:30", []

    locs = list(zip(course_df['lat'], course_df['lng']))
    dwells = list(course_df['dwelling_type'])
    n = len(locs)

    # Simple Nearest-Neighbor Ordering from Depot
    unvisited = set(range(n))
    curr_loc = depot_loc
    ordered_indices = []

    while unvisited:
        next_i = min(unvisited, key=lambda i: haversine_distance(curr_loc[0], curr_loc[1], locs[i][0], locs[i][1]))
        ordered_indices.append(next_i)
        unvisited.remove(next_i)
        curr_loc = locs[next_i]

    total_dist = 0.0
    total_time = 0.0
    curr_time_min = dep_h * 60 + dep_m
    arrival_times = [""] * n
    detour_factor = 1.45

    prev_loc = depot_loc
    for rank, idx in enumerate(ordered_indices):
        d_direct = haversine_distance(prev_loc[0], prev_loc[1], locs[idx][0], locs[idx][1])
        d_road = d_direct * detour_factor
        t_drive = (d_road / avg_speed_kmh) * 60.0

        curr_time_min += t_drive
        total_dist += d_road
        total_time += t_drive

        arr_h = int(curr_time_min // 60)
        arr_m = int(curr_time_min % 60)
        arrival_times[idx] = f"{arr_h:02d}:{arr_m:02d}"

        svc = house_svc if dwells[idx] == '戸建て' else bldg_svc
        curr_time_min += svc
        total_time += svc

        if rank == (n // 2):
            curr_time_min += break_min
            total_time += break_min

        prev_loc = locs[idx]

    # Return to depot
    d_home_direct = haversine_distance(prev_loc[0], prev_loc[1], depot_loc[0], depot_loc[1])
    d_home_road = d_home_direct * detour_factor
    t_home = (d_home_road / avg_speed_kmh) * 60.0

    curr_time_min += t_home
    total_dist += d_home_road
    total_time += t_home

    ret_h = int(curr_time_min // 60)
    ret_m = int(curr_time_min % 60)
    return_time_str = f"{ret_h:02d}:{ret_m:02d}"

    return round(total_dist, 2), round(total_time, 1), ordered_indices, curr_time_min, return_time_str, arrival_times

def optimize_single_k(depot, customers_df, num_courses, avg_speed_kmh=18.0, target_diff_max_min=20.0, use_osrm_road=False):
    if customers_df.empty or num_courses <= 0:
        return {}

    depot_loc = (depot['lat'], depot['lng'])
    house_svc = depot.get('house_service_minutes', 4)
    bldg_svc = depot.get('building_service_minutes', 8)
    break_min = depot.get('default_break_minutes', 60)
    dep_h, dep_m = map(int, depot.get('default_departure_time', '09:30').split(':'))

    coords = customers_df[['lat', 'lng']].values
    n_samples = len(coords)

    if n_samples < num_courses:
        num_courses = n_samples

    kmeans = KMeans(n_clusters=num_courses, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)

    # Balance iterations
    for _ in range(15):
        course_return_mins = {}
        for c_idx in range(num_courses):
            c_mask = (labels == c_idx)
            c_df = customers_df[c_mask]
            _, _, _, curr_min, _, _ = calculate_single_course_stats(c_df, depot_loc, house_svc, bldg_svc, dep_h, dep_m, break_min, avg_speed_kmh)
            course_return_mins[c_idx] = curr_min

        max_c = max(course_return_mins, key=course_return_mins.get)
        min_c = min(course_return_mins, key=course_return_mins.get)
        diff = course_return_mins[max_c] - course_return_mins[min_c]

        if diff <= target_diff_max_min:
            break

        max_members = np.where(labels == max_c)[0]
        if len(max_members) <= 10:
            break
        min_members = np.where(labels == min_c)[0]
        min_center = np.mean(coords[min_members], axis=0)

        dists = [haversine_distance(coords[m][0], coords[m][1], min_center[0], min_center[1]) for m in max_members]
        transfer_idx = max_members[np.argmin(dists)]
        labels[transfer_idx] = min_c

    customers_df = customers_df.copy()
    customers_df['cluster'] = labels

    courses_result = {}
    colors = ['#E6194B', '#3C8DBC', '#3CB44B', '#F58231', '#911EB4', '#42D4F4', '#F032E6', '#BFEF45', '#FABEBE', '#469990', '#DCBEFF', '#9A6324', '#008080', '#800000', '#AAFFC3', '#808000', '#000075', '#A9A9A9']

    for c_idx in range(num_courses):
        course_id = f'コース-{c_idx + 1:02d}'
        course_df = customers_df[customers_df['cluster'] == c_idx].copy()
        if course_df.empty:
            continue

        tot_dist, tot_time, ord_idx, ret_min, ret_str, arr_times = calculate_single_course_stats(
            course_df, depot_loc, house_svc, bldg_svc, dep_h, dep_m, break_min, avg_speed_kmh
        )

        ordered_df = course_df.iloc[ord_idx].copy()
        ordered_df['delivery_seq'] = range(1, len(ordered_df) + 1)
        ordered_df['estimated_arrival'] = arr_times

        house_count = (ordered_df['dwelling_type'] == '戸建て').sum()
        bldg_count = (ordered_df['dwelling_type'] == '集合住宅').sum()

        road_geom = []
        if use_osrm_road:
            route_locs = [depot_loc] + list(zip(ordered_df['lat'], ordered_df['lng'])) + [depot_loc]
            _, _, road_geom = get_complete_course_road_route(route_locs, avoid_highways=True)

        courses_result[course_id] = {
            'course_id': course_id,
            'color': colors[c_idx % len(colors)],
            'customers_df': ordered_df,
            'total_customers': len(ordered_df),
            'house_count': int(house_count),
            'building_count': int(bldg_count),
            'total_distance_km': tot_dist,
            'total_time_min': tot_time,
            'return_minutes_raw': ret_min,
            'estimated_return_time': ret_str,
            'road_geometry': road_geom,
            'avoid_highways': True
        }

    return courses_result

def recalculate_single_course_route(cdata, depot, avoid_highways=True):
    """
    指定したコースの実道路ルートを、高速道路除外のON/OFF設定に基づいて再計算
    """
    depot_loc = (depot['lat'], depot['lng'])
    ord_df = cdata['customers_df']
    if ord_df.empty:
        return cdata

    route_locs = [depot_loc] + list(zip(ord_df['lat'], ord_df['lng'])) + [depot_loc]
    tot_d, tot_t, road_geom = get_complete_course_road_route(route_locs, avoid_highways=avoid_highways)
    cdata['road_geometry'] = road_geom
    cdata['total_distance_km'] = tot_d
    cdata['avoid_highways'] = avoid_highways
    return cdata

def reassign_customer_between_courses(courses_result, customer_id, from_course_id, to_course_id, depot, avg_speed_kmh=18.0):
    """
    特定の顧客を移動元コースから移動先コースへ付替え、両コースの配達順・帰着時刻・実道路ルートを即座に再計算
    customer_id は文字列・数値両対応
    """
    if from_course_id not in courses_result or to_course_id not in courses_result:
        return courses_result
    
    from_df = courses_result[from_course_id]['customers_df'].copy()
    to_df = courses_result[to_course_id]['customers_df'].copy()

    # Find the target customer row using string comparison
    str_cid = str(customer_id)
    match = from_df[from_df['customer_id'].astype(str) == str_cid]
    if match.empty:
        return courses_result
    
    target_row = match.iloc[0:1]
    
    # Remove from from_df
    new_from_df = from_df[from_df['customer_id'].astype(str) != str_cid].copy()
    
    # Append to to_df
    new_to_df = pd.concat([to_df, target_row], ignore_index=True)

    depot_loc = (depot['lat'], depot['lng'])
    house_svc = depot.get('house_service_minutes', 4)
    bldg_svc = depot.get('building_service_minutes', 8)
    break_min = depot.get('default_break_minutes', 60)
    dep_h, dep_m = map(int, depot.get('default_departure_time', '09:30').split(':'))

    # Re-calculate From-Course
    if not new_from_df.empty:
        tot_d1, tot_t1, ord_idx1, ret_min1, ret_str1, arr_times1 = calculate_single_course_stats(
            new_from_df, depot_loc, house_svc, bldg_svc, dep_h, dep_m, break_min, avg_speed_kmh
        )
        ord_from_df = new_from_df.iloc[ord_idx1].copy()
        ord_from_df['delivery_seq'] = range(1, len(ord_from_df) + 1)
        ord_from_df['estimated_arrival'] = arr_times1

        avoid1 = courses_result[from_course_id].get('avoid_highways', True)
        route_locs1 = [depot_loc] + list(zip(ord_from_df['lat'], ord_from_df['lng'])) + [depot_loc]
        _, _, road_geom1 = get_complete_course_road_route(route_locs1, avoid_highways=avoid1)

        courses_result[from_course_id]['customers_df'] = ord_from_df
        courses_result[from_course_id]['total_customers'] = len(ord_from_df)
        courses_result[from_course_id]['house_count'] = int((ord_from_df['dwelling_type'] == '戸建て').sum())
        courses_result[from_course_id]['building_count'] = int((ord_from_df['dwelling_type'] == '集合住宅').sum())
        courses_result[from_course_id]['total_distance_km'] = tot_d1
        courses_result[from_course_id]['total_time_min'] = tot_t1
        courses_result[from_course_id]['return_minutes_raw'] = ret_min1
        courses_result[from_course_id]['estimated_return_time'] = ret_str1
        courses_result[from_course_id]['road_geometry'] = road_geom1
    else:
        # 0件になったコースは自動削除してコース数を削減
        if from_course_id in courses_result:
            del courses_result[from_course_id]

    # Re-calculate To-Course
    if not new_to_df.empty:
        tot_d2, tot_t2, ord_idx2, ret_min2, ret_str2, arr_times2 = calculate_single_course_stats(
            new_to_df, depot_loc, house_svc, bldg_svc, dep_h, dep_m, break_min, avg_speed_kmh
        )
        ord_to_df = new_to_df.iloc[ord_idx2].copy()
        ord_to_df['delivery_seq'] = range(1, len(ord_to_df) + 1)
        ord_to_df['estimated_arrival'] = arr_times2

        avoid2 = courses_result[to_course_id].get('avoid_highways', True)
        route_locs2 = [depot_loc] + list(zip(ord_to_df['lat'], ord_to_df['lng'])) + [depot_loc]
        _, _, road_geom2 = get_complete_course_road_route(route_locs2, avoid_highways=avoid2)

        courses_result[to_course_id]['customers_df'] = ord_to_df
        courses_result[to_course_id]['total_customers'] = len(ord_to_df)
        courses_result[to_course_id]['house_count'] = int((ord_to_df['dwelling_type'] == '戸建て').sum())
        courses_result[to_course_id]['building_count'] = int((ord_to_df['dwelling_type'] == '集合住宅').sum())
        courses_result[to_course_id]['total_distance_km'] = tot_d2
        courses_result[to_course_id]['total_time_min'] = tot_t2
        courses_result[to_course_id]['return_minutes_raw'] = ret_min2
        courses_result[to_course_id]['estimated_return_time'] = ret_str2
        courses_result[to_course_id]['road_geometry'] = road_geom2

    return courses_result

def dissolve_course_into_others(courses_data, target_course_id, depot):
    """
    指定したコースの全顧客を近傍の他コースへ自動最適再配分し、そのコースを完全に削除（0件化・消滅）する。
    """
    if target_course_id not in courses_data or len(courses_data) <= 1:
        return courses_data

    import copy
    updated = copy.deepcopy(courses_data)
    target_custs = updated[target_course_id]['customers_df']
    other_course_ids = [c for c in updated.keys() if c != target_course_id]

    if not other_course_ids:
        return courses_data

    # Find nearest other course centroid for each customer
    centroids = {}
    for cid in other_course_ids:
        c_df = updated[cid]['customers_df']
        centroids[cid] = (c_df['lat'].mean(), c_df['lng'].mean())

    for _, row in target_custs.iterrows():
        c_lat = row['lat']
        c_lng = row['lng']
        # Find closest other course
        best_c = other_course_ids[0]
        min_d = float('inf')
        for cid, (clat, clng) in centroids.items():
            d = (c_lat - clat)**2 + (c_lng - clng)**2
            if d < min_d:
                min_d = d
                best_c = cid

        updated = reassign_customer_between_courses(
            updated, str(row['customer_id']), target_course_id, best_c, depot
        )

    return updated

def run_fast_exploration(depot, customers_df, min_k=4, max_k=10, progress_callback=None):
    if customers_df.empty:
        return []

    ret_h, ret_m = map(int, depot.get('default_return_time', '16:00').split(':'))
    target_deadline_min = ret_h * 60 + ret_m

    trial_reports = []
    k_range = list(range(min_k, max_k + 1))
    total_steps = len(k_range)
    recommended_k = None

    for i, k in enumerate(k_range):
        if progress_callback:
            progress_callback(i + 1, total_steps, f"🔍 コース数 {k} の運行シミュレーションを検証中...")

        res = optimize_single_k(depot, customers_df, num_courses=k, use_osrm_road=False)

        max_ret_min = max(c['return_minutes_raw'] for c in res.values())
        min_ret_min = min(c['return_minutes_raw'] for c in res.values())
        
        max_ret_str = f"{int(max_ret_min//60):02d}:{int(max_ret_min%60):02d}"
        min_ret_str = f"{int(min_ret_min//60):02d}:{int(min_ret_min%60):02d}"
        
        is_safe = (max_ret_min <= target_deadline_min)
        margin_min = target_deadline_min - max_ret_min

        if is_safe and recommended_k is None:
            recommended_k = k

        trial_reports.append({
            "courses_num": k,
            "cust_per_course": math.ceil(len(customers_df) / k),
            "max_return_time": max_ret_str,
            "min_return_time": min_ret_str,
            "margin_minutes": margin_min,
            "is_on_time": is_safe,
            "status": "✅ 目標時間内" if is_safe else f"❌ {int(abs(margin_min))}分 超過"
        })

    if recommended_k is None:
        recommended_k = max_k

    return trial_reports, recommended_k

def generate_detailed_course_plan(depot, customers_df, selected_k, progress_callback=None):
    if progress_callback:
        progress_callback(1, 2, f"🔄 {selected_k} コースの最適配達順を編成中...")

    if progress_callback:
        progress_callback(2, 2, f"🛣️ {selected_k} コースの実道路ポリライン（OSRM）を描画中...")

    return optimize_single_k(depot, customers_df, num_courses=selected_k, use_osrm_road=True)

def optimize_courses(depot, customers_df, num_courses=None, avg_speed_kmh=18.0, target_diff_max_min=20.0, use_osrm_road=True):
    if not num_courses or num_courses <= 0:
        num_courses = 6
    return optimize_single_k(depot, customers_df, num_courses, avg_speed_kmh, target_diff_max_min, use_osrm_road)
