import feedparser, os, smtplib, re, trafilatura
from google import genai
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from time import mktime

FEEDS = {
    "IDRW": "https://idrw.org/feed/",
    "Diplomat": "https://thediplomat.com/feed/",
    "ORF": "https://www.orfonline.org/rss.xml",
    "Livefist": "https://www.livefistdefence.com/feed/"
}

IST_OFFSET = timedelta(hours=5, minutes=30)

# ---------- Date helpers ----------

def get_target_date_ist():
    """Return yesterday's date in IST, e.g. if today is the 16th, this
    returns the 15th."""
    now_ist = datetime.now(timezone.utc) + IST_OFFSET
    return (now_ist - timedelta(days=1)).date()

def entry_date_ist(entry):
    parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    if not parsed:
        return None
    published_utc = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    return (published_utc + IST_OFFSET).date()

# ---------- Text helpers ----------

def clean_html(raw):
    text = re.sub(r'<[^>]+>', ' ', raw or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def fetch_full_text(url):
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
            return text.strip()[:2000]
    except Exception:
        pass
    return None

# ---------- SSB relevance scoring ----------

TIER1_DEFENCE = [
    "rafale", "tejas mk2", "tejas mk-2", "amca", "tedbf", "lca tejas", "su-30 upgrade", "mrfa",
    "s-400", "s400", "akash missile", "brahmos", "agni-", "agni v", "agni prime", "pralay", "pinaka",
    "ins vikrant", "ins vishal", "ins arighat", "ins aridhaman", "project 75", "project-75i", "scorpene",
    "arihant", "zorawar tank", "atags", "k9 vajra", "chief of defence staff", "theatre command",
    "theaterisation", "theatrisation", "agniveer", "agnipath scheme", "atmanirbhar bharat",
    "make in india defence", "positive indigenisation", "defence corridor", "no first use",
    "nuclear doctrine", "cold start doctrine", "mission shakti", "anti-satellite", "a-sat",
    "loitering munition", "marcos commando", "para sf", "garud commando",
    "lac", "loc", "galwan", "tawang", "doklam", "depsang", "demchok", "siachen",
    "surgical strike", "infiltration", "ceasefire violation"
]

TIER1_GEO = [
    "quad summit", "aukus", "indo-pacific strategy", "indian ocean region", " ior ",
    "china pakistan", "string of pearls", "cpec", "gwadar port", "hambantota",
    "maldives india", "bangladesh india", "nepal india", "sri lanka crisis"
]

TIER2_DEFENCE = [
    "exercise malabar", "yudh abhyas", "varuna exercise", "garuda exercise", "shakti exercise",
    "dustlik", "mitra shakti", "vayu shakti", "tarkash", "joint military exercise", "tri-service",
    "drdo", "isro military", "spy satellite", "cartosat", "hypersonic missile", "combat drone",
    "uav strike", "predator drone", "heron drone", "ghatak drone", "swarm drone",
    "hal ", "bel ", "ordnance factory", "defence production", "arms export india",
    "defence budget", "special forces", "amphibious assault", "andaman nicobar command"
]

TIER2_GEO = [
    "taiwan strait", "south china sea", "arunachal pradesh china", "brics expansion",
    "india us defence", "india russia defence", "india france defence", "india israel defence",
    "chabahar port", "asean india", "unsc permanent seat", "nsg membership",
    "military coup myanmar", "taliban afghanistan", "afghanistan india"
]

TIER3 = [
    "nato", "russia ukraine war", "israel hamas", "houthi red sea", "piracy arabian sea",
    "un peacekeeping", "g20 security", "shangri-la dialogue", "raisina dialogue",
    "defence expo", "aero india", "one belt one road", "belt and road initiative",
    "malacca strait", "diego garcia", "sco summit", "shanghai cooperation organisation",
    "wagner group", "north korea missile", "iran nuclear", "israel iran tension",
    "suez canal", "strait of hormuz", "opec", "brics currency", "de-dollarization",
    "g7 summit", "un security council reform", "cyber warfare", "ai in warfare",
    "space warfare", "arms control treaty", "nuclear non-proliferation"
]

NEGATIVE = [
    "election", "bjp vs", "congress vs", "rahul gandhi", "modi rally", "bollywood", "cricket", "ipl",
    "trump speech domestic", "biden domestic", "us election internal", "stock market", "sensex",
    "entertainment", "football", "celebrity", "gossip", "big boss", "assembly election",
    "byelection", "reality show", "award show", "box office"
]

def ssb_score(title, desc=""):
    text = (title + " " + desc).lower()
    score = 0
    for word in TIER1_DEFENCE + TIER1_GEO:
        if word in text:
            score += 15
    for word in TIER2_DEFENCE + TIER2_GEO:
        if word in text:
            score += 10
    for word in TIER3:
        if word in text:
            score += 5
    for word in NEGATIVE:
        if word in text:
            score -= 20

    if "india" in text and any(x in text for x in ["china", "pakistan"]):
        score += 10
    if any(x in text for x in ["indian army", "indian navy", "indian air force"]):
        score += 8
    if any(x in text for x in ["commissioned", "inducted", "deal signed"]):
        score += 7

    return score

# ---------- News fetching ----------

def get_news_articles():
    """Returns a list of dicts: {source, title, link, content}"""
    target_date = get_target_date_ist()
    articles = []
    for name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            same_day_entries = [e for e in feed.entries if entry_date_ist(e) == target_date]
            for e in same_day_entries:
                title = e.get('title', '')
                link = e.get('link', '')

                if 'content' in e and e.content:
                    body = clean_html(e.content[0].value)
                else:
                    body = None

                if not body or len(body) < 200:
                    fetched = fetch_full_text(link)
                    if fetched:
                        body = fetched

                if not body:
                    raw_desc = e.get('summary', '') or e.get('description', '')
                    body = clean_html(raw_desc)

                articles.append({"source": name, "title": title, "link": link, "content": body})
        except Exception:
            pass
    return articles

def build_news_text(articles, max_articles=15):
    """Score, sort, and keep only the most SSB-relevant articles."""
    for a in articles:
        a['score'] = ssb_score(a['title'], a['content'])

    articles.sort(key=lambda a: a['score'], reverse=True)

    relevant = [a for a in articles if a['score'] > 0][:max_articles]
    if not relevant:
        relevant = articles[:max_articles]

    data = ""
    for a in relevant:
        data += f"Source: {a['source']}\nTitle: {a['title']}\nLink: {a['link']}\nContent: {a['content']}\n\n"
    return data

# ---------- Summarize + email ----------

def summarize(news, for_date):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = f"""You are helping an Indian SSB (Services Selection Board) candidate prepare a
morning current-affairs brief covering news from {for_date.strftime('%d %B %Y')}.

The articles below have already been pre-filtered for SSB relevance (defence acquisitions,
LAC/LoC, military exercises, DRDO/ISRO tech, and geopolitics directly affecting India).

For each article, write:
1. What happened - 1-2 sentences based on the actual Content, not just the Title.
2. SSB Angle - one line on why this could come up in Lecturette/GD/Interview
   (e.g. relevance to two-front war doctrine, Atmanirbharta, IOR dominance, grey-zone warfare).
3. The link in parentheses.

Format each item like:
1. INS Aridhaman commissioned into service
   -> What: India's third nuclear-powered ballistic missile submarine (SSBN) joined the fleet.
   -> SSB Angle: Strengthens India's nuclear triad and second-strike capability against China.
   -> (link)

Organize into two sections:
**INDIAN DEFENCE**
**GLOBAL GEOPOLITICS**

If there isn't enough material for 5 items in a section, include only the genuine ones -
do not pad with repeated or unrelated items.

At the end, add "What to watch today" - 2 lines on upcoming events worth tracking.

Articles:
{news}"""
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )
    return response.text

def send_email(body, for_date):
    html = f"<pre style='font-family: Arial; white-space: pre-wrap;'>{body}</pre>"
    msg = MIMEText(html, 'html')
    msg['Subject'] = f"SSB Defence Brief - {for_date.strftime('%d %b %Y')}"
    msg['From'] = os.getenv("EMAIL")
    msg['To'] = os.getenv("EMAIL")

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(os.getenv("EMAIL"), os.getenv("APP_PASS"))
        s.send_message(msg)

if __name__ == "__main__":
    target_date = get_target_date_ist()
    articles = get_news_articles()
    news_text = build_news_text(articles)
    brief = summarize(news_text, target_date)
    send_email(brief, target_date)
