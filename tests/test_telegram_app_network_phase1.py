from telegram.error import NetworkError

from telegram_bot.telegram_app import (
    POLLING_BOOTSTRAP_RETRIES,
    build_polling_kwargs,
    format_network_error_message,
    is_network_error,
)


def test_build_polling_kwargs_retries_bootstrap_forever():
    kwargs = build_polling_kwargs()

    assert kwargs["drop_pending_updates"] is True
    assert kwargs["bootstrap_retries"] == POLLING_BOOTSTRAP_RETRIES
    assert kwargs["bootstrap_retries"] == -1


def test_network_error_detection_and_formatting_for_dns_failure():
    error = NetworkError("httpx.ConnectError: [Errno 11001] getaddrinfo failed")

    assert is_network_error(error) is True
    assert "DNS lookup failed" in format_network_error_message(error)


def test_network_error_formatting_for_generic_timeout():
    error = NetworkError("timed out while connecting")

    assert "Retrying automatically." in format_network_error_message(error)
    assert "timed out" in format_network_error_message(error)
