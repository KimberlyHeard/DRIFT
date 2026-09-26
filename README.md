# DRIFT

## Datasheet-to-Driver Virtual Verification Lab

From a real hardware specification to tested driver behavior before the board arrives.

**Scaffold status:** the application is not implemented yet. Start with [START_HERE.md](START_HERE.md), the [playbook](DRIFT_PLAYBOOK.md) and [Bob task cards](prompts/BOB_TASKS.md).

Primary target: real TI TMP117 one-shot/no averaging at I²C 0x48. Extension: real Bosch BME280 forced temperature-only measurement. See [provenance](PROVENANCE.md) for when this planning/support kit was created and how to attribute it.

Bob will implement the reviewed contract, driver, deterministic virtual device, independent tests, four faults, trace/reports, generator, workbench and documented repair. Replace this scaffold status with actual tested commands/results as the build proceeds.

This models a selected digital profile; physical hardware validation remains future work.
