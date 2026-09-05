import folium
from folium import plugins
import os
import base64

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return None

def create_delivery_map(depot, courses_data, selected_course_id=None, photos_dir=None, custom_center=None, custom_zoom=None):
    if custom_center and isinstance(custom_center, (list, tuple, dict)):
        if isinstance(custom_center, dict):
            center_lat = float(custom_center.get('lat', depot['lat']))
            center_lng = float(custom_center.get('lng', depot['lng']))
        else:
            center_lat = float(custom_center[0])
            center_lng = float(custom_center[1])
    else:
        center_lat = float(depot['lat'])
        center_lng = float(depot['lng'])

    zoom_level = int(custom_zoom) if custom_zoom else 14
    all_course_ids = list(courses_data.keys())

    # Create Map with standard OpenStreetMap (Japanese labels)
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=zoom_level,
        tiles="OpenStreetMap",
        control_scale=True
    )

    # Add GSI (国土地理院) Maps as alternate layers
    folium.TileLayer(
        tiles='https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png',
        attr='&copy; <a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>',
        name='国土地理院 標準地図 (日本語)',
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles='https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png',
        attr='&copy; <a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>',
        name='国土地理院 淡色地図 (日本語)',
        overlay=False,
        control=True
    ).add_to(m)

    # Depot marker
    depot_popup_html = f"""
    <div style="font-family: sans-serif; width: 220px;">
        <div style="background-color: #1E3A8A; color: white; padding: 6px; border-radius: 4px; font-weight: bold; text-align: center;">
            🏢 配送拠点 (デポ)
        </div>
        <p style="margin: 6px 0 2px 0; font-weight: bold; font-size: 14px;">{depot['name']}</p>
        <p style="margin: 2px 0; font-size: 12px; color: #555;">{depot['address']}</p>
        <p style="margin: 2px 0; font-size: 12px;">出発: {depot.get('default_departure_time', '09:30')} / 目標帰着: {depot.get('default_return_time', '16:00')}</p>
    </div>
    """
    folium.Marker(
        location=[float(depot['lat']), float(depot['lng'])],
        popup=folium.Popup(depot_popup_html, max_width=260),
        tooltip=f"🏢 拠点: {depot['name']}",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)

    all_lats = [float(depot['lat'])]
    all_lngs = [float(depot['lng'])]

    # Courses
    for course_id, cdata in courses_data.items():
        if selected_course_id and selected_course_id != "全コース表示" and course_id != selected_course_id:
            continue

        color = cdata.get('color', '#3388ff')
        fg = folium.FeatureGroup(name=f"{course_id} ({cdata['total_customers']}件)")

        road_geom = cdata.get('road_geometry', [])
        if road_geom and len(road_geom) > 1:
            folium.PolyLine(
                locations=road_geom,
                color=color,
                weight=4.5,
                opacity=0.85,
                tooltip=f"🚚 {course_id} 実道路ルート (実走: {cdata['total_distance_km']}km / 帰着: {cdata['estimated_return_time']})"
            ).add_to(fg)

        customers_df = cdata['customers_df']
        for _, row in customers_df.iterrows():
            c_lat = float(row['lat'])
            c_lng = float(row['lng'])
            all_lats.append(c_lat)
            all_lngs.append(c_lng)

            seq = row['delivery_seq']
            arr_time = row['estimated_arrival']
            dwell_icon = "🏠" if row['dwelling_type'] == '戸建て' else "🏢"
            
            photo_b64 = None
            if photos_dir and row.get('photo_filename'):
                p_path = os.path.join(photos_dir, row['photo_filename'])
                photo_b64 = get_base64_image(p_path)

            img_tag = ""
            if photo_b64:
                img_tag = f'<img src="data:image/jpeg;base64,{photo_b64}" style="width: 100%; border-radius: 4px; margin-top: 6px; border: 1px solid #ddd; max-height: 120px; object-fit: cover;" />'
            else:
                img_tag = '<div style="background: #F1F5F9; color: #94A3B8; text-align: center; padding: 12px 0; border-radius: 4px; margin-top: 6px; font-size: 11px;">📷 荷物写真なし</div>'

            popup_html = f"""
            <div style="font-family: sans-serif; width: 260px; line-height: 1.4;">
                <div style="background-color: {color}; color: white; padding: 6px 10px; border-radius: 4px; font-weight: bold; font-size: 14px; display: flex; justify-content: space-between;">
                    <span>#{seq} {course_id}</span>
                    <span style="font-size: 12px; background: rgba(255,255,255,0.2); padding: 1px 5px; border-radius: 3px;">到着 {arr_time}</span>
                </div>
                <div style="margin-top: 6px;">
                    <strong style="font-size: 15px; color: #1E293B;">{row['name']} 様</strong>
                </div>
                <div style="font-size: 12px; color: #475569; margin: 2px 0;">
                    {dwell_icon} {row['dwelling_type']} | {row.get('current_item', 'プチママ')}
                </div>
                <div style="font-size: 11px; color: #64748B; margin-bottom: 4px;">
                    📍 {row['address']}
                </div>
                <div style="background-color: #F8FAFC; border-left: 3px solid {color}; padding: 4px 6px; font-size: 11px; color: #334155;">
                    📦 <strong>設置場所:</strong> {row.get('drop_location_text', '玄関前')}
                </div>
                {img_tag}
            </div>
            """

            marker_html = f"""
            <div style="background-color: {color}; color: white; border-radius: 50%; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; border: 2px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
                {seq}
            </div>
            """
            icon = folium.DivIcon(
                icon_size=(26, 26),
                icon_anchor=(13, 13),
                html=marker_html
            )

            folium.Marker(
                location=[c_lat, c_lng],
                popup=folium.Popup(popup_html, max_width=290),
                tooltip=f"#{seq} {row['name']}様 ({course_id} - 到着{arr_time})",
                icon=icon
            ).add_to(fg)

        fg.add_to(m)

    # Only fit bounds if user has NOT customized center/zoom
    if not custom_center and len(all_lats) > 1:
        m.fit_bounds([[min(all_lats), min(all_lngs)], [max(all_lats), max(all_lngs)]], padding=[20, 20])

    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    return m

