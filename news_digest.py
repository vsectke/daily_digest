#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily News Digest System
Collects news from RSS feeds and sends email summary
"""

import os
import sys
import feedparser
import requests
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import re
import time

print("🚀 Khởi động Daily News Digest System...")
print(f"🐍 Python version: {sys.version}")
print(f"⏰ Thời gian: {datetime.now()}")

# Danh sách RSS feeds theo chủ đề
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

# User agent để tránh bị block
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def clean_text(text):
    """Làm sạch text từ HTML"""
    if not text:
        return ""
    
    # Loại bỏ HTML tags
    soup = BeautifulSoup(text, 'html.parser')
    text = soup.get_text()
    
    # Làm sạch whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Loại bỏ ký tự đặc biệt không cần thiết
    text = re.sub(r'[^\w\s.,!?;:()\-""''…]', '', text)
    
    return text

def extract_content_from_html(html_content, url):
    """Trích xuất nội dung chính từ HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Loại bỏ các phần không cần thiết
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'menu']):
            tag.decompose()
        
        # Tìm content chính theo các pattern phổ biến
        selectors = [
            'article',
            '[class*="content"]', 
            '[class*="article"]',
            '[class*="post"]',
            '[class*="story"]',
            '[id*="content"]',
            '[id*="article"]',
            '.main-content',
            '.entry-content',
            '.post-content'
        ]
        
        content_text = ""
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                content_text = " ".join([elem.get_text() for elem in elements])
                break
        
        # Nếu không tìm được selector cụ thể, lấy toàn bộ body
        if not content_text:
            body = soup.find('body')
            if body:
                content_text = body.get_text()
            else:
                content_text = soup.get_text()
        
        # Làm sạch và cắt ngắn
        content_text = clean_text(content_text)
        
        return content_text[:3000] if content_text else ""
        
    except Exception as e:
        print(f"    ⚠️ Lỗi parse HTML: {e}")
        return ""

