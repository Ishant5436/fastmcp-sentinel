# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-10-22

### Added
- `SentinelVault` Solidity contract (Foundry project in `contracts/`): USDC vault for AI agents on Arc with
  per-transaction and per-period caps, recipient allowlist, pause, owner withdraw, two-step ownership,
  `check` dry-run, and `Payment` events. 20 unit + fuzz tests; deploy script for Arc Mainnet/Testnet.
- `sentinel_arc_vault` MCP tool: read policy, on-chain check, and `prepare_payment` (policy check, native
  calldata gate, `eth_call` simulation from the agent, gas estimate, unsigned tx).
- Static dashboard (`app/index.html`) with deposit / pay / pause / withdraw via a browser wallet; GitHub Pages workflow.
- Arc Testnet (5042002) endpoint, USDC ERC-20 address, `SENTINEL_VAULT_ADDRESS`, `SENTINEL_DEFAULT_CHAIN_ID`.
- Revert decoding for SentinelVault custom errors.
- Integration tests: Python vault client and the dashboard (real Chromium) against anvil; CI contracts job.
- `docs/ARC_DEPLOYMENT.md` runbook and `SUBMISSION_ARC_MICROGRANTS.md`.

### Fixed
- `arc_status` converted native-balance values with 6 decimals; Arc's native USDC uses 18 (ERC-20 view: 6).

## [1.1.0] - 2026-10-22

### Security
- Fixed value/gas ceiling bypass: values >= 2^64 gwei (or gas >= 2^64) wrapped modulo 2^64 in ctypes and passed validation.
- Fixed partial-gwei truncation allowing values slightly above the 100 ETH ceiling.
- `sentinel_agent_guard` `record` no longer accepts negative values (which increased the remaining budget).
- `sentinel_agent_guard` `reset` is disabled unless `SENTINEL_ALLOW_AGENT_RESET=1`.
- `mock://` simulation (which always "succeeds") is disabled unless `SENTINEL_ALLOW_MOCK_RPC=1`.
- `rpc_url` is restricted to configured endpoints unless `SENTINEL_ALLOW_CUSTOM_RPC=1` (SSRF).
- Native target-address and calldata-shape validation (`ERR_INVALID_ADDRESS`, `ERR_MALFORMED_CALLDATA`).
- Cache: re-written keys no longer return stale values; oversized keys/values are rejected instead of truncated.
- Guard and native arena are now actually thread-safe (ctypes releases the GIL).

### Added
- `authorize` guard action: atomic check + budget reservation.
- `chain_id` selection and real `eth_estimateGas` gas usage in simulation; `gas` is now forwarded.
- Cache TTLs (`ttl_seconds`), revert decoding for custom errors and all Solidity panic codes.
- `value_wei` argument for exact validation amounts.
- Environment-driven `SentinelSettings` with validation; MCP server instructions and tool annotations.
- `fastmcp-sentinel audit` and `--version`; ABI version + struct layout check between bridge and library.
- scikit-build-core packaging: `pip install .` builds and bundles the native core (one wheel per platform).
- Native C++ unit tests (CTest) under ASan/UBSan; MCP stdio end-to-end test; security regression suite.
- CI: lint (ruff), type-check (mypy), Python 3.12/3.13 on Linux + macOS, sanitizers, wheel smoke test.
- `SECURITY.md`, `CHANGELOG.md`, `LICENSE`, Dependabot, pre-commit.

### Changed
- Simulation reports measured gas instead of a hard-coded 45000; `gas=0` means node default.
- The static audit ignores comments/string literals and flags direct recursion.
- Removed forced `-arch arm64`; macOS architectures are selected via `CMAKE_OSX_ARCHITECTURES` / `ARCHFLAGS`.
- `register_mcp.py` no longer hard-codes a developer's home directory; writes are atomic with backups.
- Demo and health check report real pass/fail instead of unconditional success.

## [1.0.0]
- Initial release.
