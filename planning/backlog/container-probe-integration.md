# Container Probe — Integration Test Suite

- **Summary**: Integrate `scripts/container_probe.py` as a post-lifecycle verification tool. Copy to hybrid-mounted location, run from inside container to validate volume masking, isolation volumes, and extension state.
- **Blocked by**: Nothing — probe script exists, needs test harness.
- **Estimated scope**: M
- **Source**: `scripts/container_probe.py` (8 diagnostic sections: identity, network, filesystem walk, mount inspection, device topology, /proc audit, capability probe, volume mask verification)
- **Integration approach**: Copy probe to a path visible inside the container (bind mount or docker cp), execute via `exec_in_container()`, parse results as test assertions.
