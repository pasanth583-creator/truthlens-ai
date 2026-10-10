"""services/url_extractor.py
Robust, secure article-fetching and content extraction service for TruthLens AI.

Features:
- Multi-layer SSRF defense: Pre-flight DNS resolution and IP verification blocking loopback, private RFC1918, link-local, and cloud metadata.
- Safe redirect following with recursive SSRF re-validation on every hop.
- Realistic modern browser headers and TLS session handling via requests (with urllib fallback) to prevent false bot rejections on public news articles.
- Multi-tier extraction: Trafilatura (primary) -> BeautifulSoup4 (secondary) -> SimpleHTMLArticleExtractor (fallback).
- Extraction of article title, body, author, publish date, publisher domain, canonical URL, and word count.
- Structured diagnostics and user-friendly error guidance (e.g. AUTH_REQUIRED for 401, FORBIDDEN_OR_PAYWALL for 403, RATE_LIMITED for 429, and HOMEPAGE_SECTION_DETECTED for directory indexes).
"""
import ipaddress
import socket
import urllib.parse
import urllib.request
import urllib.error
import re
import html
import logging
from typing import Dict, Any, Tuple, Optional, List
from html.parser import HTMLParser

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

logger = logging.getLogger("truthlens.url_extractor")

# Restricted hostnames and cloud metadata endpoints for SSRF defense
RESTRICTED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "127.0.0.1", "0.0.0.0",
    "::1", "[::1]", "metadata.google.internal", "instance-data",
    "169.254.169.254", "metadata.nic.in"
}

MAX_ARTICLE_RESPONSE_BYTES = 4 * 1024 * 1024  # 4 MB limit
REQUEST_TIMEOUT_SECONDS = 8
MAX_REDIRECTS = 4

# Modern browser User-Agent and headers
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_FETCH_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

# Patterns identifying homepage or section index URLs
HOMEPAGE_SECTION_PATTERNS = [
    r"^/?$",
    r"^/(world|politics|news|business|opinion|sports|tech|science|entertainment|health|us|uk|india|asia|europe|features|latest|trending)/?$",
    r"^/category/[^/]+/?$",
    r"^/section/[^/]+/?$"
]


class SimpleHTMLArticleExtractor(HTMLParser):
    """Clean, dependency-free HTML text and metadata extractor."""
    
    def __init__(self):
        super().__init__()
        self.title_tokens: List[str] = []
        self.in_title = False
        self.og_title: Optional[str] = None
        self.og_site_name: Optional[str] = None
        self.h1_tokens: List[str] = []
        self.in_h1 = False
        
        self.ignored_depth = 0
        self.ignored_tags = {
            "script", "style", "nav", "footer", "header", "aside",
            "noscript", "svg", "form", "iframe", "button", "select",
            "menu", "dialog"
        }
        
        self.paragraphs: List[str] = []
        self.current_block: List[str] = []
        self.in_block = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Metadata extraction
        if tag_lower == "meta":
            prop = attr_dict.get("property", "").lower()
            name = attr_dict.get("name", "").lower()
            content = attr_dict.get("content", "").strip()
            if (prop in ("og:title", "twitter:title") or name in ("title", "twitter:title")) and content:
                if not self.og_title:
                    self.og_title = content
            if prop == "og:site_name" and content and not self.og_site_name:
                self.og_site_name = content

        if tag_lower in self.ignored_tags:
            self.ignored_depth += 1
            return

        if self.ignored_depth > 0:
            return

        if tag_lower == "title":
            self.in_title = True
        elif tag_lower == "h1":
            self.in_h1 = True
        elif tag_lower in ("p", "article", "section", "blockquote", "h2", "h3", "li"):
            self.in_block = True
            self.current_block = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self.ignored_tags:
            if self.ignored_depth > 0:
                self.ignored_depth -= 1
            return

        if self.ignored_depth > 0:
            return

        if tag_lower == "title":
            self.in_title = False
        elif tag_lower == "h1":
            self.in_h1 = False
        elif tag_lower in ("p", "article", "section", "blockquote", "h2", "h3", "li"):
            if self.current_block:
                text = " ".join(self.current_block).strip()
                if len(text) > 20:
                    self.paragraphs.append(text)
                self.current_block = []
            self.in_block = False

    def handle_data(self, data: str):
        if self.ignored_depth > 0:
            return
            
        cleaned = data.strip()
        if not cleaned:
            return

        if self.in_title:
            self.title_tokens.append(cleaned)
        elif self.in_h1:
            self.h1_tokens.append(cleaned)
        elif self.in_block:
            self.current_block.append(cleaned)
        else:
            self.current_block.append(cleaned)


