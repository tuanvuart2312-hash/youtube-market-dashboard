import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="YouTube Niche Competitor Finder", layout="wide")
st.title("🎯 Tìm Top 20 Video Cùng Ngách Với Kênh Của Bạn")

default_key = st.secrets.get("YOUTUBE_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Cấu hình kênh & bộ lọc")
    api_key = st.text_input("YouTube API Key", value=default_key, type="password")
    channel_handle = st.text_input("Handle kênh của bạn", value="@ChucNguyenLittleLife")
    custom_keywords = st.text_input(
        "Từ khóa ngách bổ sung (tùy chọn)",
        value='"little life" | "daily vlog" | "slow living" | "cuộc sống hàng ngày"',
        help="Hệ thống sẽ tự động kết hợp từ khóa từ kênh của bạn với cụm từ khóa này."
    )
    region = st.selectbox("Thị trường mục tiêu", ["VN", "US", "KR", "JP", "GB"])
    days_ago = st.slider("Video đăng trong vòng (ngày qua)", 7, 180, 60)
    run_btn = st.button("🚀 Tìm Top 20 Video Cùng Ngách", type="primary", use_container_width=True)

if run_btn:
    if not api_key:
        st.error("⚠️ Vui lòng nhập YouTube API Key ở cột bên trái!")
    else:
        with st.spinner(f"Đang phân tích kênh {channel_handle} và quét thị trường..."):
            try:
                youtube = build("youtube", "v3", developerKey=api_key)
                
                # 1. Lấy thông tin kênh của bạn để nhận diện ngách tự động
                handle_clean = channel_handle.strip()
                if "youtube.com/" in handle_clean:
                    handle_clean = "@" + handle_clean.split("@")[-1].split("/")[0]
                if not handle_clean.startswith("@"):
                    handle_clean = "@" + handle_clean

                ch_res = youtube.channels().list(
                    part="snippet,brandingSettings,contentDetails,statistics",
                    forHandle=handle_clean
                ).execute()

                my_channel_id = ""
                auto_keywords = []

                if ch_res.get("items"):
                    my_ch = ch_res["items"][0]
                    my_channel_id = my_ch["id"]
                    ch_title = my_ch["snippet"]["title"]
                    ch_subs = int(my_ch["statistics"].get("subscriberCount", 0))
                    st.success(f"✅ Đã nhận diện kênh: **{ch_title}** ({ch_subs:,} Subscribers)")

                    # Trích xuất từ khóa cài đặt của kênh (nếu có)
                    raw_kw = my_ch.get("brandingSettings", {}).get("channel", {}).get("keywords", "")
                    if raw_kw:
                        auto_keywords.extend([k.strip('"') for k in raw_kw.split() if len(k) > 2][:4])

                    # Lấy thêm từ khóa từ các video đã đăng của kênh
                    uploads_id = my_ch["contentDetails"]["relatedPlaylists"]["uploads"]
                    pl_res = youtube.playlistItems().list(
                        part="snippet",
                        playlistId=uploads_id,
                        maxResults=5
                    ).execute()
                    
                    if pl_res.get("items"):
                        st.info("📌 **Các video gần nhất trên kênh của bạn:** " + " | ".join([item["snippet"]["title"] for item in pl_res["items"][:3]]))
                else:
                    st.warning(f"Không tìm thấy dữ liệu công khai cho {handle_clean}, hệ thống sẽ quét theo bộ từ khóa ngách bên trái.")

                # 2. Xây dựng truy vấn tìm kiếm kết hợp
                final_query = custom_keywords
                if auto_keywords:
                    extra_q = " | ".join([f'"{kw}"' for kw in auto_keywords])
                    final_query = f"({final_query}) | ({extra_q})" if final_query else extra_q

                published_after = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()

                # Lấy dư 30 video để sau khi lọc bỏ kênh của bạn vẫn đủ Top 20 đối thủ
                search_res = youtube.search().list(
                    part="id,snippet",
                    q=final_query,
                    type="video",
                    regionCode=region,
                    publishedAfter=published_after,
                    order="viewCount",
                    maxResults=30
                ).execute()

                # Lọc bỏ video thuộc chính kênh của bạn
                video_ids = [
                    item["id"]["videoId"] 
                    for item in search_res.get("items", []) 
                    if item["snippet"]["channelId"] != my_channel_id
                ][:20]

                if not video_ids:
                    st.warning("Không tìm thấy video đối thủ nào phù hợp. Hãy thử mở rộng số ngày hoặc điều chỉnh từ khóa.")
                else:
                    # 3. Lấy thông số chi tiết của Top 20 video
                    vid_res = youtube.videos().list(
                        part="snippet,statistics",
                        id=",".join(video_ids)
                    ).execute()

                    channel_ids = list(set([v["snippet"]["channelId"] for v in vid_res["items"]]))
                    comp_ch_res = youtube.channels().list(
                        part="statistics",
                        id=",".join(channel_ids)
                    ).execute()
                    sub_map = {c["id"]: int(c["statistics"].get("subscriberCount", 1)) for c in comp_ch_res["items"]}

                    rows = []
                    for idx, v in enumerate(vid_res["items"], 1):
                        views = int(v["statistics"].get("viewCount", 0))
                        likes = int(v["statistics"].get("likeCount", 0))
                        comments = int(v["statistics"].get("commentCount", 0))
                        c_id = v["snippet"]["channelId"]
                        subs = max(sub_map.get(c_id, 1), 1)
                        outlier = round(views / subs, 2)

                        rows.append({
                            "Top": idx,
                            "Thumbnail": v["snippet"]["thumbnails"]["medium"]["url"],
                            "Tiêu đề Video": v["snippet"]["title"],
                            "Kênh": v["snippet"]["channelTitle"],
                            "Subscribers": subs,
                            "Lượt xem": views,
                            "Đột phá (View/Sub)": outlier,
                            "Tương tác (%)": round(((likes + comments) / max(views, 1)) * 100, 2),
                            "Ngày đăng": v["snippet"]["publishedAt"][:10],
                            "Link": f"https://www.youtube.com/watch?v={v['id']}"
                        })

                    df = pd.DataFrame(rows).sort_values(by="Lượt xem", ascending=False).reset_index(drop=True)
                    df["Top"] = df.index + 1

                    # Chỉ số tổng quan
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Số lượng video phân tích", f"Top {len(df)}")
                    col2.metric("Lượt xem trung bình Top 20", f"{int(df['Lượt xem'].mean()):,}")
                    col3.metric("Hệ số đột phá cao nhất", f"{df['Đột phá (View/Sub)'].max()}x")

                    # Bảng hiển thị Top 20
                    st.subheader("🏆 Bảng Xếp Hạng Top 20 Video Cùng Ngách")
                    st.dataframe(
                        df,
                        column_config={
                            "Thumbnail": st.column_config.ImageColumn("Ảnh bìa", width="medium"),
                            "Link": st.column_config.LinkColumn("Xem Video", display_text="Mở YouTube")
                        },
                        use_container_width=True,
                        height=750
                    )

            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")
