import json
import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DEPOTS_FILE = os.path.join(DATA_DIR, 'depots.json')
CUSTOMERS_FILE = os.path.join(DATA_DIR, 'sample_customers.csv')
PHOTOS_DIR = os.path.join(DATA_DIR, 'photos')
CONFIRMED_PLAN_FILE = os.path.join(DATA_DIR, 'confirmed_courses.json')

def load_depots():
    if not os.path.exists(DEPOTS_FILE):
        return []
    with open(DEPOTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_depots(depots):
    with open(DEPOTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(depots, f, ensure_ascii=False, indent=2)

def add_or_update_depot(depot_data):
    depots = load_depots()
    found = False
    for i, d in enumerate(depots):
        if d['id'] == depot_data['id']:
            depots[i] = depot_data
            found = True
            break
    if not found:
        depots.append(depot_data)
    save_depots(depots)

def delete_depot(depot_id):
    depots = load_depots()
    depots = [d for d in depots if d['id'] != depot_id]
    save_depots(depots)

def load_customers(depot_id=None):
    if not os.path.exists(CUSTOMERS_FILE):
        return pd.DataFrame()
    df = pd.read_csv(CUSTOMERS_FILE, encoding='utf-8-sig')
    if depot_id:
        df = df[df['depot_id'] == depot_id].copy()
    return df

def save_customers(df):
    df.to_csv(CUSTOMERS_FILE, index=False, encoding='utf-8-sig')

def update_customer_drop_info(customer_id, drop_text, photo_filename=None):
    df = load_customers()
    idx = df[df['customer_id'] == customer_id].index
    if not idx.empty:
        df.loc[idx, 'drop_location_text'] = drop_text
        if photo_filename:
            df.loc[idx, 'photo_filename'] = photo_filename
        save_customers(df)
        return True
    return False

def load_confirmed_courses(depot_id):
    """
    確定済みコースを読み込み（なければNone）
    """
    if os.path.exists(CONFIRMED_PLAN_FILE):
        try:
            with open(CONFIRMED_PLAN_FILE, 'r', encoding='utf-8') as f:
                all_plans = json.load(f)
                depot_plan = all_plans.get(depot_id)
                if depot_plan:
                    # Reconstruct DataFrames
                    reconstructed = {}
                    for cid, cinfo in depot_plan.items():
                        c_copy = dict(cinfo)
                        if 'customers_list' in c_copy:
                            c_copy['customers_df'] = pd.DataFrame(c_copy['customers_list'])
                        reconstructed[cid] = c_copy
                    return reconstructed
        except Exception:
            pass
    return None

def save_confirmed_courses(depot_id, courses_dict):
    """
    確定済みコースを保存（DataFrameをシリアライズ）
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    all_plans = {}
    if os.path.exists(CONFIRMED_PLAN_FILE):
        try:
            with open(CONFIRMED_PLAN_FILE, 'r', encoding='utf-8') as f:
                all_plans = json.load(f)
        except Exception:
            all_plans = {}

    serializable = {}
    for cid, cinfo in courses_dict.items():
        c_copy = dict(cinfo)
        if 'customers_df' in c_copy and isinstance(c_copy['customers_df'], pd.DataFrame):
            c_copy['customers_list'] = c_copy['customers_df'].to_dict(orient='records')
            del c_copy['customers_df']
        serializable[cid] = c_copy

    all_plans[depot_id] = serializable
    with open(CONFIRMED_PLAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_plans, f, ensure_ascii=False, indent=2)

def reset_confirmed_courses(depot_id=None):
    if depot_id and os.path.exists(CONFIRMED_PLAN_FILE):
        try:
            with open(CONFIRMED_PLAN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if depot_id in data:
                del data[depot_id]
            with open(CONFIRMED_PLAN_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    elif not depot_id and os.path.exists(CONFIRMED_PLAN_FILE):
        try:
            os.remove(CONFIRMED_PLAN_FILE)
        except Exception:
            pass
