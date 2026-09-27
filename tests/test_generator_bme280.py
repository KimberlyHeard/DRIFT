"""Independent checks for Bob's generated BME280 profile and delivered fault trace."""
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from drift.bus import ScriptedBus, VirtualDeviceBus
from drift.clock import StepClock, VirtualClock
from drift.contract import StaleApprovalError, UnsupportedProfileError
from drift.generator import generate
from drift.reporting_bme280 import bme280_report_to_dict
from drift.runner_bme280 import execute_bme280_scenario

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'contracts' / 'bme280.approved.json'
CALIB = bytes.fromhex('70 6B 43 67 18 FC')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeneratedBME280Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = pathlib.Path(self.temp.name)
        self.result = generate(CONTRACT, self.out)
        self.Driver = load_module(self.result.driver_path, 'generated_bme_driver').BME280Generated
        self.Model = load_module(self.result.model_path, 'generated_bme_model').BME280GeneratedModel

    def test_literal_scripted_and_generated_model(self):
        for raw, expected in [(bytes.fromhex('7E ED 00'), 25.08),
                              (bytes.fromhex('65 5A C0'), -7.86)]:
            with self.subTest(raw=raw.hex()):
                clock = StepClock()
                steps = [ScriptedBus.step_read(0x76, 0xD0, b'\x60'),
                         ScriptedBus.step_read(0x76, 0x88, CALIB),
                         ScriptedBus.step_write(0x76, 0xF4, b'\x21')]
                steps += [ScriptedBus.step_read(0x76, 0xF3, b'\x08') for _ in range(3)]
                steps += [ScriptedBus.step_read(0x76, 0xF3, b'\x00'),
                          ScriptedBus.step_read(0x76, 0xFA, raw)]
                bus = ScriptedBus(steps)
                driver = self.Driver(bus, clock)
                driver.identify()
                result = driver.measure()
                self.assertEqual((result.celsius, result.virtual_time_us), (expected, 4000))
                bus.assert_exhausted()

                virtual_clock = VirtualClock()
                virtual_device = self.Model(virtual_clock, calib_bytes=CALIB, temp_raw_bytes=raw)
                virtual_bus = VirtualDeviceBus(virtual_device, address_7bit=0x76)
                driver2 = self.Driver(virtual_bus, virtual_clock)
                driver2.identify()
                measurement = driver2.measure()
                self.assertEqual((measurement.celsius, measurement.virtual_time_us), (expected, 4000))

    def test_repeat_and_manifest_hashes(self):
        again = generate(CONTRACT, self.out / 'again')
        self.assertEqual(self.result.driver_path.read_bytes(), again.driver_path.read_bytes())
        self.assertEqual(self.result.model_path.read_bytes(), again.model_path.read_bytes())
        manifest = json.loads(self.result.manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(manifest['outputs']['driver_sha256'],
                         hashlib.sha256(self.result.driver_path.read_bytes()).hexdigest())
        self.assertEqual(manifest['outputs']['model_sha256'],
                         hashlib.sha256(self.result.model_path.read_bytes()).hexdigest())
        self.assertEqual(manifest['inputs']['contract_sha256'],
                         '5b1ef2802b99e0e708dafae30de96f0bdacc5a349c0e9e6504d65a5f7f3bfa13')

    def test_stale_approval_rejected(self):
        altered = json.loads(CONTRACT.read_text(encoding='utf-8'))
        altered['contract']['policies_not_vendor_facts']['timeout_us'] = 22222
        path = self.out / 'stale.json'
        path.write_text(json.dumps(altered), encoding='utf-8')
        with self.assertRaises(StaleApprovalError):
            generate(path, self.out / 'stale-output')

    def test_unsupported_mapping_rejected(self):
        import drift.generator as gen
        with patch.dict(gen._PROFILE_TEMPLATE, {}, clear=True):
            with self.assertRaises(UnsupportedProfileError):
                generate(CONTRACT, self.out / 'unsupported-output')

    def test_short_read_report_records_delivered_bytes(self):
        report = bme280_report_to_dict(execute_bme280_scenario('bme280_short_temp'))
        self.assertEqual(report['device_outcome'], 'ProtocolReadError')
        self.assertEqual(report['verification_status'], 'pass')
        self.assertEqual([ev['sequence'] for ev in report['trace']], list(range(8)))
        delivered = report['trace'][-1]
        self.assertEqual((delivered['register'], delivered['received_bytes'], delivered['outcome']),
                         ('0xFA', '7eed', 'fault_short_read'))


if __name__ == '__main__':
    unittest.main()
