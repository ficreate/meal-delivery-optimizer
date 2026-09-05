import streamlit as st
import pandas as pd
import os
import json
import streamlit.components.v1 as components
from datetime import datetime
from PIL import Image
from streamlit_folium import folium_static

from modules.data_manager import (
    load_depots, save_depots, add_or_update_depot, delete_depot,
    load_customers, save_customers, update_customer_drop_info,
    load_confirmed_courses, save_confirmed_courses, reset_confirmed_courses,
    PHOTOS_DIR
)
from modules.optimizer import (
    optimize_courses, run_fast_exploration, generate_detailed_course_plan,
    reassign_customer_between_courses, dissolve_course_into_others,
    recalculate_single_course_route
)
from modules.map_visualizer import create_delivery_map, create_unassigned_customers_map, create_driver_current_map
from modules.interactive_editor import interactive_map_editor
from modules.user_manager import (
    load_users, add_user, load_assignments, set_course_driver,
    get_driver_course, load_delivery_logs, record_departure,
    record_delivery_step, record_return, get_today_str
)

# Page configuration
st.set_page_config(
    page_title="スマート食材宅配 配送最適化・運行管理システム",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 24px;
        font-weight: bold;
        color: #1E3A8A;
        padding-bottom: 8px;
        border-bottom: 2px solid #E2E8F0;
        margin-bottom: 16px;
    }
    .driver-nav-box {
        background: white;
        border: 2px solid #3B82F6;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.12);
        margin-bottom: 16px;
    }
    .driver-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 16px;
        font-weight: bold;
        color: white;
        margin-right: 8px;
    }
    .status-box-unconfirmed {
        background: #FFFBEB;
        border: 2px dashed #F59E0B;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .status-box-confirmed {
        background: #F0FDF4;
        border: 2px solid #22C55E;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .user-pill {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 13px;
        color: #1E40AF;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# TTS Helper
def play_voice_guidance(text):
    clean_text = text.replace('"', '\\"').replace('\n', ' ')
    js_code = f"""
    <script>
        (function() {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance("{clean_text}");
                utterance.lang = 'ja-JP';
                utterance.rate = 1.05;
                utterance.pitch = 1.0;
                window.speechSynthesis.speak(utterance);
            }}
        }})();
    </script>
    """
    components.html(js_code, height=0, width=0)

# Session state initialization
if 'depots' not in st.session_state:
    st.session_state.depots = load_depots()

if 'selected_depot_id' not in st.session_state:
    st.session_state.selected_depot_id = st.session_state.depots[0]['id'] if st.session_state.depots else None

if 'users' not in st.session_state:
    st.session_state.users = load_users()

if 'current_user_id' not in st.session_state:
    st.session_state.current_user_id = "admin01"

if 'trial_reports' not in st.session_state:
    st.session_state.trial_reports = None

if 'recommended_k' not in st.session_state:
    st.session_state.recommended_k = 6

if 'selected_k_human' not in st.session_state:
    st.session_state.selected_k_human = 6

if 'preview_courses' not in st.session_state:
    st.session_state.preview_courses = None

if 'map_center' not in st.session_state:
    st.session_state.map_center = None

if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = None

if 'editor_version' not in st.session_state:
    st.session_state.editor_version = 0

if 'driver_current_idx' not in st.session_state:
    st.session_state.driver_current_idx = 0

if 'trigger_voice' not in st.session_state:
    st.session_state.trigger_voice = False

# Helpers
def get_current_user():
    for u in st.session_state.users:
        if u['user_id'] == st.session_state.current_user_id:
            return u
    return st.session_state.users[0] if st.session_state.users else None

def get_current_depot():
    for d in st.session_state.depots:
        if d['id'] == st.session_state.selected_depot_id:
            return d
    return st.session_state.depots[0] if st.session_state.depots else None

current_depot = get_current_depot()
customers_df = load_customers(current_depot['id'])

# -------------------------------------------------------------
# SIDEBAR: ログイン & ナビゲーション
# -------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/delivery-van.png", width=56)
    st.title("スマート配送管理")
    
    st.markdown("### 👤 ログインユーザー")
    user_options = {u['user_id']: f"{'👑 [管理者] ' if u['role']=='admin' else '🚚 [配達員] '}{u['name']}" for u in st.session_state.users}
    selected_uid = st.selectbox(
        "ログイン切替",
        options=list(user_options.keys()),
        format_func=lambda x: user_options.get(x, x),
        index=list(user_options.keys()).index(st.session_state.current_user_id) if st.session_state.current_user_id in user_options else 0
    )
    if selected_uid != st.session_state.current_user_id:
        st.session_state.current_user_id = selected_uid
        st.rerun()

    logged_user = get_current_user()
    is_admin = (logged_user['role'] == 'admin')

    st.markdown(f"<div class='user-pill'>ログイン中: {logged_user['name']} ({'管理者' if is_admin else '配送ドライバー'})</div>", unsafe_allow_html=True)
    st.markdown("---")

    if is_admin:
        app_mode = st.radio(
            "📱 管理メニュー",
            [
                "🖥️ 管理者: コース編成・確定",
                "👥 コース担当者アサイン",
                "📊 本日の配達実績ログ・進捗",
                "🏢 拠点・運行設定",
                "📦 顧客住所録マスター",
                "📱 配達員画面プレビュー"
            ]
        )
    else:
        app_mode = "📱 配達員: スマホ連続配達ナビ"
        st.success("🚚 配達員専用画面を表示中")

    st.markdown("---")
    st.subheader("📍 所属拠点")
    depot_names = {d['id']: d['name'] for d in st.session_state.depots}
    selected_depot_id = st.selectbox(
        "拠点切替",
        options=list(depot_names.keys()),
        format_func=lambda x: depot_names.get(x, x),
        index=0 if st.session_state.selected_depot_id not in depot_names else list(depot_names.keys()).index(st.session_state.selected_depot_id)
    )
    if selected_depot_id != st.session_state.selected_depot_id:
        st.session_state.selected_depot_id = selected_depot_id
        st.session_state.preview_courses = None
        st.session_state.trial_reports = None
        st.session_state.map_center = None
        st.session_state.map_zoom = None
        st.rerun()

# -------------------------------------------------------------
# MODE 1: 管理者: コース編成（高速比較 ➔ 人間選択 ➔ 手動微調整 ➔ 確定）
# -------------------------------------------------------------
if app_mode == "🖥️ 管理者: コース編成・確定":
    st.markdown("<div class='main-header'>🚚 配送コース最適化・確定ワークフロー</div>", unsafe_allow_html=True)

    current_depot = get_current_depot()
    customers_df = load_customers(current_depot['id'])
    
    if customers_df.empty:
        st.warning(f"現在、{current_depot['name']} に登録されている顧客データがありません。")
        st.stop()

    confirmed_courses = load_confirmed_courses(current_depot['id'])
    has_confirmed = confirmed_courses is not None

    # Step status bar
    step_col1, step_col2, step_col3 = st.columns(3)
    with step_col1:
        st.info(f"**Step 1: 顧客住所録 読み込み**\n\n✅ 完了（**{len(customers_df)} 件**）")
    with step_col2:
        if st.session_state.preview_courses or has_confirmed:
            st.info("**Step 2: コース選定 & 実道路計算**\n\n✅ 実道ルート生成完了")
        elif st.session_state.trial_reports:
            st.warning("**Step 2: コース選定 & 実道路計算**\n\n⏳ 比較表作成済（人間選択待ち）")
        else:
            st.warning("**Step 2: コース選定 & 実道路計算**\n\n⏳ 未計算（未編成）")
    with step_col3:
        if has_confirmed:
            st.success(f"**Step 3: コース編成の確定**\n\n🟢 **確定済み（現場配信中: {len(confirmed_courses)}コース）**")
        else:
            st.error("**Step 3: コース編成の確定**\n\n⚠️ **未確定**")

    st.markdown("---")

    # Target Return Time & Parameters Bar
    target_ret_str = current_depot.get('default_return_time', '16:00')
    dep_time_str = current_depot.get('default_departure_time', '09:30')
    break_m = current_depot.get('default_break_minutes', 60)
    h_svc = current_depot.get('house_service_minutes', 4)
    b_svc = current_depot.get('building_service_minutes', 8)

    cfg_col1, cfg_col2, cfg_col3, cfg_col4 = st.columns([3, 3, 3, 3])
    with cfg_col1:
        custom_dep_time = st.text_input("出発時刻", value=dep_time_str, key="dyn_dep_time")
    with cfg_col2:
        custom_ret_time = st.text_input("🎯 目標帰着時刻（必着）", value=target_ret_str, key="dyn_ret_time")
    with cfg_col3:
        custom_break_min = st.number_input("昼休憩 (分)", min_value=0, max_value=120, value=int(break_m), step=10, key="dyn_break_min")
    with cfg_col4:
        st.caption("※ 住居別 作業時間")
        st.write(f"戸建 {h_svc}分 / 集合 {b_svc}分")

    # Update active depot parameters
    active_depot_params = dict(current_depot)
    active_depot_params['default_departure_time'] = custom_dep_time
    active_depot_params['default_return_time'] = custom_ret_time
    active_depot_params['default_break_minutes'] = custom_break_min

    # =========================================================================
    # STAGE 1: 探索範囲指定 & 高速シミュレーション比較表の生成
    # =========================================================================
    st.markdown("""
    <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px;">
        <h4 style="margin: 0 0 6px; color: #1E3A8A;">📊 【Stage 1】コース数別のシミュレーション比較表を作成</h4>
        <div style="font-size: 13px; color: #475569;">
            最小〜最大コース数の範囲を指定し、システムが各コース数での帰着予測・件数を瞬時に試行比較します。
        </div>
    </div>
    """, unsafe_allow_html=True)

    search_col1, search_col2, search_col3 = st.columns([4, 4, 4])
    with search_col1:
        k_min = st.number_input("最小コース数", min_value=3, max_value=15, value=5, step=1)
    with search_col2:
        k_max = st.number_input("最大コース数", min_value=k_min, max_value=15, value=9, step=1)
    with search_col3:
        st.write("")
        run_sim_btn = st.button("⚡ 各コース数の比較表を作成する", type="primary", use_container_width=True)

    progress_placeholder = st.empty()

    if run_sim_btn:
        with progress_placeholder.container():
            p_bar = st.progress(0)
            status_text = st.empty()

            def p_callback(curr_s, tot_s, msg):
                pct = int((curr_s / tot_s) * 100)
                p_bar.progress(min(pct, 100))
                status_text.markdown(f"**[{pct}%]** {msg}")

            reports, rec_k = run_fast_exploration(
                active_depot_params, customers_df, min_k=k_min, max_k=k_max, progress_callback=p_callback
            )

            p_bar.progress(100)
            status_text.markdown(f"✅ **比較表の作成が完了しました！（システム推奨: {rec_k} コース）**")

        st.session_state.trial_reports = reports
        st.session_state.recommended_k = rec_k
        st.session_state.selected_k_human = rec_k
        st.session_state.preview_courses = None
        st.session_state.map_center = None
        st.session_state.map_zoom = None
        st.rerun()

    # =========================================================================
    # STAGE 2: 比較表の提示 & 人間（管理者）によるコース数選択
    # =========================================================================
    if st.session_state.trial_reports and not st.session_state.preview_courses and not has_confirmed:
        st.markdown(f"### 📊 コース数別シミュレーション比較表（目標: {custom_ret_time} 必着）")
        
        rep_rows = []
        for r in st.session_state.trial_reports:
            is_rec = (r['courses_num'] == st.session_state.recommended_k)
            badge_str = "⭐ 【システム推奨】" if is_rec else r['status']
            rep_rows.append({
                "判定": badge_str,
                "コース数": f"{r['courses_num']} コース",
                "1コース件数": f"約 {r['cust_per_course']} 件",
                "最も遅い車の帰着予定": r['max_return_time'],
                "最も早い車の帰着予定": r['min_return_time'],
                f"目標({custom_ret_time})までの余裕": f"+{int(r['margin_minutes'])} 分" if r['margin_minutes']>=0 else f"{int(r['margin_minutes'])} 分 (超過)"
            })
        st.dataframe(pd.DataFrame(rep_rows), use_container_width=True, hide_index=True)

        st.markdown("""
        <div style="background: #EFF6FF; border: 2px solid #3B82F6; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <h4 style="margin: 0 0 8px; color: #1E40AF;">👤 【Stage 2】人間（管理者）によるコース数選択 & 実ルート精密計算</h4>
            <div style="font-size: 14px; color: #1E3A8A; margin-bottom: 12px;">
                上の比較表を確認の上、<strong>実際に編成するコース数を選択</strong>してください。選択したコース数に対してのみ、詳細な実道路ルート（OSRM）を計算・展開します。
            </div>
        </div>
        """, unsafe_allow_html=True)

        option_map = {}
        for r in st.session_state.trial_reports:
            k = r['courses_num']
            rec_tag = "⭐[推奨] " if k == st.session_state.recommended_k else ""
            status_txt = "✅ 時間内" if r['is_on_time'] else "⚠️ 超過注意"
            label = f"{rec_tag}{k} コース ({status_txt} | 最遅帰着: {r['max_return_time']} | 1コース約{r['cust_per_course']}件)"
            option_map[k] = label

        sel_col1, sel_col2 = st.columns([7, 5])
        with sel_col1:
            chosen_k = st.selectbox(
                "👉 編成するコース数を選択",
                options=list(option_map.keys()),
                format_func=lambda x: option_map[x],
                index=list(option_map.keys()).index(st.session_state.selected_k_human) if st.session_state.selected_k_human in option_map else 0
            )
            st.session_state.selected_k_human = chosen_k

        with sel_col2:
            st.write("")
            st.write("")
            calc_road_btn = st.button(f"🛣️ 選択した【 {chosen_k} コース 】で実道路ルートを計算・展開する", type="primary", use_container_width=True)

        if calc_road_btn:
            with st.spinner(f"{chosen_k} コースの実道路ネットワーク（OSRM）を計算中..."):
                detailed_plan = generate_detailed_course_plan(active_depot_params, customers_df, selected_k=chosen_k)
                st.session_state.preview_courses = detailed_plan
                st.session_state.map_center = None
                st.session_state.map_zoom = None
                st.success(f"{chosen_k} コースでの実道路ルート計算が完了しました！")
                st.rerun()

    # =========================================================================
    # STAGE 3: 実道路ルートプレビュー & マップ直接クリック付替え & 最終確定
    # =========================================================================
    display_courses = st.session_state.preview_courses if st.session_state.preview_courses is not None else confirmed_courses

    if display_courses is None and not st.session_state.trial_reports:
        st.markdown("### 🗺️ 読み込み済み 顧客住所録プロット（コース未編成）")
        st.caption(f"※ 現在は住所録（{len(customers_df)}件）を読み込んだ初期状態です。上の「⚡ 各コース数の比較表を作成する」を押してください。")
        unassigned_map = create_unassigned_customers_map(active_depot_params, customers_df)
        folium_static(unassigned_map, width=1100, height=550)

    elif display_courses is not None:
        is_preview = (st.session_state.preview_courses is not None)

        if is_preview:
            st.markdown(f"""
            <div class="status-box-unconfirmed">
                <h4 style="color: #B45309; margin: 0 0 6px;">📋 実道路ルート プレビュー（選択: 全 {len(display_courses)} コース）</h4>
                <div style="font-size: 14px; color: #78350F;">
                    人間が選択した <strong>{len(display_courses)} コース</strong> の詳細実道路ルートと帰着予定時刻が算出されました。<br/>
                    地図上のピンをクリックしてその場でサクサク別コースへ付替えることができます。確認後、<strong>「✅ こちらで確定しますか？（現場へ配信）」</strong>を押してください。
                </div>
            </div>
            """, unsafe_allow_html=True)

            conf_col1, conf_col2 = st.columns([5, 5])
            with conf_col1:
                if st.button("✅ こちらで確定しますか？（現場へ配信）", type="primary", use_container_width=True):
                    save_confirmed_courses(current_depot['id'], st.session_state.preview_courses)
                    st.session_state.preview_courses = None
                    st.session_state.map_center = None
                    st.session_state.map_zoom = None
                    st.success("🎉 コース編成を確定しました！現場配達員のスマホ画面に配信されました。")
                    st.rerun()
            with conf_col2:
                if st.button("🔄 別のコース数を選び直す（比較表に戻る）", use_container_width=True):
                    st.session_state.preview_courses = None
                    st.session_state.map_center = None
                    st.session_state.map_zoom = None
                    st.rerun()
        else:
            st.markdown(f"""
            <div class="status-box-confirmed">
                <h4 style="color: #166534; margin: 0 0 6px;">🟢 コース編成は確定済みです（現場配信中: 全 {len(display_courses)} コース）</h4>
                <div style="font-size: 14px; color: #14532D;">
                    現場配達員のスマホ画面にこのコース編成が反映されています。
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🔄 コースの確定を解除して再編成する"):
                reset_confirmed_courses(current_depot['id'])
                st.session_state.preview_courses = None
                st.session_state.trial_reports = None
                st.session_state.map_center = None
                st.session_state.map_zoom = None
                st.warning("コース確定を解除しました。初期状態に戻ります。")
                st.rerun()

        # Course Dissolve & Delete Tool
        if len(display_courses) > 1:
            with st.expander("🗑️ 【コースの解体・削除】 特定のコースを0件にして他コースへ再配分する"):
                st.caption("指定したコースの全顧客を、周辺の近接コースへ自動配分して該当コースを完全に削除（コース数を-1）します。")
                del_c1, del_c2 = st.columns([6, 4])
                with del_c1:
                    dissolve_target = st.selectbox("解体・削除するコースを選択", options=list(display_courses.keys()), key="dissolve_target_sel")
                with del_c2:
                    st.write("")
                    if st.button(f"🗑️ 【 {dissolve_target} 】を解体して削除する", type="secondary", use_container_width=True):
                        with st.spinner(f"【{dissolve_target}】の全顧客を他コースへ最適配分し、コースを削除中..."):
                            dissolved_courses = dissolve_course_into_others(display_courses, dissolve_target, active_depot_params)
                            if is_preview:
                                st.session_state.preview_courses = dissolved_courses
                            else:
                                save_confirmed_courses(current_depot['id'], dissolved_courses)
                            st.session_state.editor_version += 1
                            st.success(f"🎉 【{dissolve_target}】を解体・削除し、全 {len(dissolved_courses)} コースに再編成しました！")
                            st.rerun()

        # Summary KPI Cards
        st.markdown(f"### 📊 各コースの運行サマリー（目標: {custom_ret_time} 必着 / 全 {len(display_courses)} コース）")
        kpi_cols = st.columns(len(display_courses))

        highway_settings_changed = False
        for idx, (cid, cdata) in enumerate(display_courses.items()):
            with kpi_cols[idx % len(kpi_cols)]:
                is_on_time = cdata['estimated_return_time'] <= custom_ret_time
                status_color = "#16A34A" if is_on_time else "#DC2626"
                time_badge = f"✅ {custom_ret_time}前帰着" if is_on_time else "⚠️ 超過"
                curr_avoid = cdata.get('avoid_highways', True)

                st.markdown(f"""
                <div style="border-top: 4px solid {cdata['color']}; padding: 10px; background: white; border-radius: 6px; border-left: 1px solid #ddd; border-right: 1px solid #ddd; border-bottom: 1px solid #ddd;">
                    <div style="display: flex; justify-content: space-between;">
                        <strong style="color: {cdata['color']}; font-size: 15px;">{cid}</strong>
                        <span style="font-size: 11px; color: {status_color}; font-weight: bold;">{time_badge}</span>
                    </div>
                    <div style="font-size: 20px; font-weight: bold; margin: 4px 0;">{cdata['total_customers']} <span style="font-size: 12px; font-weight: normal;">件</span></div>
                    <div style="font-size: 11px; color: #475569;">実走: <strong>{cdata['total_distance_km']} km</strong></div>
                    <div style="font-size: 12px; color: {status_color}; font-weight: bold; margin-top: 2px;">帰着予定: {cdata['estimated_return_time']}</div>
                </div>
                """, unsafe_allow_html=True)

                # Avoid Highways toggle per course
                avoid_val = st.checkbox("🚫 高速道路を除外", value=curr_avoid, key=f"avoid_hw_{cid}_{st.session_state.editor_version}")
                if avoid_val != curr_avoid:
                    cdata['avoid_highways'] = avoid_val
                    highway_settings_changed = True

        if highway_settings_changed:
            with st.spinner("🔄 高速道路除外設定を適用し、実道路ルートを再計算中..."):
                import copy
                updated_c = copy.deepcopy(display_courses)
                for c_k, c_v in updated_c.items():
                    updated_c[c_k] = recalculate_single_course_route(c_v, active_depot_params, avoid_highways=c_v.get('avoid_highways', True))

                if is_preview:
                    st.session_state.preview_courses = updated_c
                else:
                    save_confirmed_courses(current_depot['id'], updated_c)
                st.session_state.editor_version += 1
                st.toast("🎉 高速道路除外設定を反映してルートを再計算しました！", icon="🛣️")
                st.rerun()

        st.markdown("---")

        # Map & Table Tabs
        tab_map, tab_table = st.tabs(["🗺️ 実道路配送マップ（ピンをクリックして付替え）", "📋 コース別 配達順リスト"])

        with tab_map:
            st.info("💡 **【複数まとめ選択対応】** 上部の「🔲 矩形ドラッグで囲む」や「✏️ フリーハンド投げ縄」で地図上のピンをまとめて囲むか、**Shiftキーを押しながらドラッグ** すると複数顧客を一括選択できます。移動先コースボタンを押すだけで **10〜20件を一瞬でまとめてコース変更** できます！")

            # Render Instant Standalone Map Editor Component (ZERO RELOAD!)
            editor_result = interactive_map_editor(
                active_depot_params,
                display_courses,
                initial_center=st.session_state.map_center,
                initial_zoom=st.session_state.map_zoom,
                key=f"interactive_editor_{len(display_courses)}_{st.session_state.editor_version}"
            )

            # Process Save event from JS
            if editor_result and isinstance(editor_result, dict):
                reassigns = editor_result.get('reassignments', {})
                new_center = editor_result.get('center')
                new_zoom = editor_result.get('zoom')

                if reassigns:
                    with st.spinner(f"🔄 {len(reassigns)} 件のコース変更を反映し、実道路ルートを再計算中..."):
                        import copy
                        updated_courses = copy.deepcopy(display_courses)
                        for cid_str, r_info in reassigns.items():
                            from_c = r_info['from_course']
                            to_c = r_info['to_course']
                            updated_courses = reassign_customer_between_courses(
                                updated_courses, str(cid_str), from_c, to_c, active_depot_params
                            )

                        if is_preview:
                            st.session_state.preview_courses = updated_courses
                        else:
                            save_confirmed_courses(current_depot['id'], updated_courses)

                        st.session_state.editor_version += 1
                        st.session_state.map_center = new_center
                        st.session_state.map_zoom = new_zoom
                        st.toast(f"🎉 {len(reassigns)} 件のコース付替えを完了し、実道ルートを再計算しました！", icon="🚚")
                        st.rerun()

        with tab_table:
            for cid, cdata in display_courses.items():
                with st.expander(f"📌 {cid} : 合計 {cdata['total_customers']} 件 (戸建: {cdata['house_count']} / 集合: {cdata['building_count']}) | 帰着予定 {cdata['estimated_return_time']}"):
                    df_display = cdata['customers_df'][['delivery_seq', 'estimated_arrival', 'name', 'dwelling_type', 'address', 'current_item', 'drop_location_text']].copy()
                    df_display.columns = ['配達順', '到着目安', '顧客名', '住居種別', '住所', 'お届け商品', '荷物設置場所']
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# MODE 2: 配達員画面（配送ユーザー専用・確定コース自動表示・打刻・現在地車ピン）
# -------------------------------------------------------------
elif app_mode in ["📱 配達員: スマホ連続配達ナビ", "📱 配達員画面プレビュー"]:
    current_depot = get_current_depot()
    logged_user = get_current_user()
    
    confirmed_courses = load_confirmed_courses(current_depot['id'])
    
    if not confirmed_courses:
        st.warning(f"⚠️ 現在、{current_depot['name']} のコース編成は未確定です。\n\n管理者がコースを確定するまでお待ちください。")
        if is_admin:
            if st.button("👑 管理画面へ移動してコースを確定する"):
                st.session_state.current_user_id = "admin01"
                st.rerun()
        st.stop()

    assigned_course = get_driver_course(current_depot['id'], logged_user['user_id'])
    if not assigned_course or assigned_course not in confirmed_courses:
        assigned_course = list(confirmed_courses.keys())[0]

    header_col1, header_col2 = st.columns([7, 3])
    with header_col1:
        st.markdown(f"<div class='main-header'>📱 {logged_user['name']} さんの配達ナビ</div>", unsafe_allow_html=True)
    with header_col2:
        selected_course_id = st.selectbox("担当コース", options=list(confirmed_courses.keys()), index=list(confirmed_courses.keys()).index(assigned_course))

    my_course = confirmed_courses[selected_course_id]
    my_df = my_course['customers_df'].reset_index(drop=True)
    total_in_course = len(my_df)

    today = get_today_str()
    logs_data = load_delivery_logs()
    log_key = f"{today}_{current_depot['id']}_{selected_course_id}"
    current_log = logs_data.get(log_key, {
        "departure_time": None,
        "return_time": None,
        "deliveries": {}
    })

    # --- STEP 1: 事務所出発打刻 ---
    if not current_log.get("departure_time"):
        st.markdown(f"""
        <div style="background: #EFF6FF; border: 2px dashed #3B82F6; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 20px;">
            <h3 style="color: #1E3A8A; margin-bottom: 8px;">🏢 おはようございます！</h3>
            <p style="color: #475569; font-size: 15px;">本日担当: <strong>{selected_course_id}</strong> (合計 {total_in_course} 件)<br/>
            目標帰着時刻: <strong>{my_course['estimated_return_time']}</strong><br/>
            積込が完了したら「事務所を出発」を押して配達を開始してください。</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 事務所を出発する (出発時間を記録)", type="primary", use_container_width=True):
            record_departure(current_depot['id'], selected_course_id, logged_user['user_id'])
            st.session_state.driver_current_idx = 0
            st.session_state.trigger_voice = True
            st.rerun()
        st.stop()

    # --- STEP 2: 配達中ナビゲーション ---
    completed_deliveries = current_log.get("deliveries", {})
    completed_count = len(completed_deliveries)
    is_all_finished = (completed_count >= total_in_course)

    if completed_count < total_in_course and not st.session_state.get('manual_nav', False):
        for idx_check, row_check in my_df.iterrows():
            if str(row_check['customer_id']) not in completed_deliveries:
                st.session_state.driver_current_idx = idx_check
                break

    curr_idx = st.session_state.driver_current_idx
    if curr_idx >= total_in_course:
        curr_idx = total_in_course - 1

    curr_row = my_df.iloc[curr_idx]
    cust_id = str(curr_row['customer_id'])
    seq = curr_row['delivery_seq']
    name = curr_row['name']
    arr = curr_row['estimated_arrival']
    addr = curr_row['address']
    dwell = curr_row['dwelling_type']
    item = curr_row.get('current_item', 'プチママ 2人用')
    drop_text = curr_row.get('drop_location_text', '玄関前')
    photo_name = curr_row.get('photo_filename', '')

    voice_sentence = f"次は、{seq}番、{name}様です。{dwell}、お届け商品は、{item}です。荷物は、{drop_text}に設置してください。"

    if st.session_state.trigger_voice:
        play_voice_guidance(voice_sentence)
        st.session_state.trigger_voice = False

    dep_time_str = current_log.get('departure_time', '-')
    progress_val = min(1.0, completed_count / total_in_course)
    
    top_col1, top_col2, top_col3 = st.columns([3, 4, 3])
    with top_col1:
        st.caption(f"🏢 出発打刻: **{dep_time_str}**")
    with top_col2:
        auto_voice_toggle = st.checkbox("📢 自動音声案内", value=True)
    with top_col3:
        if current_log.get('return_time'):
            st.success(f"🏁 帰着打刻: **{current_log['return_time']}**")

    st.progress(progress_val, text=f"配達進捗: {completed_count} / {total_in_course} 件完了 ({int(progress_val*100)}%)")

    if is_all_finished and not current_log.get("return_time"):
        st.balloons()
        st.success("🎉 全ての配達が完了しました！事務所へお戻りください。")
        if st.button("🏢 事務所に帰着した (帰着時間を記録)", type="primary", use_container_width=True):
            record_return(current_depot['id'], selected_course_id)
            st.rerun()

    is_cust_done = cust_id in completed_deliveries
    done_stamp = f" [✅ {completed_deliveries[cust_id]['completed_at']} 完了]" if is_cust_done else ""

    st.markdown(f"""
    <div class="driver-nav-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div>
                <span class="driver-badge" style="background: {my_course['color']};">配達順 #{seq}</span>
                <span style="font-size: 22px; font-weight: bold; color: #1E293B;">{name} 様</span>
                <span style="color: #16A34A; font-weight: bold; font-size: 14px;">{done_stamp}</span>
            </div>
            <div style="background: #EEF2FF; color: #4338CA; padding: 6px 12px; border-radius: 6px; font-weight: bold; font-size: 14px;">
                ⏰ 到着目安 {arr}
            </div>
        </div>
        <div style="font-size: 15px; color: #334155; margin-bottom: 8px;">
            📍 <strong>住所:</strong> {addr}
        </div>
        <div style="font-size: 15px; margin-bottom: 12px;">
            🍱 <strong>お届け品:</strong> <span style="color: #D97706; font-weight: bold;">{item}</span> 
            <span style="background: #F1F5F9; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin-left: 6px;">{dwell}</span>
        </div>
    """, unsafe_allow_html=True)

    c_info1, c_info2 = st.columns([6, 4])
    with c_info1:
        st.markdown(f"""
        <div style="background: #FFFBEB; border: 2px solid #FCD34D; padding: 12px 16px; border-radius: 8px; font-size: 15px; margin-bottom: 12px;">
            <div style="color: #B45309; font-weight: bold; margin-bottom: 4px; font-size: 13px;">📦 荷物設置場所の指示:</div>
            <div style="font-size: 16px; font-weight: bold; color: #78350F;">{drop_text}</div>
        </div>
        """, unsafe_allow_html=True)

        b_c1, b_c2 = st.columns(2)
        with b_c1:
            if st.button("🔊 音声案内を再生", use_container_width=True):
                play_voice_guidance(voice_sentence)
        with b_c2:
            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={curr_row['lat']},{curr_row['lng']}"
            st.markdown(f"""
            <a href="{maps_url}" target="_blank" style="display: block; text-align: center; background: #2563EB; color: white; text-decoration: none; padding: 8px 12px; border-radius: 6px; font-size: 13px; font-weight: bold;">
                🗺️ Googleナビを開く
            </a>
            """, unsafe_allow_html=True)

    with c_info2:
        if photo_name:
            photo_path = os.path.join(PHOTOS_DIR, photo_name)
            if os.path.exists(photo_path):
                img = Image.open(photo_path)
                st.image(img, caption=f"📷 設置場所写真: {drop_text[:12]}...", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Action buttons
    btn_col1, btn_col2, btn_col3 = st.columns([2, 6, 2])
    with btn_col1:
        if st.button("◀ 前の配達先へ", disabled=(curr_idx == 0), use_container_width=True):
            st.session_state.driver_current_idx -= 1
            st.session_state.manual_nav = True
            if auto_voice_toggle:
                st.session_state.trigger_voice = True
            st.rerun()

    with btn_col2:
        if not is_cust_done:
            if st.button("📦 荷物を設置完了（時刻打刻して次へ進む）", type="primary", use_container_width=True):
                record_delivery_step(current_depot['id'], selected_course_id, cust_id, seq, name)
                if curr_idx < total_in_course - 1:
                    st.session_state.driver_current_idx += 1
                    st.session_state.manual_nav = False
                    if auto_voice_toggle:
                        st.session_state.trigger_voice = True
                st.rerun()
        else:
            if st.button("✅ 設置完了済（次の配達先へ進む）", type="primary", use_container_width=True):
                if curr_idx < total_in_course - 1:
                    st.session_state.driver_current_idx += 1
                    st.session_state.manual_nav = False
                    if auto_voice_toggle:
                        st.session_state.trigger_voice = True
                st.rerun()

    with btn_col3:
        if st.button("⏩ スキップ（次へ）", disabled=(curr_idx == total_in_course - 1), use_container_width=True):
            st.session_state.driver_current_idx += 1
            st.session_state.manual_nav = True
            if auto_voice_toggle:
                st.session_state.trigger_voice = True
            st.rerun()

    # Mini Map with Moving Vehicle Icon
    st.markdown("### 🗺️ 現在地・走行ルート マップ")
    with st.expander("🗺️ 配達ルート地図を表示（青いトラック🚚が現在地に合わせて追従）", expanded=True):
        road_geom = my_course.get('road_geometry', [])
        driver_map = create_driver_current_map(current_depot, my_df, curr_idx, road_geom=road_geom)
        folium_static(driver_map, width=1000, height=380)

    # Overview List
    with st.expander("📋 本日の全配達リスト一覧 & 打刻状況"):
        list_rows = []
        for i, r in my_df.iterrows():
            cid_str = str(r['customer_id'])
            if cid_str in completed_deliveries:
                st_txt = f"✅ 完了 ({completed_deliveries[cid_str]['completed_at']})"
            elif i == curr_idx:
                st_txt = "🚚 配達中"
            else:
                st_txt = "⏳ 未配達"
            list_rows.append({
                "状態": st_txt,
                "順": r['delivery_seq'],
                "目安時刻": r['estimated_arrival'],
                "お名前": r['name'],
                "住所": r['address'],
                "商品": r['current_item'],
                "置き場所": r['drop_location_text']
            })
        st.dataframe(pd.DataFrame(list_rows), use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# MODE 3: コース担当者アサイン
# -------------------------------------------------------------
elif app_mode == "👥 コース担当者アサイン":
    st.markdown("<div class='main-header'>👥 配送コース担当者アサイン & ユーザー管理</div>", unsafe_allow_html=True)
    current_depot = get_current_depot()
    confirmed_courses = load_confirmed_courses(current_depot['id'])
    
    if not confirmed_courses:
        st.warning("⚠️ まだコース編成が確定していません。「🖥️ 管理者: コース編成・確定」からコースを確定してください。")
        st.stop()

    assignments = load_assignments().get(current_depot['id'], {})
    all_users = load_users()
    drivers = [u for u in all_users if u['role'] == 'driver']
    driver_dict = {d['user_id']: d['name'] for d in drivers}
    driver_dict[""] = "（未割り当て）"

    with st.form("assign_form"):
        st.subheader(f"📍 {current_depot['name']} 担当者割り当て")
        new_assigns = {}
        for cid in confirmed_courses.keys():
            curr_driver = assignments.get(cid, "")
            idx = list(driver_dict.keys()).index(curr_driver) if curr_driver in driver_dict else 0
            col_a1, col_a2 = st.columns([3, 7])
            with col_a1:
                st.markdown(f"**{cid}** ({confirmed_courses[cid]['total_customers']} 件)")
            with col_a2:
                selected_d = st.selectbox(
                    f"{cid} の担当配達員",
                    options=list(driver_dict.keys()),
                    format_func=lambda x: driver_dict.get(x, x),
                    index=idx,
                    key=f"assign_{cid}"
                )
                new_assigns[cid] = selected_d
            st.markdown("---")

        if st.form_submit_button("💾 コース担当者の割り当てを保存する", type="primary"):
            for cid, uid in new_assigns.items():
                set_course_driver(current_depot['id'], cid, uid)
            st.success("コース担当者を更新しました！")
            st.rerun()

# -------------------------------------------------------------
# MODE 4: 本日の配達実績ログ・進捗
# -------------------------------------------------------------
elif app_mode == "📊 本日の配達実績ログ・進捗":
    st.markdown("<div class='main-header'>📊 本日の配達実績ログ & リアルタイム運行進捗</div>", unsafe_allow_html=True)
    current_depot = get_current_depot()
    confirmed_courses = load_confirmed_courses(current_depot['id'])

    if not confirmed_courses:
        st.warning("コース編成が未確定です。")
        st.stop()

    today = get_today_str()
    logs_data = load_delivery_logs()
    assignments = load_assignments().get(current_depot['id'], {})
    users_map = {u['user_id']: u['name'] for u in st.session_state.users}

    summary_rows = []
    for cid, cinfo in confirmed_courses.items():
        driver_id = assignments.get(cid, "-")
        driver_name = users_map.get(driver_id, "未割当")
        total_cnt = cinfo['total_customers']
        
        log_key = f"{today}_{current_depot['id']}_{cid}"
        course_log = logs_data.get(log_key, {})
        dep_time = course_log.get('departure_time', '未出発')
        ret_time = course_log.get('return_time', '配達中' if dep_time != '未出発' else '-')
        deliveries = course_log.get('deliveries', {})
        done_cnt = len(deliveries)
        progress_pct = f"{int((done_cnt / total_cnt) * 100)}%" if total_cnt > 0 else "0%"
        last_time = list(deliveries.values())[-1].get('completed_at', '-') if deliveries else "-"

        summary_rows.append({
            "コース": cid,
            "担当配達員": driver_name,
            "総件数": total_cnt,
            "完了件数": done_cnt,
            "進捗率": progress_pct,
            "出発打刻": dep_time,
            "直近打刻": last_time,
            "帰着打刻": ret_time
        })

    st.subheader(f"📈 拠点全体 運行状況サマリー ({today})")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# MODE 5: 拠点・運行設定
# -------------------------------------------------------------
elif app_mode == "🏢 拠点・運行設定":
    st.markdown("<div class='main-header'>🏢 拠点登録 & 運行パラメータ設定</div>", unsafe_allow_html=True)
    current_depot = get_current_depot()
    if current_depot:
        with st.form("edit_depot_form"):
            st.subheader(f"拠点編集: {current_depot['name']}")
            e_name = st.text_input("拠点名", value=current_depot['name'])
            e_addr = st.text_input("拠点住所", value=current_depot['address'])
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_lat = st.number_input("緯度", value=float(current_depot['lat']), format="%.6f")
                e_dep_time = st.text_input("標準出発時刻", value=current_depot.get('default_departure_time', '09:30'))
                e_house_svc = st.number_input("戸建て作業時間 (分)", min_value=1, max_value=30, value=int(current_depot.get('house_service_minutes', 4)))
            with col_e2:
                e_lng = st.number_input("経度", value=float(current_depot['lng']), format="%.6f")
                e_ret_time = st.text_input("目標帰着時刻", value=current_depot.get('default_return_time', '16:00'))
                e_bldg_svc = st.number_input("集合住宅作業時間 (分)", min_value=1, max_value=30, value=int(current_depot.get('building_service_minutes', 8)))
                e_break_min = st.number_input("昼休憩時間 (分)", min_value=0, max_value=120, value=int(current_depot.get('default_break_minutes', 60)))

            if st.form_submit_button("💾 設定を保存する", type="primary"):
                updated_depot = {
                    "id": current_depot['id'], "name": e_name, "address": e_addr, "lat": e_lat, "lng": e_lng,
                    "default_departure_time": e_dep_time, "default_return_time": e_ret_time,
                    "default_break_minutes": e_break_min, "house_service_minutes": e_house_svc,
                    "building_service_minutes": e_bldg_svc
                }
                add_or_update_depot(updated_depot)
                st.session_state.depots = load_depots()
                st.success("設定を更新しました！")
                st.rerun()

# -------------------------------------------------------------
# MODE 6: 顧客住所録マスター
# -------------------------------------------------------------
elif app_mode == "📦 顧客住所録マスター":
    st.markdown("<div class='main-header'>👥 顧客住所録マスター & 荷物設置場所管理</div>", unsafe_allow_html=True)
    current_depot = get_current_depot()
    cust_df = load_customers(current_depot['id'] if current_depot else None)

    tab_c1, tab_c2 = st.tabs(["📋 顧客住所録一覧", "📷 荷物設置場所・写真更新"])
    with tab_c1:
        st.dataframe(cust_df[['customer_id', 'name', 'dwelling_type', 'address', 'drop_location_text', 'photo_filename']], use_container_width=True, hide_index=True)
    with tab_c2:
        cust_options = {f"{row['customer_id']} : {row['name']} 様 ({row['address'][:18]}...)": row['customer_id'] for _, row in cust_df.iterrows()}
        selected_cust_label = st.selectbox("対象顧客を選択", options=list(cust_options.keys()))
        if selected_cust_label:
            cid = cust_options[selected_cust_label]
            target_row = cust_df[cust_df['customer_id'] == cid].iloc[0]
            col_ed1, col_ed2 = st.columns([6, 4])
            with col_ed1:
                new_drop_text = st.text_area("📦 荷物設置場所の指示テキスト", value=str(target_row.get('drop_location_text', '')))
                uploaded_photo = st.file_uploader("📷 設置場所の写真画像をアップロード", type=["jpg", "jpeg", "png"])
                if st.button("💾 置き場所情報を更新する", type="primary"):
                    photo_fname = target_row.get('photo_filename', '')
                    if uploaded_photo:
                        photo_fname = f"cust_{cid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        save_path = os.path.join(PHOTOS_DIR, photo_fname)
                        img = Image.open(uploaded_photo)
                        img.save(save_path)
                    update_customer_drop_info(cid, new_drop_text, photo_fname if uploaded_photo else None)
                    st.success(f"{target_row['name']} 様の情報を更新しました！")
                    st.rerun()
            with col_ed2:
                curr_photo = target_row.get('photo_filename', '')
                if curr_photo:
                    photo_path = os.path.join(PHOTOS_DIR, curr_photo)
                    if os.path.exists(photo_path):
                        img = Image.open(photo_path)
                        st.image(img, caption=f"現在の写真 ({curr_photo})", use_container_width=True)
