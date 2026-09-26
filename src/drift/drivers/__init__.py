"""
TMP117 driver stub.

The production driver will be implemented in Task 04 against the RegisterBus
and Clock protocols only.  It must never access a virtual device object,
raw fixture table, or expected oracle values.

Selected profile: one-shot, averaging disabled, 7-bit address 0x48.
Source: TI TMP117 SNOSD82D Rev. D.
"""

# Registers (TMP117 SNOSD82D p25, F03)
REG_TEMPERATURE: int = 0x00
REG_CONFIGURATION: int = 0x01
REG_DEVICE_ID: int = 0x0F

# Selected operating profile address (ADD0 grounded, SNOSD82D Table 7-2 p21, F01)
DEVICE_ADDRESS: int = 0x48

# DRIFT policy values (not vendor facts):
TIMEOUT_US: int = 100_000   # 100 ms — DRIFT policy
POLL_INTERVAL_US: int = 1_000   # 1 ms  — DRIFT policy
