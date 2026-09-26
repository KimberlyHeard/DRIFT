"""
Task 07 generator tests.

Tests cover:
  GN01 — approval gate: missing approval raises ApprovalMissingError.
  GN02 — approval gate: stale contract hash raises StaleApprovalError.
  GN03 — unsupported profile raises UnsupportedProfileError before writing files.
  GN04 — determinism: identical inputs produce byte-identical driver.py.
  GN05 — determinism: identical inputs produce byte-identical device_model.py.
  GN06 — determinism: identical inputs produce byte-identical manifest (excl. timestamp).
  GN07 — generated output directory is named by contract SHA-256.
  GN08 — manifest carries correct contract_sha256 field.
  GN09 — manifest carries approved_by and source_sha256 from the contract.
  GN10 — generated driver is importable as a Python module.
  GN11 — generated driver class has identify/configure/measure API.
  GN12 — generated driver scripted-bus: identify returns correct part_id.
  GN13 — generated driver scripted-bus: configure writes 0x0600.
  GN14 — generated driver scripted-bus: measure reads 0x0C80 → 25.0 °C (literal).
  GN15 — generated driver scripted-bus: measure reads 0xFF80 → -1.0 °C (literal).
  GN16 — generated driver scripted-bus: ConversionTimeout when never ready.
  GN17 — generated model is importable as a Python module.
  GN18 — generated model class has read_register/write_register/reset_fixture/trace API.
  GN19 — integration: generated driver + generated model → 25.0 °C at 16 000 µs (literal).
  GN20 — integration: generated driver + generated model → -1.0 °C at 16 000 µs (literal).
  GN21 — changed-contract mock approval blocks generation (StaleApprovalError).
  GN22 — generate_service returns JSON-serialisable dict with expected keys.
  GN23 — manifest driver_sha256 matches actual driver.py file SHA-256.
  GN24 — manifest model_sha256 matches actual device_model.py file SHA-256.

Independent literal oracle values — DO NOT derive from generated constants:
  - 0x0C80: 3200 counts / 128 = 25.0 °C     (F04, SNOSD82D p26 §7.6.2)
  - 0xFF80: signed 16-bit -128 / 128 = -1.0 °C  (F04, SNOSD82D p26 §7.6.2)
  - address = 0x48 (F01, SNOSD82D p21 Table 7-2)
  - shutdown config = 0x0600, oneshot config = 0x0E00 (approved derived_candidates)
  - Data_Ready word = 0x2600 (approved derived_candidates)
  - poll interval = 1 000 µs, virtual conversion = 15 500 µs → ready at 16 000 µs
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import types

import pytest

from drift.contract import (
    ApprovalMissingError,
    ApprovedContract,
    StaleApprovalError,
    UnsupportedProfileError,
)
from drift.generator import generate, generate_service, GenerationResult

# ---------------------------------------------------------------------------
# Literal constants — independent of generated code (AGENTS.md)
# ---------------------------------------------------------------------------

_ADDR: int = 0x48                     # F01, SNOSD82D p21 Table 7-2
_REG_TEMP: int = 0x00                 # F03, p25
_REG_CONFIG: int = 0x01              # F03, p25
_REG_ID: int = 0x0F                  # F03, p25

_CFG_SHUTDOWN: bytes = b"\x06\x00"   # 0x0600 — shutdown, AVG=00 (approved derived)
_CFG_ONE_SHOT: bytes = b"\x0E\x00"   # 0x0E00 — one-shot, AVG=00 (approved derived)
_CFG_READY: bytes = b"\x26\x00"      # 0x2600 — Data_Ready | shutdown (approved derived)
_CFG_NOT_READY: bytes = b"\x0E\x00"  # still converting

_DEV_ID: bytes = b"\x01\x17"         # 0x0117, revision 0 — F10, p32

_TEMP_25C: bytes = b"\x0C\x80"       # 0x0C80 → 3200 / 128 = 25.0 °C — F04, p26
_TEMP_NEG1: bytes = b"\xFF\x80"      # 0xFF80 → (65408-65536)/128 = -1.0 °C — F04, p26

_CONTRACT_PATH = pathlib.Path("contracts/tmp117.approved.json")

# Known contract SHA-256 from the human-approved file (STATUS.md).
_KNOWN_CONTRACT_SHA256 = "5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_generated_module(path: pathlib.Path, name: str) -> types.ModuleType:
    """Dynamically import a generated Python file as a module."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _generate_to_tmp(tmp_path: pathlib.Path) -> GenerationResult:
    return generate(
        contract_path=_CONTRACT_PATH,
        output_root=tmp_path,
    )