def create_unassigned_customers_map(depot, customers_df):
    center_lat = float(depot['lat'])
    center_lng = float(depot['lng'])

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True
    )

    folium.TileLayer(
        tiles='https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png',
        attr='&copy; <a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>',
        name='国土地理院 標準地図 (日本語)',
        overlay=False,
        control=True
    ).add_to(m)

    depot_popup_html = f"""
    <div style="font-family: sans-serif; width: 200px;">
        <div style="background-color: #1E3A8A; color: white; padding: 4px; border-radius: 4px; font-weight: bold; text-align: center;">
            🏢 配送拠点 (デポ)
        </div>
        <p style="margin: 4px 0 2px 0; font-weight: bold;">{depot['name']}</p>
        <p style="margin: 2px 0; font-size: 12px; color: #555;">{depot['address']}</p>
    </div>
    """
    folium.Marker(
        location=[center_lat, center_lng],
        popup=folium.Popup(depot_popup_html, max_width=240),
        tooltip=f"🏢 拠点: {depot['name']}",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)

    all_lats = [center_lat]
    all_lngs = [center_lng]

    for _, row in customers_df.iterrows():
        c_lat = float(row['lat'])
        c_lng = float(row['lng'])
        all_lats.append(c_lat)
        all_lngs.append(c_lng)

        dwell_icon = "🏠" if row['dwelling_type'] == '戸建て' else "🏢"
        popup_html = f"""
        <div style="font-family: sans-serif; width: 220px;">
            <div style="background-color: #475569; color: white; padding: 4px; border-radius: 4px; font-weight: bold;">
                顧客ID: {row['customer_id']}
            </div>
            <p style="margin: 4px 0 2px 0; font-weight: bold; font-size: 14px;">{row['name']} 様</p>
            <p style="margin: 2px 0; font-size: 12px; color: #333;">{dwell_icon} {row['dwelling_type']} | {row.get('current_item', '定番')}</p>
            <p style="margin: 2px 0; font-size: 11px; color: #666;">📍 {row['address']}</p>
        </div>
        """
        folium.CircleMarker(
            location=[c_lat, c_lng],
            radius=5,
            color="#3B82F6",
            fill=True,
            fill_color="#60A5FA",
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{row['name']} 様 ({row['dwelling_type']})"
        ).add_to(m)

    if len(all_lats) > 1:
        m.fit_bounds([[min(all_lats), min(all_lngs)], [max(all_lats), max(all_lngs)]], padding=[20, 20])

    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    return m

