import feedparser, os, smtplib
from google import genai
from email.mime.text import MIMEText
from datetime import datetime

FEEDS = {
    "IDRW": "https://idrw.org/feed/",
    "Diplomat": "https://thediplomat.com/feed/",
    "ORF": "https://www.orfonline.org/rss.xml",
    "Livefist": "https://www.livefistdefence.com/feed/"
}

def get_news():
    data = ""
    for name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            data += f"\n--- {name} ---\n"
            for e in feed.entries[:6]:
                data += f"Title: {e.title}\nLink: {e.link}\n"
        except Exception:
            pass
    return data

def summarize(news):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = f"""You are an Indian defence analyst. Create a morning brief for {datetime.now().date()}.

From this raw news, give:
**INDIAN DEFENCE (Top 5 bullets)**
**GLOBAL GEOPOLITICS (Top 5 bullets)**
Each bullet: 1 line news + link
At end: "What to watch today" (2 lines)
Keep it crisp, military briefing style.

Raw news:
{news}"""
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )
    return response.text

def send_email(body):
    html = f"<pre style='font-family: Arial; white-space: pre-wrap;'>{body}</pre>"
    msg = MIMEText(html, 'html')
    msg['Subject'] = f"Morning Defence Brief - {datetime.now().strftime('%d %b %Y')}"
    msg['From'] = os.getenv("EMAIL")
    msg['To'] = os.getenv("EMAIL")

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(os.getenv("EMAIL"), os.getenv("APP_PASS"))
        s.send_message(msg)

if __name__ == "__main__":
    news = get_news()
    brief = summarize(news)
    send_email(brief)
