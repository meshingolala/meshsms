import pytest
from meshsms.services.encoding import calculate_sms_metrics


def test_empty_string():
    m = calculate_sms_metrics("")
    assert m.encoding == "GSM7"
    assert m.segments == 1
    assert m.smpp_coding == 0


def test_single_gsm7_message():
    text = "Hello world from MeshSMS! Standard GSM 7-bit characters only."
    m = calculate_sms_metrics(text)
    assert m.encoding == "GSM7"
    assert m.segments == 1
    assert m.smpp_coding == 0
    assert m.character_count == len(text)
    assert m.wire_length == len(text)


def test_gsm7_boundary_160_chars():
    # Exactly 160 characters
    text = "A" * 160
    m = calculate_sms_metrics(text)
    assert m.encoding == "GSM7"
    assert m.segments == 1

    # 161 characters should split into 2 segments (161 / 153 = 2)
    text_161 = "A" * 161
    m2 = calculate_sms_metrics(text_161)
    assert m2.encoding == "GSM7"
    assert m2.segments == 2


def test_gsm7_extended_characters():
    # Euro symbol (€) and brackets ([]{}) take 2 septets each in GSM-7
    # 79 'A's + 1 '€' = 79 + 2 = 81 septets
    text = ("A" * 79) + "€"
    m = calculate_sms_metrics(text)
    assert m.encoding == "GSM7"
    assert m.wire_length == 81
    assert m.segments == 1

    # 159 'A's + 1 '€' = 159 + 2 = 161 septets -> exceeds 160 -> 2 segments!
    text_extended_overflow = ("A" * 159) + "€"
    m_overflow = calculate_sms_metrics(text_extended_overflow)
    assert m_overflow.encoding == "GSM7"
    assert m_overflow.wire_length == 161
    assert m_overflow.segments == 2


def test_ucs2_unicode_detection():
    # Emojis or Arabic/Cyrillic/Chinese require UCS-2 (coding=8)
    text = "Hello world! 🚀 Verification code: 1234"
    m = calculate_sms_metrics(text)
    assert m.encoding == "UCS2"
    assert m.smpp_coding == 8
    assert m.segments == 1


def test_ucs2_boundary_70_chars():
    # In UCS-2, single part is <= 70 characters
    text_70 = "🚀" + ("A" * 68)  # note: rocket is a unicode surrogate pair or char
    # Let's test standard unicode non-GSM char like accented or Cyrillic:
    cyrillic = "Привет" + ("A" * 64)  # 6 + 64 = 70 chars
    m = calculate_sms_metrics(cyrillic)
    assert m.encoding == "UCS2"
    assert m.segments == 1

    # 71 characters splits into 2 segments (71 / 67 = 2)
    cyrillic_71 = "Привет" + ("A" * 65)  # 71 chars
    m2 = calculate_sms_metrics(cyrillic_71)
    assert m2.encoding == "UCS2"
    assert m2.segments == 2
