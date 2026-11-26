import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta, timezone
import re

st.set_page_config(page_title="Camxi - VN/CN Creators Targeting US", layout="wide")
st.title("🇺🇸 Top 50 Video Ngách Sống Độc Lập (Creator VN & TQ Đánh Thị Trường Mỹ)")

default_key = st.secrets.get("YOUTUBE_API_KEY", "")

# Từ khóa nhận diện kênh xuất xứ Việt Nam hoặc Trung Quốc đánh thị trường ngoại
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
    # Kiểm tra tiêu đề chủ yếu dùng bảng chữ cái Latin/tiếng Anh để đánh thị trường US
    ascii_chars = sum(1 for c in title if ord(c) < 128 and c.isalpha())
    total_alpha = sum(1 for c in title if c.isalpha())
    if total_alpha == 0:
        return True
    return (ascii_chars / total_alpha) >= 0.7

with st.sidebar:
    st.header("⚙️ Cấu Hình Lọc Thị Trường")
    api_key = st.text_input("YouTube API Key", value=default_key, type="password")

    st.subheader("1. Kênh đối thủ chuẩn (VN / TQ)")
    default_competitors = (
        "@Ting-DailylifeinChina\n"
        "@HueHueLife\n"
        "@LinhLinhLife\n"
        "@ThusLife"
    )
    competitor_handles = st.text_area(
        "Handle / Link kênh đối thủ (mỗi kênh 1 dòng)",
        value=default_competitors,
        height=120
    )

    st.subheader("2. Quét mở rộng thị trường Mỹ")
    niche_queries = st.text_input(
        "Từ khóa ngách (đã gắn định vị VN/CN)",
        value='("tiny apartment" | "budget makeover" | "solo living" | "small apartment") (Vietnam | China | "in Vietnam" | "in China")'
    )
    strict_origin = st.checkbox(
        "Chỉ giữ lại kênh xác định rõ xuất xứ VN hoặc TQ",
        value=True,
        help="Tự động loại bỏ các kênh của người Mỹ/Hàn/Nhật để tập trung 100% vào creator VN & TQ làm thị trường US."
    )
    days_ago = st.slider("Đăng trong vòng (ngày qua)", 1, 30, 7)
    top_n = st.number_input("Số lượng video xếp hạng", min_value=10, max_value=50, value=50)
    run_btn = st.button("🚀 Quét Top 50 Video (VN/CN -> US)", type="primary", use_container_width=True)

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
    if res.get("items"):
        return res["items"][0]["id"]
    return None

