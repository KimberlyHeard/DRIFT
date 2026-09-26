"""
TMP117 raw-register decoder.

Source fact: TI SNOSD82D Rev. D
  p26 §7.6.2  — 16-bit signed two's-complement, 1/128 °C per LSB (= 0.0078125 °C).
  p20 §7.5.3.1 — register bytes transferred MSB first.
  p32          — device-ID register 0x0F: lower 12 bits are 0x117; upper 4 bits are revision.

All expected values in the test suite are literal constants reviewed independently
of this module.  Never import this module to compute expected answers for tests.
"""

from __future__ import annotations

# Source: SNOSD82D p26 §7.6.2
_LSB_DEG_C: float = 0.0078125   # 1/128 degree Celsius per LSB — literal, not derived here

# Source: SNOSD82D p32
_DEVICE_ID_PART_MASK: int = 0x0FFF
_DEVICE_ID_PART_VALUE: int = 0x0117


class DecoderError(ValueError):
    """Raised when raw bytes cannot be decoded."""


def decode_temperature(raw: bytes) -> float:
    """
    Decode a two-byte MSB-first TMP117 temperature register read.

    The wire order is MSB first (F02, SNOSD82D p20 §7.5.3.1).
    The 16-bit value is signed two's-complement (F04, SNOSD82D p26 §7.6.2).
    Resolution is 1/128 °C per LSB.

    Parameters
    ----------
    raw:
        Exactly two bytes as received from the bus (high byte, low byte).

    Returns
    -------
    float
        Temperature in degrees Celsius.

    Raises
    ------
    DecoderError
        If ``raw`` is not exactly two bytes.
    """
    if len(raw) != 2:
        raise DecoderError(
            f"TMP117 temperature register requires exactly 2 bytes; got {len(raw)}"
        )
    # MSB first: reconstruct 16-bit unsigned then reinterpret as signed.
    unsigned = (raw[0] << 8) | raw[1]
    # Reinterpret as signed 16-bit two's-complement.
    signed = unsigned if unsigned < 0x8000 else unsigned - 0x10000
    return signed * _LSB_DEG_C


def decode_device_id(raw: bytes) -> tuple[int, int]:
    """
    Decode a two-byte MSB-first TMP117 device-ID register read.

    Lower 12 bits must equal 0x117 (F10, SNOSD82D p32).
    Upper 4 bits carry the silicon revision; any revision value is accepted.

    Parameters
    ----------
    raw:
        Exactly two bytes as received from the bus (high byte, low byte).

    Returns
    -------
    tuple[int, int]
        ``(part_id, revision)`` where ``part_id == 0x117`` on a genuine TMP117.

    Raises
    ------
    DecoderError
        If ``raw`` is not exactly two bytes, or if the lower 12-bit part ID
        does not equal 0x117.
    """
    if len(raw) != 2:
        raise DecoderError(
            f"TMP117 device-ID register requires exactly 2 bytes; got {len(raw)}"
        )
    unsigned = (raw[0] << 8) | raw[1]
    part_id = unsigned & _DEVICE_ID_PART_MASK
    revision = (unsigned >> 12) & 0xF
    if part_id != _DEVICE_ID_PART_VALUE:
        raise DecoderError(
            f"TMP117 device-ID part mismatch: expected 0x{_DEVICE_ID_PART_VALUE:03X}, "
            f"got 0x{part_id:03X} (raw word 0x{unsigned:04X})"
        )
    return part_id, revision
