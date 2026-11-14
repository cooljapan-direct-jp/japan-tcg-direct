"""
weekly_update.py  -  JapanMania 週次レポートの自動更新

サイトのルートフォルダ(index.html がある場所)で実行する。
やること:
  1. weekly/ の YYYY-MM-DD-*.html を集める
  2. KEEP_DAYS より古い週を削除し、vercel.json にリダイレクト(301 → /weekly/)を追加
  3. weekly/index.html(一覧ページ)をサイトと同じデザインで作り直す
  4. sitemap.xml をサイト内の全HTMLから丸ごと作り直す(無ければ新規作成)

既定はドライラン(何も書き換えない)。--apply を付けると実際に書き換える。
  python weekly_update.py          → 確認だけ
  python weekly_update.py --apply  → 実行

各週のページには次の2つを必ず入れておく(一覧の見出しと要約に使う):
  <title>Weekly TCG Report from Japan (Nov 8, 2026)</title>
  <meta name="description" content="今週の結論を英語で2〜3文">
"""

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

SITE_URL = "https://japanmania.store"
KEEP_DAYS = 35          # これより古い週は削除(約1か月+余裕1週)
WEEKLY_DIR = Path("weekly")
SITEMAP = Path("sitemap.xml")
VERCEL_JSON = Path("vercel.json")
SKIP_NAMES = {"404.html"}
SKIP_DIRS = {".git", ".github", "node_modules"}

FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.html$")


# ---------- サイト共通の外枠(トップページと同じヘッダー・フッター・GA・Cookie同意) ----------

