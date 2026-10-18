import re
from dataclasses import dataclass
from enum import IntEnum


class TON(IntEnum):
    """Type of Number according to SMPP v3.4 specification."""
    UNKNOWN = 0
    INTERNATIONAL = 1
    NATIONAL = 2
    NETWORK_SPECIFIC = 3
    SUBSCRIBER_NUMBER = 4
    ALPHANUMERIC = 5
    ABBREVIATED = 6


class NPI(IntEnum):
    """Numbering Plan Indicator according to SMPP v3.4 specification."""
    UNKNOWN = 0
    ISDN_E164 = 1
    DATA = 3
    TELEX = 4
    LAND_MOBILE = 6
    NATIONAL = 8
    PRIVATE = 9
    ERMES = 10
    INTERNET = 14
    WAP_CLIENT_ID = 18


@dataclass(frozen=True)
class AddressAddressing:
    """TON and NPI resolution for a sender or recipient address."""
    address: str
    cleaned_address: str
    ton: TON
    npi: NPI
    address_type: str  # 'alphanumeric', 'international', 'shortcode', 'unknown'


def determine_ton_npi(address: str, is_source: bool = True) -> AddressAddressing:
    """
    Determines TON and NPI based on SMPP specifications.
    
    Rules:
    - Alphanumeric (e.g. "MYBRAND", contains letters): TON=5, NPI=0
    - Shortcode (e.g. 3 to 6 digits, e.g. "1448"): TON=3, NPI=0
    - International number (starts with + or 7-15 digits starting with country code): TON=1, NPI=1
    """
    trimmed = address.strip()
    cleaned = trimmed.lstrip("+")

    # If it contains letters or is clearly an alphanumeric brand
    if any(c.isalpha() for c in trimmed):
        return AddressAddressing(
            address=trimmed,
            cleaned_address=trimmed,
            ton=TON.ALPHANUMERIC,
            npi=NPI.UNKNOWN,
            address_type="alphanumeric",
        )

    # Pure numeric
    digits = re.sub(r"\D", "", trimmed)

    # Shortcode check (typically 3 to 6 digits, and usually source address)
    if is_source and 3 <= len(digits) <= 6:
        return AddressAddressing(
            address=trimmed,
            cleaned_address=digits,
            ton=TON.NETWORK_SPECIFIC,
            npi=NPI.UNKNOWN,
            address_type="shortcode",
        )

    # International phone number
    if trimmed.startswith("+") or len(digits) >= 8:
        return AddressAddressing(
            address=trimmed,
            cleaned_address=digits,
            ton=TON.INTERNATIONAL,
            npi=NPI.ISDN_E164,
            address_type="international",
        )

    # Fallback unknown
    return AddressAddressing(
        address=trimmed,
        cleaned_address=digits,
        ton=TON.UNKNOWN,
        npi=NPI.UNKNOWN,
        address_type="unknown",
    )
