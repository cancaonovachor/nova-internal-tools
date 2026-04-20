import hashlib
import hmac

from common.signature import verify_notion_signature

TOKEN = "secret-verification-token"
BODY = b'{"type":"page.created"}'


def _sig(body: bytes, token: str) -> str:
    return "sha256=" + hmac.new(
        token.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def test_valid_signature():
    assert verify_notion_signature(
        raw_body=BODY,
        signature_header=_sig(BODY, TOKEN),
        verification_token=TOKEN,
    )


def test_valid_signature_without_prefix():
    hex_only = _sig(BODY, TOKEN).removeprefix("sha256=")
    assert verify_notion_signature(
        raw_body=BODY,
        signature_header=hex_only,
        verification_token=TOKEN,
    )


def test_missing_header_rejected():
    assert not verify_notion_signature(
        raw_body=BODY,
        signature_header=None,
        verification_token=TOKEN,
    )


def test_empty_header_rejected():
    assert not verify_notion_signature(
        raw_body=BODY,
        signature_header="",
        verification_token=TOKEN,
    )


def test_wrong_token_rejected():
    assert not verify_notion_signature(
        raw_body=BODY,
        signature_header=_sig(BODY, "other-token"),
        verification_token=TOKEN,
    )


def test_tampered_body_rejected():
    sig = _sig(BODY, TOKEN)
    assert not verify_notion_signature(
        raw_body=BODY + b"tampered",
        signature_header=sig,
        verification_token=TOKEN,
    )