def fetch_article_content(url, max_retries=2):
    """Lấy nội dung bài báo từ URL"""
    for attempt in range(max_retries):
        try:
            print(f"    🌐 Fetching: {url[:80]}...")
            
            response = requests.get(
                url, 
                headers=HEADERS, 
                timeout=15,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Auto-detect encoding
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
            
            content = extract_content_from_html(response.text, url)
            
            if len(content) > 100:  # Có nội dung hợp lệ
                print(f"    ✅ Lấy được {len(content)} ký tự")
                return content
            else:
                print(f"    ⚠️ Nội dung quá ngắn ({len(content)} ký tự)")
                return ""
                
        except requests.exceptions.Timeout:
            print(f"    ⚠️ Timeout attempt {attempt+1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(2)
            continue
            
        except requests.exceptions.RequestException as e:
            print(f"    ⚠️ Request error: {str(e)[:100]}")
            return ""
            
        except Exception as e:
            print(f"    ⚠️ Unexpected error: {str(e)[:100]}")
            return ""
    
    return ""

def get_rss_description(entry):
    """Lấy mô tả từ RSS entry"""
    description = ""
    
    # Thử các trường khác nhau
    for field in ['description', 'summary', 'content']:
        if hasattr(entry, field):
            content = getattr(entry, field)
            
            if isinstance(content, list) and content:
                # Trường hợp content là list (như feedparser)
                description = content[0].get('value', '') if isinstance(content[0], dict) else str(content[0])
            elif isinstance(content, str):
                description = content
            
            if description:
                break
    
    if description:
        description = clean_text(description)
        return description[:1500]
    
    return ""

def summarize_with_deepseek(content, title=""):
    """Tóm tắt nội dung bằng DeepSeek API"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ Thiếu DEEPSEEK_API_KEY"
    
    if not content or len(content.strip()) < 50:
        return "⚠️ Nội dung quá ngắn để tóm tắt"

    try:
        # Tạo prompt context
        prompt_text = f"Tiêu đề: {title}\n\nNội dung: {content[:2000]}"  # Giới hạn để tránh token limit
        
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system", 
                        "content": "Bạn là chuyên gia phân tích tin tức Việt Nam về PCCC (phòng cháy chữa cháy), năng lượng LNG, và giao thông MRT. Tóm tắt tin tức ngắn gọn, chính xác bằng tiếng Việt."
                    },
                    {
                        "role": "user", 
                        "content": f"Hãy tóm tắt tin tức này trong 2-3 câu, tập trung vào thông tin quan trọng:\n\n{prompt_text}"
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 200,
                "top_p": 0.9
            },
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        if 'choices' in result and result['choices'] and 'message' in result['choices'][0]:
            summary = result['choices'][0]['message']['content'].strip()
            return summary if summary else "⚠️ AI không trả về kết quả"
        else:
            return "⚠️ Phản hồi API không hợp lệ"
            
    except requests.exceptions.Timeout:
        return "⚠️ Timeout khi gọi DeepSeek API"
    except requests.exceptions.RequestException as e:
        return f"⚠️ Lỗi API: {str(e)[:80]}"
    except Exception as e:
        return f"⚠️ Lỗi: {str(e)[:80]}"

def process_rss_feed(feed_url, topic, max_articles=3):
    """Xử lý một RSS feed"""
    articles = []
    
    try:
        print(f"  📡 Đang xử lý: {feed_url}")
        
        # Parse RSS
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            print(f"  ❌ Không có bài viết nào")
            return articles
        
        print(f"  📰 Tìm thấy {len(feed.entries)} bài viết, xử lý {min(max_articles, len(feed.entries))} bài")
        
        for i, entry in enumerate(feed.entries[:max_articles]):
            print(f"\n    📄 [{i+1}/{max_articles}] {entry.title[:60]}...")
            
            # Lấy nội dung full từ link
            full_content = ""
            if hasattr(entry, 'link') and entry.link:
                full_content = fetch_article_content(entry.link)
            
            # Nếu không lấy được full content, dùng description từ RSS
            if not full_content:
                full_content = get_rss_description(entry)
                print(f"    📝 Sử dụng RSS description: {len(full_content)} ký tự")
            
            if not full_content:
                print(f"    ❌ Không có nội dung")
                continue
            
            # Tóm tắt bằng AI
            print(f"    🤖 Đang tóm tắt...")
            summary = summarize_with_deepseek(full_content, entry.title)
            
            # Lưu thông tin bài viết
            article_info = {
                "title": getattr(entry, 'title', 'Không có tiêu đề'),
                "link": getattr(entry, 'link', ''),
                "summary": summary,
                "published": getattr(entry, 'published', ''),
                "content_length": len(full_content)
            }
            
            articles.append(article_info)
            print(f"    ✅ Hoàn thành bài {i+1}")
            
            # Delay để tránh overload
            time.sleep(1)
        
    except Exception as e:
        print(f"  ❌ Lỗi xử lý feed: {e}")
    
    return articles

def collect_all_news():
    """Thu thập tin tức từ tất cả RSS feeds"""
    all_news = {}
    total_articles = 0
    
    print(f"\n🔄 Bắt đầu thu thập tin tức từ {len(RSS_FEEDS)} chủ đề...")
    
    for topic, feed_urls in RSS_FEEDS.items():
        print(f"\n📚 CHUYÊN MỤC: {topic}")
        print("=" * 40)
        
        all_news[topic] = []
        
        for feed_url in feed_urls:
            articles = process_rss_feed(feed_url, topic, max_articles=3)
            all_news[topic].extend(articles)
            total_articles += len(articles)
            
            # Nghỉ giữa các feed
            time.sleep(2)
        
        print(f"  📊 Tổng {topic}: {len(all_news[topic])} bài")
    
    print(f"\n📈 TỔNG KẾT: {total_articles} bài viết từ {len(RSS_FEEDS)} chuyên mục")
    return all_news

def generate_email_content(news_data):
    """Tạo nội dung email"""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%H:%M:%S")
    
    total_count = sum(len(articles) for articles in news_data.values())
    
    # Subject
    subject = f"[BẢN TIN] PCCC·LNG·MRT — {date_str} ({total_count} tin)"
    
    # Body header
    body = f"""📰 BẢN TIN TỰ ĐỘNG HÀNG NGÀY
📅 Ngày: {date_str}
⏰ Tạo lúc: {time_str}
📊 Tổng số: {total_count} tin tức
{'='*60}

"""
    
    # Content cho từng chuyên mục
    for topic, articles in news_data.items():
        if not articles:
            continue
            
        body += f"\n🏷️  {topic} ({len(articles)} tin)\n"
        body += "─" * 50 + "\n\n"
        
        for i, article in enumerate(articles, 1):
            body += f"{i}. {article['title']}\n"
            
            if article['link']:
                body += f"🔗 {article['link']}\n"
            
            if article['published']:
                body += f"📅 {article['published']}\n"
            
            body += f"📝 Tóm tắt: {article['summary']}\n"
            body += f"📏 Độ dài: {article['content_length']} ký tự\n"
            body += "\n" + "·" * 40 + "\n\n"
    
    # Footer
    body += f"""
{'='*60}
🤖 Hệ thống Daily Digest tự động
🔄 Lần chạy tiếp theo: Ngày mai 08:00
⚙️ Phiên bản: 2.0 (No newspaper3k)
"""
    
    return subject, body

def send_daily_email(news_data):
    """Gửi email báo cáo hàng ngày"""
    
    # Kiểm tra cấu hình SMTP
    smtp_config = {
        'host': os.getenv("SMTP_HOST", "smtp.gmail.com"),
        'port': int(os.getenv("SMTP_PORT", "587")),
        'user': os.getenv("SMTP_USER"),
        'pass': os.getenv("SMTP_PASS"),
        'to': os.getenv("EMAIL_TO")
    }
    
    missing_config = [k for k, v in smtp_config.items() if k != 'host' and k != 'port' and not v]
    if missing_config:
        print(f"❌ Thiếu cấu hình email: {missing_config}")
        return False
    
    try:
        # Tạo nội dung email
        subject, body = generate_email_content(news_data)
        
        # Tạo message
        msg = MIMEMultipart()
        msg['From'] = smtp_config['user']
        msg['To'] = smtp_config['to']
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Gửi email
        print("📧 Đang kết nối SMTP server...")
        with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
            server.starttls()
            server.login(smtp_config['user'], smtp_config['pass'])
            server.send_message(msg)
        
        print("✅ Email đã được gửi thành công!")
        print(f"📬 Gửi tới: {smtp_config['to']}")
        print(f"📋 Tiêu đề: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("❌ Lỗi xác thực SMTP - kiểm tra username/password")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ Lỗi SMTP: {e}")
        return False
    except Exception as e:
        print(f"❌ Lỗi gửi email: {e}")
        return False

def main():
    """Hàm chính của chương trình"""
    print("🚀 DAILY NEWS DIGEST SYSTEM v2.0")
    print(f"⏰ Khởi động: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔧 Không sử dụng newspaper3k")
    print("="*60)
    
    try:
        # Bước 1: Thu thập tin tức
        print("\n📡 BƯỚC 1: THU THẬP TIN TỨC")
        news_data = collect_all_news()
        
        # Bước 2: Kiểm tra kết quả
        total_news = sum(len(articles) for articles in news_data.values())
        
        if total_news == 0:
            print("\n⚠️ CẢNH BÁO: Không thu thập được tin tức nào!")
            print("Có thể nguyên nhân:")
            print("- RSS feeds không khả dụng")
            print("- Kết nối mạng kém")  
            print("- Website chặn requests")
            print("- Lỗi API DeepSeek")
            return False
        
        print(f"\n✅ Thu thập thành công {total_news} tin tức!")
        
        # Bước 3: Gửi email
        print("\n📧 BƯỚC 2: GỬI EMAIL")
        success = send_daily_email(news_data)
        
        if success:
            print("\n🎉 HOÀN THÀNH THÀNH CÔNG!")
            print(f"📊 Đã xử lý: {total_news} tin tức")
            print(f"⏰ Thời gian thực hiện: {datetime.now()}")
            return True
        else:
            print("\n💥 THẤT BẠI KHI GỬI EMAIL!")
            return False
            
    except KeyboardInterrupt:
        print("\n⏹️ Chương trình bị dừng bởi người dùng")
        return False
    except Exception as e:
        print(f"\n💥 LỖI NGHIÊM TRỌNG: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
