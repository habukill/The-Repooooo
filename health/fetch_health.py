import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import requests

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]
BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
ICT = ZoneInfo("Asia/Bangkok")
DIR = os.path.dirname(__file__)


def get_credentials():
    creds = None
    token_path = os.path.join(DIR, "token.json")
    creds_path = os.path.join(DIR, "credentials.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def get_drive_credentials():
    from google.oauth2.credentials import Credentials as GCreds
    drive_scopes = ["https://www.googleapis.com/auth/drive.file"]
    token_path = os.path.join(DIR, "drive_token.json")
    creds_path = os.path.join(DIR, "credentials.json")
    creds = None
    if os.path.exists(token_path):
        creds = GCreds.from_authorized_user_file(token_path, drive_scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, drive_scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch(creds, data_type, extra_params=None):
    headers = {"Authorization": f"Bearer {creds.token}"}
    results = []
    params = dict(extra_params or {})
    while True:
        r = requests.get(
            f"{BASE_URL}/{data_type}/dataPoints",
            headers=headers,
            params=params,
        )
        if not r.ok:
            print(f"ERROR {r.status_code} for {data_type}: {r.text}")
            break
        data = r.json()
        batch = data.get("dataPoints", [])
        results.extend(batch)
        next_token = data.get("nextPageToken")
        print(f"  [{data_type}] batch={len(batch)} total={len(results)} keys={list(data.keys())} nextPage={'yes' if next_token else 'no'}")
        if not batch and not next_token:
            print(f"  [{data_type}] raw sample: {str(data)[:300]}")
        if not next_token:
            break
        params = {**(extra_params or {}), "pageToken": next_token}
    return results


def to_ict(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(ICT)
    except Exception:
        return None


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_and_merge(creds):
    json_path = os.path.join(DIR, "health_data.json")
    db = load_json(json_path)

    # --- Sleep ---
    if "sleep" not in db:
        db["sleep"] = {}
    for p in fetch(creds, "sleep"):
        v = p.get("value", {})
        start_dt = to_ict(p.get("startTime"))
        end_dt = to_ict(p.get("endTime"))
        if not start_dt:
            continue
        key = f"{start_dt.strftime('%Y-%m-%d')}_{start_dt.strftime('%H%M')}"
        duration_ms = v.get("durationMilliseconds", 0)
        stages = v.get("sleepStageData", {})
        db["sleep"][key] = {
            "date": start_dt.strftime("%Y-%m-%d"),
            "start": start_dt.strftime("%H:%M"),
            "end": end_dt.strftime("%H:%M") if end_dt else "-",
            "duration_h": round(duration_ms / 3600000, 1),
            "bed_h": round((end_dt - start_dt).total_seconds() / 3600, 1) if end_dt else None,
            "efficiency": round(duration_ms / ((end_dt - start_dt).total_seconds() * 1000) * 100) if end_dt else None,
            "light_m": round(stages.get("lightSleepDurationMilliseconds", 0) / 60000),
            "deep_m": round(stages.get("deepSleepDurationMilliseconds", 0) / 60000),
            "rem_m": round(stages.get("remSleepDurationMilliseconds", 0) / 60000),
            "awake_m": round(stages.get("awakeDurationMilliseconds", 0) / 60000),
            "restless_m": round(stages.get("restlessDurationMilliseconds", 0) / 60000),
        }

    # --- Heart Rate ---
    if "resting_hr" not in db:
        db["resting_hr"] = {}
    for p in fetch(creds, "daily-resting-heart-rate"):
        date = p["startTime"][:10]
        db["resting_hr"][date] = p["value"].get("beatsPerMinute")

    # --- HRV ---
    if "hrv" not in db:
        db["hrv"] = {}
    for p in fetch(creds, "daily-heart-rate-variability"):
        date = p["startTime"][:10]
        val = p["value"].get("rmssd")
        if val:
            db["hrv"][date] = round(val, 1)

    # --- Steps ---
    if "steps" not in db:
        db["steps"] = {}
    for p in fetch(creds, "steps"):
        date = p["startTime"][:10]
        db["steps"][date] = p["value"].get("steps")

    # --- Active Zone Minutes ---
    if "azm" not in db:
        db["azm"] = {}
    for p in fetch(creds, "active-zone-minutes"):
        date = p["startTime"][:10]
        db["azm"][date] = p["value"].get("totalMinutes")

    # --- Calories ---
    if "calories" not in db:
        db["calories"] = {}
    for p in fetch(creds, "active-energy-burned"):
        date = p["startTime"][:10]
        db["calories"].setdefault(date, {})["active"] = round(p["value"].get("kilocalories", 0))
        date = p["startTime"][:10]
        db["calories"].setdefault(date, {})["total"] = round(p["value"].get("kilocalories", 0))

    # --- Body Composition ---
    if "body" not in db:
        db["body"] = {}
    for p in fetch(creds, "weight"):
        st = p.get("sampleTime", {})
        date = st.get("civilTime", {}).get("date", "")
        if not date:
            continue
        date_str = f"{date.get('year', '')}-{str(date.get('month', '')).zfill(2)}-{str(date.get('day', '')).zfill(2)}"
        db["body"].setdefault(date_str, {})["weight_kg"] = round(p["value"].get("weightGrams", 0) / 1000, 1)
    for p in fetch(creds, "body-fat"):
        st = p.get("sampleTime", {})
        date = st.get("civilTime", {}).get("date", "")
        if not date:
            continue
        date_str = f"{date.get('year', '')}-{str(date.get('month', '')).zfill(2)}-{str(date.get('day', '')).zfill(2)}"
        fat = p["value"].get("percentage")
        if fat:
            db["body"].setdefault(date_str, {})["fat_pct"] = round(fat, 1)

    # --- Wellness ---
    if "wellness" not in db:
        db["wellness"] = {}
    for p in fetch(creds, "daily-respiratory-rate"):
        date = p.get("date") or p.get("startTime", "")[:10]
        val = p["value"].get("breathsPerMinute")
        if val:
            db["wellness"].setdefault(date, {})["breathing_rate"] = round(val, 1)
    for p in fetch(creds, "daily-oxygen-saturation"):
        date = p.get("date") or p.get("startTime", "")[:10]
        val = p["value"].get("averagePercentage")
        if val:
            db["wellness"].setdefault(date, {})["spo2"] = round(val, 1)
    for p in fetch(creds, "daily-sleep-temperature-derivations"):
        date = p.get("date") or p.get("startTime", "")[:10]
        nightly = p["value"].get("nightlyTemperatureCelsius")
        baseline = p["value"].get("baselineTemperatureCelsius")
        if nightly:
            entry = db["wellness"].setdefault(date, {})
            entry["skin_temp"] = round(float(nightly), 1)
            if baseline:
                entry["skin_temp_base"] = round(float(baseline), 1)
                entry["skin_temp_var"] = round(float(nightly) - float(baseline), 2)

    save_json(json_path, db)
    print(f"health_data.json updated ({len(db.get('sleep', {}))} sleep records)")
    return db


def render_markdown(db):
    now_str = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Health Data — อัพเดท {now_str}\n"]

    # --- Sleep ---
    lines.append("## Sleep")
    lines.append("| วันที่ | เข้านอน | ตื่น | นอนหลับ | อยู่บนเตียง | Efficiency | Light | Deep | REM | Awake | Restless |")
    lines.append("|--------|---------|------|---------|------------|------------|-------|------|-----|-------|----------|")
    for key in sorted(db.get("sleep", {}).keys(), reverse=True):
        s = db["sleep"][key]
        eff = f"{s['efficiency']}%" if s.get("efficiency") else "-"
        bed = f"{s['bed_h']}h" if s.get("bed_h") else "-"
        lines.append(
            f"| {s['date']} | {s['start']} | {s['end']} | {s['duration_h']}h | {bed} | {eff} | "
            f"{s['light_m']}m | {s['deep_m']}m | {s['rem_m']}m | {s['awake_m']}m | {s['restless_m']}m |"
        )

    lines.append("")

    # --- Heart ---
    lines.append("## Heart Metrics (Daily)")
    lines.append("| วันที่ | Resting HR | HRV |")
    lines.append("|--------|-----------|-----|")
    all_heart_dates = sorted(set(list(db.get("resting_hr", {}).keys()) + list(db.get("hrv", {}).keys())), reverse=True)
    for date in all_heart_dates:
        hr = db.get("resting_hr", {}).get(date, "-")
        hrv = db.get("hrv", {}).get(date, "-")
        hr_str = f"{hr} bpm" if hr != "-" else "-"
        hrv_str = f"{hrv} ms" if hrv != "-" else "-"
        lines.append(f"| {date} | {hr_str} | {hrv_str} |")

    lines.append("")

    # --- Activity ---
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min | Active Cal | Total Cal |")
    lines.append("|--------|-------|----------------|------------|-----------|")
    all_act_dates = sorted(set(
        list(db.get("steps", {}).keys()) +
        list(db.get("azm", {}).keys()) +
        list(db.get("calories", {}).keys())
    ), reverse=True)
    for date in all_act_dates:
        steps = db.get("steps", {}).get(date, "-")
        azm = db.get("azm", {}).get(date, "-")
        cal = db.get("calories", {}).get(date, {})
        active_cal = cal.get("active", "-")
        total_cal = cal.get("total", "-")
        azm_str = f"{azm} min" if azm != "-" else "- min"
        active_str = f"{active_cal} kcal" if active_cal != "-" else "-"
        total_str = f"{total_cal} kcal" if total_cal != "-" else "-"
        lines.append(f"| {date} | {steps} | {azm_str} | {active_str} | {total_str} |")

    lines.append("")

    # --- Body Composition ---
    lines.append("## Body Composition")
    lines.append("| วันที่ | น้ำหนัก | Fat% | Fat Mass | Lean Mass |")
    lines.append("|--------|---------|------|----------|-----------|")
    for date in sorted(db.get("body", {}).keys(), reverse=True):
        b = db["body"][date]
        w = b.get("weight_kg", "-")
        fat = b.get("fat_pct")
        fat_mass = round(w * fat / 100, 1) if isinstance(w, float) and fat else "-"
        lean_mass = round(w - fat_mass, 1) if isinstance(fat_mass, float) else "-"
        fat_str = f"{fat}%" if fat else "-"
        lines.append(f"| {date} | {w} kg | {fat_str} | {fat_mass if fat_mass != '-' else '-'} kg | {lean_mass if lean_mass != '-' else '-'} kg |")

    lines.append("")

    # --- Wellness ---
    lines.append("## Wellness (Daily)")
    lines.append("| วันที่ | Breathing Rate | SpO2 | Skin Temp Var |")
    lines.append("|--------|---------------|------|--------------|")
    for date in sorted(db.get("wellness", {}).keys(), reverse=True):
        w = db["wellness"][date]
        br = f"{w['breathing_rate']} brpm" if w.get("breathing_rate") else "-"
        spo2 = f"{w['spo2']}%" if w.get("spo2") else "-"
        if w.get("skin_temp") and w.get("skin_temp_base"):
            var = w.get("skin_temp_var", 0)
            sign = "+" if var >= 0 else ""
            skin = f"{w['skin_temp']}°C (base {w['skin_temp_base']}°C, {sign}{var})"
        elif w.get("skin_temp"):
            skin = f"{w['skin_temp']}°C"
        else:
            skin = "-"
        lines.append(f"| {date} | {br} | {spo2} | {skin} |")

    out_path = os.path.join(DIR, "health_data.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("health_data.md rendered")


def fetch_sleep_stages(creds):
    json_path = os.path.join(DIR, "health_data.json")
    db = load_json(json_path)

    if "sleep_stages" not in db:
        db["sleep_stages"] = {}

    for p in fetch(creds, "sleep"):
        v = p.get("value", {})
        start_dt = to_ict(p.get("startTime"))
        end_dt = to_ict(p.get("endTime"))
        if not start_dt:
            continue
        key = f"{start_dt.strftime('%Y-%m-%d')}_{start_dt.strftime('%H%M')}"
        stages_raw = v.get("sleepStageData", {}).get("sleepStages", [])
        segments = []
        for seg in stages_raw:
            seg_start = to_ict(seg.get("startTime"))
            seg_end = to_ict(seg.get("endTime"))
            stage_type = seg.get("stage", "UNKNOWN")
            if seg_start and seg_end:
                dur_m = round((seg_end - seg_start).total_seconds() / 60)
                segments.append({
                    "start": seg_start.strftime("%H:%M"),
                    "end": seg_end.strftime("%H:%M"),
                    "stage": stage_type,
                    "minutes": dur_m,
                })
        if segments:
            duration_ms = v.get("durationMilliseconds", 0)
            db["sleep_stages"][key] = {
                "date": start_dt.strftime("%Y-%m-%d"),
                "start": start_dt.strftime("%H:%M"),
                "end": end_dt.strftime("%H:%M") if end_dt else "-",
                "duration_h": round(duration_ms / 3600000, 1),
                "segments": segments,
            }

    save_json(json_path, db)

    # render sleep_stages.md
    now_str = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Sleep Stages Timeline — อัพเดท {now_str}\n"]
    lines.append("ข้อมูล timeline การนอนรายคืน แต่ละบรรทัดคือ segment ของ sleep stage\n")

    for key in sorted(db.get("sleep_stages", {}).keys(), reverse=True):
        s = db["sleep_stages"][key]
        lines.append(f"## {s['date']} ({s['start']} – {s['end']}, นอนหลับ {s['duration_h']}h)")
        lines.append("| เวลา | Stage | นาที |")
        lines.append("|------|-------|------|")
        for seg in s["segments"]:
            lines.append(f"| {seg['start']}–{seg['end']} | {seg['stage']} | {seg['minutes']}m |")
        lines.append("")

    out_path = os.path.join(DIR, "sleep_stages.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"sleep_stages.md rendered ({len(db.get('sleep_stages', {}))} sessions)")


def upload_to_drive(creds_drive):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    FOLDER_ID = "1Wnuivjjo0EclgTNmZcM6Sg6PYwpWhMmR"
    service = build("drive", "v3", credentials=creds_drive)

    for name in ["health_data.md", "sleep_stages.md"]:
        path = os.path.join(DIR, name)
        if not os.path.exists(path):
            continue
        results = service.files().list(
            q=f"name='{name}' and '{FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        media = MediaFileUpload(path, mimetype="text/markdown")
        if files:
            service.files().update(fileId=files[0]["id"], media_body=media).execute()
        else:
            service.files().create(
                body={"name": name, "parents": [FOLDER_ID]},
                media_body=media
            ).execute()
        print(f"[✓] uploaded {name} to Drive")


if __name__ == "__main__":
    creds = get_credentials()
    db = fetch_and_merge(creds)
    render_markdown(db)
    fetch_sleep_stages(creds)
    creds_drive = get_drive_credentials()
    upload_to_drive(creds_drive)
