import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

JUNK_PREFIXES = (
    "noreply@", "no-reply@", "info@", "support@", "help@",
    "admin@", "webmaster@", "sales@", "contact@", "hello@",
    "team@", "office@", "mail@", "enquiries@", "billing@",
)

# Domains to skip when discovering company sites from search results
_SKIP_DOMAINS = frozenset({
    "google.com", "linkedin.com", "facebook.com", "twitter.com",
    "youtube.com", "wikipedia.org", "crunchbase.com", "github.com",
    "instagram.com", "reddit.com", "yelp.com", "bbb.org",
    "glassdoor.com", "indeed.com", "x.com",
})

# Common contact-related paths to scrape on a company website
_CONTACT_PATHS = (
    "/", "/contact", "/contact-us", "/about", "/about-us",
    "/team", "/our-team", "/people", "/leadership", "/staff",
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _is_skip_domain(domain):
    """Check if a domain or any of its parent domains is in the skip set."""
    parts = domain.lower().split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in _SKIP_DOMAINS:
            return True
    return False

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def find_leads(criteria, hunter_api_key, google_search_api_key=None,
               google_search_cx=None, hunter_limit=10,
               google_search_limit=5, max_leads=10,
               scraping_timeout=10, scraping_max_pages=5):
    """Discover leads based on search criteria.

    Uses three paths depending on available information:
      A) Specific domains → Hunter.io domain search on each
      B) Company names → guess domain → Hunter.io; fallback to Google CSE
      C) General description → Google CSE to find domains → Hunter.io

    When API keys are missing, free alternatives are used:
      - DuckDuckGo replaces Google CSE for domain discovery
      - Website scraping replaces Hunter.io for email extraction

    Args:
        criteria: dict with roles, companies, company_type, industry, domains, location
        hunter_api_key: Hunter.io API key (optional — scraping used as fallback)
        google_search_api_key: Google Custom Search API key (optional)
        google_search_cx: Google Custom Search Engine ID (optional)
        hunter_limit: max results per Hunter.io query
        google_search_limit: max results per Google CSE query
        max_leads: overall cap on returned leads
        scraping_timeout: timeout in seconds for each HTTP request during scraping
        scraping_max_pages: max pages to scrape per domain

    Returns:
        list of dicts: [{name, email, company, role}, ...]
    """
    leads = []
    target_roles = [r.lower() for r in criteria.get("roles", [])]
    domains = criteria.get("domains", [])
    companies = criteria.get("companies", [])
    has_google = bool(google_search_api_key and google_search_cx)
    has_hunter = bool(hunter_api_key and not hunter_api_key.startswith("YOUR_"))

    if domains:
        # Path A: specific domains provided
        print(f"  Searching {len(domains)} domain(s)...")
        for domain in domains:
            results = []
            if has_hunter:
                results = _hunter_domain_search(domain, hunter_api_key, hunter_limit)
            if not results:
                print(f"    Scraping {domain} for emails...")
                results = _scrape_website_emails(domain, scraping_timeout, scraping_max_pages)
            leads.extend(results)

    elif companies:
        # Path B: company names provided
        print(f"  Looking up {len(companies)} company domain(s)...")
        for company in companies:
            domain = _guess_domain(company)
            results = []

            # Try Hunter.io on guessed domain first
            if has_hunter:
                results = _hunter_domain_search(domain, hunter_api_key, hunter_limit)

            if results:
                leads.extend(results)
                continue

            # Find the real domain via Google CSE or DuckDuckGo
            real_domain = None
            if has_google:
                print(f"    No results for {domain}, trying Google search...")
                real_domain = _google_find_domain(company, google_search_api_key,
                                                  google_search_cx)
            if not real_domain:
                print(f"    Trying DuckDuckGo search for {company}...")
                real_domain = _duckduckgo_find_domain(company)

            if real_domain and real_domain != domain:
                if has_hunter:
                    results = _hunter_domain_search(real_domain, hunter_api_key, hunter_limit)
                if not results:
                    print(f"    Scraping {real_domain} for emails...")
                    results = _scrape_website_emails(real_domain, scraping_timeout, scraping_max_pages)
                leads.extend(results)
            else:
                # Scrape the guessed domain as last resort
                print(f"    Scraping {domain} for emails...")
                results = _scrape_website_emails(domain, scraping_timeout, scraping_max_pages)
                leads.extend(results)

    else:
        # Path C: general description — discover companies
        query = _build_search_query(criteria)

        # Discover domains via Google CSE or DuckDuckGo
        discovered_domains = []
        if has_google:
            print(f"  Searching Google for: {query}")
            discovered_domains = _google_discover_domains(
                query, google_search_api_key, google_search_cx, google_search_limit
            )
        if not discovered_domains:
            print(f"  Searching DuckDuckGo for: {query}")
            discovered_domains = _duckduckgo_discover_domains(query, google_search_limit)

        if discovered_domains:
            print(f"  Found {len(discovered_domains)} domain(s), searching for emails...")
            for domain in discovered_domains:
                results = []
                if has_hunter:
                    results = _hunter_domain_search(domain, hunter_api_key, hunter_limit)
                if not results:
                    print(f"    Scraping {domain} for emails...")
                    results = _scrape_website_emails(domain, scraping_timeout, scraping_max_pages)
                leads.extend(results)

        # Fallback: scrape emails from search snippets
        if not leads:
            print("  No results from domain scraping. Trying email scraping from search snippets...")
            if has_google:
                leads.extend(_google_scrape_emails(
                    query, google_search_api_key, google_search_cx, google_search_limit
                ))
            if not leads:
                leads.extend(_duckduckgo_scrape_emails(query, google_search_limit))

        if not leads and not discovered_domains:
            print("  No domains or companies found. Try a more specific prompt.")
            return []

    # Filter by target roles
    if target_roles:
        leads = _filter_by_roles(leads, target_roles)

    # Remove junk emails
    leads = [l for l in leads if not l["email"].lower().startswith(JUNK_PREFIXES)]

    # Deduplicate by email
    seen = set()
    unique = []
    for lead in leads:
        if lead["email"].lower() not in seen:
            seen.add(lead["email"].lower())
            unique.append(lead)
    leads = unique

    # Cap at max_leads
    return leads[:max_leads]


# ---------------------------------------------------------------------------
# DuckDuckGo-based functions (free, no API key required)
# ---------------------------------------------------------------------------

def _duckduckgo_find_domain(company_name):
    """Use DuckDuckGo to find a company's real domain."""
    query = f"{company_name} official website"
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=3)
    except Exception as e:
        print(f"    DuckDuckGo error: {e}")
        return None

    for result in results:
        link = result.get("href", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            domain = match.group(1).lower()
            if not _is_skip_domain(domain):
                return domain
    return None


def _duckduckgo_discover_domains(query, max_results=5):
    """Search DuckDuckGo and extract unique domains from results."""
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max(max_results * 2, 10))
    except Exception as e:
        print(f"    DuckDuckGo error: {e}")
        return []

    domains = []
    seen = set()
    for result in results:
        link = result.get("href", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            domain = match.group(1).lower()
            if domain not in seen and domain not in _SKIP_DOMAINS:
                seen.add(domain)
                domains.append(domain)
    return domains[:max_results]


def _duckduckgo_scrape_emails(query, max_results=5):
    """Fallback: search DuckDuckGo and extract emails from snippets."""
    search_query = f"{query} email contact"
    try:
        ddgs = DDGS()
        results = ddgs.text(search_query, max_results=max(max_results * 2, 10))
    except Exception as e:
        print(f"    DuckDuckGo error: {e}")
        return []

    leads = []
    for result in results:
        text = (result.get("body", "") + " " + result.get("title", "")
                + " " + result.get("href", ""))
        emails = _EMAIL_RE.findall(text)
        domain = ""
        link = result.get("href", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            domain = match.group(1)
        for email in emails:
            leads.append({
                "name": "",
                "email": email,
                "company": domain.split(".")[0].title() if domain else "",
                "role": "",
            })
    return leads


# ---------------------------------------------------------------------------
# Website scraping (free, replaces Hunter.io when key is absent)
# ---------------------------------------------------------------------------

def _scrape_website_emails(domain, timeout=10, max_pages=5):
    """Crawl common pages on a domain and extract emails with context.

    Visits homepage + contact/about/team pages, extracts email addresses
    via regex, and attempts to infer name/role from surrounding HTML.

    Returns list of dicts: [{name, email, company, role}, ...]
    """
    base_url = f"https://{domain}"
    company_name = domain.split(".")[0].title()
    urls_to_try = [urljoin(base_url, path) for path in _CONTACT_PATHS]
    urls_to_try = urls_to_try[:max_pages]

    found_emails = {}  # email -> {name, role}
    session = requests.Session()
    session.headers.update({"User-Agent": _BROWSER_UA})

    for url in urls_to_try:
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue

        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style to avoid false matches
        for tag in soup(["script", "style"]):
            tag.decompose()

        page_text = soup.get_text(separator=" ")
        emails_in_page = _EMAIL_RE.findall(page_text)

        # Also check mailto: links
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if _EMAIL_RE.match(email):
                    emails_in_page.append(email)

        for email in emails_in_page:
            email_lower = email.lower()
            if email_lower in found_emails:
                continue

            name, role = _extract_context(soup, email)
            found_emails[email_lower] = {
                "name": name,
                "email": email,
                "company": company_name,
                "role": role,
            }

    return list(found_emails.values())


def _extract_context(soup, email):
    """Try to extract a name and role from HTML near an email address."""
    name = ""
    role = ""

    # Find elements containing the email
    elements = soup.find_all(string=re.compile(re.escape(email)))
    for el in elements:
        parent = el.parent
        if not parent:
            continue

        # Walk up to find a container (div, li, td, article, section)
        container = parent
        for _ in range(5):
            if container.name in ("div", "li", "td", "article", "section", "tr"):
                break
            if container.parent:
                container = container.parent
            else:
                break

        # Look for name in heading or strong tags within the container
        for tag in container.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
            text = tag.get_text(strip=True)
            # Simple heuristic: 2-4 words, no @ sign, not too long
            if text and 1 < len(text.split()) <= 5 and "@" not in text and len(text) < 60:
                if not name:
                    name = text
                    break

        # Look for role-like text (smaller headings, spans, p tags)
        role_keywords = ("ceo", "cto", "cfo", "vp", "director", "manager",
                         "head of", "lead", "chief", "founder", "president",
                         "engineer", "developer", "designer", "marketing",
                         "coordinator", "analyst", "specialist", "officer",
                         "partner", "associate", "consultant")
        for tag in container.find_all(["p", "span", "div", "h4", "h5", "em", "small"]):
            text = tag.get_text(strip=True).lower()
            if any(kw in text for kw in role_keywords) and "@" not in text and len(text) < 80:
                if not role:
                    role = tag.get_text(strip=True)
                    break

    return name, role


# ---------------------------------------------------------------------------
# Hunter.io functions (used when API key is available)
# ---------------------------------------------------------------------------

def _hunter_domain_search(domain, api_key, limit):
    """Search Hunter.io for emails at a domain."""
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": limit,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    Hunter.io error for {domain}: {e}")
        return []

    results = []
    emails_data = data.get("data", {}).get("emails", [])
    company_name = data.get("data", {}).get("organization", domain.split(".")[0].title())

    for entry in emails_data:
        email = entry.get("value", "")
        if not email:
            continue
        first = entry.get("first_name", "")
        last = entry.get("last_name", "")
        name = f"{first} {last}".strip() if first or last else ""
        role = entry.get("position", "") or ""
        results.append({
            "name": name,
            "email": email,
            "company": company_name,
            "role": role,
        })
    return results


# ---------------------------------------------------------------------------
# Google CSE functions (used when API keys are available)
# ---------------------------------------------------------------------------

def _google_find_domain(company_name, api_key, cx):
    """Use Google Custom Search to find a company's real domain."""
    query = f"{company_name} official website"
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": 1}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    Google Search error: {e}")
        return None

    items = data.get("items", [])
    if items:
        link = items[0].get("link", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            return match.group(1)
    return None


def _google_discover_domains(query, api_key, cx, limit):
    """Search Google CSE and extract unique domains from results."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": min(limit, 10)}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    Google Search error: {e}")
        return []

    domains = []
    seen = set()
    for item in data.get("items", []):
        link = item.get("link", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            domain = match.group(1).lower()
            if domain not in seen and domain not in _SKIP_DOMAINS:
                seen.add(domain)
                domains.append(domain)
    return domains


def _google_scrape_emails(query, api_key, cx, limit):
    """Fallback: search Google and extract emails from snippets."""
    url = "https://www.googleapis.com/customsearch/v1"
    search_query = f"{query} email contact"
    params = {"key": api_key, "cx": cx, "q": search_query, "num": min(limit, 10)}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    Google Search error: {e}")
        return []

    leads = []
    for item in data.get("items", []):
        snippet = item.get("snippet", "") + " " + item.get("title", "")
        emails = _EMAIL_RE.findall(snippet)
        domain = ""
        link = item.get("link", "")
        match = re.search(r"https?://(?:www\.)?([^/]+)", link)
        if match:
            domain = match.group(1)
        for email in emails:
            leads.append({
                "name": "",
                "email": email,
                "company": domain.split(".")[0].title() if domain else "",
                "role": "",
            })
    return leads


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _guess_domain(company_name):
    """Guess a company's domain from its name (e.g. 'Acme Corp' → 'acmecorp.com')."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", company_name).lower()
    return f"{cleaned}.com"


def _build_search_query(criteria):
    """Build a search query from criteria."""
    parts = []
    if criteria.get("industry"):
        parts.append(criteria["industry"])
    if criteria.get("company_type"):
        parts.append(criteria["company_type"])
    if criteria.get("roles"):
        parts.append(" ".join(criteria["roles"][:2]))
    if criteria.get("location"):
        parts.append(criteria["location"])
    if not parts:
        parts.append("companies")
    return " ".join(parts)


def _filter_by_roles(leads, target_roles):
    """Filter leads to those whose role matches any target role (fuzzy)."""
    filtered = []
    for lead in leads:
        role = lead.get("role", "").lower()
        if not role:
            # Keep leads with no role info — better than discarding
            filtered.append(lead)
            continue
        for target in target_roles:
            # Check if any word from the target role appears in the lead's role
            target_words = target.split()
            if any(word in role for word in target_words):
                filtered.append(lead)
                break
    return filtered
