"""
tests/test_decoder_tmp117.py
Task 03 — TMP117 decoder and mutation tests.

Independent oracle source:
  tests/oracles/tmp117_vectors.json
  (literal arithmetic prepared independently; never recompute from production helpers)

Arithmetic spot-checks (Task 03 review requirement):
  0C 80  =>  (0x0C80 = 3200)  * (1/128) = 25.0 °C
  FF 80  =>  (0xFF80 = 65408) - 65536 = -128  * (1/128) = -1.0 °C

Source facts cited:
  F02: SNOSD82D p20 §7.5.3.1 — MSB first
  F04: SNOSD82D p26 §7.6.2   — signed 16-bit two's-complement, 1/128 °C per LSB
  F10: SNOSD82D p32           — lower 12 bits of device-ID register = 0x117
"""

from __future__ import annotations

import pytest

from drift.decoders.tmp117 import DecoderError, decode_device_id, decode_temperature

# ---------------------------------------------------------------------------
# Literal oracle vectors — from tests/oracles/tmp117_vectors.json
# These are not generated or computed; they are the independent ground truth.
# ---------------------------------------------------------------------------

# Each entry: (test_id, high_byte, low_byte, expected_signed_integer, expected_celsius)
_TEMPERATURE_VECTORS: list[tuple[str, int, int, int, float]] = [
    # id           HB    LB    signed     °C
    ("zero",       0x00, 0x00,      0,   0.0),
    ("room",       0x0C, 0x80,   3200,  25.0),
    ("negative_one",  0xFF, 0x80, -128,  -1.0),
    ("negative_25",   0xF3, 0x80, -3200, -25.0),
    ("positive_lsb",  0x00, 0x01,    1,   0.0078125),
    ("negative_lsb",  0xFF, 0xFF,   -1,  -0.0078125),
    ("low",        0xE4, 0x80, -7040, -55.0),
    ("high",       0x4B, 0x00, 19200, 150.0),
]

# Reset word — 0x8000; arithmetic value computed independently:
# 0x8000 = 32768 unsigned; 32768 - 65536 = -32768 signed; -32768/128 = -256.0 °C
# (Not a valid new measurement; tested separately as arithmetic correctness only.)
_RESET_WORD_HB = 0x80
_RESET_WORD_LB = 0x00
_RESET_WORD_CELSIUS: float = -256.0   # literal from oracle reset_word entry


# ---------------------------------------------------------------------------
# T01–T08: Temperature decode — all eight oracle vectors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vec_id, hb, lb, signed_int, expected_c", _TEMPERATURE_VECTORS)
def test_temperature_decode_oracle_vectors(
    vec_id: str, hb: int, lb: int, signed_int: int, expected_c: float
) -> None:
    """
    T01–T08 — Each of the eight oracle vectors must decode to the literal expected value.
    Expected answers are taken verbatim from tests/oracles/tmp117_vectors.json.
    """
    raw = bytes([hb, lb])
    result = decode_temperature(raw)
    assert result == pytest.approx(expected_c, abs=1e-9), (
        f"vector '{vec_id}': bytes=[{hb:#04x},{lb:#04x}] "
        f"expected {expected_c} °C, got {result} °C"
    )


# ---------------------------------------------------------------------------
# T09: Reset word — arithmetic correctness; not a valid measurement sentinel
# ---------------------------------------------------------------------------

def test_temperature_reset_word_arithmetic() -> None:
    """
    T09 — 0x8000 decodes arithmetically to -256.0 °C.
    The oracle notes this is not a completed new measurement; this test checks
    only that the decoder is arithmetically correct for this bit pattern.
    """
    raw = bytes([_RESET_WORD_HB, _RESET_WORD_LB])
    result = decode_temperature(raw)
    assert result == pytest.approx(_RESET_WORD_CELSIUS, abs=1e-9), (
        f"reset word 0x8000: expected {_RESET_WORD_CELSIUS} °C, got {result} °C"
    )


