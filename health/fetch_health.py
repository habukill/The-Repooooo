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


def get_credentials():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")

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
    token_path = os.path.join(os.path.dirname(__file__), "drive_token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")

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
    # fetch from 2 years ago to cover all history
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


def write_health_md(creds):
    updated = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Health Data — อัพเดท {updated}\n"]

    # Sleep
    lines.append("## Sleep")
    lines.append("| วันที่ | เข้านอน | ตื่น | นอนหลับ | อยู่บนเตียง | Efficiency | Light | Deep | REM | Awake | Restless |")
    lines.append("|--------|---------|------|---------|------------|------------|-------|------|-----|-------|----------|")
    for p in fetch(creds, "sleep"):
        s = p.get("sleep", {})
        interval = s.get("interval", {})
        summary = s.get("summary", {})
        raw_start = interval.get("startTime", "")
        raw_end = interval.get("endTime", "")
        if raw_start:
            dt_start = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).astimezone(ICT)
            date = dt_start.strftime("%Y-%m-%d")
            start = dt_start.strftime("%H:%M")
        else:
            date, start = "", "-"
        if raw_end:
            end = datetime.fromisoformat(raw_end.replace("Z", "+00:00")).astimezone(ICT).strftime("%H:%M")
        else:
            end = "-"
        minutes_asleep = int(summary.get("minutesAsleep", 0))
        minutes_in_bed = int(summary.get("minutesInSleepPeriod", 0))
        total = round(minutes_asleep / 60, 1)
        in_bed = round(minutes_in_bed / 60, 1)
        efficiency = f"{int(minutes_asleep / minutes_in_bed * 100)}%" if minutes_in_bed > 0 else "-"
        stages = {st["type"]: int(st["minutes"]) for st in summary.get("stagesSummary", [])}
        light = stages.get("LIGHT", "-")
        deep = stages.get("DEEP", "-")
        rem = stages.get("REM", "-")
        awake = stages.get("AWAKE", "-")
        restless = stages.get("RESTLESS", 0)
        lines.append(
            f"| {date} | {start} | {end} | {total}h | {in_bed}h | {efficiency} | {light}m | {deep}m | {rem}m | {awake}m | {restless}m |"
        )

    lines.append("")

    # Resting HR + HRV
    lines.append("## Heart Metrics (Daily)")
    lines.append("| วันที่ | Resting HR | HRV |")
    lines.append("|--------|-----------|-----|")
    hr_data = {}
    for p in fetch(creds, "daily-resting-heart-rate"):
        d = p.get("dailyRestingHeartRate", {})
        if "date" in d:
            date = fmt_date(d["date"])
            hr_data[date] = d.get("beatsPerMinute", "-")
    hrv_data = {}
    for p in fetch(creds, "daily-heart-rate-variability"):
        d = p.get("dailyHeartRateVariability", {})
        if "date" in d:
            date = fmt_date(d["date"])
            hrv_data[date] = round(d.get("averageHeartRateVariabilityMilliseconds", 0), 1)
    for date in sorted(set(list(hr_data.keys()) + list(hrv_data.keys())), reverse=True):
        hr = hr_data.get(date, "-")
        hrv = hrv_data.get(date, "-")
        lines.append(f"| {date} | {hr} bpm | {hrv} ms |")

    lines.append("")

    # Steps + Active Zone Minutes + Calories
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min | Active Cal | Total Cal |")
    lines.append("|--------|-------|----------------|------------|-----------|")
    steps_data = {}
    for p in fetch(creds, "steps", paginate=True):
        d = p.get("steps", {})
        civil = d.get("interval", {}).get("civilStartTime", {})
        date_obj = civil.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            steps_data[date] = steps_data.get(date, 0) + int(d.get("count", 0))
    azm_data = {}
    for p in fetch(creds, "active-zone-minutes", paginate=True):
        d = p.get("activeZoneMinutes", {})
        civil = d.get("interval", {}).get("civilStartTime", {})
        date_obj = civil.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            azm_data[date] = azm_data.get(date, 0) + int(d.get("activeZoneMinutes", 0))
    active_cal_data = {}
    for p in fetch(creds, "active-energy-burned", paginate=True):
        d = p.get("activeEnergyBurned", {})
        civil = d.get("interval", {}).get("civilStartTime", {})
        date_obj = civil.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            active_cal_data[date] = active_cal_data.get(date, 0) + round(d.get("kcal", 0), 1)
    total_cal_data = {}
    for p in fetch_daily_rollup(creds, "total-calories", max_range_days=14):
        date_obj = p.get("civilStartTime", {}).get("date")
        d = p.get("totalCalories", {})
        if date_obj and d:
            date = fmt_date(date_obj)
            kcal = d.get("kcal_sum") or d.get("kcalSum") or d.get("kcal") or 0
            total_cal_data[date] = int(kcal)
    all_dates = set(list(steps_data) + list(azm_data) + list(active_cal_data) + list(total_cal_data))
    for date in sorted(all_dates, reverse=True):
        steps = steps_data.get(date, "-")
        azm = azm_data.get(date, "-")
        active_cal = f"{int(active_cal_data[date])} kcal" if date in active_cal_data else "-"
        total_cal = f"{int(total_cal_data[date])} kcal" if date in total_cal_data else "-"
        lines.append(f"| {date} | {steps} | {azm} min | {active_cal} | {total_cal} |")

    lines.append("")

    # Body Composition
    lines.append("## Body Composition")
    lines.append("| วันที่ | น้ำหนัก | Fat% | Fat Mass | Lean Mass |")
    lines.append("|--------|---------|------|----------|-----------|")
    weight_data = {}
    for p in fetch(creds, "weight", paginate=True):
        d = p.get("weight", {})
        date_obj = d.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            grams = d.get("weightGrams")
            if grams:
                weight_data[date] = round(float(grams) / 1000, 1)
    fat_data = {}
    for p in fetch(creds, "body-fat", paginate=True):
        d = p.get("bodyFat", {})
        date_obj = d.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            pct = d.get("percentage")
            if pct is not None:
                fat_data[date] = round(float(pct), 1)
    for date in sorted(set(list(weight_data) + list(fat_data)), reverse=True):
        w = weight_data.get(date)
        f = fat_data.get(date)
        if w and f:
            fat_mass = round(w * f / 100, 1)
            lean_mass = round(w - fat_mass, 1)
            lines.append(f"| {date} | {w} kg | {f}% | {fat_mass} kg | {lean_mass} kg |")
        elif w:
            lines.append(f"| {date} | {w} kg | - | - | - |")
        else:
            lines.append(f"| {date} | - | {f}% | - | - |")

    lines.append("")

    # Wellness Metrics
    lines.append("## Wellness (Daily)")
    lines.append("| วันที่ | Breathing Rate | SpO2 | Skin Temp Var |")
    lines.append("|--------|---------------|------|--------------|")
    br_data = {}
    for p in fetch(creds, "daily-respiratory-rate"):
        d = p.get("dailyRespiratoryRate", {})
        date_obj = d.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            bpm = d.get("breathsPerMinute") or d.get("value")
            if bpm:
                br_data[date] = round(float(bpm), 1)
    spo2_data = {}
    for p in fetch(creds, "daily-oxygen-saturation"):
        d = p.get("dailyOxygenSaturation", {})
        date_obj = d.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            pct = d.get("averagePercentage")
            if pct is not None:
                spo2_data[date] = round(float(pct), 1)
    skintemp_data = {}
    for p in fetch(creds, "daily-sleep-temperature-derivations"):
        d = p.get("dailySleepTemperatureDerivations", {})
        date_obj = d.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            nightly = d.get("nightlyTemperatureCelsius")
            baseline = d.get("baselineTemperatureCelsius")
            if nightly is not None:
                nightly = float(nightly)
                baseline = float(baseline) if baseline is not None else None
                deviation = round(nightly - baseline, 2) if baseline is not None else None
                skintemp_data[date] = (round(nightly, 1), round(baseline, 1) if baseline is not None else "-", f"{deviation:+.2f}" if deviation is not None else "-")
    all_wellness = set(list(br_data) + list(spo2_data) + list(skintemp_data))
    for date in sorted(all_wellness, reverse=True):
        br = f"{br_data[date]} brpm" if date in br_data else "-"
        spo2 = f"{spo2_data[date]}%" if date in spo2_data else "-"
        if date in skintemp_data:
            nightly, baseline, dev = skintemp_data[date]
            skintemp = f"{nightly}°C (base {baseline}°C, {dev})"
        else:
            skintemp = "-"
        lines.append(f"| {date} | {br} | {spo2} | {skintemp} |")

    out_path = os.path.join(os.path.dirname(__file__), "health_data.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("health_data.md updated")


def write_sleep_stages_md(creds):
    updated = datetime.now(ICT).strftime("%Y-%m-%d %H:%M")
    lines = [f"# Sleep Stages Timeline — อัพเดท {updated}\n"]
    lines.append("ข้อมูล timeline การนอนรายคืน แต่ละบรรทัดคือ segment ของ sleep stage\n")

    for p in fetch(creds, "sleep"):
        s = p.get("sleep", {})
        interval = s.get("interval", {})
        stages = s.get("stages", [])
        if not stages:
            continue
        raw_start = interval.get("startTime", "")
        if raw_start:
            dt_start = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).astimezone(ICT)
            date = dt_start.strftime("%Y-%m-%d")
            start = dt_start.strftime("%H:%M")
        else:
            continue
        raw_end = interval.get("endTime", "")
        end = datetime.fromisoformat(raw_end.replace("Z", "+00:00")).astimezone(ICT).strftime("%H:%M") if raw_end else "-"

        summary = s.get("summary", {})
        minutes_asleep = int(summary.get("minutesAsleep", 0))
        total = round(minutes_asleep / 60, 1)

        lines.append(f"## {date} ({start} – {end}, นอนหลับ {total}h)")
        lines.append("| เวลา | Stage | นาที |")
        lines.append("|------|-------|------|")
        for stage in stages:
            st_raw = stage.get("startTime", "")
            et_raw = stage.get("endTime", "")
            stype = stage.get("type", "")
            if not st_raw or not et_raw:
                continue
            st = datetime.fromisoformat(st_raw.replace("Z", "+00:00")).astimezone(ICT)
            et = datetime.fromisoformat(et_raw.replace("Z", "+00:00")).astimezone(ICT)
            duration = int((et - st).total_seconds() / 60)
            lines.append(f"| {st.strftime('%H:%M')}–{et.strftime('%H:%M')} | {stype} | {duration}m |")
        lines.append("")

    out_path = os.path.join(os.path.dirname(__file__), "sleep_stages.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("sleep_stages.md updated")


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

    media = MediaFileUpload(file_path, mimetype="text/markdown")
    if files:
        service.files().update(fileId=files[0]["id"], media_body=media).execute()
        print(f"{file_name} updated in Google Drive")
    else:
        service.files().create(
            body={"name": file_name, "parents": [folder_id]},
            media_body=media
        ).execute()
        print(f"{file_name} uploaded to Google Drive")


if __name__ == "__main__":
    creds = get_credentials()
    write_health_md(creds)
    write_sleep_stages_md(creds)
    upload_to_drive(os.path.join(os.path.dirname(__file__), "health_data.md"))
    upload_to_drive(os.path.join(os.path.dirname(__file__), "sleep_stages.md"))