if run_btn:
    if not api_key:
        st.error("⚠️ Vui lòng nhập YouTube API Key ở thanh bên trái!")
    else:
        with st.spinner(f"Đang quét video từ creator VN & TQ đánh thị trường Hoa Kỳ ({days_ago} ngày qua)..."):
            try:
                youtube = build("youtube", "v3", developerKey=api_key)
                cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
                published_after = cutoff_dt.isoformat()

                all_video_ids = set()
                my_channel_id = resolve_channel_id(youtube, "@ChucNguyenLittleLife")

                # 1. Lấy video trong 7 ngày qua từ các kênh mẫu VN/TQ
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
                                part="snippet,contentDetails",
                                playlistId=uploads_id,
                                maxResults=15
                            ).execute()
                            for item in pl_items.get("items", []):
                                pub_dt = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
                                if pub_dt >= cutoff_dt:
                                    all_video_ids.add(item["contentDetails"]["videoId"])

                # 2. Tìm kiếm mở rộng trên thị trường Hoa Kỳ (regionCode="US", ngôn ngữ tiếng Anh)
                search_res = youtube.search().list(
                    part="id,snippet",
                    q=niche_queries,
                    type="video",
                    regionCode="US",
                    relevanceLanguage="en",
                    publishedAfter=published_after,
                    order="viewCount",
                    maxResults=50
                ).execute()

                for item in search_res.get("items", []):
                    if item["snippet"]["channelId"] != my_channel_id:
                        all_video_ids.add(item["id"]["videoId"])

                if not all_video_ids:
                    st.warning("Chưa có video mới nào trong khoảng thời gian này. Hãy thử kéo thanh ngày lên 14 hoặc 30 ngày.")
                else:
                    # 3. Lấy chi tiết video
                    vid_list = list(all_video_ids)
                    video_details = []
                    for i in range(0, len(vid_list), 50):
                        v_res = youtube.videos().list(
                            part="snippet,statistics",
                            id=",".join(vid_list[i:i+50])
                        ).execute()
                        video_details.extend(v_res.get("items", []))

                    # 4. Lấy thông tin kênh (snippet + statistics) để xác định quốc gia VN/CN
                    c_ids = list(set([v["snippet"]["channelId"] for v in video_details]))
                    channel_meta = {}
                    for i in range(0, len(c_ids), 50):
                        c_res = youtube.channels().list(
                            part="snippet,statistics",
                            id=",".join(c_ids[i:i+50])
                        ).execute()
                        for c in c_res.get("items", []):
                            origin = detect_origin(c["snippet"])
                            # Nếu nằm trong danh sách kênh mẫu mà chưa gắn quốc gia, mặc định nhận diện
                            if not origin and c["id"] in seed_channel_ids:
                                origin = "🇻🇳/🇨🇳 Kênh mẫu"
                            channel_meta[c["id"]] = {
                                "subs": max(int(c["statistics"].get("subscriberCount", 1)), 1),
                                "origin": origin,
                                "country_setting": c["snippet"].get("country", "Chưa đặt")
                            }

                    now_utc = datetime.now(timezone.utc)
                    rows = []
                    for v in video_details:
                        pub_dt = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
                        if pub_dt < cutoff_dt:
                            continue

                        title = v["snippet"]["title"]
                        # Lọc video sử dụng tiêu đề tiếng Anh để đánh thị trường US
                        if not is_english_title(title):
                            continue

                        cid = v["snippet"]["channelId"]
                        meta = channel_meta.get(cid, {"subs": 1, "origin": None, "country_setting": ""})
                        
                        # Kiểm tra thêm từ khóa VN/CN ngay trong tiêu đề/mô tả video nếu kênh chưa khai báo
                        origin = meta["origin"]
                        if not origin:
                            vid_text = (title + " " + v["snippet"].get("description", "")).lower()
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
                            "Thumbnail": v["snippet"]["thumbnails"]["medium"]["url"],
                            "Tiêu đề Video": title,
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

                    if not rows:
                        st.warning("Không tìm thấy video nào đạt đủ điều kiện xuất xứ VN/TQ và tiêu đề tiếng Anh trong 7 ngày qua. Bạn có thể tăng số ngày lên 14–30 ngày.")
                    else:
                        df = pd.DataFrame(rows).sort_values(by="Lượt xem", ascending=False).head(int(top_n)).reset_index(drop=True)
                        df.insert(0, "Top", df.index + 1)

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Video VN/TQ -> US", f"{len(df)} video")
                        c2.metric("Lượt xem trung bình", f"{int(df['Lượt xem'].mean()):,}")
                        c3.metric("VPH trung bình cao nhất", f"{df['VPH TB'].max():,} /h")
                        c4.metric("Đột phá cao nhất", f"{df['Đột phá (View/Sub)'].max()}x")

                        st.subheader(f"🏆 Top {len(df)} Video Creator VN & TQ Đánh Thị Trường Mỹ ({days_ago} Ngày Qua)")
                        st.dataframe(
                            df,
                            column_config={
                                "Thumbnail": st.column_config.ImageColumn("Ảnh bìa", width="medium"),
                                "Link": st.column_config.LinkColumn("Xem Video", display_text="Mở YouTube")
                            },
                            use_container_width=True,
                            height=800
                        )
            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")
