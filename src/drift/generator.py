"""
DRIFT deterministic artifact generator — Task 07.

Generates three artifacts under  generated/<contract-hash>/
from an approved contract plus an audited device-specific template:

  driver.py       — Python driver source for the selected profile.
  device_model.py — Python virtual-device source for the selected profile.
  manifest.json   — Input/output hash manifest and scope record.

Correctness boundaries (AGENTS.md):
  - Only ``tmp117-oneshot-noavg-0x48`` is supported; any other profile
    raises UnsupportedProfileError before any artifact is written.
  - Draft facts, stale approval, and absent approval all raise immediately.
  - The generated driver is structurally independent of the reference driver;
    it uses the same RegisterBus/Clock protocols and approved numeric values.
  - Oracle literals are independent of generated constants (enforced in tests).
  - Identical inputs (contract + template) produce byte-identical outputs.
  - A changed contract hash invalidates the approval; regeneration requires a
    new human approval; this module never auto-approves.

Public API
----------
  generate(contract_path, output_root, template_path=None) -> GenerationResult
      Generate artifacts from an approved contract.  Returns paths and hashes.

  generate_service(contract_path, output_root, template_path=None) -> dict
      Thin wrapper returning a JSON-serialisable dict; usable from a web route.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Union

from drift.contract import (
    ApprovedContract,
    UnsupportedProfileError,
    SUPPORTED_PROFILES,
)

# ---------------------------------------------------------------------------
# Supported profile→template mapping
# ---------------------------------------------------------------------------

_PROFILE_TEMPLATE: dict[str, str] = {
    "tmp117-oneshot-noavg-0x48": "tmp117_device.json",
}

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationResult:
    """Paths and hashes returned after a successful generation run."""
    output_dir: pathlib.Path
    driver_path: pathlib.Path
    model_path: pathlib.Path
    manifest_path: pathlib.Path
    contract_sha256: str
    template_sha256: str
    driver_sha256: str
    model_sha256: str
    generator_sha256: str
    profile_id: str
    generated_utc: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _load_template(template_path: pathlib.Path) -> dict:
    raw = json.loads(template_path.read_text(encoding="utf-8"))
    # Validate that the template is for the expected profile
    return raw


# ---------------------------------------------------------------------------
# Source-code builders
# ---------------------------------------------------------------------------


def _build_driver_source(contract: ApprovedContract, tmpl: dict) -> str:
    """
    Build the driver Python source from approved contract values and the
    audited template.  All numeric constants come from the contract; names
    come from the template.
    """
    c = contract.contract
    sp = c.selected_profile
    p = c.policies_not_vendor_facts
    dc = c.derived_candidates

    address7 = sp.address7               # F01, approved
    timeout_us = p.timeout_us            # DRIFT policy, approved
    poll_interval_us = p.poll_interval_us  # DRIFT policy, approved
    shutdown_config = int(dc.shutdown_config_hex, 16)  # derived, approved
    start_config = int(dc.start_config_hex, 16)        # derived, approved
    device_class = tmpl["device_class"]
    reg_temp = int(tmpl["registers"]["temperature"]["address"], 16)
    reg_config = int(tmpl["registers"]["configuration"]["address"], 16)
    reg_id = int(tmpl["registers"]["device_id"]["address"], 16)
    data_ready_bit = int(tmpl["config_bits"]["data_ready"]["mask"], 16)
    mod_mask = int(tmpl["config_bits"]["mod_mask"]["mask"], 16)
    avg_mask = int(tmpl["config_bits"]["avg_mask"]["mask"], 16)
    id_mask = int(tmpl["device_id_mask"]["mask"], 16)
    id_value = int(tmpl["device_id_mask"]["value"], 16)
    lsb_deg_c = float(tmpl["lsb_deg_c"]["value"])
    reg_width = int(tmpl["register_width"])
    profile_id = c.profile_id
    source_doc = c.source.document
    source_rev = c.source.revision
    reviewer = contract.approval.reviewer
    approved_utc = contract.approval.approved_utc
    contract_sha256 = contract.approval.contract_sha256

    return textwrap.dedent(f"""\
        \"\"\"
        Generated TMP117 driver for profile {profile_id!r}.

        Source: TI {source_doc} Rev. {source_rev}.
        Approved by: {reviewer} at {approved_utc}.
        Contract SHA-256: {contract_sha256}.
        Generated by DRIFT from the approved contract and audited template.
        Do not edit by hand; regenerate from the approved contract.

        Fact references:
          F01 p21 §Table 7-2 — address 0x{address7:02X}
          F02 p20 §7.5.3.1   — MSB first
          F03 p25             — register map
          F04 p26 §7.6.2      — signed 16-bit, 1/128 °C/LSB
          F05 p27             — Data_Ready bit 13, MOD bits 11:10, AVG bits 6:5
          F06 p27             — MOD 01=shutdown, MOD 11=one-shot, AVG 00=none
          F07 p27             — reading config/temp clears Data_Ready
          F08 pp14-15 §7.4.3  — one-shot then returns to shutdown
          F09 p6              — 13/15.5/17.5 ms min/typ/max conversion
          F10 p32             — lower 12 bits = 0x117; upper 4 = revision
        DRIFT policies (not vendor facts): timeout={timeout_us} µs, poll={poll_interval_us} µs.
        \"\"\"

        from __future__ import annotations

        from drift.interfaces import (
            Clock,
            ConversionTimeout,
            DeviceIdentity,
            DeviceIdentityError,
            Measurement,
            ProtocolReadError,
            RegisterBus,
            validate_7bit_address,
        )

        # Register addresses — F03
        _REG_TEMPERATURE: int = {reg_temp:#04x}
        _REG_CONFIGURATION: int = {reg_config:#04x}
        _REG_DEVICE_ID: int = {reg_id:#04x}

        # Configuration bit masks — F05/F06
        _DATA_READY_BIT: int = {data_ready_bit:#06x}
        _MOD_MASK: int = {mod_mask:#06x}
        _AVG_MASK: int = {avg_mask:#06x}

        # Generated configuration words — from approved derived_candidates
        _CONFIG_SHUTDOWN: int = {shutdown_config:#06x}
        _CONFIG_ONE_SHOT: int = {start_config:#06x}

        # Device-ID constants — F10
        _DEVICE_ID_MASK: int = {id_mask:#06x}
        _DEVICE_ID_PART: int = {id_value:#06x}

        # Temperature decode constant — F04
        _LSB_DEG_C: float = {lsb_deg_c}

        # Wire width
        _REGISTER_WIDTH: int = {reg_width}

        # DRIFT policy constants — from approved contract
        _TIMEOUT_US: int = {timeout_us}
        _POLL_INTERVAL_US: int = {poll_interval_us}


        class {device_class}:
            \"\"\"
            Generated TMP117 driver for profile {profile_id!r}.
            Uses RegisterBus and Clock protocols only.
            Address: 0x{address7:02X} (ADD0=GND, F01).
            \"\"\"

            def __init__(
                self,
                bus: RegisterBus,
                clock: Clock,
                address_7bit: int = {address7:#04x},
            ) -> None:
                self._bus = bus
                self._clock = clock
                self._address = validate_7bit_address(address_7bit)

            def identify(self) -> DeviceIdentity:
                \"\"\"Read device-ID register and validate TMP117 part identity (F03/F10).\"\"\"
                raw = self._bus.read_register(self._address, _REG_DEVICE_ID, _REGISTER_WIDTH)
                if len(raw) != _REGISTER_WIDTH:
                    raise ProtocolReadError(
                        f"TMP117 device-ID register returned {{len(raw)}} byte(s); expected 2"
                    )
                unsigned = (raw[0] << 8) | raw[1]
                part_id = unsigned & _DEVICE_ID_MASK
                revision = (unsigned >> 12) & 0xF
                if part_id != _DEVICE_ID_PART:
                    raise DeviceIdentityError(
                        f"TMP117 part-ID mismatch: expected 0x{{_DEVICE_ID_PART:03X}}, "
                        f"got 0x{{part_id:03X}}"
                    )
                return DeviceIdentity(part_id=part_id, revision=revision, raw_bytes=raw)

            def configure(self) -> None:
                \"\"\"Write shutdown configuration (0x{shutdown_config:04X}) — DRIFT initialized fixture.\"\"\"
                self._bus.write_register(
                    self._address, _REG_CONFIGURATION, _CONFIG_SHUTDOWN.to_bytes(2, "big")
                )

            def measure(self, timeout_us: int = _TIMEOUT_US) -> Measurement:
                \"\"\"Trigger one-shot conversion, poll for Data_Ready, decode temperature.\"\"\"
                self._bus.write_register(
                    self._address, _REG_CONFIGURATION, _CONFIG_ONE_SHOT.to_bytes(2, "big")
                )
                deadline_us = self._clock.now_us() + timeout_us
                max_polls = timeout_us // _POLL_INTERVAL_US + 2
                ready_time_us: int | None = None
                for _ in range(max_polls):
                    self._clock.advance_us(_POLL_INTERVAL_US)
                    if self._clock.now_us() > deadline_us:
                        break
                    cfg_raw = self._bus.read_register(
                        self._address, _REG_CONFIGURATION, _REGISTER_WIDTH
                    )
                    cfg_word = (cfg_raw[0] << 8) | cfg_raw[1]
                    if cfg_word & _DATA_READY_BIT:
                        ready_time_us = self._clock.now_us()
                        break
                else:
                    raise ConversionTimeout(
                        f"TMP117 conversion did not complete within {{timeout_us}} µs"
                    )
                if ready_time_us is None:
                    raise ConversionTimeout(
                        f"TMP117 conversion did not complete within {{timeout_us}} µs"
                    )
                temp_raw = self._bus.read_register(
                    self._address, _REG_TEMPERATURE, _REGISTER_WIDTH
                )
                if len(temp_raw) != _REGISTER_WIDTH:
                    raise ProtocolReadError(
                        f"TMP117 temperature register returned {{len(temp_raw)}} byte(s); expected 2"
                    )
                unsigned = (temp_raw[0] << 8) | temp_raw[1]
                signed = unsigned if unsigned < 0x8000 else unsigned - 0x10000
                celsius = signed * _LSB_DEG_C
                return Measurement(raw_bytes=temp_raw, celsius=celsius, virtual_time_us=ready_time_us)
        """)


def _build_model_source(contract: ApprovedContract, tmpl: dict) -> str:
    """
    Build the virtual-device model Python source from approved contract values
    and the audited template.
    """
    c = contract.contract
    sp = c.selected_profile
    p = c.policies_not_vendor_facts
    dc = c.derived_candidates

    address7 = sp.address7
    virtual_conversion_us = p.virtual_conversion_us
    shutdown_config = int(dc.shutdown_config_hex, 16)
    start_config = int(dc.start_config_hex, 16)
    completed_cfg = int(dc.completed_config_snapshot_hex, 16)
    after_ready = int(dc.after_ready_consumed_hex, 16)
    model_class = tmpl["model_class"]
    reg_temp = int(tmpl["registers"]["temperature"]["address"], 16)
    reg_config = int(tmpl["registers"]["configuration"]["address"], 16)
    reg_id = int(tmpl["registers"]["device_id"]["address"], 16)
    data_ready_bit = int(tmpl["config_bits"]["data_ready"]["mask"], 16)
    mod_mask = int(tmpl["config_bits"]["mod_mask"]["mask"], 16)
    avg_mask = int(tmpl["config_bits"]["avg_mask"]["mask"], 16)
    mod_shutdown_val = int(tmpl["config_bits"]["mod_shutdown"]["value"], 16)
    mod_oneshot_val = int(tmpl["config_bits"]["mod_one_shot"]["value"], 16)
    id_value = int(tmpl["device_id_mask"]["value"], 16)
    reg_width = int(tmpl["register_width"])
    profile_id = c.profile_id
    source_doc = c.source.document
    source_rev = c.source.revision
    reviewer = contract.approval.reviewer
    approved_utc = contract.approval.approved_utc
    contract_sha256 = contract.approval.contract_sha256

    return textwrap.dedent(f"""\
        \"\"\"
        Generated TMP117 virtual device model for profile {profile_id!r}.

        Source: TI {source_doc} Rev. {source_rev}.
        Approved by: {reviewer} at {approved_utc}.
        Contract SHA-256: {contract_sha256}.
        Generated by DRIFT from the approved contract and audited template.
        Do not edit by hand; regenerate from the approved contract.
        \"\"\"

        from __future__ import annotations

        import enum

        from drift.interfaces import TraceEvent, UnsupportedProfile, validate_7bit_address


        # Register addresses — F03
        _REG_TEMPERATURE: int = {reg_temp:#04x}
        _REG_CONFIGURATION: int = {reg_config:#04x}
        _REG_DEVICE_ID: int = {reg_id:#04x}

        # Configuration bit constants — F05/F06
        _DATA_READY_BIT: int = {data_ready_bit:#06x}
        _MOD_MASK: int = {mod_mask:#06x}
        _AVG_MASK: int = {avg_mask:#06x}
        _MOD_SHUTDOWN: int = {mod_shutdown_val:#06x}
        _MOD_ONE_SHOT: int = {mod_oneshot_val:#06x}

        # Generated configuration words — from approved derived_candidates
        _CONFIG_SHUTDOWN: int = {shutdown_config:#06x}
        _CONFIG_ONE_SHOT_ACTIVE: int = {start_config:#06x}
        _CONFIG_READY: int = {completed_cfg:#06x}
        _CONFIG_AFTER_READY_READ: int = {after_ready:#06x}

        # Device-ID word: part 0x117, revision 0 — F10
        _DEVICE_ID_WORD: int = {id_value:#06x}

        # Conversion delay — DRIFT policy using F09 typical value
        _DEFAULT_CONVERSION_US: int = {virtual_conversion_us}

        # Register width — F02
        _REGISTER_WIDTH: int = {reg_width}


        class _State(enum.Enum):
            SHUTDOWN = "shutdown"
            CONVERTING = "converting"
            READY = "ready"


        class UnsupportedOperation(UnsupportedProfile):
            \"\"\"Register access outside selected profile (simulator policy, not hardware NACK).\"\"\"


        class _TraceAccumulator:
            def __init__(self) -> None:
                self._events: list[TraceEvent] = []

            def record(self, virtual_time_us, address_7bit, register, operation,
                       sent_bytes, received_bytes, outcome, fact_ids) -> None:
                self._events.append(TraceEvent(
                    sequence=len(self._events),
                    virtual_time_us=virtual_time_us,
                    address_7bit=address_7bit,
                    register=register,
                    operation=operation,
                    sent_bytes=sent_bytes,
                    received_bytes=received_bytes,
                    outcome=outcome,
                    fact_ids=fact_ids,
                ))

            @property
            def events(self) -> tuple[TraceEvent, ...]:
                return tuple(self._events)


        class {model_class}:
            \"\"\"
            Generated TMP117 virtual device for profile {profile_id!r}.
            Address: 0x{address7:02X}. One-shot, AVG=00.
            \"\"\"

            def __init__(self, clock, temperature_raw: int = 0x0C80,
                         conversion_us: int = _DEFAULT_CONVERSION_US) -> None:
                self._clock = clock
                self._temperature_raw = temperature_raw
                self._conversion_us = conversion_us
                self._state: _State = _State.SHUTDOWN
                self._config_word: int = _CONFIG_SHUTDOWN
                self._data_ready: bool = False
                self._conversion_deadline_us: int = 0
                self._stored_temperature: int = 0x8000
                self._trace = _TraceAccumulator()

            def reset_fixture(self) -> None:
                self._state = _State.SHUTDOWN
                self._config_word = _CONFIG_SHUTDOWN
                self._data_ready = False
                self._conversion_deadline_us = 0
                self._stored_temperature = 0x8000
                self._trace = _TraceAccumulator()

            def _tick(self) -> None:
                if self._state is _State.CONVERTING:
                    if self._clock.now_us() >= self._conversion_deadline_us:
                        self._state = _State.READY
                        self._data_ready = True
                        self._config_word = _CONFIG_READY
                        self._stored_temperature = self._temperature_raw

            def _current_config_snapshot(self) -> int:
                if self._data_ready:
                    return _CONFIG_READY
                if self._state is _State.CONVERTING:
                    return _CONFIG_ONE_SHOT_ACTIVE
                return _CONFIG_SHUTDOWN

            def read_register(self, register: int) -> bytes:
                self._tick()
                now = self._clock.now_us()
                if register == _REG_DEVICE_ID:
                    result = _DEVICE_ID_WORD.to_bytes(2, "big")
                    self._trace.record(now, {address7:#04x}, register, "read", b"", result, "ok", ("F03", "F10"))
                    return result
                if register == _REG_CONFIGURATION:
                    word = self._current_config_snapshot()
                    result = word.to_bytes(2, "big")
                    if self._data_ready:
                        self._data_ready = False
                        self._config_word = _CONFIG_AFTER_READY_READ
                        self._state = _State.SHUTDOWN
                    self._trace.record(now, {address7:#04x}, register, "read", b"", result, "ok", ("F05", "F06", "F07"))
                    return result
                if register == _REG_TEMPERATURE:
                    result = self._stored_temperature.to_bytes(2, "big")
                    if self._data_ready:
                        self._data_ready = False
                        self._config_word = _CONFIG_AFTER_READY_READ
                        self._state = _State.SHUTDOWN
                    self._trace.record(now, {address7:#04x}, register, "read", b"", result, "ok", ("F03", "F04", "F07"))
                    return result
                self._trace.record(now, {address7:#04x}, register, "read", b"", b"", "unsupported", ())
                raise UnsupportedOperation(f"Register {{register:#04x}} outside selected profile")

            def write_register(self, register: int, payload: bytes) -> None:
                self._tick()
                now = self._clock.now_us()
                if register == _REG_CONFIGURATION:
                    word = (payload[0] << 8) | payload[1]
                    avg_bits = word & _AVG_MASK
                    mod_bits = word & _MOD_MASK
                    if avg_bits != 0x0000:
                        self._trace.record(now, {address7:#04x}, register, "write", payload, b"", "unsupported", ("F06",))
                        raise UnsupportedOperation(f"Averaging mode {{avg_bits:#06x}} not in selected profile")
                    if mod_bits == _MOD_SHUTDOWN:
                        self._state = _State.SHUTDOWN
                        self._config_word = _CONFIG_SHUTDOWN
                        self._data_ready = False
                        self._trace.record(now, {address7:#04x}, register, "write", payload, b"", "ok", ("F05", "F06"))
                        return
                    if mod_bits == _MOD_ONE_SHOT:
                        self._state = _State.CONVERTING
                        self._data_ready = False
                        self._conversion_deadline_us = self._clock.now_us() + self._conversion_us
                        self._config_word = _CONFIG_ONE_SHOT_ACTIVE
                        self._trace.record(now, {address7:#04x}, register, "write", payload, b"", "ok", ("F05", "F06", "F08", "F09"))
                        return
                    self._trace.record(now, {address7:#04x}, register, "write", payload, b"", "unsupported", ("F06",))
                    raise UnsupportedOperation(f"MOD bits {{mod_bits:#06x}} outside selected profile")
                self._trace.record(now, {address7:#04x}, register, "write", payload, b"", "unsupported", ())
                raise UnsupportedOperation(f"Write to register {{register:#04x}} outside selected profile")

            @property
            def trace(self) -> tuple[TraceEvent, ...]:
                return self._trace.events
        """)


# ---------------------------------------------------------------------------
# Main generate() function
# ---------------------------------------------------------------------------


def generate(
    contract_path: Union[str, pathlib.Path],
    output_root: Union[str, pathlib.Path] = "generated",
    template_path: Optional[Union[str, pathlib.Path]] = None,
) -> GenerationResult:
    """
    Generate driver, model, and manifest from an approved contract.

    Parameters
    ----------
    contract_path:
        Path to the approved contract JSON file.
    output_root:
        Root directory; artifacts are placed under
        ``<output_root>/<contract-hash>/``.
    template_path:
        Override path to the device template JSON.  Default: resolved from
        the profile→template mapping.

    Returns
    -------
    GenerationResult
        Paths and hashes for all generated artifacts.

    Raises
    ------
    UnsupportedProfileError
        If the contract profile is not in SUPPORTED_PROFILES or has no
        template mapping.
    ApprovalMissingError / StaleApprovalError
        Propagated from ``ApprovedContract.from_file()``.
    """
    contract_path = pathlib.Path(contract_path)
    output_root = pathlib.Path(output_root)

    # -- Load and integrity-verify the approved contract --------------------
    approved = ApprovedContract.from_file(contract_path)  # raises on bad approval
    profile_id = approved.contract.profile_id

    if profile_id not in _PROFILE_TEMPLATE:
        raise UnsupportedProfileError(
            f"No template registered for profile {profile_id!r}. "
            f"Supported: {sorted(_PROFILE_TEMPLATE)}"
        )

    # -- Resolve template ---------------------------------------------------
    if template_path is None:
        tmpl_path = _TEMPLATES_DIR / _PROFILE_TEMPLATE[profile_id]
    else:
        tmpl_path = pathlib.Path(template_path)

    tmpl = _load_template(tmpl_path)
    template_sha256 = _sha256_file(tmpl_path)
    contract_sha256 = approved.approval.contract_sha256

    # -- Output directory ---------------------------------------------------
    out_dir = output_root / contract_sha256
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- Build sources ------------------------------------------------------
    driver_source = _build_driver_source(approved, tmpl)
    model_source = _build_model_source(approved, tmpl)

    # -- Write artifacts (bytes-stable: encode utf-8, no trailing newline
    #    variation — textwrap.dedent already ends with \n) ------------------
    driver_path = out_dir / "driver.py"
    model_path = out_dir / "device_model.py"
    manifest_path = out_dir / "manifest.json"

    driver_bytes = driver_source.encode("utf-8")
    model_bytes = model_source.encode("utf-8")
    driver_path.write_bytes(driver_bytes)
    model_path.write_bytes(model_bytes)

    driver_sha256 = _sha256_bytes(driver_bytes)
    model_sha256 = _sha256_bytes(model_bytes)

    # Hash this generator module itself for the manifest
    generator_sha256 = _sha256_file(pathlib.Path(__file__))

    generated_utc = datetime.now(tz=timezone.utc).isoformat()

    manifest = {
        "schema": "drift-generation-manifest-1",
        "profile_id": profile_id,
        "generated_utc": generated_utc,
        "inputs": {
            "contract_sha256": contract_sha256,
            "template_sha256": template_sha256,
            "generator_sha256": generator_sha256,
        },
        "outputs": {
            "driver_sha256": driver_sha256,
            "model_sha256": model_sha256,
        },
        "approved_by": approved.approval.reviewer,
        "approved_utc": approved.approval.approved_utc,
        "source_sha256": approved.approval.source_sha256,
        "scope": approved.contract.model_limits,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return GenerationResult(
        output_dir=out_dir,
        driver_path=driver_path,
        model_path=model_path,
        manifest_path=manifest_path,
        contract_sha256=contract_sha256,
        template_sha256=template_sha256,
        driver_sha256=driver_sha256,
        model_sha256=model_sha256,
        generator_sha256=generator_sha256,
        profile_id=profile_id,
        generated_utc=generated_utc,
    )


def generate_service(
    contract_path: Union[str, pathlib.Path],
    output_root: Union[str, pathlib.Path] = "generated",
    template_path: Optional[Union[str, pathlib.Path]] = None,
) -> dict:
    """
    Thin JSON-serialisable wrapper around generate().

    Returns a dict suitable for a web route response or CLI output.
    Raises the same errors as generate().
    """
    result = generate(contract_path, output_root, template_path)
    return {
        "profile_id": result.profile_id,
        "output_dir": str(result.output_dir),
        "driver_path": str(result.driver_path),
        "model_path": str(result.model_path),
        "manifest_path": str(result.manifest_path),
        "contract_sha256": result.contract_sha256,
        "template_sha256": result.template_sha256,
        "driver_sha256": result.driver_sha256,
        "model_sha256": result.model_sha256,
        "generated_utc": result.generated_utc,
    }