# ---------------------------------------------------------------------------
# T10–T12: Invalid byte lengths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_bytes", [
    b"",          # length 0
    b"\x0C",      # length 1
    b"\x0C\x80\x00",  # length 3
])
def test_temperature_invalid_length_raises(bad_bytes: bytes) -> None:
    """T10–T12 — Lengths other than 2 must raise DecoderError."""
    with pytest.raises(DecoderError):
        decode_temperature(bad_bytes)


# ---------------------------------------------------------------------------
# T13–T16: Device-ID — valid IDs with different revision nibbles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rev, word", [
    (0x0, 0x0117),  # revision 0 — part 0x117
    (0x1, 0x1117),  # revision 1
    (0xA, 0xA117),  # revision 10
    (0xF, 0xF117),  # revision 15 (max)
])
def test_device_id_valid_all_revisions(rev: int, word: int) -> None:
    """T13–T16 — Any revision nibble with part 0x117 must be accepted."""
    hb = (word >> 8) & 0xFF
    lb = word & 0xFF
    part_id, revision = decode_device_id(bytes([hb, lb]))
    assert part_id == 0x117, f"part_id mismatch: {part_id:#05x}"
    assert revision == rev, f"revision mismatch: {revision} vs {rev}"


# ---------------------------------------------------------------------------
# T17: Device-ID — wrong lower 12 bits must be rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_word", [
    0x0116,  # off by one low
    0x0118,  # off by one high
    0x0000,  # all zeros
    0x0FFF,  # all part bits set
    0x1118,  # wrong part, different revision
])
def test_device_id_wrong_part_raises(bad_word: int) -> None:
    """T17 — Any word whose lower 12 bits differ from 0x117 must raise DecoderError."""
    hb = (bad_word >> 8) & 0xFF
    lb = bad_word & 0xFF
    with pytest.raises(DecoderError):
        decode_device_id(bytes([hb, lb]))


# ---------------------------------------------------------------------------
# T18–T19: Device-ID invalid byte lengths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_bytes", [b"", b"\x01\x17\x00"])
def test_device_id_invalid_length_raises(bad_bytes: bytes) -> None:
    """T18–T19 — Lengths other than 2 must raise DecoderError."""
    with pytest.raises(DecoderError):
        decode_device_id(bad_bytes)


# ===========================================================================
# MUTATION TESTS
# These sections contain DELIBERATE DEFECTS clearly labeled as such.
# They prove that specific incorrect implementations produce wrong answers
# for the oracle vectors, and that the correct decoder does NOT fail.
# ===========================================================================

# ---------------------------------------------------------------------------
# Deliberate defect 1: BYTE-SWAP — reads bytes LSB first instead of MSB first.
# Source violation: ignores F02 (SNOSD82D p20 §7.5.3.1).
# ---------------------------------------------------------------------------

def _decode_temperature_byteswap_DEFECT(raw: bytes) -> float:
    """
    DELIBERATE DEFECT — byte-swap mutant.
    Treats the wire bytes as LSB-first instead of MSB-first.
    This is intentionally wrong; it is labelled a defect.
    """
    if len(raw) != 2:
        raise DecoderError(f"requires 2 bytes; got {len(raw)}")
    # BUG: swaps byte order — low byte in high position
    unsigned = (raw[1] << 8) | raw[0]
    signed = unsigned if unsigned < 0x8000 else unsigned - 0x10000
    return signed * 0.0078125


def test_byteswap_defect_fails_room_vector() -> None:
    """
    TM01 — Byte-swap mutant produces wrong result for 'room' vector (0C 80 → 25.0 °C).
    The defect decodes 0x800C = -32756/128 = -255.953125 °C instead of 25.0 °C.
    Proves this defect is detectable by the oracle assertions.
    """
    raw = bytes([0x0C, 0x80])
    correct_celsius: float = 25.0            # literal oracle value
    defect_result = _decode_temperature_byteswap_DEFECT(raw)
    # The defect must NOT equal the correct answer.
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Byte-swap defect unexpectedly produced the correct answer — "
        "mutation test is not effective for this vector."
    )
    # The correct decoder DOES produce the right answer.
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)


