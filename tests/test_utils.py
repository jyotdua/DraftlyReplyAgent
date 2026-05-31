from email.mime.text import MIMEText

from app.utils import encode_gmail_message, make_idempotency_key


def test_make_idempotency_key_is_stable():
    assert make_idempotency_key("a", "b") == make_idempotency_key("a", "b")


def test_encode_gmail_message_is_urlsafe():
    message = MIMEText("hello")
    encoded = encode_gmail_message(message)
    assert "+" not in encoded
    assert "/" not in encoded
