import os
from datetime import datetime, timedelta
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


def fetch(creds, data_type):
    headers = {"Authorization": f"Bearer {creds.token}"}
    r = requests.get(f"{BASE_URL}/{data_type}/dataPoints", headers=headers)
    if not r.ok:
        print(f"ERROR {r.status_code} for {data_type}: {r.text}")
        return []
    return r.json().get("dataPoints", [])


def fetch_daily_rollup(creds, data_type):
    headers = {"Authorization": f"Bearer {creds.token}"}
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    params = {
        "startDate": week_ago.strftime("%Y-%m-%d"),
        "endDate": now.strftime("%Y-%m-%d"),
    }
    r = requests.get(
        f"{BASE_URL}/{data_type}/dataPoints:dailyRollup",
        headers=headers,
        params=params,
    )
    if not r.ok:
        print(f"ERROR {r.status_code} for {data_type} dailyRollup: {r.text}")
        return []
    return r.json().get("dataPoints", [])


def fmt_date(d):
    return f"{d['year']}-{d['month']:02d}-{d['day']:02d}"


def write_health_md(creds):
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Health Data — อัพเดท {updated}\n"]

    # Sleep
    lines.append("## Sleep (7 วันล่าสุด)")
    lines.append("| วันที่ | เข้านอน | ตื่น | นอนหลับ | Deep | REM |")
    lines.append("|--------|---------|------|---------|------|-----|")
    for p in fetch(creds, "sleep"):
        s = p.get("sleep", {})
        interval = s.get("interval", {})
        summary = s.get("summary", {})
        date = interval.get("startTime", "")[:10]
        start = interval.get("startTime", "")[11:16] or "-"
        end = interval.get("endTime", "")[11:16] or "-"
        minutes_asleep = int(summary.get("minutesAsleep", 0))
        stages = {st["type"]: int(st["minutes"]) for st in summary.get("stagesSummary", [])}
        deep = stages.get("DEEP", 0)
        rem = stages.get("REM", 0)
        total = round(minutes_asleep / 60, 1)
        lines.append(
            f"| {date} | {start} | {end} | {total}h | {deep}m | {rem}m |"
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
            hr_data[fmt_date(d["date"])] = d.get("beatsPerMinute", "-")
    hrv_data = {}
    for p in fetch(creds, "daily-heart-rate-variability"):
        d = p.get("dailyHeartRateVariability", {})
        if "date" in d:
            hrv_data[fmt_date(d["date"])] = round(d.get("averageHeartRateVariabilityMilliseconds", 0), 1)
    for date in sorted(set(list(hr_data.keys()) + list(hrv_data.keys())), reverse=True):
        hr = hr_data.get(date, "-")
        hrv = hrv_data.get(date, "-")
        lines.append(f"| {date} | {hr} bpm | {hrv} ms |")

    lines.append("")

    # Steps + Active Zone Minutes (daily rollup)
    lines.append("## Activity (Daily)")
    lines.append("| วันที่ | Steps | Active Zone Min |")
    lines.append("|--------|-------|----------------|")
    steps_data = {}
    for p in fetch(creds, "steps"):
        d = p.get("steps", {})
        interval = d.get("interval", {})
        date = interval.get("startTime", "")[:10]
        if date:
            steps_data[date] = steps_data.get(date, 0) + int(d.get("count", 0))
    azm_data = {}
    for p in fetch(creds, "active-zone-minutes"):
        d = p.get("activeZoneMinutes", {})
        interval = d.get("interval", {})
        date = interval.get("startTime", "")[:10]
        if date:
            azm_data[date] = azm_data.get(date, 0) + int(d.get("totalMinutes", 0))
    for date in sorted(set(list(steps_data.keys()) + list(azm_data.keys())), reverse=True):
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
