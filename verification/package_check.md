A full `make verify` ran from an unzipped copy of this archive, in a fresh directory with no dependencies, caches or datasets carried over and project volumes wiped first. All 17 gates passed, and the logs linked above come from that run.

- **Archive tested, SHA-256:** `e1ff38c2f596a823074688dc97322c3edfa63b502cfbc3f89f7842c6c45e3c19`
- **Command:** `make verify`, which covers the quick start (`docker compose up --wait`) and the smoke tests.
- **What changed after that run:** this report, generated portfolio files and evidence copied from the run, security justification notes, and one test setting (`src/lib/types.ts`, which has no runtime code, excluded from frontend coverage, followed by a rerun of the frontend tests). The application code did not change.
