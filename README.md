# FastMCP-Sentinel

**Deterministic Safety Gateway & Sandboxing Kernel for Enterprise, Industrial IoT, and Distributed Autonomous AI Agents**

[![CI](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml)
[![Safety Standard](https://img.shields.io/badge/Safety_Invariants-Power_of_10-00E599.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![Arc Mainnet](https://img.shields.io/badge/Network-Arc%20Mainnet%20(5042)-00F0FF.svg)](https://arc.io)
[![Gas Token](https://img.shields.io/badge/Gas-Native%20USDC-2775CA.svg)](https://circle.com)
[![Platforms](https://img.shields.io/badge/Platforms-macOS%20%7C%20Linux-blue.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![C++20](https://img.shields.io/badge/Language-C%2B%2B20-00599C.svg)](https://isocpp.org)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://python.org)
[![FastMCP](https://img.shields.io/badge/Protocol-FastMCP%20v1.29-FF6B6B.svg)](https://modelcontextprotocol.io)

FastMCP-Sentinel is a high-performance, deterministic safety gateway for autonomous AI agents. Built for mission-critical enterprise workflows, industrial IoT actuator interfaces, and Arc Mainnet smart contract execution, it couples a compiled C++20 invariant kernel (macOS arm64/x86_64 and Linux) with a standard FastMCP server. It prevents agent parameter errors, unauthorized financial leakage, out-of-bounds actuator commands, and infrastructure rate-limit exhaustion.

```
+-------------------------------------------------------------------+
|                   Autonomous Agent Environment                    |
|                (FastMCP Client / IDE / CLI Engine)                |
+-------------------------------------------------------------------+
                                  |
                                  | MCP stdio protocol
                                  v
+-------------------------------------------------------------------+
|                        FastMCP-Sentinel                           |
|  +---------------------------+     +----------------------------+ |
|  |   Stateful Agent Guard    |     |  Zero-Mutation Simulator   | |
|  |   - Cumulative spend cap  |     |  - Pre-flight dry-run      | |
|  |   - Token-bucket limiter  |     |  - Revert reason decoding  | |
|  +---------------------------+     +----------------------------+ |
|                                |                                  |
|                                v                                  |
|  +-------------------------------------------------------------+  |
|  |             C++20 Invariant Core (ARM64 Native)             |  |
|  |  - Zero dynamic heap allocation on hot path (Rule 3)        |  |
|  |  - Function lengths <= 60 lines (Rule 4)                    |  |
|  |  - Assertion density >= 2 per function (Rule 5)             |  |
|  |  - Fixed 1024-slot ring-buffer cache with per-entry TTL     |  |
|  |  - Address/selector decoding & invariant validation         |  |
|  +-------------------------------------------------------------+  |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|            External Networks, APIs & Industrial Actuators         |
|     (Enterprise ERP / SCADA IoT / EVM & Distributed RPCs)        |
+-------------------------------------------------------------------+
```

---

## Strategic Track & Application Alignment

FastMCP-Sentinel is engineered to target both enterprise industrial challenges and high-stakes autonomous agent infrastructure:

### 1. Arc Mainnet & Web3 Autonomous Execution
Autonomous agents interacting with Arc Mainnet (Chain ID 5042) require deterministic pre-execution guarantees to protect native USDC balances:
* **Zero-Mutation Revert Interception:** Pre-flights calldata and state transitions via local zero-mutation fork simulation before broadcast, preventing wasted USDC gas on reverted calls.
* **Native USDC Spend Sandboxing:** Enforces per-session cumulative USDC caps ($50 USDC) and per-transaction limits ($10 USDC).
* **Token-Bucket Throttling:** Restricts automated agent polling loops, preventing accidental transaction bursts against Arc JSON-RPC nodes.
* **Universal FastMCP Protocol:** Plugs natively into any standard FastMCP-compliant agent host.

### 2. Industrial AI, IoT & Safety-Critical Actuation
In robotic process automation and Industrial IoT (SCADA, PLC, actuator controllers), out-of-range tool calls can cause physical damage or process disruption:
* **Native C++ Kernel:** Microsecond-scale zero-copy parameter validation with bounded loops and zero heap allocation, suitable for low-latency control loops.
* **Pre-Flight Invariant Simulation:** Every mutating command is validated in a zero-mutation state fork before physical or transactional dispatch.

### 3. Developer Tooling & Safety-Critical Verification
* **Sub-Millisecond Ring Cache:** Fixed 1024-slot ring buffer (FIFO eviction, per-entry TTL) removes redundant static state reads.
* **Automated Static Audit Tooling:** `fastmcp-sentinel audit` mechanically checks Holzmann Power of 10 invariants on the C++ sources.

### 4. Security & Safety-Critical Verification
Built upon Gerard J. Holzmann's **Power of 10 Safety Invariants**, eliminating memory corruption and non-deterministic behavior:
* **Pre-Flight Zero-Mutation State Fork Simulation:** Executes transactions via dry-run before authorizing onchain signing, catching reverts, out-of-gas conditions, and slippage violations.
* **Mechanical Invariant Checks:** Every C++ function is checked by the static auditor in CI, and the core runs under ASan/UBSan.

---

## Mission-Critical Architectural Invariants
 
| Architectural Invariant | Institutional Implementation | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Control Flow Determinism** | Zero `goto`, `setjmp`, `longjmp`, or direct recursion. | Static source audit (`fastmcp-sentinel audit`) | PASS |
| **Bounded Execution Horizons** | All ring buffer traversals bounded by `SENTINEL_CACHE_CAPACITY` (1024 slots). | Static analyzer bounds verification | PASS |
| **Zero-Allocation Hot Path** | Zero `malloc`, `new`, `free`, or `delete` on hot path. Fixed arena allocated at initialization. | Static source audit + ASan | PASS |
| **Atomic Function Geometry** | Longest C++ function is 44 lines (`sentinel_cache_put`); threshold $\le 60$. | Static line counter | PASS |
| **Continuous Invariant Assertions** | Minimum 2 runtime assertions per function validating pointer and buffer bounds (kept enabled in release builds). | Assert density scanner | PASS |
| **Zero-Macro Hygiene** | Preprocessor restricted to `#include` and header guards. Zero macro functions. | Preprocessor check | PASS |
| **Single-Indirection Pointer Safety** | Maximum 1 level of pointer dereference. Zero function pointers or `**`. | Pointer pattern check | PASS |
| **Pedantic Static Compilation Gate** | Compiled with `-Wall -Wextra -Wpedantic -Wshadow -Werror -std=c++20` with 0 warnings. | Clang & GCC in CI | PASS |
| **Memory-Safety Verification** | Native unit tests run under AddressSanitizer + UndefinedBehaviorSanitizer. | CTest in CI | PASS |
| **ABI Integrity** | Python bridge verifies library ABI version and struct layout before use. | Load-time check | PASS |

---

## Native FastMCP Tools

FastMCP-Sentinel exposes 5 tools via the Model Context Protocol stdio transport:

### 1. `sentinel_validate_calldata`
Validates EVM transaction parameters and calldata against the native safety invariants.
* **Arguments:**
  * `to_address` (str): Target address; must be `0x` + 40 hex characters.
  * `value_eth` (float): Value in Ether (converted exactly via `Decimal`; enforces <= 100 ETH ceiling).
  * `value_wei` (int, optional): Exact value in wei; takes precedence over `value_eth`.
  * `gas_limit` (int): Gas allocation (enforces <= 15M block ceiling).
  * `calldata_hex` (str): Hex-encoded calldata (empty, or >= 4-byte selector; <= 32KB).
* **Returns:** `is_valid`, `status_code`, `status_name`, `reason`, `function_selector`, `latency_us`.

### 2. `sentinel_simulate_transaction`
Simulates execution with `eth_call` and measures gas with `eth_estimateGas`, without mutating state.
* **Arguments:**
  * `to_address` (str), `from_address` (str), `value_wei` (int), `data` (str).
  * `gas` (int): Gas cap forwarded to `eth_call`; `0` lets the node decide.
  * `chain_id` (int): Select a configured network (5042, 1, 42161, 8453, 10). Preferred.
  * `rpc_url` (str): Must be one of the configured endpoints unless `SENTINEL_ALLOW_CUSTOM_RPC=1`.
* **Returns:** `success`, `revert_reason` (Error(string), Panic codes, custom-error selectors), `gas_used`, `gas_estimated`, `return_data`, `chain_id`.

### 3. `sentinel_rpc_cache`
Fixed-capacity native ring buffer (1024 slots, FIFO eviction) for RPC reads.
* **Arguments:**
  * `action`: `"get"`, `"put"`, or `"stats"`.
  * `key` (str, <= 127 bytes) / `value` (str, <= 511 bytes). Oversized input is rejected, never truncated.
  * `ttl_seconds` (float): Expiry for `put`; `0` = never, negative = server default.
* **Returns:** Cached data, status code, and capacity statistics.

### 4. `sentinel_agent_guard`
Enforces session-wide financial spend limits, address filtering, and rate limiting.
* **Arguments:**
  * `action`: `"authorize"` (atomic check + reserve — use before signing), `"check"` (dry run), `"record"`, `"status"`, `"arc_status"`, `"reset"` (operator opt-in only).
  * `to_address` (str), `value_wei` (int, non-negative), `tx_hash` (str).
* **Returns:** Permission decision, remaining session budget, and token bucket state.

### 5. `sentinel_audit_invariants`
Runs the static Power of 10 audit of the C++ core.
* **Arguments:** None.
* **Returns:** Compliance boolean, violations list, audited functions, and per-rule breakdown.

---

## Quickstart & Verification

### Prerequisites
* macOS (arm64 or x86_64) or Linux
* A C++20 compiler (Clang or GCC) and CMake >= 3.20 (installed automatically by `pip` if missing)
* Python 3.12+

### Install
```bash
pip install .                 # builds the C++ core and bundles it in the package
fastmcp-sentinel check        # verify every subsystem
```

### Develop
```bash
python -m venv venv && source venv/bin/activate
make dev          # editable install with dev tools + build csrc/libsentinel_core
make all          # lint, type-check, tests, Power of 10 audit
make sanitize     # native C++ tests under ASan + UBSan
make demo         # 1-second end-to-end demonstration
```

The CMake build is also available directly: `cmake -S . -B build && cmake --build build && ctest --test-dir build`.

---

## MCP Server Configuration

Register FastMCP-Sentinel with your agent host (`claude_desktop_config.json`, `mcp_config.json`, ...):

```json
{
  "mcpServers": {
    "fastmcp-sentinel": {
      "command": "fastmcp-sentinel",
      "args": ["serve"],
      "env": {
        "SENTINEL_MAX_SINGLE_TX_WEI": "1000000000000000000",
        "SENTINEL_MAX_SESSION_SPEND_WEI": "5000000000000000000"
      }
    }
  }
}
```

`python scripts/register_mcp.py --dry-run` prints a config for the current interpreter and can write it into
locally installed hosts (each file is backed up and rewritten atomically).

### Configuration

All settings are environment variables. Defaults are **fail-closed**.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SENTINEL_MAX_SINGLE_TX_WEI` | `10**18` | Per-transaction value cap |
| `SENTINEL_MAX_SESSION_SPEND_WEI` | `5 * 10**18` | Cumulative session cap |
| `SENTINEL_RATE_LIMIT_PER_MINUTE` / `SENTINEL_BURST_LIMIT` | `60` / `10` | Token-bucket rate limit |
| `SENTINEL_BLOCKED_ADDRESSES` / `SENTINEL_ALLOWED_ADDRESSES` | empty | Comma-separated recipient deny/allow lists |
| `SENTINEL_ALLOW_AGENT_RESET` | `false` | Let the agent reset its own budget |
| `SENTINEL_ALLOW_CUSTOM_RPC` | `false` | Allow `rpc_url` values outside the configured endpoints |
| `SENTINEL_ALLOW_MOCK_RPC` | `false` | Allow `mock://` simulation (testing only) |
| `SENTINEL_RPC_TIMEOUT_SECONDS` | `5` | JSON-RPC timeout |
| `SENTINEL_CACHE_DEFAULT_TTL_SECONDS` | `0` (never) | Default cache entry TTL |
| `ARC_RPC_URL`, `ETH_RPC_URL`, `ARB_RPC_URL`, `BASE_RPC_URL`, `OP_RPC_URL` | public endpoints | Per-chain RPC endpoints |
| `SENTINEL_LIB_PATH` / `SENTINEL_CSRC_DIR` | auto | Override native library / audited source location |
| `SENTINEL_LOG_LEVEL` | `INFO` (serve) | Logs go to stderr; guard decisions are logged for audit |

See [SECURITY.md](SECURITY.md) for the threat model.

---

## Performance Benchmarks

Measured on Apple Silicon M5 Pro (indicative; run `fastmcp-sentinel check` for numbers on your hardware):

| Subsystem | Latency | Memory Footprint | Invariant |
| :--- | :--- | :--- | :--- |
| **Native Calldata Validation** | 9.8 µs | 0 heap allocations | Rule 3 & 4 |
| **Ring-Buffer Cache Read** | 5.8 µs | Fixed 1024 slots (640 KB arena) | Rule 2 & 3 |
| **State Fork Simulation (Dry-Run)** | Network-dependent (< 45 ms) | Zero onchain state mutation | Pure read |
| **Token-Bucket Rate Limiter** | 1.2 µs | Minimal scalar state | Thread-safe |
| **Static Invariant Compliance Audit** | 8.1 ms | Ephemeral static analysis | Holzmann Rules 1-5, 8, 9 |

---

## Repository Structure

```
fastmcp-sentinel/
├── csrc/
│   ├── sentinel_core.hpp           # Power of 10 structs, arena bounds, error codes, ABI version
│   ├── sentinel_core.cpp           # Validation kernel & ring-buffer cache
│   └── Makefile                    # Standalone build of the shared library
├── src/fastmcp_sentinel/
│   ├── bridge.py                   # ctypes wrapper with ABI/layout checks and input hardening
│   ├── simulation.py               # eth_call / eth_estimateGas simulation & revert decoding
│   ├── guard.py                    # Thread-safe spend limits & token-bucket limiter
│   ├── server.py                   # FastMCP server exposing the 5 tools
│   ├── config.py                   # Network constants and environment-driven settings
│   ├── paths.py                    # Native library / source discovery
│   ├── audit.py                    # Power of 10 static analysis engine
│   └── cli.py                      # serve / check / demo / audit
├── tests/
│   ├── native/                     # C++ unit tests (CTest, sanitizers)
│   ├── test_security.py            # Regression tests for safety bypasses
│   ├── test_stdio_e2e.py           # Real MCP stdio client <-> server round-trip
│   └── ...                         # Bridge, guard, simulation, audit, CLI, tool tests
├── scripts/                        # Audit, demo, and MCP host registration helpers
├── CMakeLists.txt                  # Library, native tests, sanitizer option, wheel install
├── pyproject.toml                  # scikit-build-core packaging, ruff, mypy, pytest config
├── Makefile                        # Developer workflow
└── SECURITY.md                     # Threat model and hardening notes
```

---

## License

MIT License. Engineered for deterministic safety and autonomous execution.
