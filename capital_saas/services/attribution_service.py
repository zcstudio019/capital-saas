import secrets

from fastapi import Request


ATTRIBUTION_FIELDS = [
    "source_channel", "source_campaign", "source_keyword", "source_landing_page",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
]


def capture_attribution(request: Request, landing_page: str = "") -> dict:
    session = request.session
    if not session.get("visitor_session_id"):
        session["visitor_session_id"] = secrets.token_urlsafe(18)
    mapping = {
        "utm_source": request.query_params.get("utm_source", ""),
        "utm_medium": request.query_params.get("utm_medium", ""),
        "utm_campaign": request.query_params.get("utm_campaign", ""),
        "utm_content": request.query_params.get("utm_content", ""),
        "utm_term": request.query_params.get("utm_term", ""),
        "source_channel": request.query_params.get("channel", ""),
        "source_campaign": request.query_params.get("campaign", ""),
        "source_keyword": request.query_params.get("keyword", ""),
    }
    if landing_page:
        mapping["source_landing_page"] = landing_page
    for key, value in mapping.items():
        if value:
            session[key] = value[:200]
    partner = request.query_params.get("partner", "").strip()
    if partner:
        session["partner_source_code"] = partner[:100]
    pilot = request.query_params.get("pilot", "").strip()
    if pilot:
        session["pilot_invite_code"] = pilot[:100]
    if not session.get("source_channel") and session.get("utm_source"):
        session["source_channel"] = session["utm_source"]
    if not session.get("source_campaign") and session.get("utm_campaign"):
        session["source_campaign"] = session["utm_campaign"]
    return attribution_from_session(request)


def attribution_from_session(request: Request) -> dict:
    return {key: str(request.session.get(key, ""))[:200] for key in ATTRIBUTION_FIELDS}


def attribution_from_object(obj) -> dict:
    return {key: getattr(obj, key, "") or "" for key in ATTRIBUTION_FIELDS}
