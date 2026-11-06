
"""Find permitted How-To Videos from the Redis catalog."""

import logging
import re
from urllib.parse import urlsplit, parse_qs

from app.persistence.redis_store import RedisCacheKeys
from app.services.api_cache_service import APICacheService
from app.services.feature_access_service import (
    has_key_feature,
)


logger = logging.getLogger(__name__)


# Title -> allowed feature keys and matching Excel names.
# Each title may have multiple known Excel names.
VIDEO_RULES = {
    "how to create eoi": {
        "keys": ("EoiCreate",),
        "features": (
            "Create EOI",
            "EOI Creation",
            "EOI (Expression of Interest) / EOI Request",
        ),
    },
    "how to view eoi dashboard": {
        "keys": ("EoiView",),
        "features": ("View EOI", "EOI Dashboard"),
    },
    "how to view sales order": {
        "keys": ("Sales Order",),
        "features": (
            "Sales Order",
            "Sales Order / Booking",
        ),
    },
    "how to enable or disable agent": {
        "keys": ("AddAgent", "AddReferral"),
        "features": (
            "Enable or Disable Agent",
            "Add or Remove Agent/s",
        ),
    },
    "how to add agent": {
        "keys": ("AddAgent", "AddReferral"),
        "features": (
            "Add Agent",
            "Add or Remove Agent/s",
        ),
    },
    "how to view unit details": {
        "keys": ("UDPage",),
        "features": ("Unit Details Page",),
    },
    "how to download availability": {
        "keys": ("DownloadAvailability",),
        "features": (
            "Project Details Page – Download Availability",
            "Download Availability",
        ),
    },
    "how to change password": {
        "keys": ("ChangePassword",),
        "features": ("Change Password",),
    },
    "how to create lead": {
        "keys": ("LeadTab", "LeadAdd"),
        "features": ("Create Lead",),
    },
    "how to compare units": {
        "keys": ("CompareUnit",),
        "features": ("Add a Unit to Compare",),
    },
    "daily activity report": {
        "keys": ("DAR Dashboard",),
        "features": ("Daily Activity Report",),
    },
    "how to view dar stories": {
        "keys": ("DarAnalytics",),
        "features": ("View DAR Stories",),
    },
    "how to download sales offer": {
        "keys": ("SalesOfferEnable",),
        "features": ("Download Sales Offer",),
    },
    "how to download marketing material": {
        "keys": ("MarketingList",),
        "features": ("Download Marketing Material",),
    },
    "how to raise support ticket": {
        "keys": ("SupportTicket",),
        "features": ("Raise Support Ticket",),
    },
}


def normalize(value) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value or "").casefold(),
    ).strip()


def normalize_role(value) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value or "").casefold(),
    )


def split_excel_keys(value: str) -> set[str]:
    return {
        normalize(part)
        for part in re.split(r"[/,|]", value or "")
        if normalize(part)
    }


def get_player(url: str) -> dict | None:
    """
    Supported:
    1. YouTube Shorts
    2. YouTube short links (youtu.be)
    3. Standard YouTube links
    4. CloudFront MP4
    5. Danube Properties MP4
    """

    if not isinstance(url, str):
        return None

    original_url = url.strip()

    if not original_url:
        return None

    if any(ord(char) < 32 for char in original_url):
        return None

    parsed = urlsplit(original_url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None

    host = parsed.hostname.lower()
    path = parsed.path

    # YouTube URLs
    if host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtube-nocookie.com",
    }:

        video_id = None
        parts = path.strip("/").split("/")

        if host == "youtu.be":
            video_id = parts[0] if parts else None

        elif len(parts) >= 2 and parts[0] in {
            "shorts",
            "embed",
        }:
            video_id = parts[1]

        elif path == "/watch":
            video_id = parse_qs(
                parsed.query
            ).get("v", [None])[0]

        if not video_id or not re.fullmatch(
            r"[A-Za-z0-9_-]{11}",
            video_id,
        ):
            return None

        return {
            "kind": "youtube",
            "url": (
                "https://www.youtube.com"
                f"/embed/{video_id}"
            ),
            "original_url": original_url,
        }

    # Direct MP4 videos
    if path.lower().endswith(".mp4"):

        return {
            "kind": "mp4",
            "url": original_url,
            "original_url": original_url,
        }

    # Unknown formats are not embedded.
    return None



class HowToVideoService:

    def __init__(self, redis_client):
        self.cache = APICacheService(
            redis_client
        )

    async def find_videos(
        self,
        *,
        feature_name: str,
        excel_feature_key: str,
        key_features: str | None,
        role: str,
    ) -> list[dict]:

        cached = await self.cache.get(
            RedisCacheKeys.HOW_TO_VIDEOS
        )

        if not isinstance(cached, dict):
            return []

        data = cached.get("data")

        if not isinstance(data, dict):
            return []

        records = data.get("howToVideos")

        if not isinstance(records, list):
            return []

        guide_name = normalize(feature_name)
        guide_keys = split_excel_keys(
            excel_feature_key
        )

        user_role = normalize_role(role)

        if not guide_keys or not user_role:
            return []

        matched = []

        for record in records:

            if not isinstance(record, dict):
                continue

            title = normalize(record.get("title"))
            rule = VIDEO_RULES.get(title)

            if rule is None:
                continue

            # Match an official Excel feature by name.
            permitted_feature_names = {
                normalize(name)
                for name in rule["features"]
            }

            if guide_name not in permitted_feature_names:
                continue

            # Require a matching Excel developer key.
            video_keys = {
                normalize(key)
                for key in rule["keys"]
            }

            if not guide_keys.intersection(video_keys):
                continue

            # Independently validate video feature access.
            if not any(
                has_key_feature(key_features, key)
                for key in rule["keys"]
            ):
                continue

            # Apply API allowed_roles independently.
            allowed_roles = record.get("allowed_roles")

            if not isinstance(allowed_roles, list):
                continue

            normalized_roles = {
                normalize_role(item)
                for item in allowed_roles
                if isinstance(item, str)
            }

            if (
                "all" not in normalized_roles
                and user_role not in normalized_roles
            ):
                continue

            videos = record.get("videos")

            if not isinstance(videos, list):
                continue

            for video in videos:

                if not isinstance(video, dict):
                    continue

                player = get_player(
                    video.get("video_url", "")
                )

                if player is None:
                    continue

                matched.append({
                    "title": (
                        video.get("title")
                        or record.get("title")
                    ),
                    "duration": (
                        video.get("video_duration")
                        or ""
                    ),
                    "kind": player["kind"],
                    "player_url": player["url"],
                    "original_url": player["original_url"],
                })

        return matched
