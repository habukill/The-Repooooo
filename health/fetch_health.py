import json
import os
from datetime import datetime, timezone, timedelta, date as date_type

ICT = timezone(timedelta(hours=7))
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests

HEALTH_SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
DIR = os.path.dirname(__file__)


def get_credentials():
    creds = None
    token_path = os.path.join(DIR, "token.json")
    creds_path = os.path.join(DIR, "credentials.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, HEALTH_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, HEALTH_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def get_drive_credentials():
    creds = None
    token_path = os.path.join(DIR, "drive_token.json")
    creds_path = os.path.join(DIR, "credentials.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_daily_rollup(creds, data_type, max_range_days=90):
    headers = {"Authorization": f"Bearer {creds.token}"}
    results = []
    end_dt = datetime.now(ICT).date()
    start_dt = end_dt.replace(year=end_dt.year - 2)
    chunk = timedelta(days=max_range_days)
    current_start = start_dt
    while current_start < end_dt:
        current_end = min(current_start + chunk, end_dt)
        body = {
            "range": {
                "start": {"date": {"year": current_start.year, "month": current_start.month, "day": current_start.day}},
                "end":   {"date": {"year": current_end.year,   "month": current_end.month,   "day": current_end.day}},
            }
        }
        page_token = None
        while True:
            if page_token:
                body["pageToken"] = page_token
            r = requests.post(f"{BASE_URL}/{data_type}/dataPoints:dailyRollUp", headers=headers, json=body)
            if not r.ok:
                print(f"ERROR {r.status_code} for {data_type} dailyRollUp: {r.text}")
                break
            data = r.json()
            results.extend(data.get("rollupDataPoints", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        current_start = current_end
    return results


def fetch(creds, data_type, paginate=False):
    headers = {"Authorization": f"Bearer {creds.token}"}
    results = []
    params = {}
    while True:
        r = requests.get(f"{BASE_URL}/{data_type}/dataPoints", headers=headers, params=params)
        if not r.ok:
            print(f"ERROR {r.status_code} for {data_type}: {r.text}")
            break
        data = r.json()
        results.extend(data.get("dataPoints", []))
        next_token = data.get("nextPageToken")
        if not paginate or not next_token:
            break
        params = {"pageToken": next_token}
    return results


def fmt_date(d):
    return f"{d['year']}-{d['month']:02d}-{d['day']:02d}"


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_and_merge(creds):
    """Fetch all data types and upsert into health_data.json."""
    json_path = os.path.join(DIR, "health_data.json")
    db = load_json(json_path)

    # --- Sleep ---
    db.setdefault("sleep", {})
    for p in fetch(creds, "sleep"):
        s = p.get("sleep", {})
        interval = s.get("interval", {})
        summary = s.get("summary", {})
        raw_start = interval.get("startTime", "")
        raw_end = interval.get("endTime", "")
        if not raw_start:
            continue
        dt_start = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).astimezone(ICT)
        dt_end = datetime.fromisoformat(raw_end.replace("Z", "+00:00")).astimezone(ICT) if raw_end else None
        key = f"{dt_start.strftime('%Y-%m-%d')}_{dt_start.strftime('%H%M')}"
        minutes_asleep = int(summary.get("minutesAsleep", 0))
        minutes_in_bed = int(summary.get("minutesInSleepPeriod", 0))
        stages = {st["type"]: int(st["minutes"]) for st in summary.get("stagesSummary", [])}
        new_stages = [
            {
                "start": datetime.fromisoformat(st.get("startTime", "").replace("Z", "+00:00")).astimezone(ICT).strftime("%H:%M"),
                "end": datetime.fromisoformat(st.get("endTime", "").replace("Z", "+00:00")).astimezone(ICT).strftime("%H:%M"),
                "type": st.get("type", ""),
                "minutes": int((
                    datetime.fromisoformat(st.get("endTime", "").replace("Z", "+00:00")) -
                    datetime.fromisoformat(st.get("startTime", "").replace("Z", "+00:00"))
                ).total_seconds() / 60),
            }
            for st in s.get("stages", [])
            if st.get("startTime") and st.get("endTime")
        ]
        existing = db["sleep"].get(key, {})
        db["sleep"][key] = {
            "date": dt_start.strftime("%Y-%m-%d"),
            "start": dt_start.strftime("%H:%M"),
            "end": dt_end.strftime("%H:%M") if dt_end else "-",
            "duration_h": round(minutes_asleep / 60, 1),
            "bed_h": round(minutes_in_bed / 60, 1),
            "efficiency": f"{int(minutes_asleep / minutes_in_bed * 100)}%" if minutes_in_bed > 0 else "-",
            "light_m": stages.get("LIGHT", 0),
            "deep_m": stages.get("DEEP", 0),
            "rem_m": stages.get("REM", 0),
            "awake_m": stages.get("AWAKE", 0),
            "restless_m": stages.get("RESTLESS", 0),
            "stages": new_stages if new_stages else existing.get("stages", []),
        }

    # --- Resting HR ---
    db.setdefault("resting_hr", {})
    for p in fetch(creds, "daily-resting-heart-rate"):
        d = p.get("dailyRestingHeartRate", {})
        if "date" in d:
            db["resting_hr"][fmt_date(d["date"])] = d.get("beatsPerMinute")

    # --- HRV ---
    db.setdefault("hrv", {})
    for p in fetch(creds, "daily-heart-rate-variability"):
        d = p.get("dailyHeartRateVariability", {})
        if "date" in d:
            val = d.get("averageHeartRateVariabilityMilliseconds", 0)
            db["hrv"][fmt_date(d["date"])] = round(val, 1)

    # --- Steps ---
    db.setdefault("steps", {})
    for p in fetch(creds, "steps", paginate=True):
        d = p.get("steps", {})
        date_obj = d.get("interval", {}).get("civilStartTime", {}).get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            db["steps"][date] = db["steps"].get(date, 0) + int(d.get("count", 0))

    # --- Active Zone Minutes ---
    db.setdefault("azm", {})
    for p in fetch(creds, "active-zone-minutes", paginate=True):
        d = p.get("activeZoneMinutes", {})
        date_obj = d.get("interval", {}).get("civilStartTime", {}).get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            db["azm"][date] = db["azm"].get(date, 0) + int(d.get("activeZoneMinutes", 0))

    # --- Calories ---
    db.setdefault("calories", {})
    for p in fetch(creds, "active-energy-burned", paginate=True):
        d = p.get("activeEnergyBurned", {})
        date_obj = d.get("interval", {}).get("civilStartTime", {}).get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            existing = db["calories"].setdefault(date, {})
            existing["active"] = existing.get("active", 0) + round(d.get("kcal", 0), 1)
    for p in fetch_daily_rollup(creds, "total-calories", max_range_days=14):
        date_obj = p.get("civilStartTime", {}).get("date")
        d = p.get("totalCalories", {})
        if date_obj and d:
            date = fmt_date(date_obj)
            kcal = d.get("kcal_sum") or d.get("kcalSum") or d.get("kcal") or 0
            db["calories"].setdefault(date, {})["total"] = int(kcal)

    # --- Body Composition ---
    db.setdefault("body", {})
    for p in fetch(creds, "weight", paginate=True):
        d = p.get("weight", {})
        date_obj = d.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if date_obj:
            grams = d.get("weightGrams")
            if grams:
                db["body"].setdefault(fmt_date(date_obj), {})["weight_kg"] = round(float(grams) / 1000, 1)
    for p in fetch(creds, "body-fat", paginate=True):
        d = p.get("bodyFat", {})
        date_obj = d.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if date_obj:
            pct = d.get("percentage")
            if pct is not None:
                db["body"].setdefault(fmt_date(date_obj), {})["fat_pct"] = round(float(pct), 1)

    # --- Wellness ---
    db.setdefault("wellness", {})
    for p in fetch(creds, "daily-respiratory-rate"):
        d = p.get("dailyRespiratoryRate", {})
        date_obj = d.get("date", {})
        if date_obj:
            bpm = d.get("breathsPerMinute") or d.get("value")
            if bpm:
                db["wellness"].setdefault(fmt_date(date_obj), {})["breathing_rate"] = round(float(bpm), 1)
    for p in fetch(creds, "daily-oxygen-saturation"):
        d = p.get("dailyOxygenSaturation", {})
        date_obj = d.get("date", {})
        if date_obj:
            pct = d.get("averagePercentage")
            if pct is not None:
                db["wellness"].setdefault(fmt_date(date_obj), {})["spo2"] = round(float(pct), 1)
    for p in fetch(creds, "daily-sleep-temperature-derivations"):
        d = p.get("dailySleepTemperatureDerivations", {})
        date_obj = d.get("date", {})
        if date_obj:
            nightly = d.get("nightlyTemperatureCelsius")
            baseline = d.get("baselineTemperatureCelsius")
            if nightly is not None:
                entry = db["wellness"].setdefault(fmt_date(date_obj), {})
                entry["skin_temp"] = round(float(nightly), 1)
                if baseline is not None:
                    entry["skin_temp_base"] = round(float(baseline), 1)
                    entry["skin_temp_var"] = round(float(nightly) - float(baseline), 2)

    save_json(json_path, db)
    n_sleep = len(db.get("sleep", {}))
    print(f"health_data.json updated ({n_sleep} sleep records)")
    return db


def render_markdown(db):
    updated = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Health Data — อัพเดท {updated}\n"]

    # Sleep
    lines.append("## Sleep")
    lines.append("| วันที่ | เข้านอน | ตื่น | นอนหลับ | อยู่บนเตียง | Efficiency | Light | Deep | REM | Awake |")
    lines.append("|--------|---------|------|---------|------------|------------|-------|------|-----|-------|")
    for key in sorted(db.get("sleep", {}).keys(), reverse=True):
        s = db["sleep"][key]
        lines.append(
            f"| {s['date']} | {s['start']} | {s['end']} | {s['duration_h']}h | {s['bed_h']}h | {s['efficiency']} "
            f"| {s['light_m']}m | {s['deep_m']}m | {s['rem_m']}m | {s['awake_m']}m |"
        )
    lines.append("")

    # Heart
    lines.append("## Heart Metrics (Daily)")
    lines.append("| วันที่ | Resting HR | HRV |")
    lines.append("|--------|-----------|-----|")
    all_dates = set(list(db.get("resting_hr", {})) + list(db.get("hrv", {})))
    for date in sorted(all_dates, reverse=True):
        hr = db.get("resting_hr", {}).get(date, "-")
        hrv = db.get("hrv", {}).get(date, "-")
        lines.append(f"| {date} | {hr} bpm | {hrv} ms |")
    lines.append("")

    # Activity
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min | Active Cal | Total Cal |")
    lines.append("|--------|-------|----------------|------------|-----------|")
    all_dates = set(list(db.get("steps", {})) + list(db.get("azm", {})) + list(db.get("calories", {})))
    for date in sorted(all_dates, reverse=True):
        steps = db.get("steps", {}).get(date, "-")
        azm = db.get("azm", {}).get(date, "-")
        cal = db.get("calories", {}).get(date, {})
        active_cal = f"{int(cal['active'])} kcal" if "active" in cal else "-"
        total_cal = f"{int(cal['total'])} kcal" if "total" in cal else "-"
        lines.append(f"| {date} | {steps} | {azm} min | {active_cal} | {total_cal} |")
    lines.append("")

    # Body
    lines.append("## Body Composition")
    lines.append("| วันที่ | น้ำหนัก | Fat% | Fat Mass | Lean Mass |")
    lines.append("|--------|---------|------|----------|-----------|")
    for date in sorted(db.get("body", {}).keys(), reverse=True):
        b = db["body"][date]
        w = b.get("weight_kg")
        f = b.get("fat_pct")
        if w and f:
            fat_mass = round(w * f / 100, 1)
            lean_mass = round(w - fat_mass, 1)
            lines.append(f"| {date} | {w} kg | {f}% | {fat_mass} kg | {lean_mass} kg |")
        elif w:
            lines.append(f"| {date} | {w} kg | - | - | - |")
        else:
            lines.append(f"| {date} | - | {f}% | - | - |")
    lines.append("")

    # Wellness
    lines.append("## Wellness (Daily)")
    lines.append("| วันที่ | Breathing Rate | SpO2 | Skin Temp Var |")
    lines.append("|--------|---------------|------|--------------|")
    for date in sorted(db.get("wellness", {}).keys(), reverse=True):
        w = db["wellness"][date]
        br = f"{w['breathing_rate']} brpm" if "breathing_rate" in w else "-"
        spo2 = f"{w['spo2']}%" if "spo2" in w else "-"
        if "skin_temp" in w:
            base = w.get("skin_temp_base", "-")
            var = f"{w['skin_temp_var']:+.2f}" if "skin_temp_var" in w else "-"
            skintemp = f"{w['skin_temp']}°C (base {base}°C, {var})"
        else:
            skintemp = "-"
        lines.append(f"| {date} | {br} | {spo2} | {skintemp} |")

    out_path = os.path.join(DIR, "health_data.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("health_data.md rendered")


def render_sleep_stages_md(db):
    updated = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Sleep Stages Timeline — อัพเดท {updated}\n"]
    lines.append("ข้อมูล timeline การนอนรายคืน\n")

    for key in sorted(db.get("sleep", {}).keys(), reverse=True):
        s = db["sleep"][key]
        stages = s.get("stages", [])
        if not stages:
            continue
        lines.append(f"## {s['date']} ({s['start']} – {s['end']}, นอนหลับ {s['duration_h']}h)")
        lines.append("| เวลา | Stage | นาที |")
        lines.append("|------|-------|------|")
        for st in stages:
            lines.append(f"| {st['start']}–{st['end']} | {st['type']} | {st['minutes']}m |")
        lines.append("")

    out_path = os.path.join(DIR, "sleep_stages.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("sleep_stages.md rendered")


def upload_to_drive(file_path, file_name=None):
    folder_id = "1Wnuivjjo0EclgTNmZcM6Sg6PYwpWhMmR"
    if file_name is None:
        file_name = os.path.basename(file_path)
    creds = get_drive_credentials()
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=f"name='{file_name}' and '{folder_id}' in parents and trashed=false",
        fields="files(id)"
    ).execute()
    files = results.get("files", [])
    mimetype = "application/json" if file_name.endswith(".json") else "text/markdown"
    media = MediaFileUpload(file_path, mimetype=mimetype)
    if files:
        service.files().update(fileId=files[0]["id"], media_body=media).execute()
    else:
        service.files().create(body={"name": file_name, "parents": [folder_id]}, media_body=media).execute()
    print(f"{file_name} updated in Google Drive")


if __name__ == "__main__":
    creds = get_credentials()
    db = fetch_and_merge(creds)
    render_markdown(db)
    render_sleep_stages_md(db)
    upload_to_drive(os.path.join(DIR, "health_data.md"))
    upload_to_drive(os.path.join(DIR, "sleep_stages.md"))
