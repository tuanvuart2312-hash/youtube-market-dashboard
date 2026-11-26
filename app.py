import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Camxi - YouTube Market & Topic AI", layout="wide")
st.title("🎯 Hệ Thống Nghiên Cứu Thị Trường & Bóc Tách Chủ Đề YouTube")

default_yt_key = st.secrets.get("YOUTUBE_API_KEY", "")
default_gemini_key = st.secrets.get("GEMINI_API_KEY", "")

VN_MARKERS = [
    "vietnam", "viet nam", "hanoi", "ha noi", "saigon", "sai gon",
    "ho chi minh", "da nang", "dalat", "da lat", "🇻🇳", "việt nam"
]
CN_MARKERS = [
    "china", "shenzhen", "shanghai", "beijing", "guangzhou", "chengdu",
    "hangzhou", "chongqing", "🇨🇳", "taobao", "temu", "trung quốc"
]

def ask_gemini(api_key, prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}]
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code == 200:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        return f"⚠️ Lỗi kết nối Gemini API ({response.status_code}): {response.text}"

def detect_origin(snippet):
    country_code = snippet.get("country", "").upper()
    text_blob = (
        snippet.get("title", "") + " " +
        snippet.get("description", "") + " " +
        snippet.get("customUrl", "")
    ).lower()
    if country_code == "VN" or any(m in text_blob for m in VN_MARKERS):
        return "🇻🇳 Việt Nam"
    if country_code in ["CN", "HK", "TW"] or any(m in text_blob for m in CN_MARKERS):
        return "🇨🇳 Trung Quốc"
    return None

def is_english_title(title):
    ascii_chars = sum(1 for c in title if ord(c) < 128 and c.isalpha())
    total_alpha = sum(1 for c in title if c.isalpha())
    return True if total_alpha == 0 else (ascii_chars / total_alpha) >= 0.7

def resolve_channel_id(youtube, raw_input):
    text = raw_input.strip()
    if not text:
        return None
    if "youtube.com/channel/" in text:
        return text.split("youtube.com/channel/")[-1].split("/")[0].split("?")[0]
    if "youtube.com/@" in text:
        text = "@" + text.split("youtube.com/@")[-1].split("/")[0].split("?")[0]
    if not text.startswith("@"):
        text = "@" + text
    res = youtube.channels().list(part="id", forHandle=text).execute()
    return res["items"][0]["id"] if res.get("items") else None

with st.sidebar:
    st.header("⚙️ Cấu Hình API & Bộ Lọc")
    yt_key = st.text_input("YouTube API Key", value=default_yt_key, type="password")
    gemini_key = st.text_input("Gemini API Key (Cho tab Phân tích AI)", value=default_gemini_key, type="password")

    st.subheader("1. Kênh đối thủ chuẩn (VN / TQ)")
    default_competitors = (
        "@Ting-DailylifeinChina\n"
        "@HueHueLife\n"
        "@LinhLinhLife\n"
        "@ThusLife"
    )
    competitor_handles = st.text_area("Handle / Link kênh đối thủ", value=default_competitors, height=110)

    st.subheader("2. Bộ lọc thị trường Mỹ")
    niche_queries = st.text_input(
        "Từ khóa ngách",
        value='("tiny apartment" | "budget makeover" | "solo living" | "small apartment") (Vietnam | China | "in Vietnam" | "in China")'
    )
    strict_origin = st.checkbox("Chỉ lấy creator VN hoặc TQ", value=True)
    days_ago = st.slider("Đăng trong vòng (ngày qua)", 1, 30, 7)
    top_n = st.number_input("Số video xếp hạng", 10, 50, 50)
    run_btn = st.button("🚀 Quét Dữ Liệu Thị Trường", type="primary", use_container_width=True)

if run_btn:
    if not yt_key:
        st.error("⚠️ Vui lòng nhập YouTube API Key!")
    else:
        with st.spinner("Đang quét Top video từ creator VN & TQ đánh thị trường Mỹ..."):
            try:
                youtube = build("youtube", "v3", developerKey=yt_key)
                cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
                published_after = cutoff_dt.isoformat()
                all_video_ids = set()
                my_channel_id = resolve_channel_id(youtube, "@ChucNguyenLittleLife")

                handles = [line.strip() for line in competitor_handles.splitlines() if line.strip()]
                seed_channel_ids = []
                for h in handles:
                    cid = resolve_channel_id(youtube, h)
                    if cid and cid != my_channel_id:
                        seed_channel_ids.append(cid)
                        ch_info = youtube.channels().list(part="contentDetails", id=cid).execute()
                        if ch_info.get("items"):
                            uploads_id = ch_info["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
                            pl_items = youtube.playlistItems().list(
                                part="snippet,contentDetails", playlistId=uploads_id, maxResults=15
                            ).execute()
                            for item in pl_items.get("items", []):
                                pub_dt = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
                                if pub_dt >= cutoff_dt:
                                    all_video_ids.add(item["contentDetails"]["videoId"])

                search_res = youtube.search().list(
                    part="id,snippet", q=niche_queries, type="video",
                    regionCode="US", relevanceLanguage="en",
                    publishedAfter=published_after, order="viewCount", maxResults=50
                ).execute()

                for item in search_res.get("items", []):
                    if item["snippet"]["channelId"] != my_channel_id:
                        all_video_ids.add(item["id"]["videoId"])

                if not all_video_ids:
                    st.warning("Không tìm thấy video phù hợp. Hãy thử tăng số ngày lên 14 hoặc 30 ngày.")
                else:
                    vid_list = list(all_video_ids)
                    video_details = []
                    for i in range(0, len(vid_list), 50):
                        v_res = youtube.videos().list(part="snippet,statistics", id=",".join(vid_list[i:i+50])).execute()
                        video_details.extend(v_res.get("items", []))

                    c_ids = list(set([v["snippet"]["channelId"] for v in video_details]))
                    channel_meta = {}
                    for i in range(0, len(c_ids), 50):
                        c_res = youtube.channels().list(part="snippet,statistics", id=",".join(c_ids[i:i+50])).execute()
                        for c in c_res.get("items", []):
                            origin = detect_origin(c["snippet"])
                            if not origin and c["id"] in seed_channel_ids:
                                origin = "🇻🇳/🇨🇳 Kênh mẫu"
                            channel_meta[c["id"]] = {
                                "subs": max(int(c["statistics"].get("subscriberCount", 1)), 1),
                                "origin": origin
                            }

                    now_utc = datetime.now(timezone.utc)
                    rows
