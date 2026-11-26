import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Camxi - Benchmark Đối Thủ & Ngách", layout="wide")
st.title("🎯 Phân Tích Top Video Đối Thủ & Ngách (Chuc Nguyen's Little Life)")

default_key = st.secrets.get("YOUTUBE_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Cấu Hình Quét Thị Trường")
    api_key = st.text_input("YouTube API Key", value=default_key, type="password")
    
    st.subheader("1. Danh sách kênh đối thủ chuẩn")
    default_competitors = (
        "@Ting-DailylifeinChina\n"
        "@HueHueLife\n"
        "@LinhLinhLife\n"
        "@ThusLife"
    )
    competitor_handles = st.text_area(
        "Nhập Handle hoặc Link kênh đối thủ (mỗi kênh 1 dòng)",
        value=default_competitors,
        height=130,
        help="Hệ thống sẽ lấy các video viral nhất từ chính các kênh này (chỉ tốn 1 quota/kênh)."
    )
    
    st.subheader("2. Mở rộng tìm kênh mới cùng ngách")
    niche_queries = st.text_input(
        "Từ khóa đặc trưng của ngách",
        value='"tiny apartment" | "budget makeover" | "solo living" | "small room" Vietnam'
    )
    region = st.selectbox("Thị trường ưu tiên", ["US", "VN", "KR", "JP", "GB"], index=0)
    days_ago = st.slider("Lọc video đăng trong (ngày qua)", 30, 365, 180)
    run_btn = st.button("🚀 Quét Top 20 Video Chuẩn Ngách", type="primary", use_container_width=True)

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
        with st.spinner("Đang thu thập dữ liệu từ các kênh đối thủ và thị trường ngách..."):
            try:
                youtube = build("youtube", "v3", developerKey=api_key)
                all_video_ids = set()
                my_channel_id = resolve_channel_id(youtube, "@ChucNguyenLittleLife")

                # BƯỚC 1: Lấy top video từ danh sách kênh đối thủ trực tiếp (Siêu chuẩn & tiết kiệm quota)
                handles = [line.strip() for line in competitor_handles.splitlines() if line.strip()]
                valid_channels = []
                for h in handles:
                    cid = resolve_channel_id(youtube, h)
                    if cid and cid != my_channel_id:
                        valid_channels.append(cid)
                        ch_info = youtube.channels().list(part="contentDetails", id=cid).execute()
                        if ch_info.get("items"):
                            uploads_id = ch_info["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
                            pl_items = youtube.playlistItems().list(
                                part="contentDetails",
                                playlistId=uploads_id,
                                maxResults=15
                            ).execute()
                            for item in pl_items.get("items", []):
                                all_video_ids.add(item["contentDetails"]["videoId"])

                # BƯỚC 2: Tìm mở rộng các kênh mới cùng ngách căn hộ nhỏ / cải tạo tiết kiệm / sống một mình
                published_after = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
                search_res = youtube.search().list(
                    part="id,snippet",
                    q=niche_queries,
                    type="video",
                    regionCode=region,
                    publishedAfter=published_after,
                    order="viewCount",
                    maxResults=25
                ).execute()

                for item in search_res.get("items", []):
                    if item["snippet"]["channelId"] != my_channel_id:
                        all_video_ids.add(item["id"]["videoId"])

                if not all_video_ids:
                    st.warning("Không tìm thấy video phù hợp. Hãy kiểm tra lại danh sách handle đối thủ.")
                else:
                    # BƯỚC 3: Lấy thông số chi tiết của toàn bộ video thu thập được (chia lô 50 video/lần)
                    vid_list = list(all_video_ids)
                    video_details = []
                    for i in range(0, len(vid_list), 50):
                        batch = vid_list[i:i+50]
                        v_res = youtube.videos().list(
                            part="snippet,statistics",
                            id=",".join(batch)
                        ).execute()
                        video_details.extend(v_res.get("items", []))

                    # Lấy số Subscribers của tất cả kênh liên quan
                    c_ids = list(set([v["snippet"]["channelId"] for v in video_details]))
                    sub_map = {}
                    for i in range(0, len(c_ids), 50):
                        c_res = youtube.channels().list(
                            part="statistics",
                            id=",".join(c_ids[i:i+50])
                        ).execute()
                        for c in c_res.get("items", []):
                            sub_map[c["id"]] = max(int(c["statistics"].get("subscriberCount", 1)), 1)

                    rows = []
                    for v in video_details:
                        # Lọc bỏ video quá ngắn (Shorts dưới 60s) nếu muốn tập trung vlog dài
                        views = int(v["statistics"].get("viewCount", 0))
                        likes = int(v["statistics"].get("likeCount", 0))
                        comments = int(v["statistics"].get("commentCount", 0))
                        cid = v["snippet"]["channelId"]
                        subs = sub_map.get(cid, 1)
                        source_type = "Đối thủ trực tiếp" if cid in valid_channels else "Mở rộng thị trường"

                        rows.append({
                            "Thumbnail": v["snippet"]["thumbnails"]["medium"]["url"],
                            "Tiêu đề Video": v["snippet"]["title"],
                            "Kênh": v["snippet"]["channelTitle"],
                            "Nguồn": source_type,
                            "Subscribers": subs,
                            "Lượt xem": views,
                            "Đột phá (View/Sub)": round(views / subs, 2),
                            "Tương tác (%)": round(((likes + comments) / max(views, 1)) * 100, 2),
                            "Ngày đăng": v["snippet"]["publishedAt"][:10],
                            "Link": f"https://www.youtube.com/watch?v={v['id']}"
                        })

                    # Lấy Top 20 video có lượt xem cao nhất
                    df = pd.DataFrame(rows).sort_values(by="Lượt xem", ascending=False).head(20).reset_index(drop=True)
                    df.insert(0, "Top", df.index + 1)

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Top Video Hiển Thị", f"{len(df)} video")
                    c2.metric("Lượt xem trung bình", f"{int(df['Lượt xem'].mean()):,}")
                    c3.metric("Hệ số đột phá cao nhất", f"{df['Đột phá (View/Sub)'].max()}x")

                    st.subheader("🏆 Top 20 Video Chuẩn Ngách (Căn Hộ Nhỏ / Cải Tạo Tiết Kiệm / Sống Độc Lập)")
                    st.dataframe(
                        df,
                        column_config={
                            "Thumbnail": st.column_config.ImageColumn("Ảnh bìa", width="medium"),
                            "Link": st.column_config.LinkColumn("Video", display_text="Mở YouTube")
                        },
                        use_container_width=True,
                        height=750
                    )
            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")
