
"""Feature access checks for request-scoped entitlements."""

def parse_key_features(value: str | None) -> frozenset[str]:
    """
    Convert the comma-separated request string to a set.

    Examples:
      "HomePage,UDPage,CompareUnit"
      -> {"homepage", "udpage", "compareunit"}
    """
    if not isinstance(value, str):
        return frozenset()

    return frozenset(
        part.strip().casefold()
        for part in value.split(",")
        if part.strip()
    )


def has_key_feature(
    key_features: str | None,
    required_key: str | None,
) -> bool:
    """
    Exact feature-token matching, ignoring casing.

    Missing permissions always fail closed.
    """
    if not isinstance(required_key, str):
        return False

    required_key = required_key.strip().casefold()

    if not required_key:
        return False

    return required_key in parse_key_features(key_features)