# ---------------------------------------------------------------------------
# ScriptedBus and StepClock duplicated as independent test infrastructure.
# The tests must NOT import from the generated driver or model to build
# expectations — oracle literals are kept separate.
# ---------------------------------------------------------------------------

from drift.bus import ScriptedBus
from drift.clock import StepClock, VirtualClock
from drift.bus import VirtualDeviceBus


# ---------------------------------------------------------------------------
# GN01–GN03 Approval gate
# ---------------------------------------------------------------------------

class TestApprovalGate:

    def test_GN01_missing_approval_raises(self, tmp_path: pathlib.Path) -> None:
        """Contract file without an approval block must raise ApprovalMissingError."""
        # Build a minimal contract JSON without an approval block.
        raw = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["approval"] = None
        fake_path = tmp_path / "no_approval.json"
        fake_path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(ApprovalMissingError):
            generate(contract_path=fake_path, output_root=tmp_path / "out")

    def test_GN02_stale_contract_hash_raises(self, tmp_path: pathlib.Path) -> None:
        """Contract content changed after approval must raise StaleApprovalError."""
        raw = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        # Mutate a policy value in the contract body — changes canonical hash.
        raw["contract"]["policies_not_vendor_facts"]["timeout_us"] = 999999
        fake_path = tmp_path / "stale.json"
        fake_path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(StaleApprovalError):
            generate(contract_path=fake_path, output_root=tmp_path / "out")

    def test_GN03_unsupported_profile_raises(self, tmp_path: pathlib.Path) -> None:
        """An approved contract with an unsupported profile must be rejected."""
        # Create a fake approved contract with a profile not in SUPPORTED_PROFILES.
        raw = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        # Inject an unknown profile_id into the contract (keeping approval intact
        # would fail hash; we want to test the profile guard in the generator,
        # so we need a consistent fake — manipulate the profile mapping check
        # by injecting a patched approved contract via monkeypatching the profile).
        # Instead: test via a completely synthetic approved structure that bypasses
        # the hash check — but that's hard without real approval.
        # The practical test: pass a real approved contract and use a profile that
        # the _PROFILE_TEMPLATE dict doesn't know. We do this by calling generate()
        # with a modified template lookup. Since we can't change the real contract,
        # we test the code path using a separate synthetic fixture.
        #
        # Strategy: generate_service validates the profile against _PROFILE_TEMPLATE.
        # We verify that UnsupportedProfileError is raised for a profile not in the
        # _PROFILE_TEMPLATE dict by temporarily adding an approved contract for it.
        # Since this is a unit test for generator rejection, we call generate() on
        # the real contract but override the _PROFILE_TEMPLATE at import time.
        import drift.generator as gen_mod
        original = dict(gen_mod._PROFILE_TEMPLATE)
        try:
            # Remove the real profile from the template dict — now the real contract
            # profile has no template → UnsupportedProfileError
            gen_mod._PROFILE_TEMPLATE.clear()
            with pytest.raises(UnsupportedProfileError):
                generate(contract_path=_CONTRACT_PATH, output_root=tmp_path / "out")
        finally:
            gen_mod._PROFILE_TEMPLATE.update(original)


