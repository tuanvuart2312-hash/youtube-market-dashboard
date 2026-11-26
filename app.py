import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
import pandas as pd
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

# Thanh cấu hình bên trái
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
                                origin = "🇻🇳 Việt Nam"
                            elif any(m in vid_text for m in CN_MARKERS):
                                origin = "🇨🇳 Trung Quốc"
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
                            "Tiêu đề Video": v["snippet"]["title"],
                            "Kênh": v["snippet"]["channelTitle"],
                            "Xuất xứ": origin if origin else "Khác",
                            "Subscribers": subs,
                            "Lượt xem": views,
                            "VPH TB": round(views / hours_live, 1),
                            "Đột phá (View/Sub)": round(views / subs, 2),
                            "Tương tác (%)": round(((likes + comments) / max(views, 1)) * 100, 2),
                            "Ngày đăng": v["snippet"]["publishedAt"][:10],
                            "Link": f"https://www.youtube.com/watch?v={v['id']}"
                        })

                    if rows:
                        df = pd.DataFrame(rows).sort_values(by="Lượt xem", ascending=False).head(int(top_n)).reset_index(drop=True)
                        df.insert(0, "Top", df.index + 1)
                        st.session_state["market_df"] = df
                    else:
                        st.warning("Chưa có video đạt đủ bộ lọc trong khoảng thời gian này.")
            except Exception as e:
                st.error(f"Lỗi quét dữ liệu: {e}")

# Hiển thị giao diện 2 Tab nếu đã có dữ liệu
if "market_df" in st.session_state:
    df = st.session_state["market_df"]
    tab1, tab2 = st.tabs(["📊 Bảng Xếp Hạng Top Video", "🧠 AI Phân Tích Chủ Đề & Bóc Tách Kịch Bản"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Video VN/TQ -> US", f"{len(df)} video")
        c2.metric("Lượt xem trung bình", f"{int(df['Lượt xem'].mean()):,}")
        c3.metric("VPH trung bình cao nhất", f"{df['VPH TB'].max():,} /h")
        c4.metric("Đột phá cao nhất", f"{df['Đột phá (View/Sub)'].max()}x")

        st.dataframe(
            df.drop(columns=["Video ID"]),
            column_config={
                "Thumbnail": st.column_config.ImageColumn("Ảnh bìa", width="medium"),
                "Link": st.column_config.LinkColumn("Xem Video", display_text="Mở YouTube")
            },
            use_container_width=True,
            height=750
        )

    with tab2:
        if not gemini_key:
            st.warning("⚠️ Bạn cần nhập **Gemini API Key** ở thanh bên trái (hoặc lưu trong Secrets) để kích hoạt tính năng phân tích AI.")
        else:
            client = genai.Client(api_key=gemini_key)

            # Phần A: Tổng hợp xu hướng chủ đề của toàn bộ danh sách video
            st.subheader("1️⃣ Tổng Hợp Xu Hướng Tuyến Đề Đang Lên (Từ Toàn Bộ Danh Sách)")
            if st.button("✨ Phân Tích Xu Hướng Chủ Đề Toàn Thị Trường"):
                with st.spinner("AI đang đọc tiêu đề, chỉ số view và gom nhóm tuyến đề..."):
                    titles_summary = "\n".join([
                        f"- {r['Tiêu đề Video']} | Kênh: {r['Kênh']} | View: {r['Lượt xem']:,} | View/Sub: {r['Đột phá (View/Sub)']}x"
                        for _, r in df.iterrows()
                    ])
                    prompt_macro = f"""
                    Dưới đây là danh sách các video YouTube mới của creator Việt Nam và Trung Quốc đánh thị trường người xem Hoa Kỳ trong ngách sống độc lập / căn hộ nhỏ / cải tạo tiết kiệm:
                    {titles_summary}

                    Hãy phân tích theo đúng tư duy phát triển kênh YouTube:
                    1. Gom các video trên thành 3-5 Trụ cột chủ đề (Content Pillars) chính đang kéo view tốt nhất tuần này và chỉ ra vì sao chúng hiệu quả.
                    2. Trích xuất các "Ngòi nổ" (Triggers) và từ khóa/con số đắt giá xuất hiện trong các tiêu đề có tỷ lệ View/Sub cao.
                    3. Đề xuất 5 ý tưởng tiêu đề tiếng Anh (kèm dịch nghĩa tiếng Việt) tối ưu nhất để triển khai ngay cho kênh Chuc Nguyen's Little Life.
                    """
                    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_macro)
                    st.markdown(resp.text)

            st.divider()

            # Phần B: Bóc tách chi tiết từng video (Phụ đề + Bình luận)
            st.subheader("2️⃣ Bóc Tách Sâu Bố Cục Kịch Bản & Nhu Cầu Khán Giả Từng Video")
            video_options = {f"Top {r['Top']}: {r['Tiêu đề Video']} ({r['Lượt xem']:,} views)": r["Video ID"] for _, r in df.iterrows()}
            selected_label = st.selectbox("Chọn 1 video muốn mổ xẻ chi tiết:", list(video_options.keys()))
            selected_vid_id = video_options[selected_label]

            if st.button("🔍 Bóc Tách Video Này (Phụ Đề + Bình Luận)"):
                with st.spinner("Đang tải phụ đề, quét bình luận và phân tích cấu trúc..."):
                    # Lấy phụ đề
                    transcript_text = ""
                    try:
                        ytt_api = YouTubeTranscriptApi()
                        transcript_list = ytt_api.fetch(selected_vid_id)
                        transcript_text = " ".join([t.text for t in transcript_list])[:12000]
                    except Exception:
                        transcript_text = "(Video này không bật phụ đề tự động hoặc chỉ dùng nhạc nền ASMR không lời)."

                    # Lấy top 30 bình luận nhiều like nhất
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
                        comments_text = "(Video tắt bình luận)."

                    prompt_micro = f"""
                    Phân tích chuyên sâu video YouTube sau đây dành cho team sản xuất kênh Chuc Nguyen's Little Life:
                    - Tiêu đề: {selected_label}
                    - Nội dung phụ đề (Transcript): {transcript_text}
                    - Top bình luận từ khán giả Mỹ: {comments_text}

                    Hãy trình bày rõ ràng 4 mục:
                    1. **Cấu trúc & Nhịp điệu kịch bản:** Bóc tách video này chia làm mấy phần, cách mở đầu (Hook) giữ chân người xem ở những phút đầu ra sao.
                    2. **Yếu tố tâm lý & ASMR thị giác:** Điều gì khiến khán giả Mỹ bị cuốn vào video này (chi phí rẻ, sự biến đổi không gian, âm thanh, tâm sự đời sống...)?
                    3. **Insight từ bình luận khán giả:** Khán giả đang khen điều gì nhất và họ đang hỏi/mong muốn xem thêm nội dung gì tiếp theo?
                    4. **Gợi ý cách làm lại (Remix) hay hơn cho kênh của mình:** Đề xuất bố cục 4 phần cụ thể để quay tại Việt Nam.
                    """
                    resp_micro = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_micro)
                    st.markdown(resp_micro.text)
