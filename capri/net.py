"""Secure downloads that work on every PC.

Python checks website certificates with its own rules, and on some Windows PCs that check fails
where a browser works fine ("CERTIFICATE_VERIFY_FAILED"). Common reasons are antivirus that scans
HTTPS (Avast, Kaspersky, ESET...) with its own certificate that Windows trusts, a school or work
network that does the same, or a root certificate Windows hasn't fetched yet.

So every web request Capri makes (urllib) goes through a handler that tries, in order:
1. Python's normal check (Windows' certificate store) - what works on most PCs,
2. Windows' own verification, like a browser (the `truststore` package) - antivirus / school networks,
3. Mozilla's list of trusted certificates (`certifi`).
Certificates are always checked: verification is never turned off. (1.36.2 switched everything to
2. globally, which broke "check for updates" on some PCs - now it's only a fallback.)
"""

from __future__ import annotations

import http.client
import logging
import ssl
import urllib.error
import urllib.request

log = logging.getLogger("capri")

_done = ""


def is_ssl_problem(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    text = str(exc)
    return isinstance(reason, ssl.SSLError) or isinstance(exc, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in text \
        or "SSL" in text and "certificate" in text.lower()


def _truststore_context() -> ssl.SSLContext | None:
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return None


def _certifi_context() -> ssl.SSLContext | None:
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        try:
            ctx.load_default_certs()                 # Windows' store as well
        except Exception:
            pass
        return ctx
    except Exception:
        return None


FALLBACKS = (("Windows verification", _truststore_context), ("Mozilla's certificate list", _certifi_context))


class FallbackHTTPSHandler(urllib.request.HTTPSHandler):
    """HTTPS that tries the other two certificate checks before giving up on a certificate error."""

    def https_open(self, req):
        try:
            return super().https_open(req)
        except urllib.error.URLError as exc:
            if not is_ssl_problem(exc):
                raise
            first = exc
        for name, make in FALLBACKS:
            context = make()
            if context is None:
                continue
            try:
                response = self.do_open(http.client.HTTPSConnection, req, context=context)
                log.info("https: %s needed %s", req.host, name)
                return response
            except urllib.error.URLError as exc:
                if not is_ssl_problem(exc):
                    raise
        raise first


def use_system_certificates() -> str:
    """Call once at start-up: every urllib request gets the fallbacks. Returns what's available."""
    global _done
    if _done:
        return _done
    urllib.request.install_opener(urllib.request.build_opener(FallbackHTTPSHandler()))
    have = [name for name, make in FALLBACKS if make() is not None]
    _done = "fallbacks: " + (", ".join(have) or "none")
    log.info("certificates: Python's check, then %s", ", ".join(have) or "nothing else")
    return _done


def friendly(exc: BaseException) -> str:
    """A download error in words a person can act on."""
    text = str(exc)
    status = getattr(exc, "code", None) or getattr(exc, "status", None)
    if is_ssl_problem(exc):
        return ("couldn't make a secure connection. If you have antivirus with “HTTPS scanning” "
                "or “web shield”, allow Capri or turn that off for a minute, then try again")
    if "timed out" in text.lower():
        return "the connection timed out - check your internet and try again"
    if status == 403 or "rate limit" in text.lower():
        return "GitHub is busy - try again in a few minutes"
    if status == 404 or "404" in text:
        return "the file isn't available right now - try again later"
    if "getaddrinfo" in text or "Name or service not known" in text or "nodename nor servname" in text:
        return "no internet connection"
    if "No space left" in text or "Errno 28" in text:
        return "your disk is full - free some space and try again"
    return text[:120]
