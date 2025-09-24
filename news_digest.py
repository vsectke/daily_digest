import os
import logging
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        if not article.text.strip():
            logging.warning(f"Không lấy được nội dung từ {url}")
            return ""
        return article.text
    except Exception as e:
        logging.error(f"Lỗi khi lấy nội dung từ {url}: {e}")
        return ""

# Hàm cắt nội dung ở ranh giới câu
def truncate_to_sentence(text, max_length=4000):
    if len(text) <= max_length:
        return text
    end = text.rfind('.', 0, max_length)
    if end == -1:
        end = max_length
    return text[:end + 1]

# Hàm tóm tắt bằng DeepSeek
def summarize_with_deepseek(text, max_retries=3):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logging.error("Thiếu DEEPSEEK_API_KEY")
        return "⚠️ Thiếu DEEPSEEK_API_KEY"

    for attempt in range(max_retries):
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
                },
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if "choices" not in data or not data["choices"]:
                logging.error("Phản hồi API không chứa 'choices'")
                return "⚠️ Lỗi: Phản hồi API không hợp lệ"
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            logging.error(f"Lỗi khi gọi DeepSeek (thử {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
    return "⚠️ Không thể tóm tắt: Lỗi kết nối API"

# Hàm quét tin & tóm tắt
def collect_news():
    summaries = {}
    for topic, feeds in RSS_FEEDS.items():
        summaries[topic] = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                if feed.bozo:
                    logging.error(f"Lỗi khi phân tích RSS feed {feed_url}: {feed.bozo_exception}")
                    continue
                for entry in feed.entries[:3]:  # lấy 3 tin đầu
                    content = fetch_article_content(entry.link)
                    if not content:
                        continue
                    truncated_content = truncate_to_sentence(content, 4000)
                    summary = summarize_with_deepseek(truncated_content)
                    summaries[topic].append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": summary
                    })
            except Exception as e:
                logging.error(f"Lỗi khi xử lý feed {feed_url}: {e}")
                continue
    return summaries

# Hàm gửi email
def send_email(summaries):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("EMAIL_TO")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, email_to]):
        logging.error("Thiếu thông tin SMTP hoặc EMAIL_TO")
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
        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logging.info("✅ Đã gửi email thành công.")
    except Exception as e:
        logging.error(f"⚠️ Lỗi gửi email: {e}")

if __name__ == "__main__":
    news = collect_news()
    send_email(news)
