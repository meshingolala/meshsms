import math
from dataclasses import dataclass
from typing import Literal

# GSM 03.38 7-bit default alphabet basic character set
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# GSM 03.38 7-bit extension table (escape table). Each character requires an ESC byte (0x1B) + symbol = 2 septets.
GSM7_EXTENDED = set("^{}\\[~]|€")


@dataclass(frozen=True)
class SMSMetrics:
    """Calculated metrics for an SMS text payload."""
    encoding: Literal["GSM7", "UCS2"]
    segments: int
    smpp_coding: int  # 0 for GSM 7-bit, 8 for UCS-2 (Unicode)
    character_count: int
    wire_length: int  # septets for GSM-7, characters (16-bit code units) for UCS-2
    single_max: int
    multipart_max: int


def calculate_sms_metrics(text: str) -> SMSMetrics:
    r"""
    Determines encoding (GSM7 vs UCS2) and exact segment count.
    
    Standards:
    - GSM-7:
        Single message: <= 160 septets (1 segment)
        Multipart message: > 160 septets, split into 153-septet segments (6 bytes reserved for UDH)
        Coding: 0
        Extended characters (^{}\[~]|€) consume 2 septets each.
    - UCS-2:
        Single message: <= 70 characters (1 segment)
        Multipart message: > 70 characters, split into 67-character segments
        Coding: 8
    """
    if not text:
        return SMSMetrics(
            encoding="GSM7",
            segments=1,
            smpp_coding=0,
            character_count=0,
            wire_length=0,
            single_max=160,
            multipart_max=153,
        )

    is_gsm7 = all(c in GSM7_BASIC or c in GSM7_EXTENDED for c in text)

    if is_gsm7:
        # Extended characters count as 2 septets
        septet_length = sum(2 if c in GSM7_EXTENDED else 1 for c in text)
        segments = 1 if septet_length <= 160 else math.ceil(septet_length / 153)
        return SMSMetrics(
            encoding="GSM7",
            segments=segments,
            smpp_coding=0,
            character_count=len(text),
            wire_length=septet_length,
            single_max=160,
            multipart_max=153,
        )
    else:
        char_length = len(text)
        segments = 1 if char_length <= 70 else math.ceil(char_length / 67)
        return SMSMetrics(
            encoding="UCS2",
            segments=segments,
            smpp_coding=8,
            character_count=char_length,
            wire_length=char_length,
            single_max=70,
            multipart_max=67,
        )