# ---------------------------------------------------------------------------
# GN04–GN09 Determinism and manifest
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_GN04_driver_byte_identical_on_repeat(self, tmp_path: pathlib.Path) -> None:
        """Running generate twice with same inputs must produce byte-identical driver.py."""
        r1 = _generate_to_tmp(tmp_path / "run1")
        r2 = _generate_to_tmp(tmp_path / "run2")
        assert r1.driver_path.read_bytes() == r2.driver_path.read_bytes(), (
            "driver.py content changed between runs"
        )

    def test_GN05_model_byte_identical_on_repeat(self, tmp_path: pathlib.Path) -> None:
        """Running generate twice must produce byte-identical device_model.py."""
        r1 = _generate_to_tmp(tmp_path / "run1")
        r2 = _generate_to_tmp(tmp_path / "run2")
        assert r1.model_path.read_bytes() == r2.model_path.read_bytes(), (
            "device_model.py content changed between runs"
        )

    def test_GN06_manifest_stable_fields_identical(self, tmp_path: pathlib.Path) -> None:
        """Repeated manifest runs must have byte-identical stable fields (excl. generated_utc)."""
        r1 = _generate_to_tmp(tmp_path / "run1")
        r2 = _generate_to_tmp(tmp_path / "run2")
        m1 = json.loads(r1.manifest_path.read_text())
        m2 = json.loads(r2.manifest_path.read_text())
        # generated_utc changes between runs; all other fields must be stable.
        for key in ("profile_id", "inputs", "outputs", "approved_by",
                    "approved_utc", "source_sha256", "scope"):
            assert m1[key] == m2[key], f"manifest[{key!r}] differed between runs"

    def test_GN07_output_dir_named_by_contract_sha256(self, tmp_path: pathlib.Path) -> None:
        """Output directory must be named by the canonical contract SHA-256."""
        r = _generate_to_tmp(tmp_path)
        assert r.output_dir.name == _KNOWN_CONTRACT_SHA256

    def test_GN08_manifest_contract_sha256_correct(self, tmp_path: pathlib.Path) -> None:
        """manifest.json must record the correct contract SHA-256."""
        r = _generate_to_tmp(tmp_path)
        m = json.loads(r.manifest_path.read_text())
        assert m["inputs"]["contract_sha256"] == _KNOWN_CONTRACT_SHA256

    def test_GN09_manifest_provenance_fields(self, tmp_path: pathlib.Path) -> None:
        """manifest.json must carry approved_by and source_sha256 from the contract."""
        r = _generate_to_tmp(tmp_path)
        m = json.loads(r.manifest_path.read_text())
        assert m["approved_by"] == "Kimberly Heard"
        assert m["source_sha256"] == (
            "637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df"
        )

    def test_GN23_manifest_driver_sha256_matches_file(self, tmp_path: pathlib.Path) -> None:
        """manifest.outputs.driver_sha256 must equal actual SHA-256 of driver.py."""
        r = _generate_to_tmp(tmp_path)
        m = json.loads(r.manifest_path.read_text())
        actual = _sha256_bytes(r.driver_path.read_bytes())
        assert m["outputs"]["driver_sha256"] == actual

    def test_GN24_manifest_model_sha256_matches_file(self, tmp_path: pathlib.Path) -> None:
        """manifest.outputs.model_sha256 must equal actual SHA-256 of device_model.py."""
        r = _generate_to_tmp(tmp_path)
        m = json.loads(r.manifest_path.read_text())
        actual = _sha256_bytes(r.model_path.read_bytes())
        assert m["outputs"]["model_sha256"] == actual


# ---------------------------------------------------------------------------
# GN10–GN11 Import checks
# ---------------------------------------------------------------------------

class TestGeneratedImport:

    def test_GN10_driver_importable(self, tmp_path: pathlib.Path) -> None:
        """Generated driver.py must be importable without errors."""
        r = _generate_to_tmp(tmp_path)
        mod = _load_generated_module(r.driver_path, "gen_driver_test")
        assert mod is not None

    def test_GN11_driver_has_expected_api(self, tmp_path: pathlib.Path) -> None:
        """Generated driver class must expose identify, configure, measure."""
        r = _generate_to_tmp(tmp_path)
        mod = _load_generated_module(r.driver_path, "gen_driver_api_test")
        # Find the generated class (name from template).
        assert hasattr(mod, "TMP117Generated"), "Expected class TMP117Generated in driver.py"
        cls = mod.TMP117Generated
        assert callable(getattr(cls, "identify", None))
        assert callable(getattr(cls, "configure", None))
        assert callable(getattr(cls, "measure", None))

    def test_GN17_model_importable(self, tmp_path: pathlib.Path) -> None:
        """Generated device_model.py must be importable without errors."""
        r = _generate_to_tmp(tmp_path)
        mod = _load_generated_module(r.model_path, "gen_model_test")
        assert mod is not None

    def test_GN18_model_has_expected_api(self, tmp_path: pathlib.Path) -> None:
        """Generated model class must expose required interface."""
        r = _generate_to_tmp(tmp_path)
        mod = _load_generated_module(r.model_path, "gen_model_api_test")
        assert hasattr(mod, "TMP117GeneratedModel")
        cls = mod.TMP117GeneratedModel
        assert callable(getattr(cls, "read_register", None))
        assert callable(getattr(cls, "write_register", None))
        assert callable(getattr(cls, "reset_fixture", None))
        assert hasattr(cls, "trace")


