import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, 'course_assignments.json')
LOGS_FILE = os.path.join(DATA_DIR, 'delivery_logs.json')

# Initial default users
DEFAULT_USERS = [
    {"user_id": "admin01", "name": "山田 営業所長", "role": "admin", "depot_id": "depot-001", "pin": "1234"},
    {"user_id": "driver01", "name": "佐藤 花子 (京都東)", "role": "driver", "depot_id": "depot-001", "pin": "1111"},
    {"user_id": "driver02", "name": "鈴木 美咲 (京都東)", "role": "driver", "depot_id": "depot-001", "pin": "2222"},
    {"user_id": "driver03", "name": "高橋 友香 (京都東)", "role": "driver", "depot_id": "depot-001", "pin": "3333"},
    {"user_id": "driver04", "name": "伊藤 葵 (京都東)", "role": "driver", "depot_id": "depot-001", "pin": "4444"},
    {"user_id": "driver05", "name": "渡辺 結衣 (京都東)", "role": "driver", "depot_id": "depot-001", "pin": "5555"},
    {"user_id": "driver06", "name": "田中 陽子 (京都南)", "role": "driver", "depot_id": "depot-002", "pin": "6666"}
]

# Initial course assignments
DEFAULT_ASSIGNMENTS = {
    "depot-001": {
        "コース-01": "driver01",
        "コース-02": "driver02",
        "コース-03": "driver03",
        "コース-04": "driver04",
        "コース-05": "driver05"
    },
    "depot-002": {
        "コース-01": "driver06"
    }
}

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    save_users(DEFAULT_USERS)
    return DEFAULT_USERS

def save_users(users):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def add_user(user_id, name, role, depot_id, pin="1234"):
    users = load_users()
    users = [u for u in users if u['user_id'] != user_id]
    users.append({"user_id": user_id, "name": name, "role": role, "depot_id": depot_id, "pin": pin})
    save_users(users)

def load_assignments():
    if os.path.exists(ASSIGNMENTS_FILE):
        try:
            with open(ASSIGNMENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    save_assignments(DEFAULT_ASSIGNMENTS)
    return DEFAULT_ASSIGNMENTS

def save_assignments(assignments):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ASSIGNMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(assignments, f, ensure_ascii=False, indent=2)

def set_course_driver(depot_id, course_id, driver_user_id):
    assigns = load_assignments()
    if depot_id not in assigns:
        assigns[depot_id] = {}
    assigns[depot_id][course_id] = driver_user_id
    save_assignments(assigns)

def get_driver_course(depot_id, driver_user_id):
    assigns = load_assignments()
    depot_assigns = assigns.get(depot_id, {})
    for course_id, uid in depot_assigns.items():
        if uid == driver_user_id:
            return course_id
    return None

def load_delivery_logs():
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_delivery_logs(logs):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

def record_departure(depot_id, course_id, user_id):
    today = get_today_str()
    logs = load_delivery_logs()
    key = f"{today}_{depot_id}_{course_id}"
    if key not in logs:
        logs[key] = {
            "date": today,
            "depot_id": depot_id,
            "course_id": course_id,
            "user_id": user_id,
            "departure_time": datetime.now().strftime('%H:%M:%S'),
            "return_time": None,
            "deliveries": {}
        }
    else:
        logs[key]["departure_time"] = datetime.now().strftime('%H:%M:%S')
    save_delivery_logs(logs)
    return logs[key]

def record_delivery_step(depot_id, course_id, customer_id, seq, cust_name):
    today = get_today_str()
    logs = load_delivery_logs()
    key = f"{today}_{depot_id}_{course_id}"
    now_str = datetime.now().strftime('%H:%M:%S')
    if key not in logs:
        logs[key] = {
            "date": today,
            "depot_id": depot_id,
            "course_id": course_id,
            "departure_time": now_str,
            "return_time": None,
            "deliveries": {}
        }
    logs[key]["deliveries"][str(customer_id)] = {
        "seq": seq,
        "name": cust_name,
        "completed_at": now_str
    }
    save_delivery_logs(logs)
    return logs[key]

def record_return(depot_id, course_id):
    today = get_today_str()
    logs = load_delivery_logs()
    key = f"{today}_{depot_id}_{course_id}"
    now_str = datetime.now().strftime('%H:%M:%S')
    if key in logs:
        logs[key]["return_time"] = now_str
    save_delivery_logs(logs)
    return logs.get(key)