def is_safe_ip(ip_str: str) -> bool:
    """Validate that an IP is globally routable and not in private/reserved ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    if ip_str.startswith("169.254.") or ip_str.startswith("100.100.") or ip_str == "0.0.0.0":
        return False
    return True


def is_homepage_or_section(path: str) -> bool:
    """Detect if URL path corresponds to a homepage or broad category landing page."""
    clean_path = path.strip().lower()
    for pattern in HOMEPAGE_SECTION_PATTERNS:
        if re.match(pattern, clean_path):
            return True
    return False


def validate_and_resolve_url(raw_url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate URL syntax and enforce SSRF defense by verifying DNS resolution.
    
    Returns:
        (is_valid: bool, normalized_url: Optional[str], error_message: Optional[str])
    """
    if not raw_url or not isinstance(raw_url, str):
        return False, None, "A valid article URL is required."

    url_stripped = raw_url.strip()
    if not url_stripped:
        return False, None, "URL cannot be empty."

    # Parse URL
    try:
        parsed = urllib.parse.urlparse(url_stripped)
    except Exception:
        return False, None, "Invalid URL format."

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, None, "Only HTTP and HTTPS URLs are permitted."

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, None, "URL must contain a valid domain name."

    # Check against known dangerous hostnames
    if (
        hostname in RESTRICTED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".localhost")
    ):
        return False, None, "Access to private or local network hosts is prohibited."

    # Check for direct IP in hostname
    try:
        ipaddress.ip_address(hostname)
        if not is_safe_ip(hostname):
            return False, None, "Access to private or internal IP ranges is prohibited."
    except ValueError:
        pass

    # Resolve DNS to check all underlying IP addresses
    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        resolved_ips = {item[4][0] for item in addr_info if item and len(item) > 4}
        if not resolved_ips:
            return False, None, f"Could not resolve domain name: '{hostname}'."

        for ip_addr in resolved_ips:
            if not is_safe_ip(ip_addr):
                return False, None, "Access to private, loopback, or internal IP addresses is prohibited."
    except socket.gaierror:
        return False, None, f"Unable to resolve domain: '{hostname}'. Please check the URL."
    except Exception:
        return False, None, "Domain resolution verification failed."

    # Reconstruct normalized URL
    normalized = urllib.parse.urlunparse(parsed)
    return True, normalized, None


def _extract_with_trafilatura(raw_html: str, base_url: str) -> Optional[Dict[str, Any]]:
    """Extract article text and metadata using Trafilatura."""
    if not TRAFILATURA_AVAILABLE or not raw_html:
        return None
    try:
        body = trafilatura.extract(
            raw_html,
            url=base_url,
            include_comments=False,
            include_tables=False,
            no_fallback=False
        )
        metadata = trafilatura.extract_metadata(raw_html, default_url=base_url)
        
        if body and len(body.split()) >= 15:
            title = ""
            author = ""
            date = ""
            sitename = ""
            canonical = ""
            if metadata:
                title = metadata.title or ""
                author = metadata.author or ""
                date = metadata.date or ""
                sitename = metadata.sitename or ""
                canonical = metadata.url or ""
            return {
                "content": body,
                "title": title,
                "author": author,
                "date": date,
                "sitename": sitename,
                "canonical_url": canonical
            }
    except Exception as exc:
        logger.debug(f"Trafilatura extraction exception: {exc}")
    return None


def _extract_with_bs4(raw_html: str, base_url: str) -> Optional[Dict[str, Any]]:
    """Extract article text and metadata using BeautifulSoup4."""
    if not BS4_AVAILABLE or not raw_html:
        return None
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        
        # Remove unwanted tags
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form", "iframe"]):
            element.decompose()

        # Extract title
        title = ""
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text().strip()

        # Extract metadata
        author = ""
        meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
        if meta_author and meta_author.get("content"):
            author = meta_author["content"].strip()

        date = ""
        meta_date = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
        if meta_date and meta_date.get("content"):
            date = meta_date["content"].strip()

        canonical = ""
        link_canonical = soup.find("link", rel="canonical")
        if link_canonical and link_canonical.get("href"):
            canonical = link_canonical["href"].strip()

        # Find main article container
        article_elem = soup.find("article") or soup.find("div", itemprop="articleBody") or soup.find("main")
        paragraphs = []
        target = article_elem if article_elem else soup.body
        if target:
            for p in target.find_all(["p", "blockquote"]):
                txt = p.get_text().strip()
                if len(txt) > 25:
                    paragraphs.append(txt)

        body = " ".join(paragraphs)
        body = re.sub(r'\s+', ' ', body).strip()
        if len(body.split()) >= 15:
            return {
                "content": body,
                "title": title,
                "author": author,
                "date": date,
                "sitename": "",
                "canonical_url": canonical
            }
    except Exception as exc:
        logger.debug(f"BS4 extraction exception: {exc}")
    return None


