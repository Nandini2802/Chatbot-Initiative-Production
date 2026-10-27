
"""
Project tour utilities for Danube Chatbot.

- Extract project_tour_video from OSF Portfolio.
- Match project names.
- Validate video URLs.
- Avoid ambiguous project matches.
"""

from urllib.parse import urlparse

from app.utils.google_maps import (
    normalize_map_project_name,
)


ALLOWED_VIDEO_HOSTS = {
    "danubeproperties.com",
    "www.danubeproperties.com",
    "staging.danubeproperties.com",
}


def safe_tour_video_url(value):
    """
    Return a validated HTTPS MP4 URL.
    """

    if not isinstance(value, str):
        return None

    url = value.strip()

    if not url:
        return None

    try:
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_VIDEO_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            return None

        if not parsed.path.lower().endswith(".mp4"):
            return None

        return url

    except ValueError:
        return None


def build_project_tour_lookup(portfolio):
    """
    Create:
        normalized_project_name -> video_url

    Match against:
    - OSF portfolio title
    - OSF Google Maps project name

    Conflicting matches are excluded.
    """

    lookup = {}
    ambiguous = set()

    if not isinstance(portfolio, list):
        return lookup

    for item in portfolio:

        if not isinstance(item, dict):
            continue

        title = item.get("title")

        meta = item.get("meta") or {}

        if not isinstance(meta, dict):
            continue

        video_url = safe_tour_video_url(
            meta.get("project_tour_video")
        )

        if not video_url:
            continue

        map_data = meta.get(
            "danube_google_map_address"
        ) or {}

        map_name = (
            map_data.get("name")
            if isinstance(map_data, dict)
            else None
        )

        for name in (title, map_name):

            key = normalize_map_project_name(name)

            if not key:
                continue

            if (
                key in lookup
                and lookup[key] != video_url
            ):
                ambiguous.add(key)
            else:
                lookup[key] = video_url

    for key in ambiguous:
        lookup.pop(key, None)

    return lookup
