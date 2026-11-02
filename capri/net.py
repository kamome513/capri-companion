"""Secure downloads that work on every PC.

Python checks website certificates with its own rules, and on some Windows PCs that check fails
where a browser works fine ("CERTIFICATE_VERIFY_FAILED"). Common reasons are antivirus that scans
HTTPS (Avast, Kaspersky, ESET...) with its own certificate that Windows trusts, a school or work
network that does the same, or a root certificate Windows hasn't fetched yet. That broke
"Download Parakeet", her voice download and updates.

So at start-up Capri checks certificates the way Windows and browsers do (the `truststore`
package). If that isn't available she adds Mozilla's list of trusted certificates (`certifi`) on
top of Windows' own. Certificates are still checked either way: verification is never turned off.
"""

from __future__ import annotations

import logging
import os
import ssl

log = logging.getLogger("capri")

_done = ""


def use_system_certificates() -> str:
    """Call once at start-up. Returns how certificates are checked ("system" / "certifi" / "python")."""
    global _done
    if _done:
        return _done
    try:
        import truststore
        truststore.inject_into_ssl()               # urllib, http.client... ask Windows itself
        _done = "system"
    except Exception as exc:                       # not installed / too old a Python
        log.info("certificates: truststore unavailable (%s)", exc)
        try:
            import certifi
            if not os.environ.get("SSL_CERT_FILE") and os.path.isfile(certifi.where()):
                os.environ["SSL_CERT_FILE"] = certifi.where()    # Windows' store + Mozilla's list
            _done = "certifi"
        except Exception:
            _done = "python"
    log.info("certificates: checked by %s", _done)
    return _done


def friendly(exc: BaseException) -> str:
    """A download error in words a person can act on."""
    text = str(exc)
    if isinstance(exc, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text:
        return ("couldn't make a secure connection. If you have antivirus with “HTTPS scanning” "
                "or “web shield”, allow Capri or turn that off for a minute, then try again")
    if "timed out" in text.lower():
        return "the connection timed out - check your internet and try again"
    if "403" in text or "404" in text:
        return "the file isn't available right now - try again later"
    if "No space left" in text or "Errno 28" in text:
        return "your disk is full - free some space and try again"
    return text[:120]