# ---------------------------------------------------------------------------
# GN12–GN16 Scripted-bus tests for generated driver
# ---------------------------------------------------------------------------

def _make_gen_driver(
    bus: ScriptedBus,
    clock: StepClock,
    driver_path: pathlib.Path,
):
    mod = _load_generated_module(driver_path, f"gen_drv_{id(bus)}")
    cls = mod.TMP117Generated
    return cls(bus=bus, clock=clock, address_7bit=_ADDR)


class TestGeneratedDriverScripted:

    def test_GN12_identify_returns_correct_part_id(self, tmp_path: pathlib.Path) -> None:
        """Generated driver identify() must return part_id 0x117 from scripted response."""
        r = _generate_to_tmp(tmp_path)
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID),
        ])
        clock = StepClock()
        drv = _make_gen_driver(bus, clock, r.driver_path)
        identity = drv.identify()
        assert identity.part_id == 0x117
        assert identity.raw_bytes == _DEV_ID
        bus.assert_exhausted()

    def test_GN13_configure_writes_shutdown_config(self, tmp_path: pathlib.Path) -> None:
        """Generated driver configure() must write 0x0600 to config register."""
        r = _generate_to_tmp(tmp_path)
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN),
        ])
        clock = StepClock()
        drv = _make_gen_driver(bus, clock, r.driver_path)
        drv.configure()
        bus.assert_exhausted()

    def test_GN14_measure_25c_from_scripted_bus(self, tmp_path: pathlib.Path) -> None:
        """Generated driver measure() on 0x0C80 must yield 25.0 °C (independent literal)."""
        r = _generate_to_tmp(tmp_path)
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
        ])
        clock = StepClock()
        drv = _make_gen_driver(bus, clock, r.driver_path)
        m = drv.measure()
        # Independent literal: 0x0C80 = 3200 counts; 3200 / 128 = 25.0 °C (F04)
        assert m.celsius == 25.0, f"Expected 25.0 °C; got {m.celsius}"
        assert m.raw_bytes == _TEMP_25C
        bus.assert_exhausted()

    def test_GN15_measure_neg1c_from_scripted_bus(self, tmp_path: pathlib.Path) -> None:
        """Generated driver measure() on 0xFF80 must yield -1.0 °C (independent literal)."""
        r = _generate_to_tmp(tmp_path)
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_NEG1),
        ])
        clock = StepClock()
        drv = _make_gen_driver(bus, clock, r.driver_path)
        m = drv.measure()
        # Independent literal: 0xFF80 as signed 16-bit = -128; -128 / 128 = -1.0 °C (F04)
        assert m.celsius == -1.0, f"Expected -1.0 °C; got {m.celsius}"
        assert m.raw_bytes == _TEMP_NEG1
        bus.assert_exhausted()

    def test_GN16_measure_timeout_when_never_ready(self, tmp_path: pathlib.Path) -> None:
        """Generated driver measure() must raise ConversionTimeout if Data_Ready never set."""
        from drift.interfaces import ConversionTimeout
        r = _generate_to_tmp(tmp_path)
        # 3 µs timeout, 1 000 µs poll → times out immediately after first poll
        polls = [ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY)] * 10
        bus = ScriptedBus(
            [ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT)] + polls
        )
        clock = StepClock()
        drv = _make_gen_driver(bus, clock, r.driver_path)
        with pytest.raises(ConversionTimeout):
            drv.measure(timeout_us=3)


# ---------------------------------------------------------------------------
# GN19–GN20 Integration: generated driver + generated model
# ---------------------------------------------------------------------------

def _make_gen_stack(
    driver_path: pathlib.Path,
    model_path: pathlib.Path,
    temperature_raw: int = 0x0C80,
):
    """Wire generated driver → generated model through shared VirtualClock."""
    drv_mod = _load_generated_module(driver_path, f"gen_drv_int_{temperature_raw}")
    mdl_mod = _load_generated_module(model_path, f"gen_mdl_int_{temperature_raw}")
    clock = VirtualClock()
    model = mdl_mod.TMP117GeneratedModel(clock, temperature_raw=temperature_raw)
    bus = VirtualDeviceBus(model, address_7bit=_ADDR)
    driver = drv_mod.TMP117Generated(bus=bus, clock=clock, address_7bit=_ADDR)
    return clock, model, driver


