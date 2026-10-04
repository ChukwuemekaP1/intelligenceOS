"""Website / HTML Parser with SSRF Protection.

Safely fetches and extracts readable text and article content from web URLs.
Applies strict SSRF (Server-Side Request Forgery) filtering to block attempts to access
internal networks, cloud metadata endpoints, loopback addresses, or private subnets.
"""

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.ingestion.parsers.base import BaseParser, ParserError
from app.models.source import SourceType

logger = get_logger("app.ingestion.parsers.website")

# Maximum permitted webpage download size (10 MB)
MAX_WEBPAGE_BYTES = 10 * 1024 * 1024

# Cloud metadata and forbidden local hostnames
FORBIDDEN_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
    "instance-data",
}


def validate_safe_url(url: str) -> None:
    """Validates that a URL is safe against Server-Side Request Forgery (SSRF).

    Checks:
      1. Scheme must be strictly 'http' or 'https'.
      2. Hostname must not match known metadata or loopback hostnames.
      3. DNS resolution must not resolve to any private, loopback, multicast,
         link-local (e.g. 169.254.169.254 cloud metadata), or reserved IP addresses.

    Raises:
        ParserError: If the URL violates SSRF safety rules.
    """
    if not url or not isinstance(url, str):
        raise ParserError("Invalid or empty URL provided.")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ParserError(f"Malformed URL: {exc}") from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise ParserError(
            f"Prohibited URL scheme '{parsed.scheme}'. Only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ParserError("URL does not specify a valid hostname.")

    hostname_lower = hostname.lower()
    if hostname_lower in FORBIDDEN_HOSTNAMES:
        raise ParserError(f"Access to restricted hostname '{hostname}' is forbidden.")

    # DNS Resolution and IP checking
    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ParserError(f"DNS resolution failed for hostname '{hostname}': {exc}") from exc

    resolved_ips: set[str] = {item[4][0] for item in addr_info if item[4]}
    if not resolved_ips:
        raise ParserError(f"No IP addresses resolved for hostname '{hostname}'.")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ParserError(f"Invalid resolved IP address '{ip_str}'.") from None

        if ip.is_loopback:
            raise ParserError(
                f"Target URL resolves to a loopback address ({ip_str}). Access blocked."
            )
        if ip.is_private:
            raise ParserError(
                f"Target URL resolves to a private network address ({ip_str}). Access blocked."
            )
        if ip.is_link_local:
            raise ParserError(
                f"Target URL resolves to a link-local address ({ip_str}). Access blocked."
            )
        if ip.is_multicast:
            raise ParserError(
                f"Target URL resolves to a multicast address ({ip_str}). Access blocked."
            )
        if ip.is_reserved:
            raise ParserError(
                f"Target URL resolves to a reserved address ({ip_str}). Access blocked."
            )
        if ip.is_unspecified:
            raise ParserError(
                f"Target URL resolves to an unspecified address ({ip_str}). Access blocked."
            )


class WebsiteParser(BaseParser):
    """Parses web HTML content, extracting clean text elements while rejecting SSRF attacks."""

    async def fetch_url(self, url: str) -> tuple[bytes, str]:
        """Safely fetches a web URL following SSRF rules on redirects.

        Returns:
            Tuple of (html_bytes, final_url)
        """
        validate_safe_url(url)

        headers = {
            "User-Agent": "IntelligenceOS-IngestionBot/1.0 (+https://intelligenceos.local/bot)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
        }

        # Use an explicit client with restricted timeouts and redirect handling
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=False,
            headers=headers,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        ) as client:
            current_url = url
            for _ in range(4):  # maximum 3 redirects
                try:
                    resp = await client.get(current_url)
                except httpx.RequestError as exc:
                    raise ParserError(f"Network error fetching URL '{current_url}': {exc}") from exc

                if resp.is_redirect:
                    redirect_target = resp.headers.get("Location")
                    if not redirect_target:
                        raise ParserError("Redirect received without Location header.")
                    # Build full URL if relative
                    new_url = str(resp.url.join(redirect_target))
                    # Validate the redirect target against SSRF rules!
                    validate_safe_url(new_url)
                    current_url = new_url
                    continue

                if resp.status_code != 200:
                    raise ParserError(f"HTTP request failed with status code {resp.status_code}")

                # Verify payload size
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_WEBPAGE_BYTES:
                    raise ParserError("Webpage content exceeds maximum allowed limit.")

                data = resp.content
                if len(data) > MAX_WEBPAGE_BYTES:
                    raise ParserError("Webpage content exceeds maximum allowed limit.")

                return data, str(resp.url)

            raise ParserError("Too many HTTP redirects encountered.")

    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        meta = metadata or {}
        target_url = meta.get("url")

        # If content bytes are not provided but URL is present, fetch the URL
        if not content and target_url:
            content, final_url = await self.fetch_url(target_url)
            meta["final_url"] = final_url

        if not content:
            raise ParserError("Website content is empty and no valid URL provided.")

        try:
            # Decode HTML
            html_text = content.decode("utf-8", errors="replace")
            soup = BeautifulSoup(html_text, "html.parser")

            # Remove noisy non-content elements
            for tag in soup(
                ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"]
            ):
                tag.decompose()

            # Extract document title
            title = "Web Document"
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            elif soup.h1:
                title = soup.h1.get_text(strip=True)
            elif target_url:
                title = target_url

            elements: list[NormalizedElement] = []
            elem_idx = 0

            # Gather readable text blocks: headings, paragraphs, list items
            content_nodes = soup.find_all(
                ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]
            )

            for node in content_nodes:
                text = node.get_text(separator=" ", strip=True)
                # Ignore very short or whitespace-only nodes
                if len(text) >= 15:
                    elements.append(
                        NormalizedElement(
                            element_index=elem_idx,
                            text=text,
                            page_number=None,
                            metadata={
                                "tag": node.name,
                                "url": target_url or meta.get("final_url"),
                            },
                        )
                    )
                    elem_idx += 1

            # Fallback: if no specific tags matched, get entire body text
            if not elements:
                body_text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in body_text.splitlines() if len(line.strip()) >= 15]
                for line in lines:
                    elements.append(
                        NormalizedElement(
                            element_index=elem_idx,
                            text=line,
                            page_number=None,
                            metadata={"url": target_url or meta.get("final_url")},
                        )
                    )
                    elem_idx += 1

            if not elements:
                raise ParserError("No extractable text content found on webpage.")

            return NormalizedDocument(
                title=title,
                source_type=SourceType.WEBSITE,
                elements=elements,
                raw_metadata={
                    "url": target_url or meta.get("final_url"),
                    "title": title,
                },
            )

        except ParserError:
            raise
        except Exception as exc:
            raise ParserError(f"Unexpected error parsing website HTML: {exc}") from exc