def page_head(title, desc, canonical, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(desc)}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(desc)}">
  <meta property="og:url" content="{canonical}">

  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('consent', 'default', {{
      ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
      analytics_storage: 'denied',
      region: ['AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU','IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES','SE','IS','LI','NO','GB','CH'],
      wait_for_update: 500
    }});
    gtag('consent', 'default', {{
      ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
      analytics_storage: 'granted'
    }});
    try {{
      var jmConsent = localStorage.getItem('jm_consent');
      if (jmConsent === 'granted' || jmConsent === 'denied') {{
        gtag('consent', 'update', {{ analytics_storage: jmConsent }});
      }}
    }} catch (e) {{}}
    gtag('js', new Date());
    gtag('config', 'G-K30E6LBQDN');
  </script>
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-K30E6LBQDN"></script>

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    .extra-small {{ font-size: 0.75rem; }}
    .max-width-800 {{ max-width: 800px; }}
    .sub-nav .nav-row {{ overflow-x: auto; white-space: nowrap; }}
    .sub-nav a {{ color: #212529; text-decoration: none; }}
    .sub-nav a.active {{ color: #dc3545; border-bottom: 2px solid #dc3545; }}
    .cookie-banner {{ position: fixed; left: 0; right: 0; bottom: 0; background: #212529; color: #fff; z-index: 1080; border-top: 3px solid #dc3545; }}
    .report h2 {{ font-size: 1.15rem; font-weight: 700; margin-top: 2rem; }}
    .report h3 {{ font-size: .95rem; font-weight: 700; margin-top: 1.25rem; }}
    .tag {{ display: inline-block; font-size: .7rem; font-weight: 700; padding: .1rem .5rem; border-radius: 4px; margin-right: .25rem; }}
    .tag-official {{ background: #d1e7dd; color: #0f5132; }}
    .tag-reported {{ background: #e2e3e5; color: #41464b; }}
    .tag-unclear {{ background: #fff3cd; color: #664d03; }}
    .bottom-line {{ background: #fff; border-left: 4px solid #dc3545; }}
    .week-card.latest {{ border-left: 4px solid #dc3545 !important; }}
  </style>
{extra_head}</head>
<body class="bg-light text-dark d-flex flex-column min-vh-100">

  <header class="bg-dark text-white py-2 px-3 d-flex justify-content-between align-items-center">
    <a href="/" class="fw-bold fs-6 text-white text-decoration-none">JapanMania</a>
    <div class="d-flex align-items-center gap-2">
      <a href="/buyee-flow" class="text-white text-decoration-none small fw-bold border border-secondary rounded px-2 py-1" data-i18n="f_guide">Buying Guide</a>
      <small class="text-secondary d-none d-md-inline" data-i18n="tagline">Weekly Report & Proxy Guide</small>
      <select id="langSelect" class="form-select form-select-sm w-auto bg-secondary text-white border-0" onchange="changeLanguage(this.value)" aria-label="Language">
        <option value="en">English</option>
        <option value="zh-TW">繁體中文</option>
        <option value="zh-CN">简体中文</option>
        <option value="es">Español</option>
        <option value="fr">Français</option>
        <option value="de">Deutsch</option>
        <option value="ko">한국어</option>
        <option value="th">ไทย</option>
      </select>
    </div>
  </header>
  <nav class="sub-nav bg-white border-bottom">
    <div class="container max-width-800 py-1 small fw-bold">
      <div class="nav-row d-flex gap-3 py-1">
        <a href="/" data-i18n="nav_home">Home</a>
        <a href="/weekly/" class="active" data-i18n="nav_wk">Weekly Report</a>
        <a href="/buyee-flow" data-i18n="f_guide">Buying Guide</a>
      </div>
      <div class="nav-row d-flex gap-3 py-1">
        <a href="/pokemon" data-i18n="nav_pk">Pokémon</a>
        <a href="/one-piece">ONE PIECE</a>
        <a href="/dragon-ball" data-i18n="nav_db">Dragon Ball</a>
      </div>
    </div>
  </nav>
"""


PAGE_FOOT = """
  <footer class="bg-dark text-secondary py-4 mt-auto extra-small">
    <div class="container text-center max-width-800">
      <div class="d-flex flex-wrap justify-content-center gap-3 mb-3">
        <a href="/buyee-flow" class="text-secondary text-decoration-none" data-i18n="f_guide">Buying Guide</a>
        <a href="/about" class="text-secondary text-decoration-none" data-i18n="f_about">About Us</a>
        <a href="/privacy" class="text-secondary text-decoration-none" data-i18n="f_privacy">Privacy Policy</a>
        <a href="/contact" class="text-secondary text-decoration-none" data-i18n="f_contact">Contact</a>
        <a href="#" id="cookieSettings" class="text-secondary text-decoration-none" data-i18n="f_cookie">Cookie Settings</a>
      </div>
      <p class="mb-2 text-white-50">© 2026 JapanMania. All rights reserved.</p>
      <p class="text-muted" style="font-size: 0.65rem; max-width: 600px; margin: 0 auto;">
        This site is an independent information guide. We are not affiliated with or endorsed by Buyee, card publishers or any marketplace. Weekly reports summarize publicly available information and may change after publication.
      </p>
    </div>
  </footer>

  <div id="cookieBanner" class="cookie-banner shadow-lg" role="dialog" aria-live="polite" hidden>
    <div class="container max-width-800 d-flex flex-column flex-sm-row align-items-sm-center gap-2 py-3">
      <div class="small flex-grow-1" data-i18n="cb_text">We use analytics cookies to understand how visitors use this site. You can accept or reject them.</div>
      <div class="d-flex gap-2 flex-shrink-0">
        <button type="button" id="cbReject" class="btn btn-outline-light btn-sm fw-bold px-3" data-i18n="cb_reject">Reject</button>
        <button type="button" id="cbAccept" class="btn btn-light btn-sm fw-bold px-3" data-i18n="cb_accept">Accept</button>
      </div>
    </div>
  </div>

  <script src="/site.js"></script>
</body>
</html>
"""


# ---------- 一覧ページ ----------

def read_meta(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    t = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    d = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text, re.S | re.I)
    title = html.unescape(t.group(1).strip()) if t else path.stem
    desc = html.unescape(d.group(1).strip()) if d else ""
    title = re.sub(r"\s*\|\s*JapanMania\s*$", "", title)
    return title, desc


def collect():
    weeks = []
    for p in WEEKLY_DIR.glob("*.html"):
        m = FILE_RE.match(p.name)
        if m:
            weeks.append((dt.date.fromisoformat(m.group(1)), p))
    weeks.sort(reverse=True)
    return weeks


def build_index(weeks):
    items = []
    for i, (d, p) in enumerate(weeks):
        title, desc = read_meta(p)
        cls = " latest" if i == 0 else ""
        label = '<span class="badge bg-danger me-2">Latest</span>' if i == 0 else ""
        items.append(
            f'      <article class="week-card{cls} bg-white border rounded p-3 mb-3">\n'
            f'        <div class="extra-small text-muted mb-1">{label}<time datetime="{d.isoformat()}">{d.strftime("%b %-d, %Y")}</time></div>\n'
            f'        <h2 class="fs-6 fw-bold mb-2"><a href="/weekly/{p.stem}" class="text-dark">{html.escape(title)}</a></h2>\n'
            f'        <p class="small text-muted mb-2">{html.escape(desc)}</p>\n'
            f'        <a href="/weekly/{p.stem}" class="extra-small fw-bold text-danger text-decoration-none">Read the full report →</a>\n'
            f'      </article>'
        )
    if not items:
        items.append('      <p class="small text-muted">The first report is coming soon.</p>')

    desc = ("A weekly roundup of Japanese trading card game news: ONE PIECE, Pokémon, Dragon Ball and more, "
            "sorted into what is official, what is reported and what is still unclear.")
    body = f"""
  <main class="container max-width-800 py-4">
    <h1 class="fw-bold fs-3 mb-2">Weekly TCG Report from Japan</h1>
    <p class="small text-muted mb-2">Information about Japanese card releases is scattered across official sites, shops and news outlets. Once a week, we pull it together into one page so you can see where things stand: what is official, what is only reported, and what is still unclear.</p>
    <p class="small mb-4"><a href="/buyee-flow" class="text-danger fw-bold text-decoration-none">First time buying from Japan? See how it works →</a></p>
{chr(10).join(items)}
    <p class="extra-small text-muted mt-4">Reports from the last few weeks are kept here. Older reports are retired as their information goes out of date.</p>
  </main>
"""
    return page_head("Weekly TCG Report from Japan | JapanMania", desc, f"{SITE_URL}/weekly/") + body + PAGE_FOOT


# ---------- sitemap.xml ----------

def page_url(p: Path) -> str:
    rel = p.as_posix()
    if rel == "index.html":
        return f"{SITE_URL}/"
    if rel.endswith("/index.html"):
        return f"{SITE_URL}/{rel[:-len('index.html')]}"
    return f"{SITE_URL}/{rel[:-5] if rel.endswith('.html') else rel}"


def build_sitemap(weeks):
    """サイト内の全HTMLから sitemap.xml を丸ごと作る(毎回作り直すので手で編集しない)"""
    def entry(loc, lastmod=None):
        lm = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        return f"  <url>\n    <loc>{loc}</loc>{lm}\n  </url>"

    entries = []
    for p in sorted(Path(".").rglob("*.html")):
        if set(p.parts) & SKIP_DIRS or p.name in SKIP_NAMES:
            continue
        if re.match(r"^google[0-9a-f]+\.html$", p.name):   # Search Console の確認用ファイル
            continue
        if p.parent == WEEKLY_DIR:                          # weekly は下でまとめて追加
            continue
        entries.append(entry(page_url(p)))

    latest = weeks[0][0].isoformat() if weeks else None
    entries.append(entry(f"{SITE_URL}/weekly/", latest))
    for d, p in weeks:
        entries.append(entry(f"{SITE_URL}/weekly/{p.stem}", d.isoformat()))

    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(entries) + "\n</urlset>\n")


# ---------- 古い週の転送 ----------

def add_redirects(names):
    data = json.loads(VERCEL_JSON.read_text(encoding="utf-8")) if VERCEL_JSON.exists() else {}
    redirects = data.setdefault("redirects", [])
    existing = {r.get("source") for r in redirects}
    for n in names:
        src = f"/weekly/{n}"
        if src not in existing:
            redirects.append({"source": src, "destination": "/weekly/", "permanent": True})
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    apply = "--apply" in sys.argv
    if not WEEKLY_DIR.is_dir():
        sys.exit("weekly フォルダが見つかりません。サイトのルートで実行してください。")

    today = dt.date.today()
    all_weeks = collect()
    old = [(d, p) for d, p in all_weeks if (today - d).days > KEEP_DAYS]
    keep = [(d, p) for d, p in all_weeks if (today - d).days <= KEEP_DAYS]

    print(f"残す週: {len(keep)}")
    for d, p in keep:
        print(f"  {p.name}")
    print(f"削除する週(→ /weekly/ へ転送): {len(old)}")
    for d, p in old:
        print(f"  {p.name}")

    if not apply:
        print("\nドライランです。書き換えるには --apply を付けて実行してください。")
        return

    for d, p in old:
        p.unlink()
    if old:
        VERCEL_JSON.write_text(add_redirects([p.name for _, p in old]), encoding="utf-8")
    (WEEKLY_DIR / "index.html").write_text(build_index(keep), encoding="utf-8")
    SITEMAP.write_text(build_sitemap(keep), encoding="utf-8")
    print("\n更新しました: weekly/index.html, sitemap.xml" + (", vercel.json" if old else ""))


if __name__ == "__main__":
    main()
