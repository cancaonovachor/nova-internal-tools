import hashlib
import hmac


def verify_notion_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    verification_token: str,
) -> bool:
    if not signature_header:
        return False

    expected = hmac.new(
        verification_token.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, provided)