def _extract_with_simple_parser(raw_html: str) -> Dict[str, Any]:
    """Fallback article extraction using SimpleHTMLArticleExtractor."""
    parser = SimpleHTMLArticleExtractor()
    parser.feed(raw_html)

    extracted_title = ""
    if parser.og_title:
        extracted_title = parser.og_title
    elif parser.title_tokens:
        extracted_title = " ".join(parser.title_tokens)
    elif parser.h1_tokens:
        extracted_title = " ".join(parser.h1_tokens)

    extracted_title = html.unescape(extracted_title).strip()
    extracted_title = re.sub(r'\s*[-|]\s*[\w\s.]+$', '', extracted_title).strip() or extracted_title

    combined_text = " ".join(parser.paragraphs)
    combined_text = html.unescape(combined_text)
    combined_text = re.sub(r'\s+', ' ', combined_text).strip()

    return {
        "content": combined_text,
        "title": extracted_title,
        "author": "",
        "date": "",
        "sitename": parser.og_site_name or "",
        "canonical_url": ""
    }


def _fetch_html_network(url: str, is_homepage: bool) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Execute safe network retrieval with SSRF re-validation on every redirect hop.
    
    Returns:
        (success: bool, raw_html: Optional[str], error_dict: Optional[Dict[str, Any]])
    """
    current_url = url
    redirect_count = 0
    parsed = urllib.parse.urlparse(url)
    domain_initial = parsed.netloc.lower()

    if REQUESTS_AVAILABLE:
        session = requests.Session()
        session.headers.update(DEFAULT_FETCH_HEADERS)

        while redirect_count <= MAX_REDIRECTS:
            try:
                resp = session.get(
                    current_url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                    stream=True
                )

                # Check for HTTP redirects
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        return False, None, {
                            "success": False, "url": current_url, "canonical_url": current_url,
                            "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                            "content": "", "word_count": 0, "error": "Redirect location missing from article server.",
                            "error_code": "INVALID_REDIRECT", "is_homepage": is_homepage
                        }
                    next_url = urllib.parse.urljoin(current_url, location)
                    is_safe, validated_next, redirect_err = validate_and_resolve_url(next_url)
                    if not is_safe:
                        return False, None, {
                            "success": False, "url": next_url, "canonical_url": next_url,
                            "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                            "content": "", "word_count": 0, "error": f"Redirect blocked: {redirect_err}",
                            "error_code": "SSRF_REDIRECT_BLOCKED", "is_homepage": is_homepage
                        }
                    current_url = validated_next
                    redirect_count += 1
                    continue

                # Handle HTTP Status Codes
                status = resp.status_code
                if status == 401:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The publisher requires subscription authentication or login (HTTP 401). Please paste the article text directly below to verify the claim.",
                        "error_code": "AUTH_REQUIRED", "is_homepage": is_homepage
                    }
                elif status == 403:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The news website restricted automated access or is protected by a paywall (HTTP 403). Please paste the article text directly below to verify the claims.",
                        "error_code": "FORBIDDEN_OR_PAYWALL", "is_homepage": is_homepage
                    }
                elif status == 429:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The publisher rate limit was reached (HTTP 429). Please wait a moment or paste the text directly.",
                        "error_code": "RATE_LIMITED", "is_homepage": is_homepage
                    }
                elif status == 404:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The article URL was not found on the server (HTTP 404). Please verify the link.",
                        "error_code": "NOT_FOUND", "is_homepage": is_homepage
                    }
                elif status >= 400:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": f"Article server responded with HTTP status {status}.",
                        "error_code": f"HTTP_{status}", "is_homepage": is_homepage
                    }

                # Content Type Check
                ctype = resp.headers.get("Content-Type", "").lower()
                if "text/html" not in ctype and "application/xhtml" not in ctype and "text/plain" not in ctype:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The target URL does not return HTML article content.",
                        "error_code": "UNSUPPORTED_CONTENT_TYPE", "is_homepage": is_homepage
                    }

                # Read limited bytes
                content_bytes = bytearray()
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        break
                    content_bytes.extend(chunk)
                    if len(content_bytes) >= MAX_ARTICLE_RESPONSE_BYTES:
                        break

                charset = resp.encoding or "utf-8"
                try:
                    raw_html = content_bytes.decode(charset, errors="replace")
                except Exception:
                    raw_html = content_bytes.decode("utf-8", errors="replace")
                return True, raw_html, None

            except requests.exceptions.Timeout:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "Connection to the news server timed out. You can paste the article text directly below.",
                    "error_code": "NETWORK_TIMEOUT", "is_homepage": is_homepage
                }
            except requests.exceptions.RequestException as req_err:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "Failed to connect to the article server (network timeout or unreachable host). You can paste the article text directly.",
                    "error_code": "NETWORK_TIMEOUT", "is_homepage": is_homepage
                }

    # Fallback to urllib.request if requests unavailable
    while redirect_count <= MAX_REDIRECTS:
        try:
            req = urllib.request.Request(current_url, headers=DEFAULT_FETCH_HEADERS)
            class NoAutoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(NoAutoRedirect)

            with opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml" not in content_type and "text/plain" not in content_type:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0,
                        "error": "The target URL does not return HTML article content.",
                        "error_code": "UNSUPPORTED_CONTENT_TYPE", "is_homepage": is_homepage
                    }
                content_bytes = bytearray()
                while len(content_bytes) < MAX_ARTICLE_RESPONSE_BYTES:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    content_bytes.extend(chunk)
                charset = response.headers.get_content_charset() or "utf-8"
                raw_html = content_bytes.decode(charset, errors="replace")
                return True, raw_html, None

        except urllib.error.HTTPError as http_err:
            if http_err.code in (301, 302, 303, 307, 308):
                redirect_target = http_err.headers.get("Location")
                if not redirect_target:
                    return False, None, {
                        "success": False, "url": current_url, "canonical_url": current_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0, "error": "Redirect location header missing from article server.",
                        "error_code": "INVALID_REDIRECT", "is_homepage": is_homepage
                    }
                next_url = urllib.parse.urljoin(current_url, redirect_target)
                is_safe, validated_next, redirect_err = validate_and_resolve_url(next_url)
                if not is_safe:
                    return False, None, {
                        "success": False, "url": next_url, "canonical_url": next_url,
                        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                        "content": "", "word_count": 0, "error": f"Redirect blocked: {redirect_err}",
                        "error_code": "SSRF_REDIRECT_BLOCKED", "is_homepage": is_homepage
                    }
                current_url = validated_next
                redirect_count += 1
                continue

            if http_err.code == 401:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "The publisher requires subscription authentication or login (HTTP 401). Please paste the article text directly below to verify the claim.",
                    "error_code": "AUTH_REQUIRED", "is_homepage": is_homepage
                }
            elif http_err.code == 403:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "The news website restricted automated access or is protected by a paywall (HTTP 403). Please paste the article text directly below to verify the claims.",
                    "error_code": "FORBIDDEN_OR_PAYWALL", "is_homepage": is_homepage
                }
            elif http_err.code == 429:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "The publisher rate limit was reached (HTTP 429). Please wait a moment or paste the text directly.",
                    "error_code": "RATE_LIMITED", "is_homepage": is_homepage
                }
            elif http_err.code == 404:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": "The article URL was not found on the server (HTTP 404). Please verify the link.",
                    "error_code": "NOT_FOUND", "is_homepage": is_homepage
                }
            else:
                return False, None, {
                    "success": False, "url": current_url, "canonical_url": current_url,
                    "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                    "content": "", "word_count": 0,
                    "error": f"Article server responded with HTTP status {http_err.code}.",
                    "error_code": f"HTTP_{http_err.code}", "is_homepage": is_homepage
                }
        except Exception:
            return False, None, {
                "success": False, "url": current_url, "canonical_url": current_url,
                "domain": domain_initial, "title": "", "author": "", "publish_date": "",
                "content": "", "word_count": 0,
                "error": "Failed to connect to the article server (network timeout or unreachable host). You can paste the article text directly.",
                "error_code": "NETWORK_TIMEOUT", "is_homepage": is_homepage
            }

    return False, None, {
        "success": False, "url": current_url, "canonical_url": current_url,
        "domain": domain_initial, "title": "", "author": "", "publish_date": "",
        "content": "", "word_count": 0, "error": "Too many redirects encountered while fetching the article.",
        "error_code": "TOO_MANY_REDIRECTS", "is_homepage": is_homepage
    }


def fetch_and_extract_article(url: str, max_chars: int = 10000) -> Dict[str, Any]:
    """Safely fetch a public news article and extract structured content and metadata.
    
    Returns:
        Dict with keys:
            - success (bool)
            - url (str)
            - canonical_url (str)
            - domain (str)
            - title (str)
            - author (str)
            - publish_date (str)
            - content (str)
            - word_count (int)
            - error (Optional[str])
            - error_code (Optional[str])
            - is_homepage (bool)
    """
    is_valid, normalized_url, err_msg = validate_and_resolve_url(url)
    if not is_valid:
        return {
            "success": False,
            "url": url,
            "canonical_url": url,
            "domain": "",
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": err_msg or "Invalid URL.",
            "error_code": "INVALID_URL",
            "is_homepage": False
        }

    parsed_initial = urllib.parse.urlparse(normalized_url)
    domain_initial = parsed_initial.netloc.lower()
    is_homepage = is_homepage_or_section(parsed_initial.path)

    # Perform network retrieval
    net_ok, raw_html, net_err = _fetch_html_network(normalized_url, is_homepage)
    if not net_ok or not raw_html:
        return net_err or {
            "success": False,
            "url": normalized_url,
            "canonical_url": normalized_url,
            "domain": domain_initial,
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The fetched article page was empty.",
            "error_code": "EMPTY_RESPONSE",
            "is_homepage": is_homepage
        }

    if len(raw_html.strip()) < 50:
        return {
            "success": False,
            "url": normalized_url,
            "canonical_url": normalized_url,
            "domain": domain_initial,
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The fetched article page was empty.",
            "error_code": "EMPTY_RESPONSE",
            "is_homepage": is_homepage
        }

    # Execute extraction cascade: Trafilatura -> BS4 -> SimpleParser
    extracted_data = _extract_with_trafilatura(raw_html, normalized_url)
    if not extracted_data or len(extracted_data["content"].split()) < 15:
        extracted_data = _extract_with_bs4(raw_html, normalized_url)
    if not extracted_data or len(extracted_data["content"].split()) < 15:
        extracted_data = _extract_with_simple_parser(raw_html)

    body_text = extracted_data.get("content", "").strip()
    title = extracted_data.get("title", "").strip() or "News Article"
    author = extracted_data.get("author", "").strip()
    pub_date = extracted_data.get("date", "").strip()
    canonical_url = extracted_data.get("canonical_url", "").strip() or normalized_url

    # Check for homepage / section index with insufficient article narrative
    word_count = len(body_text.split())
    if is_homepage and word_count < 40:
        return {
            "success": False,
            "url": normalized_url,
            "canonical_url": canonical_url,
            "domain": domain_initial,
            "title": title,
            "author": author,
            "publish_date": pub_date,
            "content": "",
            "word_count": word_count,
            "error": (
                "The submitted link appears to be a section or homepage (e.g. reuters.com/world/) rather than a "
                "specific news article. Please provide a link to a specific article, or paste the article text."
            ),
            "error_code": "HOMEPAGE_SECTION_DETECTED",
            "is_homepage": True
        }

    if word_count < 10:
        return {
            "success": False,
            "url": normalized_url,
            "canonical_url": canonical_url,
            "domain": domain_initial,
            "title": title,
            "author": author,
            "publish_date": pub_date,
            "content": "",
            "word_count": word_count,
            "error": (
                "Could not extract sufficient text content from this article URL. "
                "The page may rely heavily on client-side JavaScript or require interactive login. "
                "You can paste the article text directly below to analyze it."
            ),
            "error_code": "INSUFFICIENT_ARTICLE_TEXT",
            "is_homepage": is_homepage
        }

    # Truncate cleanly if too long for transformer limit
    if len(body_text) > max_chars:
        truncated = body_text[:max_chars]
        last_period = truncated.rfind(".")
        if last_period > max_chars * 0.7:
            body_text = truncated[:last_period + 1]
        else:
            body_text = truncated

    return {
        "success": True,
        "url": normalized_url,
        "canonical_url": canonical_url,
        "domain": domain_initial,
        "title": title,
        "author": author,
        "publish_date": pub_date,
        "content": body_text,
        "word_count": len(body_text.split()),
        "error": None,
        "error_code": None,
        "is_homepage": is_homepage
    }