def create_driver_current_map(depot, my_course_df, current_idx, road_geom=None):
    if my_course_df.empty:
        center_lat, center_lng = float(depot['lat']), float(depot['lng'])
    else:
        curr_cust = my_course_df.iloc[current_idx] if current_idx < len(my_course_df) else my_course_df.iloc[0]
        center_lat, center_lng = float(curr_cust['lat']), float(curr_cust['lng'])

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=15,
        tiles="OpenStreetMap",
        control_scale=True
    )

    folium.TileLayer(
        tiles='https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png',
        attr='&copy; <a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>',
        name='国土地理院 標準地図 (日本語)',
        overlay=False,
        control=True
    ).add_to(m)

    folium.Marker(
        location=[float(depot['lat']), float(depot['lng'])],
        tooltip=f"🏢 拠点: {depot['name']}",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)

    if road_geom and len(road_geom) > 1:
        folium.PolyLine(
            locations=road_geom,
            color="#2563EB",
            weight=5,
            opacity=0.75,
            tooltip="🚚 配達走行ルート"
        ).add_to(m)

    for i, row in my_course_df.iterrows():
        seq = row['delivery_seq']
        if i < current_idx:
            c_color = "#94A3B8"
            st_badge = "✅ 配達完了"
        elif i == current_idx:
            c_color = "#DC2626"
            st_badge = "📍 次の配達先"
        else:
            c_color = "#3B82F6"
            st_badge = "⏳ 未配達"

        m_html = f"""
        <div style="background-color: {c_color}; color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 11px; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
            {seq}
        </div>
        """
        icon = folium.DivIcon(
            icon_size=(24, 24),
            icon_anchor=(12, 12),
            html=m_html
        )
        folium.Marker(
            location=[float(row['lat']), float(row['lng'])],
            tooltip=f"#{seq} {row['name']}様 ({st_badge} - 到着目安 {row['estimated_arrival']})",
            icon=icon
        ).add_to(m)

    if current_idx < len(my_course_df):
        target_cust = my_course_df.iloc[current_idx]
        if current_idx == 0:
            prev_lat, prev_lng = float(depot['lat']), float(depot['lng'])
        else:
            prev_cust = my_course_df.iloc[current_idx - 1]
            prev_lat, prev_lng = float(prev_cust['lat']), float(prev_cust['lng'])

        veh_lat = prev_lat + (float(target_cust['lat']) - prev_lat) * 0.75
        veh_lng = prev_lng + (float(target_cust['lng']) - prev_lng) * 0.75

        truck_html = """
        <div style="background-color: #1D4ED8; color: white; border-radius: 8px; padding: 4px 8px; font-weight: bold; font-size: 13px; border: 2px solid white; box-shadow: 0 4px 8px rgba(0,0,0,0.4); display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
            🚚 配達車両 (現在地)
        </div>
        """
        truck_icon = folium.DivIcon(
            icon_size=(140, 30),
            icon_anchor=(70, 15),
            html=truck_html
        )
        folium.Marker(
            location=[veh_lat, veh_lng],
            tooltip="🚚 配達車両の現在地（次の目的地へ移動中）",
            icon=truck_icon,
            z_index_offset=1000
        ).add_to(m)

    return m
