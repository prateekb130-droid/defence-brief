import feedparser, os, smtplib, re, trafilatura
from google import genai
from email.mime.text import MIMEText
from datetime import datetime

FEEDS = {
    "IDRW": "https://idrw.org/feed/",
    "Diplomat": "https://thediplomat.com/feed/",
    "ORF": "https://www.orfonline.org/rss.xml",
    "Livefist": "https://www.livefistdefence.com/feed/"
}

def clean_html(raw):
    """Strip HTML tags and collapse whitespace from a feed description."""
    text = re.sub(r'<[^>]+>', ' ', raw or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def fetch_full_text(url):
    """Try to pull the actual article body from the page itself."""
    try:
        downloaded = trafilatura.fetch_url(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded)
        if text:
            return text.strip()[:2000]  # cap length so the prompt stays sane
    except Exception:
        pass
    return None

def get_news():
    data = ""
    for name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            data += f"\n--- {name} ---\n"
            for e in feed.entries[:6]:
                title = e.get('title', '')
                link = e.get('link', '')

                # 1. Prefer full content if the feed itself includes it
                if 'content' in e and e.content:
                    body = clean_html(e.content[0].value)
                else:
                    body = None

                # 2. Otherwise try fetching and extracting the article page
                if not body or len(body) < 200:
                    fetched = fetch_full_text(link)
                    if fetched:
                        body = fetched

                # 3. Last resort: whatever short snippet the feed gave us
                if not body:
                    raw_desc = e.get('summary', '') or e.get('description', '')
                    body = clean_html(raw_desc)

                data += f"Title: {title}\nLink: {link}\nContent: {body}\n\n"
        except Exception:
            pass
    return data

def summarize(news):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = f"""You are an Indian defence analyst. Create a morning brief for {datetime.now().date()}.

Each article below has a Title, Link, and Content (extracted from the actual article page).
Use the Content to understand what actually happened — do not just restate the Title.

From this raw news, give:
**INDIAN DEFENCE (Top 5 bullets)**
**GLOBAL GEOPOLITICS (Top 5 bullets)**

For each bullet, write 1-2 full sentences summarizing what happened and why it matters,
based on the Content, then add the link in parentheses at the end.
Example format: "India test-fired a new hypersonic missile from Odisha, its third
successful trial this year, signalling faster progress on strategic deterrence. (link)"

At the end add "What to watch today" (2 lines).
Keep it crisp, military-briefing style, but make sure each bullet is an actual summary,
not a repeated headline.

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
