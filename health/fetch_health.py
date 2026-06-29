import json
import os
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import requests

SCOPES = [
    "https://www.googleapis.com/auth/health.sleep.readonly",
    "https://www.googleapis.com/auth/health.activity.readonly",
    "https://www.googleapis.com/auth/health.metrics.readonly",
]
BASE_URL = "https://health.googleapis.com/v4/users/-/dataTypes"


def get_credentials():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")

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


def fetch(creds, data_type, params=None):
    if params is None:
        params = {}
    headers = {"Authorization": f"Bearer {creds.token}"}
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    default_params = {"startDate": week_ago, "endDate": today}
    r = requests.get(
        f"{BASE_URL}/{data_type}/dataPoints",
        headers=headers,
        params={**default_params, **params},
    )
    r.raise_for_status()
    return r.json().get("dataPoints", [])


def write_health_md(creds):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Health Data — อัพเดท {today}\n"]

    # Sleep
    lines.append("## Sleep (7 วันล่าสุด)")
    lines.append("| วันที่ | เข้านอน | ตื่น | รวม | Deep | REM |")
    lines.append("|--------|---------|------|-----|------|-----|")
    for p in fetch(creds, "sleep"):
        d = p.get("value", {})
        date = p.get("startTime", "")[:10]
        duration = round(d.get("durationMilliseconds", 0) / 3600000, 1)
        deep = round(
            d.get("sleepStageData", {}).get("deepSleepDurationMilliseconds", 0) / 3600000, 1
        )
        rem = round(
            d.get("sleepStageData", {}).get("remSleepDurationMilliseconds", 0) / 3600000, 1
        )
        start = p.get("startTime", "")[11:16] if p.get("startTime") else "-"
        end = p.get("endTime", "")[11:16] if p.get("endTime") else "-"
        lines.append(f"| {date} | {start} | {end} | {duration}h | {deep}h | {rem}h |")

    lines.append("")

    # Resting HR + HRV
    lines.append("## Heart Metrics (Daily)")
    lines.append("| วันที่ | Resting HR | HRV |")
    lines.append("|--------|-----------|-----|")
    hr_data = {
        p["startTime"][:10]: p["value"].get("beatsPerMinute")
        for p in fetch(creds, "daily-resting-heart-rate")
    }
    hrv_data = {
        p["startTime"][:10]: p["value"].get("rmssd")
        for p in fetch(creds, "daily-heart-rate-variability")
    }
    for date in sorted(set(list(hr_data.keys()) + list(hrv_data.keys()))):
        hr = hr_data.get(date, "-")
        hrv = hrv_data.get(date, "-")
        lines.append(f"| {date} | {hr} bpm | {hrv} ms |")

    lines.append("")

    # Steps + Active Zone Minutes
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min |")
    lines.append("|--------|-------|----------------|")
    steps_data = {
        p["startTime"][:10]: p["value"].get("steps")
        for p in fetch(creds, "steps", {"rollup": "daily"})
    }
    azm_data = {
        p["startTime"][:10]: p["value"].get("totalMinutes")
        for p in fetch(creds, "active-zone-minutes", {"rollup": "daily"})
    }
    for date in sorted(set(list(steps_data.keys()) + list(azm_data.keys()))):
        steps = steps_data.get(date, "-")
        azm = azm_data.get(date, "-")
        lines.append(f"| {date} | {steps} | {azm} min |")

    out_path = os.path.join(os.path.dirname(__file__), "health_data.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("health_data.md updated")


if __name__ == "__main__":
    creds = get_credentials()
    write_health_md(creds)
