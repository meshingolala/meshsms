import pytest
from meshsms.services.ton_npi import determine_ton_npi, TON, NPI


def test_alphanumeric_sender_id():
    res = determine_ton_npi("MYBRAND", is_source=True)
    assert res.ton == TON.ALPHANUMERIC  # 5
    assert res.npi == NPI.UNKNOWN       # 0
    assert res.address_type == "alphanumeric"


def test_shortcode():
    res = determine_ton_npi("1448", is_source=True)
    assert res.ton == TON.NETWORK_SPECIFIC  # 3
    assert res.npi == NPI.UNKNOWN           # 0
    assert res.address_type == "shortcode"


def test_international_number():
    res = determine_ton_npi("+233241234567", is_source=True)
    assert res.ton == TON.INTERNATIONAL  # 1
    assert res.npi == NPI.ISDN_E164      # 1
    assert res.address_type == "international"
    assert res.cleaned_address == "233241234567"


def test_recipient_ton_npi():
    res = determine_ton_npi("+12025550143", is_source=False)
    assert res.ton == TON.INTERNATIONAL
    assert res.npi == NPI.ISDN_E164
    assert res.address_type == "international"