def test_byteswap_defect_fails_negative_one_vector() -> None:
    """
    TM02 — Byte-swap mutant produces wrong result for 'negative_one' vector (FF 80 → -1.0 °C).
    The defect decodes 0x80FF = -32513/128 = -254.0078125 °C instead of -1.0 °C.
    """
    raw = bytes([0xFF, 0x80])
    correct_celsius: float = -1.0            # literal oracle value
    defect_result = _decode_temperature_byteswap_DEFECT(raw)
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Byte-swap defect unexpectedly produced the correct answer."
    )
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)


def test_byteswap_defect_fails_high_vector() -> None:
    """
    TM03 — Byte-swap mutant for 'high' vector (4B 00 → 150.0 °C).
    The defect decodes 0x004B = 75 → 75/128 = 0.5859375 °C instead of 150.0 °C.
    """
    raw = bytes([0x4B, 0x00])
    correct_celsius: float = 150.0           # literal oracle value
    defect_result = _decode_temperature_byteswap_DEFECT(raw)
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Byte-swap defect unexpectedly produced the correct answer."
    )
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)


# ---------------------------------------------------------------------------
# Deliberate defect 2: UNSIGNED — treats the 16-bit value as unsigned (no sign extension).
# Source violation: ignores F04 two's-complement requirement (SNOSD82D p26 §7.6.2).
# ---------------------------------------------------------------------------

def _decode_temperature_unsigned_DEFECT(raw: bytes) -> float:
    """
    DELIBERATE DEFECT — unsigned (missing sign extension) mutant.
    Treats the reconstructed 16-bit value as unsigned, never applying two's-complement.
    This is intentionally wrong; it is labelled a defect.
    """
    if len(raw) != 2:
        raise DecoderError(f"requires 2 bytes; got {len(raw)}")
    unsigned = (raw[0] << 8) | raw[1]
    # BUG: no sign extension — uses unsigned directly
    return unsigned * 0.0078125


def test_unsigned_defect_fails_negative_one_vector() -> None:
    """
    TM04 — Unsigned mutant produces wrong result for 'negative_one' vector (FF 80 → -1.0 °C).
    The defect returns 0xFF80 * 1/128 = 65408/128 = 511.0 °C instead of -1.0 °C.
    Proves the sign-extension path is tested by the oracle.
    """
    raw = bytes([0xFF, 0x80])
    correct_celsius: float = -1.0            # literal oracle value
    defect_result = _decode_temperature_unsigned_DEFECT(raw)
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Unsigned defect unexpectedly produced the correct answer — "
        "mutation test is not effective for this vector."
    )
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)


def test_unsigned_defect_fails_negative_25_vector() -> None:
    """
    TM05 — Unsigned mutant for 'negative_25' vector (F3 80 → -25.0 °C).
    The defect returns 0xF380/128 = 62336/128 = 487.0 °C instead of -25.0 °C.
    """
    raw = bytes([0xF3, 0x80])
    correct_celsius: float = -25.0           # literal oracle value
    defect_result = _decode_temperature_unsigned_DEFECT(raw)
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Unsigned defect unexpectedly produced the correct answer."
    )
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)


def test_unsigned_defect_fails_negative_lsb_vector() -> None:
    """
    TM06 — Unsigned mutant for 'negative_lsb' vector (FF FF → -0.0078125 °C).
    The defect returns 0xFFFF/128 = 65535/128 = 511.9921875 °C instead.
    """
    raw = bytes([0xFF, 0xFF])
    correct_celsius: float = -0.0078125      # literal oracle value
    defect_result = _decode_temperature_unsigned_DEFECT(raw)
    assert defect_result != pytest.approx(correct_celsius, abs=1e-9), (
        "Unsigned defect unexpectedly produced the correct answer."
    )
    assert decode_temperature(raw) == pytest.approx(correct_celsius, abs=1e-9)
