"""GMO Coin FX Private API signature generation (docs/15_PRODUCTION_
READINESS_REVIEW.md "GMO Coin Fixture Based Test").

Read `generate_private_api_signature`'s docstring before trusting these:
they verify the function is internally consistent (deterministic, correctly
keyed, sensitive to every input that's supposed to change the signature) —
NOT that the output matches what GMO Coin's real server expects, which
can only be confirmed against a real account. No live API call is made or
needed for any of these.
"""
import hashlib
import hmac

from app.brokers.gmo_coin import GmoCoinAdapter, generate_private_api_signature


def test_signature_is_deterministic_for_the_same_inputs():
    sig1 = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets")
    sig2 = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets")
    assert sig1 == sig2


def test_signature_matches_a_hand_computed_hmac_sha256():
    secret = "secret123"
    timestamp = "1700000000000"
    method = "POST"
    path = "/v1/order"
    body = '{"symbol":"USD_JPY","side":"BUY","size":"10000"}'

    expected = hmac.new(
        secret.encode("utf-8"), f"{timestamp}{method}{path}{body}".encode("utf-8"), hashlib.sha256
    ).hexdigest()

    actual = generate_private_api_signature(secret, timestamp, method, path, body)
    assert actual == expected


def test_signature_changes_with_a_different_secret():
    common_args = ("1700000000000", "GET", "/v1/positionSummary")
    sig_a = generate_private_api_signature("secret-a", *common_args)
    sig_b = generate_private_api_signature("secret-b", *common_args)
    assert sig_a != sig_b


def test_signature_changes_with_a_different_timestamp():
    sig1 = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets")
    sig2 = generate_private_api_signature("secret123", "1700000000001", "GET", "/v1/account/assets")
    assert sig1 != sig2


def test_signature_changes_with_a_different_method():
    sig_get = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/order")
    sig_post = generate_private_api_signature("secret123", "1700000000000", "POST", "/v1/order")
    assert sig_get != sig_post


def test_signature_changes_with_a_different_path():
    common_args = ("secret123", "1700000000000", "GET")
    sig1 = generate_private_api_signature(*common_args, "/v1/account/assets")
    sig2 = generate_private_api_signature(*common_args, "/v1/openPositions")
    assert sig1 != sig2


def test_signature_changes_with_a_different_body():
    common_args = ("secret123", "1700000000000", "POST", "/v1/order")
    sig1 = generate_private_api_signature(*common_args, '{"side":"BUY"}')
    sig2 = generate_private_api_signature(*common_args, '{"side":"SELL"}')
    assert sig1 != sig2


def test_get_request_defaults_to_empty_body_matching_the_documented_scheme():
    with_explicit_empty = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets", "")
    with_default = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets")
    assert with_explicit_empty == with_default


def test_adapter_sign_method_delegates_to_the_module_function_with_its_own_secret():
    adapter = GmoCoinAdapter(api_key="key123", api_secret="secret123")
    via_adapter = adapter._sign("1700000000000", "GET", "/v1/account/assets")
    via_function = generate_private_api_signature("secret123", "1700000000000", "GET", "/v1/account/assets")
    assert via_adapter == via_function
