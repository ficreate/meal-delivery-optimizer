import os
import streamlit as st
import streamlit.components.v1 as components

# Declare Streamlit Custom Component
_COMPONENT_PATH = os.path.join(os.path.dirname(__file__), "map_editor_component")
_map_editor_func = components.declare_component("course_map_editor", path=_COMPONENT_PATH)

def interactive_map_editor(depot, courses_data, initial_center=None, initial_zoom=None, key="course_map_editor"):
    """
    完全な JavaScript SPA マップエディタ。
    ピンクリックやコース移動は純粋な JS で実行され、リロード（白抜け）が一切発生しない。
    「変更を反映して再計算」ボタンが押された時のみ、変更データが返る。
    """
    serialized_courses = {}
    for cid, cdata in courses_data.items():
        cust_list = []
        for _, row in cdata['customers_df'].iterrows():
            cust_list.append({
                "customer_id": str(row['customer_id']),
                "delivery_seq": int(row['delivery_seq']),
                "name": str(row['name']),
                "lat": float(row['lat']),
                "lng": float(row['lng']),
                "address": str(row['address']),
                "dwelling_type": str(row['dwelling_type']),
                "current_item": str(row.get('current_item', 'プチママ')),
                "estimated_arrival": str(row['estimated_arrival']),
                "drop_location_text": str(row.get('drop_location_text', '玄関前'))
            })

        serialized_courses[cid] = {
            "course_id": cid,
            "color": cdata.get('color', '#3388ff'),
            "total_customers": int(cdata['total_customers']),
            "total_distance_km": float(cdata['total_distance_km']),
            "estimated_return_time": str(cdata['estimated_return_time']),
            "road_geometry": cdata.get('road_geometry', []),
            "customers": cust_list
        }

    depot_json = {
        "name": depot['name'],
        "address": depot['address'],
        "lat": float(depot['lat']),
        "lng": float(depot['lng']),
        "departure_time": depot.get('default_departure_time', '09:30'),
        "return_time": depot.get('default_return_time', '16:00')
    }

    result = _map_editor_func(
        depot=depot_json,
        courses=serialized_courses,
        center=initial_center,
        zoom=initial_zoom,
        key=key,
        default=None
    )
    return result
