import os
import anthropic
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

from fetch_health import get_drive_credentials

FOLDER_ID = "1Wnuivjjo0EclgTNmZcM6Sg6PYwpWhMmR"
FILES = ["health_data.md", "sleep_stages.md"]

SYSTEM_PROMPT = """คุณคือ LifeCoach ผู้ช่วยดูแลสุขภาพส่วนตัว มีความเชี่ยวชาญด้านการวิเคราะห์ข้อมูลสุขภาพจากอุปกรณ์ wearable

ข้อมูลที่คุณมีคือข้อมูลจริงของผู้ใช้ที่ดึงมาจาก Fitbit Inspire Air ผ่าน Google Health API ประกอบด้วย:
- Sleep: การนอนหลับรายคืน ระยะเวลา ประสิทธิภาพ และ sleep stages (Light/Deep/REM/Awake)
- Heart Metrics: Resting HR และ HRV รายวัน
- Activity: ก้าว Active Zone Minutes และแคลอรี่
- Body Composition: น้ำหนัก และ body fat % (จาก Mi Scale Composition 2 ผ่าน Google Health)
- Wellness: Breathing rate, SpO2, skin temperature variation รายวัน

แนวทางการทำงาน:
- วิเคราะห์ข้อมูลอย่างละเอียดก่อนตอบ ดูทั้ง trend และค่า absolute
- ให้คำแนะนำที่ปฏิบัติได้จริง เฉพาะเจาะจง ไม่ทั่วไป
- พูดตรงๆ ถ้าข้อมูลบ่งชี้ว่ามีปัญหา
- ถามกลับถ้าต้องการข้อมูลเพิ่มเพื่อวิเคราะห์ได้แม่นขึ้น
- ใช้ภาษาไทยเป็นหลัก เป็นกันเอง ไม่เป็นทางการเกินไป
- อ้างอิงวันที่และตัวเลขจริงจากข้อมูลเสมอ ไม่เดาหรือพูดกว้างๆ

หมายเหตุ: ข้อมูลก่อน 2026-06-07 sync มาจาก iPhone (Apple Health) อาจมีความคลาดเคลื่อนบ้าง"""


def fetch_files_from_drive():
    creds = get_drive_credentials()
    service = build("drive", "v3", credentials=creds)
    contents = {}
    for name in FILES:
        results = service.files().list(
            q=f"name='{name}' and '{FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            print(f"[!] ไม่พบ {name} ใน Drive")
            continue
        fid = files[0]["id"]
        request = service.files().get_media(fileId=fid)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        contents[name] = buf.getvalue().decode("utf-8")
        print(f"[✓] โหลด {name} ({len(contents[name])} chars)")
    return contents


def build_context(files):
    parts = []
    for name, content in files.items():
        parts.append(f"### {name}\n\n{content}")
    return "\n\n---\n\n".join(parts)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ต้องตั้ง ANTHROPIC_API_KEY ก่อน เช่น: export ANTHROPIC_API_KEY=sk-ant-...")
        return

    print("กำลังโหลดข้อมูลสุขภาพจาก Google Drive...")
    files = fetch_files_from_drive()
    if not files:
        print("ไม่มีข้อมูล ออกจากโปรแกรม")
        return

    health_context = build_context(files)
    client = anthropic.Anthropic(api_key=api_key)
    history = []

    print("\n" + "="*50)
    print("LifeCoach พร้อมแล้ว! พิมพ์ 'exit' เพื่อออก")
    print("="*50 + "\n")

    while True:
        try:
            user_input = input("คุณ: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if user_input.lower() in ("exit", "quit", "bye"):
            print("LifeCoach: แล้วเจอกันใหม่นะครับ!")
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=f"{SYSTEM_PROMPT}\n\n---\n\nข้อมูลสุขภาพปัจจุบัน:\n\n{health_context}",
            messages=history,
        )

        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        print(f"\nLifeCoach: {reply}\n")


if __name__ == "__main__":
    main()
