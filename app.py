import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import zipfile
import os

# --- TIF GENERATOR LOGIC ---
def create_tif_bytes(acct_no, name, date):
    width, height = 2480, 3508
    img = Image.new('1', (width, height), color=1)
    draw = ImageDraw.Draw(img)
    
    # พยายามโหลดฟอนต์ (ใน Codespaces)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 120)
    except:
        font = ImageFont.load_default()

    draw.text((200, 400), f"ACCOUNT DOCUMENT", font=font, fill=0)
    draw.text((200, 600), f"ACCT NO : {acct_no}", font=font, fill=0)
    draw.text((200, 750), f"NAME    : {name}", font=font, fill=0)
    draw.text((200, 900), f"DATE    : {date}", font=font, fill=0)
    
    # Save ลง Memory (ByteIO) แทนการลงไฟล์จริง
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='TIFF', compression='tiff_ccitt_4', dpi=(300, 300))
    return img_byte_arr.getvalue()

# --- STREAMLIT UI ---
st.set_page_config(page_title="TIF Batch Gen", layout="wide")
st.title("🚀 TIF Batch Generator (Pro Edition)")
st.subheader("Upload Excel to generate multiple TIF files at once")

uploaded_file = st.file_uploader("เลือกไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("### Preview ข้อมูลจาก Excel")
    st.dataframe(df.head()) # โชว์ 5 แถวแรก

    # ให้ User เลือกคอลัมน์ที่ต้องการ
    cols = df.columns.tolist()
    acct_col = st.selectbox("เลือกคอลัมน์ Account No:", cols)
    name_col = st.selectbox("เลือกคอลัมน์ Name:", cols)

    if st.button("🔥 START GENERATING"):
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, row in df.iterrows():
                # Gen TIF แต่ละแถว
                tif_data = create_tif_bytes(row[acct_col], row[name_col], "2026-02-16")
                
                # ใส่ลงใน ZIP
                filename = f"{row[acct_col]}.tif"
                zip_file.writestr(filename, tif_data)
                
                # Update Progress
                progress = (i + 1) / len(df)
                progress_bar.progress(progress)
                status_text.text(f"Processing: {row[acct_col]}")

        # เตรียมปุ่ม Download ZIP
        st.success("✅ เสร็จเรียบร้อย!")
        st.download_button(
            label="📥 DOWNLOAD ALL (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="generated_tifs.zip",
            mime="application/zip"
        )