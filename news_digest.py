import os
import feedparser
import requests
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from newspaper import Article
    NEWSPAPER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Không thể import newspaper: {e}")
    NEWSPAPER_AVAILABLE = False

# Danh sách RSS cần theo dõi
RSS_FEEDS = {
    "PCCC": [
        "https://baochinhphu.vn/rss/thoi-su.rss",
        "https://cand.com.vn/rss"
    ],
    "LNG": [
        "https://vnexpress.net/rss/kinh-doanh.rss",
        "https://nangluongquocte.petrotimes.vn/rss"
    ],
    "MRT": [
        "https://tuoitre.vn/rss/thoi-su.rss",
        "https://vnexpress.net/rss/thoi-su.rss"
    ]
}

# Hàm lấy nội dung bài báo
def fetch_article_content(url):
    if not NEWSPAPER_AVAILABLE:
        return ""
    
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text[:4000]  # Giới hạn độ dài
    except Exception as e:
        print(f"⚠️ Lỗi khi lấy nội dung từ {url}: {e}")
        return ""

# Hàm lấy mô tả từ RSS feed
def get_description_from_feed(entry):
    """Lấy mô tả từ RSS entry nếu không thể lấy full content"""
    description = ""
    if hasattr(entry, 'description'):
        description = entry.description
    elif hasattr(entry, 'summary'):
        description = entry.summary
    return description[:1000] if description else ""

# Hàm tóm tắt bằng DeepSeek
def summarize_with_deepseek(text):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ Thiếu DEEPSEEK_API_KEY"
    
    if not text.strip():
        return "⚠️ Không có nội dung để tóm tắt"

    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Bạn là chuyên gia PCCC, năng lượng, hạ tầng giao thông. Hãy tóm tắt ngắn gọn tin tức cho bản tin nội bộ bằng tiếng Việt."},
                    {"role": "user", "content": f"Tóm tắt tin tức này:\n{text}"}
                ],
                "temperature": 0.3,
                "max_tokens": 200
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        return "⚠️ Timeout khi gọi DeepSeek API"
    except requests.exceptions.RequestException as e:
        return f"⚠️ Lỗi khi gọi DeepSeek: {e}"
    except Exception as e:
        return f"⚠️ Lỗi không xác định: {e}"

# Hàm quét tin & tóm tắt
def collect_news():
    summaries = {}
    total_processed = 0
    
    for topic, feeds in RSS_FEEDS.items():
        summaries[topic] = []
        print(f"📰 Đang xử lý chủ đề: {topic}")
        
        for feed_url in feeds:
            try:
                print(f"  🔍 Đang quét: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Không có tin tức từ {feed_url}")
                    continue
                
                for entry in feed.entries[:3]:  # lấy 3 tin đầu
                    # Thử lấy full content trước
                    content = fetch_article_content(entry.link)
                    
                    # Nếu không lấy được full content, dùng description từ RSS
                    if not content:
                        content = get_description_from_feed(entry)
                    
                    if not content:
                        print(f"  ⚠️ Không thể lấy nội dung: {entry.title}")
                        continue
                    
                    summary = summarize_with_deepseek(content)
                    summaries[topic].append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": summary
                    })
                    total_processed += 1
                    print(f"  ✅ Đã xử lý: {entry.title[:50]}...")
                    
            except Exception as e:
                print(f"  ❌ Lỗi khi xử lý feed {feed_url}: {e}")
                continue
    
    print(f"📊 Tổng số tin đã xử lý: {total_processed}")
    return summaries

# Hàm gửi email
def send_email(summaries):
    # Kiểm tra biến môi trường
    required_vars = ["SMTP_USER", "SMTP_PASS", "EMAIL_TO"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Thiếu biến môi trường: {', '.join(missing_vars)}")
        return False

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("EMAIL_TO")

    # Tạo email
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"[BẢN TIN] PCCC · LNG · MRT — {today}"
    
    # Đếm tổng số tin
    total_articles = sum(len(items) for items in summaries.values())
    
    body = f"📰 Bản tin tự động ngày {today}\n"
    body += f"📊 Tổng số: {total_articles} tin tức\n"
    body += "=" * 50 + "\n\n"

    for topic, items in summaries.items():
        if not items:
            continue
            
        body += f"\n🏷️ === {topic} === ({len(items)} tin)\n\n"
        for i, item in enumerate(items, 1):
            body += f"{i}. {item['title']}\n"
            body += f"🔗 {item['link']}\n"
            body += f"📝 Tóm tắt: {item['summary']}\n"
            body += "-" * 30 + "\n\n"

    body += f"\n🤖 Được tạo tự động bởi Daily Digest\n"
    body += f"⏰ Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("✅ Đã gửi email thành công!")
        return True
    except Exception as e:
        print(f"❌ Lỗi gửi email: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Bắt đầu thu thập tin tức...")
    
    # Kiểm tra các dependency quan trọng
    if not NEWSPAPER_AVAILABLE:
        print("⚠️ Newspaper3k không khả dụng, chỉ sử dụng RSS descriptions")
    
    try:
        news = collect_news()
        
        # Kiểm tra xem có tin tức nào không
        total_news = sum(len(items) for items in news.values())
        if total_news == 0:
            print("⚠️ Không thu thập được tin tức nào!")
        else:
            print(f"📧 Đang gửi email với {total_news} tin tức...")
            success = send_email(news)
            if success:
                print("🎉 Hoàn thành!")
            else:
                print("❌ Thất bại khi gửi email!")
                
    except Exception as e:
        print(f"💥 Lỗi chính: {e}")
        raise
