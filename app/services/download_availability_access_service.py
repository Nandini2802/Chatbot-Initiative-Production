
from app.services.feature_access_service import (
    has_key_feature,
)


DOWNLOAD_AVAILABILITY_KEY = "DownloadAvailability"


class DownloadAvailabilityAccessService:

    def check(
        self,
        *,
        key_features: str | None,
    ) -> tuple[bool, str]:

        allowed = has_key_feature(
            key_features=key_features,
            required_key=DOWNLOAD_AVAILABILITY_KEY,
        )

        if not allowed:
            return (
                False,
                "download_availability_key_missing",
            )

        return True, "feature_key_verified"
