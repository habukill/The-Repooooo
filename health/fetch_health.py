import os
from datetime import datetime, timezone, timedelta

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
    lines.append("| วันที่ | เข้านอน | ตื่น | นอนหลับ | Efficiency | Score | Light | Deep | REM | Awake | Restless | Sound Sleep | Time to Sleep | Interruptions | Sleeping HR |")
    lines.append("|--------|---------|------|---------|------------|-------|-------|------|-----|-------|----------|-------------|---------------|---------------|-------------|")
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
        total = round(minutes_asleep / 60, 1)
        stages = {st["type"]: int(st["minutes"]) for st in summary.get("stagesSummary", [])}
        light = stages.get("LIGHT", "-")
        deep = stages.get("DEEP", "-")
        rem = stages.get("REM", "-")
        awake = stages.get("AWAKE", "-")
        efficiency = summary.get("sleepEfficiencyPercent", "-")
        if efficiency != "-":
            efficiency = f"{int(efficiency)}%"
        score = summary.get("sleepScore", "-")
        restless = summary.get("minutesRestless", "-")
        if restless != "-":
            restless = f"{int(restless)}m"
        sound_sleep = summary.get("minutesSoundSleep", "-")
        if sound_sleep != "-":
            sound_sleep = f"{round(int(sound_sleep)/60, 1)}h"
        time_to_sleep = summary.get("minutesToFallAsleep", "-")
        if time_to_sleep != "-":
            time_to_sleep = f"{int(time_to_sleep)}m"
        interruptions = summary.get("numberOfAwakenings", "-")
        sleeping_hr = summary.get("averageHeartRate", "-")
        if sleeping_hr != "-":
            sleeping_hr = f"{int(sleeping_hr)} bpm"
        lines.append(
            f"| {date} | {start} | {end} | {total}h | {efficiency} | {score} | {light}m | {deep}m | {rem}m | {awake}m | {restless} | {sound_sleep} | {time_to_sleep} | {interruptions} | {sleeping_hr} |"
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

    # Steps + Active Zone Minutes
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min | Calories |")
    lines.append("|--------|-------|----------------|----------|")
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
    cal_data = {}
    for p in fetch(creds, "calories", paginate=True):
        d = p.get("calories", {})
        civil = d.get("interval", {}).get("civilStartTime", {})
        date_obj = civil.get("date", {})
        if date_obj:
            date = fmt_date(date_obj)
            cal_data[date] = cal_data.get(date, 0) + round(d.get("kilocalories", 0), 1)
    for date in sorted(set(list(steps_data.keys()) + list(azm_data.keys()) + list(cal_data.keys())), reverse=True):
        steps = steps_data.get(date, "-")
        azm = azm_data.get(date, "-")
        cal = f"{int(cal_data[date])} kcal" if date in cal_data else "-"
        lines.append(f"| {date} | {steps} | {azm} min | {cal} |")

    out_path = os.path.join(os.path.dirname(__file__), "health_data.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("health_data.md updated")


def upload_to_drive(file_path):
    folder_id = "1Wnuivjjo0EclgTNmZcM6Sg6PYwpWhMmR"
    creds = get_drive_credentials()
    service = build("drive", "v3", credentials=creds)

    # Check if file already exists in folder
    results = service.files().list(
        q=f"name='health_data.md' and '{folder_id}' in parents and trashed=false",
        fields="files(id)"
    ).execute()
    files = results.get("files", [])

    media = MediaFileUpload(file_path, mimetype="text/markdown")
    if files:
        service.files().update(fileId=files[0]["id"], media_body=media).execute()
        print("health_data.md updated in Google Drive")
    else:
        service.files().create(
            body={"name": "health_data.md", "parents": [folder_id]},
            media_body=media
        ).execute()
        print("health_data.md uploaded to Google Drive")


if __name__ == "__main__":
    creds = get_credentials()
    write_health_md(creds)
    upload_to_drive(os.path.join(os.path.dirname(__file__), "health_data.md"))
