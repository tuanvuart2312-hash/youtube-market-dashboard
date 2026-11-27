import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Camxi - YouTube Market & Topic AI", layout="wide")
st.title("YouTube Market Research & AI Topic Analyzer")

default_yt_key = st.secrets.get("YOUTUBE_API_KEY", "")
default_gemini_key = st.secrets.get("GEMINI_API_KEY", "")

VN_MARKERS = [
    "vietnam", "viet nam", "hanoi", "ha noi", "saigon", "sai gon",
    "ho chi minh", "da nang", "dalat", "da lat", "vietnamese"
]
CN_MARKERS = [
    "china", "shenzhen", "shanghai", "beijing", "guangzhou", "chengdu",
    "hangzhou", "chongqing", "taobao", "temu", "chinese"
]

def ask_gemini(api_key, prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"⚠️ Lỗi API ({response.status_code}): {response.text}"
    except requests.exceptions.Timeout:
        return "⏳ Kết nối bị quá thời gian chờ (Timeout). Bạn hãy bấm nút phân tích lại một lần nữa nhé!"
    except Exception as e:
        return f"⚠️ Lỗi kết nối: {e}"
def detect_origin(snippet):
    country_code = snippet.get("country", "").upper()
    text_blob = (
        snippet.get("title", "") + " " +
        snippet.get("description", "") + " " +
        snippet.get("customUrl", "")
    ).lower()
    if country_code == "VN" or any(m in text_blob for m in VN_MARKERS):
        return "VN - Vietnam"
    if country_code in ["CN", "HK", "TW"] or any(m in text_blob for m in CN_MARKERS):
        return "CN - China"
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
    st.header("API & Filter Settings")
    yt_key = st.text_input("YouTube API Key", value=default_yt_key, type="password")
    gemini_key = st.text_input("Gemini API Key", value=default_gemini_key, type="password")

    st.subheader("1. Seed Channels (VN / CN)")
    default_competitors = (
        "@Ting-DailylifeinChina\n"
        "@HueHueLife\n"
        "@LinhLinhLife\n"
        "@ThusLife"
    )
    competitor_handles = st.text_area("Competitor Handles", value=default_competitors, height=110)

    st.subheader("2. US Market Filters")
    niche_queries = st.text_input(
        "Niche Keywords",
        value='("tiny apartment" | "budget makeover" | "solo living" | "small apartment") (Vietnam | China | "in Vietnam" | "in China")'
    )
    strict_origin = st.checkbox("Only VN or CN creators", value=True)
    days_ago = st.slider("Published within (days)", 1, 30, 7)
    top_n = st.number_input("Top N videos", 10, 50, 50)
    run_btn = st.button("Scan Market Data", type="primary", use_container_width=True)

if run_btn:
    if not yt_key:
        st.error("Please enter your YouTube API Key!")
    else:
        with st.spinner("Scanning VN & CN creators targeting US market..."):
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
                    st.warning("No matching videos found. Try increasing days to 14 or 30.")
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
                                origin = "VN/CN Seed"
                            channel_meta[c["id"]] = {
                                "subs": max(int(c["statistics"].get("subscriberCount", 1)), 1),
                                "origin": origin
                            }

                    now_utc = datetime.now(timezone.utc)
                    rows = []
                    for v in video_details:
                        pub_dt = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
                        if pub_dt < cutoff_dt or not is_english_title(v["snippet"]["title"]):
                            continue
                        cid = v["snippet"]["channelId"]
                        meta = channel_meta.get(cid, {"subs": 1, "origin": None})
                        origin = meta["origin"]
                        if not origin:
                            vid_text = (v["snippet"]["title"] + " " + v["snippet"].get("description", "")).lower()
                            if any(m in vid_text for m in VN_MARKERS):
                                origin = "VN - Vietnam"
                            elif any(m in vid_text for m in CN_MARKERS):
                                origin = "CN - China"
                        if strict_origin and not origin:
                            continue

                        views = int(v["statistics"].get("viewCount", 0))
                        likes = int(v["statistics"].get("likeCount", 0))
                        comments = int(v["statistics"].get("commentCount", 0))
                        subs = meta["subs"]
                        hours_live = max((now_utc - pub_dt).total_seconds() / 3600, 1)

                        rows.append({
                            "Video ID": v["id"],
                            "Thumbnail": v["snippet"]["thumbnails"]["medium"]["url"],
                            "Title": v["snippet"]["title"],
                            "Channel": v["snippet"]["channelTitle"],
                            "Origin": origin if origin else "Other",
                            "Subscribers": subs,
                            "Views": views,
                            "VPH": round(views / hours_live, 1),
                            "Outlier (View/Sub)": round(views / subs, 2),
                            "Engagement (%)": round(((likes + comments) / max(views, 1)) * 100, 2),
                            "Published": v["snippet"]["publishedAt"][:10],
                            "Link": f"https://www.youtube.com/watch?v={v['id']}"
                        })

                    if rows:
                        df = pd.DataFrame(rows).sort_values(by="Views", ascending=False).head(int(top_n)).reset_index(drop=True)
                        df.insert(0, "Top", df.index + 1)
                        st.session_state["market_df"] = df
                        st.session_state.pop("macro_result", None)
                        st.session_state.pop("micro_result", None)
                    else:
                        st.warning("No videos matched all filters in this timeframe.")
            except Exception as e:
                st.error(f"Error: {e}")

if "market_df" in st.session_state:
    df = st.session_state["market_df"]
    tab1, tab2 = st.tabs(["Top Videos Ranking", "AI Topic & Script Analyzer"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Videos Found", f"{len(df)}")
        c2.metric("Avg Views", f"{int(df['Views'].mean()):,}")
        c3.metric("Max VPH", f"{df['VPH'].max():,} /h")
        c4.metric("Max Outlier", f"{df['Outlier (View/Sub)'].max()}x")

        st.dataframe(
            df.drop(columns=["Video ID"]),
            column_config={
                "Thumbnail": st.column_config.ImageColumn("Thumbnail", width="medium"),
                "Link": st.column_config.LinkColumn("Watch", display_text="Open")
            },
            use_container_width=True,
            height=750
        )

    with tab2:
        if not gemini_key:
            st.warning("Please enter your Gemini API Key in the sidebar or Secrets.")
        else:
            st.subheader("1. Macro Topic Trends (All Top Videos)")
            if st.button("Analyze Market Topic Trends"):
                with st.spinner("AI is clustering topics and identifying winning pillars..."):
                    titles_summary = "\n".join([
                        f"- {r['Title']} | Channel: {r['Channel']} | Views: {r['Views']:,} | Outlier: {r['Outlier (View/Sub)']}x"
                        for _, r in df.iterrows()
                    ])
                    prompt_macro = (
                        "Analyze these recent YouTube videos from Vietnamese and Chinese creators targeting US viewers in the solo living / tiny apartment / budget makeover niche:\n"
                        + titles_summary +
                        "\n\nRespond in Vietnamese with 3 clear sections:\n"
                        "1. Gom nhóm thành 3-5 Trụ cột chủ đề (Content Pillars) đang kéo view tốt nhất tuần này và lý do hiệu quả.\n"
                        "2. Trích xuất các từ khóa, con số và ngòi nổ tâm lý (Triggers) đắt giá trong tiêu đề có hệ số Outlier cao.\n"
                        "3. Đề xuất 5 ý tưởng tiêu đề tiếng Anh (kèm dịch tiếng Việt) tối ưu nhất để quay ngay cho kênh Chuc Nguyen's Little Life."
                    )
                    st.session_state["macro_result"] = ask_gemini(gemini_key, prompt_macro)

            if "macro_result" in st.session_state:
                st.markdown(st.session_state["macro_result"])

            st.divider()

            st.subheader("2. Deep-Dive Script & Audience Comment Analysis")
            video_options = {f"Top {r['Top']}: {r['Title']} ({r['Views']:,} views)": r["Video ID"] for _, r in df.iterrows()}
            selected_label = st.selectbox("Select a video to analyze:", list(video_options.keys()))
            selected_vid_id = video_options[selected_label]

            if st.button("Analyze Selected Video (Transcript + Comments)"):
                with st.spinner("Fetching transcript, comments, and analyzing structure..."):
                    transcript_text = ""
                    try:
                        ytt_api = YouTubeTranscriptApi()
                        transcript_list = ytt_api.fetch(selected_vid_id)
                        transcript_text = " ".join([t.text for t in transcript_list])[:12000]
                    except Exception:
                        transcript_text = "(No transcript available / Silent ASMR vlog)."

                    comments_text = ""
                    try:
                        youtube = build("youtube", "v3", developerKey=yt_key)
                        c_res = youtube.commentThreads().list(
                            part="snippet", videoId=selected_vid_id,
                            order="relevance", maxResults=30
                        ).execute()
                        comments_list = [
                            item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                            for item in c_res.get("items", [])
                        ]
                        comments_text = "\n- ".join(comments_list)
                    except Exception:
                        comments_text = "(Comments disabled)."

                    prompt_micro = (
                        f"Analyze this YouTube video for Chuc Nguyen's Little Life production team:\n"
                        f"- Title: {selected_label}\n"
                        f"- Transcript: {transcript_text}\n"
                        f"- Top US Viewer Comments: {comments_text}\n\n"
                        "Respond in Vietnamese with 4 clear sections:\n"
                        "1. Cấu trúc & Nhịp điệu kịch bản (bố cục các phần, cách mở đầu Hook giữ chân người xem).\n"
                        "2. Yếu tố tâm lý & ASMR thị giác khiến khán giả Mỹ bị cuốn hút.\n"
                        "3. Insight từ bình luận khán giả (họ khen gì nhất và muốn xem gì tiếp theo).\n"
                        "4. Gợi ý bố cục 4 phần cụ thể để quay phiên bản hay hơn tại Việt Nam."
                    )
                    st.session_state["micro_result"] = ask_gemini(gemini_key, prompt_micro)

            if "micro_result" in st.session_state:
                st.markdown(st.session_state["micro_result"])