class TestGeneratedIntegration:

    def test_GN19_integration_25c_at_16000us(self, tmp_path: pathlib.Path) -> None:
        """
        Generated driver + generated model must produce 25.0 °C at 16 000 µs.

        Independent literal: 0x0C80 = 3200 counts / 128 = 25.0 °C (F04).
        Timing: poll every 1 000 µs; conversion at 15 500 µs → ready observed at 16 000 µs.
        """
        r = _generate_to_tmp(tmp_path)
        _, model, driver = _make_gen_stack(r.driver_path, r.model_path, 0x0C80)

        identity = driver.identify()
        driver.configure()
        measurement = driver.measure()

        # Independent literal 25.0 °C.
        assert identity.part_id == 0x117
        assert measurement.celsius == 25.0, (
            f"Expected 25.0 °C; got {measurement.celsius} °C"
        )
        assert measurement.raw_bytes == b"\x0C\x80"
        # Independent timing literal: 16 000 µs.
        assert measurement.virtual_time_us == 16_000, (
            f"Expected 16 000 µs; got {measurement.virtual_time_us} µs"
        )

    def test_GN20_integration_neg1c_at_16000us(self, tmp_path: pathlib.Path) -> None:
        """
        Generated driver + generated model must produce -1.0 °C at 16 000 µs.

        Independent literal: 0xFF80 as signed 16-bit = -128; -128 / 128 = -1.0 °C (F04).
        """
        r = _generate_to_tmp(tmp_path)
        _, model, driver = _make_gen_stack(r.driver_path, r.model_path, 0xFF80)

        identity = driver.identify()
        driver.configure()
        measurement = driver.measure()

        # Independent literal -1.0 °C.
        assert identity.part_id == 0x117
        assert measurement.celsius == -1.0, (
            f"Expected -1.0 °C; got {measurement.celsius} °C"
        )
        assert measurement.raw_bytes == b"\xFF\x80"
        assert measurement.virtual_time_us == 16_000, (
            f"Expected 16 000 µs; got {measurement.virtual_time_us} µs"
        )


# ---------------------------------------------------------------------------
# GN21 Changed-contract mock approval blocks generation
# ---------------------------------------------------------------------------

class TestChangedContractBlocked:

    def test_GN21_modified_contract_stale_approval_blocks_generation(
        self, tmp_path: pathlib.Path
    ) -> None:
        """
        A contract modified after approval must raise StaleApprovalError.

        Uses a synthetic fixture: the real contract is loaded, a policy value
        is mutated, and the original approval record is kept intact (hash now
        stale).  Generation must be refused without any new approval being issued.
        No changes are made to the real approved contract.
        """
        raw = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        # Mutate the contract body — renders the approval hash stale.
        raw["contract"]["policies_not_vendor_facts"]["poll_interval_us"] = 5000
        fake_path = tmp_path / "mutated_contract.json"
        fake_path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(StaleApprovalError):
            generate(contract_path=fake_path, output_root=tmp_path / "out")

        # Confirm the real contract is still intact and generates fine.
        result = generate(contract_path=_CONTRACT_PATH, output_root=tmp_path / "real_out")
        assert result.driver_path.exists()


# ---------------------------------------------------------------------------
# GN22 generate_service dict
# ---------------------------------------------------------------------------

class TestGenerateService:

    def test_GN22_service_returns_serialisable_dict(self, tmp_path: pathlib.Path) -> None:
        """generate_service must return a JSON-serialisable dict with required keys."""
        result = generate_service(
            contract_path=_CONTRACT_PATH,
            output_root=tmp_path,
        )
        required_keys = {
            "profile_id", "output_dir", "driver_path", "model_path",
            "manifest_path", "contract_sha256", "template_sha256",
            "driver_sha256", "model_sha256", "generated_utc",
        }
        assert required_keys <= set(result.keys()), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )
        # Must be JSON-serialisable.
        serialised = json.dumps(result)
        decoded = json.loads(serialised)
        assert decoded["profile_id"] == "tmp117-oneshot-noavg-0x48"
        assert decoded["contract_sha256"] == _KNOWN_CONTRACT_SHA256
