"""Shared HTTP session with retries, timeouts and a polite User-Agent."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

DEFAULT_TIMEOUT = 90


def make_session():
    s = requests.Session()
    retry = Retry(
        total=4, backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": config.USER_AGENT})
    return s


def get_json(session, url, timeout=DEFAULT_TIMEOUT, **kw):
    r = session.get(url, timeout=timeout, **kw)
    r.raise_for_status()
    return r.json()
