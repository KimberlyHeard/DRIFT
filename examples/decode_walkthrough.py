"""Educational arithmetic only: not a driver, simulator, or completed DRIFT run."""
import json
from pathlib import Path


def decode(raw):
    if len(raw) != 2:
        raise ValueError("Expected exactly two temperature bytes")
    return int.from_bytes(raw, byteorder="big", signed=True) / 128


def main():
    path = Path(__file__).resolve().parents[1] / "tests/oracles/tmp117_vectors.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))["vectors"]
    print("Educational arithmetic demonstration. Contract/oracles still require human review.")
    for vector in vectors:
        raw = bytes.fromhex(vector["bytes_hex"])
        actual = decode(raw)
        if actual != vector["expected_celsius"]:
            raise AssertionError(f"{vector['id']}: {actual} != {vector['expected_celsius']}")
        print(f"{vector['bytes_hex']:5s} -> {actual:11g} C  OK")
    print(f"{len(vectors)} literal arithmetic expectations passed.")
    swapped = int.from_bytes(bytes.fromhex("0C 80"), "little", signed=True) / 128
    unsigned = int.from_bytes(bytes.fromhex("FF 80"), "big", signed=False) / 128
    if swapped == 25 or unsigned == -1:
        raise AssertionError("A deliberately wrong decoder was not detected")
    print(f"Byte-swap mutant: {swapped} C vs expected 25 C -> CAUGHT")
    print(f"Unsigned mutant: {unsigned} C vs expected -1 C -> CAUGHT")
    print("Next: have Bob build the production decoder and independent project tests.")


if __name__ == "__main__":
    main()
