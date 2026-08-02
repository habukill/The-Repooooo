# The-Repooooo — Project Notes for Claude

## Google Health API (`health/fetch_health.py`)

### Base URL
```
https://health.googleapis.com/v4/users/me/dataTypes
```
- **MUST be `users/me`** — NOT `users/-`. Using `users/-` causes 400 errors on all endpoints.

### Endpoint pattern
```
GET {BASE_URL}/{data_type}/dataPoints
```
- No date range query params — the API does NOT accept `startDate`, `endDate`, `startTime`, `endTime` etc. These all cause 400 errors.
- Use `pageToken` for pagination only.

### Supported data type names
| Data type | Correct name |
|-----------|-------------|
| Sleep | `sleep` |
| Resting HR | `daily-resting-heart-rate` |
| HRV | `daily-heart-rate-variability` |
| Steps | `steps` |
| Active Zone Minutes | `active-zone-minutes` |
| Calories burned | `active-energy-burned` (NOT `active-calories-burned` or `total-calories-burned`) |
| Weight | `weight` |
| Body fat | `body-fat` |
| Respiratory rate | `daily-respiratory-rate` |
| SpO2 | `daily-oxygen-saturation` |
| Sleep temp | `daily-sleep-temperature-derivations` |

### OAuth tokens
- `token.json` — Google Health API scopes
- `drive_token.json` — Google Drive scope (`drive.file`)
- Both expire and need re-authorization periodically (invalid_grant error)
- Re-auth script: `health/get_token.py` (health) and `health/get_drive_token.py` (drive)
- After re-auth, update GitHub Secrets: `GOOGLE_HEALTH_TOKEN` and `GOOGLE_DRIVE_TOKEN`

### Encryption
- `HEALTH_ENCRYPT_KEY` is in `.claude/settings.json` env
- health_data.md and sleep_stages.md are Fernet-encrypted before committing → `.enc` files

### Google Drive folder
- FOLDER_ID: `1Wnuivjjo0EclgTNmZcM6Sg6PYwpWhMmR`
- `health_data.json` is stored here as source of truth (not in git)

## เวลาและวันที่ (เคยพลาดซ้ำหลายรอบ)

- **เครื่องรันเป็น UTC** ผู้ใช้อยู่ไทย (ICT = UTC+7)
- เช็คเวลาไทยด้วย `TZ=Asia/Bangkok date '+%Y-%m-%d %H:%M %A'` เสมอ
- **ห้าม** รัน `date '+%H:%M ICT'` แล้วอ่านค่าว่าเป็นเวลาไทย — format string ไม่แปลงโซนเวลา จะได้เวลา UTC ที่ติดป้าย ICT ผิดๆ คลาดเคลื่อน 7 ชั่วโมง
- ห้ามเดาวันที่จากบทสนทนา ให้เช็คจริงทุกครั้งก่อนวิเคราะห์ข้อมูลสุขภาพ

## Git workflow
- Feature branch: `claude/handoff-continuation-kolrx6`
- After each fix, rebase onto `origin/main` before creating PR (conflicts are common since main gets commits from workflow runs)
- Merge method: squash
