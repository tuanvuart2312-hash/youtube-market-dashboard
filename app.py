import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Camxi - Top 50 Video 7 Ngày Qua", layout="wide")
st.title("🔥 Top 50 Video Cùng Ngách Trong 7 Ngày Qua")

default_key = st.secrets.get("YOUTUBE_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Cấu Hình Quét (7 Ngày Qua)")
    api_key = st.text_input("YouTube API Key", value=default_key, type="password")
    
    st.subheader("1. Danh sách kênh đối thủ chuẩn")
    default_competitors = (
        "@Ting-DailylifeinChina\n"
        "@HueHueLife\n"
        "@LinhLinhLife\n"
        "@ThusLife"
    )
    competitor_handles = st.text_area(
        "Handle / Link kênh đối thủ (mỗi kênh 1 dòng)",
        value=default_competitors,
        height=130
    )
    
    st.subheader("2. Từ khóa mở rộng ngách")
    niche_queries = st.text_input(
        "Từ khóa ngách",
        value='"tiny apartment" | "budget makeover" | "solo living" | "small room" | "15m2" | "35m2"'
    )
    region = st.selectbox("Thị trường ưu tiên", ["US", "VN", "KR", "JP", "GB"], index=0)
    days_ago = st.slider("Khoảng thời gian (ngày qua)", min_value=1, max_value=30, value=7)
    top_n = st.number_input("Số lượng video xếp hạng", min_value=10, max_value=50, value=50)
    run_btn = st.button("🚀 Quét Top 50 Video (7 Ngày)", type="primary", use_container_width=True)

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
        with st.spinner(f"Đang quét toàn bộ video mới trong {days_ago} ngày qua..."):
            try:
                youtube = build("youtube", "v3", developerKey=api_key)
                cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
                published_after = cutoff_dt.isoformat()
                
                all_video_ids = set()
                my_channel_id = resolve_channel_id(youtube, "@ChucNguyenLittleLife")

                # 1. Quét video mới trong 7 ngày qua từ các kênh đối thủ trực tiếp
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
                                part="snippet,contentDetails",
                                playlistId=uploads_id,
                                maxResults=15
                            ).execute()
                            for item in pl_items.get("items", []):
                                pub_str = item["snippet"]["publishedAt"]
                                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                                if pub_dt >= cutoff_dt:
                                    all_video_ids.add(item["contentDetails"]["videoId"])

                # 2. Quét tối đa 50 video thị trường theo từ khóa ngách trong 7 ngày qua
                search_res = youtube.search().list(
                    part="id,snippet",
                    q=niche_queries,
                    type="video",
                    regionCode=region,
                    publishedAfter=published_after,
                    order="viewCount",
                    maxResults=50
                ).execute()

                for item in search_res.get("items", []):
                    if item["snippet"]["channelId"] != my_channel_id:
                        all_video_ids.add(item["id"]["videoId"])

                if not all_video_ids:
                    st.warning(f"Không có video nào đăng trong {days_ago} ngày qua khớp bộ lọc. Bạn có thể tăng số ngày lên 14 hoặc 30 ngày ở thanh bên trái.")
                else:
                    # 3. Lấy thông số chi tiết từng video (chia lô 50 ID/lần)
                    vid_list = list(all_video_ids)
                    video_details = []
                    for i in range(0, len(vid_list), 50):
                        batch = vid_list[i:i+50]
                        v_res = youtube.videos().list(
                            part="snippet,statistics",
                            id=",".join(batch)
                        ).execute()
                        video_details.extend(v_res.get("items", []))

                    # Lấy số Subscribers của các kênh để tính chỉ số đột phá & VPH
                    c_ids = list(set([v["snippet"]["channelId"] for v in video_details]))
                    sub_map = {}
                    for i in range(0, len(c_ids), 50):
                        c_res = youtube.channels().list(
                            part="statistics",
                            id=",".join(c_ids[i:i+50])
                        ).execute()
                        for c in c_res.get("items", []):
                            sub_map[c["id"]] = max(int(c["statistics"].get("subscriberCount", 1)), 1)

                    now_utc = datetime.now(timezone.utc)
                    rows = []
                    for v in video_details:
                        pub_dt = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
                        if pub_dt < cutoff_dt:
                            continue
                            
                        views = int(v["statistics"].get("viewCount", 0))
                        likes = int(v["statistics"].get("likeCount", 0))
                        comments = int(v["statistics"].get("commentCount", 0))
                        cid = v["snippet"]["channelId"]
                        subs = sub_map.get(cid, 1)
                        
                        # Tính số giờ đã đăng để ra tốc độ tăng trưởng VPH trung bình
                        hours_live = max((now_utc - pub_dt).total_seconds() / 3600, 1)
                        avg_vph = round(views / hours_live, 1)

                        rows.append({
                            "Thumbnail": v["snippet"]["thumbnails"]["medium"]["url"],
                            "Tiêu đề Video": v["snippet"]["title"],
                            "Kênh": v["snippet"]["channelTitle"],
                            "Nguồn": "Đối thủ trực tiếp" if cid in valid_channels else "Mở rộng ngách",
                            "Subscribers": subs,
                            "Lượt xem": views,
                            "VPH TB (View/Giờ)": avg_vph,
                            "Đột phá (View/Sub)": round(views / subs, 2),
                            "Tương tác (%)": round(((likes + comments) / max(views, 1)) * 100, 2),
                            "Ngày đăng": v["snippet"]["publishedAt"][:10],
                            "Link": f"https://www.youtube.com/watch?v={v['id']}"
                        })

                    df = pd.DataFrame(rows).sort_values(by="Lượt xem", ascending=False).head(int(top_n)).reset_index(drop=True)
                    df.insert(0, "Top", df.index + 1)

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Số video lọc được", f"{len(df)} video")
                    c2.metric("Lượt xem trung bình", f"{int(df['Lượt xem'].mean()):,}")
                    c3.metric("VPH trung bình cao nhất", f"{df['VPH TB (View/Giờ)'].max():,} /h")
                    c4.metric("Đột phá cao nhất", f"{df['Đột phá (View/Sub)'].max()}x")

                    st.subheader(f"🏆 Bảng Xếp Hạng Top {len(df)} Video Trong {days_ago} Ngày Qua")
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
