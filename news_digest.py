import os
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception:
        return ""

# Hàm tóm tắt bằng DeepSeek
def summarize_with_deepseek(text):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ Thiếu DEEPSEEK_API_KEY"

    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Bạn là chuyên gia PCCC, năng lượng, hạ tầng giao thông. Hãy tóm tắt ngắn gọn tin tức cho bản tin nội bộ."},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.3
            }
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ Lỗi khi gọi DeepSeek: {e}"

# Hàm quét tin & tóm tắt
def collect_news():
    summaries = {}
    for topic, feeds in RSS_FEEDS.items():
        summaries[topic] = []
        for feed_url in feeds:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:  # lấy 3 tin đầu
                content = fetch_article_content(entry.link)
                if not content:
                    continue
                summary = summarize_with_deepseek(content[:4000])  # giới hạn ký tự
                summaries[topic].append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": summary
                })
    return summaries

# Hàm gửi email
def send_email(summaries):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("EMAIL_TO")

    if not (smtp_user and smtp_pass and email_to):
        print("⚠️ Thiếu thông tin SMTP hoặc EMAIL_TO")
        return

    # Tạo email
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"[BẢN TIN] PCCC · LNG · MRT — {today}"
    body = ""

    for topic, items in summaries.items():
        body += f"\n=== {topic} ===\n"
        for item in items:
            body += f"- {item['title']}\n{item['link']}\nTóm tắt: {item['summary']}\n\n"

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
        print("✅ Đã gửi email thành công.")
    except Exception as e:
        print(f"⚠️ Lỗi gửi email: {e}")

if __name__ == "__main__":
    news = collect_news()
    send_email(news)
