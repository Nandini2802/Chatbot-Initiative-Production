"""Integration helpers. Call only after identity attributes have been verified."""
from dataclasses import dataclass
from typing import Optional
from app.services.walkthrough_access_service import WalkthroughEngine

@dataclass(frozen=True)
class VerifiedWalkthroughIdentity:
    role: str
    source: str
    employee_type: str


def resolve_walkthrough(engine: WalkthroughEngine, feature_name: Optional[str], identity: VerifiedWalkthroughIdentity) -> dict:
    """Never pass untrusted frontend role/employee_type directly to this helper."""
    if not feature_name:
        return {"status": "clarification", "message": "Which Danube One feature would you like help with?"}
    result = engine.lookup(feature_name, identity.role, identity.source, identity.employee_type)
    if result['status'] != 'ok':
        return {"status": "denied", "message": "Great question! While we don't offer that feature yet, I'd love to help you explore other features which are available for you."}
    return {"status": "ok", "feature": result['feature'], "steps": result['steps']}
