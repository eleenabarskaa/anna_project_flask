"""Сбор статей-кандидатов по категории триггера.

Порт `trigger_scraper.py` из Streamlit-версии — логика сохранена один в один:
RSS-лента сайта, при её отсутствии ссылки с главной, фильтр по ключевым словам
в заголовке, затем загрузка текста статьи и отсечение по дате публикации.

Публичная точка входа:
    scan_category(category_key, months=3, progress_callback=None) -> list[dict]

Возвращается СЫРОЕ содержимое статей, без классификации: разбор в структуру
таблицы triggers делает LLM-нода в n8n.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.scraping.sources import get_scope, normalize_key

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WealthTriggerResearchBot/1.0; "
        "+contact: replace-with-your-email@example.com)"
    )
}

REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT = 15

KEYWORD_SETS = {
    "M&A / Liquidity event": [
        "acquisisce", "acquisizione", "cessione", "cede", "vende", "vendita",
        "quota di maggioranza", "quota di minoranza", "quota", "m&a",
        "fusione", "opa", "stake", "controllo", "holding",
    ],
    "IPO / Listing": [
        "ipo", "quotazione", "quota in borsa", "debutto", "euronext growth",
        "borsa italiana", "collocamento", "aumento di capitale",
    ],
    "PE Exit": [
        "exit", "private equity", "fondo", "cede", "vende", "quota di maggioranza",
        "reinveste", "minoranza", "acquisisce il controllo",
    ],
    "Succession / Leadership transition": [
        "passaggio generazionale", "successione", "nuovo ceo", "nuovo presidente",
        "cambio al vertice", "guida operativa", "nomina",
    ],
    "Real Estate": [
        "immobile", "palazzo", "villa", "acquisisce", "vende", "portafoglio immobiliare",
        "resort", "hotel", "trophy asset",
    ],
    "Family Office": [
        "family office", "holding di famiglia", "patrimonio familiare",
        "passaggio generazionale", "single family office",
    ],
}
GENERIC_KEYWORDS = ["acquisisce", "cede", "vende", "quota", "family office", "holding"]

FEED_PATHS = ["/feed/", "/feed", "/rss", "/rss.xml", "/feed/rss/"]

# Дополняйте по мере изучения вёрстки конкретных сайтов.
# Пусто — используется общий фолбэк по тегам <p>.
SITE_SELECTORS: dict[str, dict[str, str]] = {
    # "bebeez.it": {"body": "div.entry-content"},
}


@dataclass
class Article:
    url: str
    domain: str
    title: str = ""
    published: str = ""
    text: str = ""


class ScanCancelled(RuntimeError):
    """Пользователь остановил сканирование."""


def _noop() -> bool:
    return False


def _polite_get(url: str, session: requests.Session):
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.RequestException:
        return None
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)


def _try_feed(domain: str, session: requests.Session):
    entries = []
    for path in FEED_PATHS:
        resp = _polite_get(f"https://{domain}{path}", session)
        if resp is None:
            continue
        content_type = resp.headers.get("Content-Type", "")
        head = resp.text[:200]
        if "xml" not in content_type and "<rss" not in head and "<feed" not in head:
            continue
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item") or soup.find_all("entry")
        for item in items:
            link_tag = item.find("link")
            link = link_tag.text.strip() if link_tag and link_tag.text else (
                link_tag.get("href") if link_tag else None
            )
            title = item.find("title")
            pub = item.find("pubDate") or item.find("published") or item.find("updated")
            if link:
                entries.append({
                    "url": link,
                    "title": title.text.strip() if title else "",
                    "published": pub.text.strip() if pub else "",
                })
        if entries:
            break
    return entries


def _fallback_homepage_links(domain: str, session: requests.Session):
    resp = _polite_get(f"https://{domain}/", session)
    if resp is None:
        return []
    soup = BeautifulSoup(resp.content, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(f"https://{domain}/", a["href"])
        if urlparse(href).netloc.lower().lstrip("www.") != domain.lstrip("www."):
            continue
        text = a.get_text(strip=True)
        if len(text) < 15:
            continue
        links.append({"url": href, "title": text, "published": ""})
    seen, unique = set(), []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)
    return unique[:60]


def _looks_relevant(title: str, category: str) -> bool:
    keywords = KEYWORD_SETS.get(category, GENERIC_KEYWORDS)
    lowered = title.lower()
    return any(kw in lowered for kw in keywords)


def _parse_date_safe(raw: str):
    if not raw:
        return None
    try:
        dt = dateparser.parse(raw, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OverflowError, TypeError):
        return None


def _extract_article_text(url: str, session: requests.Session, domain: str):
    resp = _polite_get(url, session)
    if resp is None:
        return None
    soup = BeautifulSoup(resp.content, "lxml")

    body_sel = SITE_SELECTORS.get(domain, {}).get("body")
    if body_sel:
        node = soup.select_one(body_sel)
        text = node.get_text(" ", strip=True) if node else ""
    else:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    published = ""
    for meta_name in ["article:published_time", "og:published_time", "date", "pubdate"]:
        tag = soup.find("meta", attrs={"property": meta_name}) or soup.find(
            "meta", attrs={"name": meta_name}
        )
        if tag and tag.get("content"):
            published = tag["content"]
            break

    return Article(url=url, domain=domain, title=title, published=published, text=text[:6000])


def scan_category(
    category_key: str,
    months: int = 3,
    progress_callback=None,
    should_stop=None,
) -> list[dict]:
    """Собрать статьи-кандидаты по одной категории.

    progress_callback: функция(str) — короткие статусные строки для UI.
    should_stop: функция() -> bool; если вернёт True, сканирование прерывается
        (кнопка Stop на странице).
    """
    should_stop = should_stop or _noop

    def report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    def check_stop() -> None:
        if should_stop():
            raise ScanCancelled("Сканирование остановлено")

    category_key = normalize_key(category_key)
    domains, known_urls_list = get_scope(category_key)
    known_urls = set(known_urls_list)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)

    if not domains:
        report(f"Для категории «{category_key}» не настроено ни одного источника.")
        return []

    session = requests.Session()
    candidates: list[dict] = []

    for index, domain in enumerate(domains, start=1):
        check_stop()
        report(f"Scanning {domain} ... ({index}/{len(domains)})")
        entries = _try_feed(domain, session)
        if not entries:
            entries = _fallback_homepage_links(domain, session)

        for entry in entries:
            if entry["url"] in known_urls:
                continue
            if not _looks_relevant(entry.get("title", ""), category_key):
                continue
            candidates.append({"domain": domain, **entry})

    report(f"{len(candidates)} keyword-relevant candidates found, fetching article text ...")

    articles: list[Article] = []
    for candidate in candidates:
        check_stop()
        article = _extract_article_text(candidate["url"], session, candidate["domain"])
        if article is None or len(article.text) < 200:
            continue
        published_at = _parse_date_safe(article.published or candidate.get("published", ""))
        if published_at and published_at < cutoff:
            continue
        articles.append(article)

    report(f"{len(articles)} articles kept after filtering.")

    return [
        {
            "category": category_key,
            "url": a.url,
            "domain": a.domain,
            "title": a.title,
            "published_meta": a.published,
            "text": a.text,
        }
        for a in articles
    ]
