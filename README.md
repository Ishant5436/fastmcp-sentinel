# FastMCP-Sentinel

**Deterministic Safety Gateway & Sandboxing Kernel for Enterprise, Industrial IoT, and Distributed Autonomous AI Agents**

[![CI](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml)
[![Safety Standard](https://img.shields.io/badge/Safety_Invariants-Power_of_10-00E599.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![Arc Mainnet](https://img.shields.io/badge/Network-Arc%20Mainnet%20(5042)-00F0FF.svg)](https://arc.io)
[![Gas Token](https://img.shields.io/badge/Gas-Native%20USDC-2775CA.svg)](https://circle.com)
[![Platforms](https://img.shields.io/badge/Platforms-macOS%20ARM64%20%7C%20Linux%20x86__64-blue.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![C++20](https://img.shields.io/badge/Language-C%2B%2B20-00599C.svg)](https://isocpp.org)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://python.org)
[![FastMCP](https://img.shields.io/badge/Protocol-FastMCP%20v1.29-FF6B6B.svg)](https://modelcontextprotocol.io)

FastMCP-Sentinel is a high-performance, deterministic safety gateway for autonomous AI agents. Built for mission-critical enterprise workflows, industrial IoT actuator interfaces, and Arc Mainnet smart contract execution, it couples a compiled C++20 invariant kernel (macOS ARM64 and Linux x86_64) with a standard FastMCP server. It prevents agent parameter errors, unauthorized USDC spend, out-of-bounds actuator commands, and infrastructure rate-limit exhaustion.

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
|  |   - USDC spend caps       |     |  - eth_call + estimateGas  | |
|  |   - Binding reservations  |     |  - Revert reason decoding  | |
|  |   - Token-bucket limiter  |     |                            | |
|  +---------------------------+     +----------------------------+ |
|                                |                                  |
|                                v                                  |
|  +-------------------------------------------------------------+  |
|  |                    C++20 Invariant Core                     |  |
|  |  - Zero dynamic heap allocation on hot path (Rule 3)        |  |
|  |  - Function lengths <= 60 lines (Rule 4)                    |  |
|  |  - Assertion density >= 2 per function (Rule 5)             |  |
|  |  - Fixed 1024-slot ring cache (FIFO eviction, optional TTL) |  |
|  |  - 4-byte selector decoding & bounds validation (~2 µs)     |  |
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
* **One Pre-Flight Gate:** `sentinel_preflight` runs C++ validation, read-only simulation (`eth_call` + `eth_estimateGas`) and a spend reservation in one call, so a reverting or over-budget transaction never reaches signing.
* **USDC Spend Sandboxing:** Enforces a per-transaction cap (10 USDC) and a per-session cap (50 USDC). Spend is reserved at approval time, so an agent that never reports back still cannot exceed the budget, and negative amounts are rejected.
* **Correct USDC Units:** Arc exposes one USDC balance through two interfaces: native value (18 decimals) and the ERC-20 contract at `0x3600…0000` (6 decimals). Sentinel accounts in native units and also counts `transfer`, `approve` and `transferFrom` amounts sent to the ERC-20 interface, converting by 10¹².
* **Token-Bucket Throttling:** Restricts automated agent polling loops, preventing accidental transaction bursts against Arc JSON-RPC nodes.
* **Universal FastMCP Protocol:** Plugs natively into any standard FastMCP-compliant agent host.

### 2. Industrial AI, IoT & Safety-Critical Actuation
In robotic process automation and Industrial IoT (SCADA, PLC, actuator controllers), out-of-range tool calls can cause physical damage or process disruption:
* **Bounded C++ Kernel:** Allocation-free parameter validation in about 2 µs (median, measured below) with fixed worst-case bounds, suitable for low-latency control loops.
* **Pre-Flight Invariant Simulation:** Every mutating command is validated with a read-only simulation before physical or transactional dispatch.

### 3. Developer Tooling & Safety-Critical Verification
* **Fixed-Size Ring Cache:** 1024-slot cache for static RPC reads (`eth_chainId`, contract code). Writes to an existing key update it in place, the oldest entry is evicted when full, and reads can enforce a maximum age.
* **Automated AST Audit Tooling:** Includes a standalone static analyzer (`scripts/audit_safety_invariants.py`) mechanically validating Holzmann Power of 10 invariants.

### 4. Security & Safety-Critical Verification
Built upon Gerard J. Holzmann's **Power of 10 Safety Invariants**, eliminating memory corruption and non-deterministic behavior:
* **Pre-Flight Zero-Mutation Simulation:** Executes transactions via `eth_call` / `eth_estimateGas` against latest state before authorizing onchain signing, catching reverts and out-of-gas conditions.
* **Mechanical Invariant Proofs:** Every C++ function is validated by static AST analysis prior to deployment.

---

## Mission-Critical Architectural Invariants
 
| Architectural Invariant | Institutional Implementation | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Control Flow Determinism** | Single-path acyclic execution; zero `goto`, `setjmp`, `longjmp`, or recursion. | AST pattern analysis (`scripts/audit_safety_invariants.py`) | PASS |
| **Bounded Execution Horizons** | All ring buffer traversals bounded by `SENTINEL_CACHE_CAPACITY` (1024 slots). | Static analyzer bounds verification | PASS |
| **Zero-Allocation Hot Path** | Zero `malloc`, `new`, `free`, or `delete` on hot path. Fixed arena allocated at initialization. | Clang static check + AST grep audit | PASS |
| **Atomic Function Geometry** | Maximum C++ function length bounded to 44 lines (`sentinel_validate_tx`) (threshold $\le 60$). | AST line-counting parser | PASS |
| **Continuous Invariant Assertions** | Minimum 2 runtime assertions per function validating pointer and buffer bounds. | AST assert density scanner | PASS |
| **Zero-Macro Hygiene** | Preprocessor restricted to `#include` and header guards. Zero macro functions. | AST preprocessor check | PASS |
| **Single-Indirection Pointer Safety** | Maximum 1 level of pointer dereference. Zero function pointers or `**`. | AST pointer validator | PASS |
| **Pedantic Static Compilation Gate** | Compiled with `-Wall -Wextra -Werror -std=c++20 -O3` with 0 warnings. | Apple Silicon Clang compiler | PASS |

---

## Native FastMCP Tools

FastMCP-Sentinel exposes 6 tools via the Model Context Protocol stdio transport:

### 1. `sentinel_validate_calldata`
Validates EVM transaction parameters and calldata against safety invariants in the C++ core.
* **Arguments:**
  * `to_address` (str): Target contract or recipient address.
  * `value_native` (float): Value in whole native units, i.e. USDC on Arc (enforces a 100-unit ceiling). `value_eth` is accepted as a deprecated alias.
  * `gas_limit` (int): Gas allocation (enforces < 15M block ceiling).
  * `calldata_hex` (str): Hex-encoded calldata (enforces <= 32KB buffer ceiling).
* **Returns:** `is_valid`, `status_code`, `reason`, `function_selector`, `latency_us`.

### 2. `sentinel_simulate_transaction`
Simulates transaction execution with `eth_call` and measures gas with `eth_estimateGas`, without mutating state. Defaults to Arc Mainnet.
* **Arguments:**
  * `to_address` (str): Target contract address.
  * `from_address` (str): Prospective sender address.
  * `value_wei` (int): Transaction value in wei.
  * `data` (str): Hex calldata.
  * `gas` (int): Gas limit (0 = let the node estimate). A transaction whose estimate exceeds it is reported as out of gas.
  * `rpc_url` (str): Upstream JSON-RPC endpoint (empty = Arc Mainnet).
* **Returns:** `success`, `revert_reason`, `gas_used` (estimated), `return_data`.

### 3. `sentinel_rpc_cache`
Manages the fixed-size C++ ring-buffer cache for static RPC reads.
* **Arguments:**
  * `action` (str): `"get"`, `"put"`, or `"stats"`.
  * `key` (str): Cache lookup key (e.g. `eth_chainId:[]`, max 127 bytes).
  * `value` (str): Value to store in cache (max 511 bytes; larger values are rejected, not truncated).
  * `max_age_seconds` (float): For `"get"`, treat entries older than this as misses (0 = no expiry).
* **Returns:** Cached data, status code, and capacity statistics.

### 4. `sentinel_agent_guard`
Enforces session-wide USDC spend limits (10 USDC per transaction, 50 USDC per session) and rate limiting.
* **Arguments:**
  * `action` (str): `"check"` (advisory), `"reserve"`, `"confirm"`, `"release"`, `"record"`, `"status"`, `"arc_status"`, or `"reset"`.
  * `to_address` (str): Intended recipient or contract address.
  * `value_wei` (int): Native value in 18-decimal units (must be non-negative).
  * `calldata_hex` (str): Calldata, so ERC-20 USDC `transfer` / `approve` / `transferFrom` amounts are counted.
  * `reservation_id` (str): Returned by `"reserve"`; pass it to `"confirm"` (with `tx_hash`) after broadcast, or to `"release"` if the transaction is abandoned.
  * `tx_hash` (str): Hash of executed transaction (for `"confirm"` / `"record"`).
* **Returns:** Permission decision, reservation id, remaining session budget (in wei, and in USDC for `"arc_status"`), and token bucket state.

### 5. `sentinel_audit_invariants`
Executes mechanical static AST analysis of the C++ codebase, verifying Power of 10 compliance.
* **Arguments:** None.
* **Returns:** Compliance boolean, violations list, audited functions, and per-rule breakdown.

### 6. `sentinel_preflight`
The recommended single gate before an agent signs. Runs C++ validation, then simulation, then a guard reservation, and stops at the first failing stage. Nothing is reserved unless every stage passes.
* **Arguments:** `to_address`, `from_address`, `value_wei`, `data`, `gas`, `rpc_url` (same meaning as above).
* **Returns:** `approved`, `reservation_id`, `usdc_exposure`, `failed_stage` / `reason` on refusal, and per-stage results.
* **Agent flow:** `sentinel_preflight` → sign & broadcast → `sentinel_agent_guard(action="confirm", reservation_id=…, tx_hash=…)`.

---

## Quickstart & Verification

### Prerequisites
* macOS (Apple Silicon) or Linux (x86_64), both covered by CI
* Clang++ or g++ with C++20 support
* Python 3.12+ (`uv` recommended)

### Build & Run Tests (< 2 Seconds)

#### Option A: Build via CMake
```bash
# Configure and build native C++ core
cmake -B build && cmake --build build

# Run Power of 10 AST safety audit
cmake --build build --target audit

# Run complete test suite (56 tests)
cmake --build build --target run_tests
```

#### Option B: Build via Make
```bash
# Build native C++ dynamic library
make csrc

# Run complete test suite (56 tests)
make test

# Run Power of 10 AST safety audit
make audit

# Run 1-second live end-to-end demonstration
make demo

# Reproduce the latency numbers below
python scripts/benchmark.py
```

---

## MCP Server Configuration

To register FastMCP-Sentinel with your agent host, add the following entry to your `mcp_config.json`:

```json
{
  "mcpServers": {
    "fastmcp-sentinel": {
      "command": "/path/to/fastmcp-sentinel/venv/bin/python",
      "args": ["-m", "fastmcp_sentinel.cli", "serve"],
      "env": {
        "PYTHONPATH": "/path/to/fastmcp-sentinel/src",
        "ARC_RPC_URL": "https://rpc.mainnet.arc.io"
      }
    }
  }
}
```

---

## Performance Benchmarks

Warm median / p99 latency from `python scripts/benchmark.py` (20,000 iterations), measured on a Linux x86_64 cloud container with Python 3.13:

| Subsystem | Median | p99 | Notes |
| :--- | ---: | ---: | :--- |
| **C++ `validate_tx` (ctypes call)** | 1.7 µs | 9.5 µs | 0 heap allocations in the C++ path |
| **`validate_transaction` (hex parse + C++)** | 6.0 µs | 25.8 µs | What the MCP tool runs |
| **C++ ring cache read (hit)** | 1.7 µs | 7.9 µs | Fixed 1024-slot arena, linear scan |
| **Spend guard check** | 1.3 µs | 6.9 µs | Python, lock-protected |
| **Simulation** | network-bound | | One `eth_call` + one `eth_estimateGas` round trip |

Numbers vary by machine; run the script to reproduce them on yours. A first, cold call is slower (about 100 µs) while Python warms up.

---

## Repository Structure

```
fastmcp-sentinel/
├── csrc/
│   ├── sentinel_core.hpp           # Power of 10 structs, arena bounds, error codes
│   ├── sentinel_core.cpp           # Bounded validation kernel & ring cache
│   └── Makefile                    # macOS ARM64 / Linux build
├── src/
│   └── fastmcp_sentinel/
│       ├── __init__.py
│       ├── bridge.py               # ctypes wrapper to C++ core
│       ├── config.py               # Arc Mainnet parameters, USDC units & exposure accounting
│       ├── simulation.py           # EVM transaction simulation & revert decoding
│       ├── guard.py                # Stateful spend limits & token-bucket limiter
│       ├── server.py               # FastMCP server exposing the 6 tools
│       ├── audit.py                # Power of 10 static AST analysis engine
│       └── cli.py                  # Unified terminal runner (serve / check / demo)
├── scripts/
│   ├── audit_safety_invariants.py  # Standalone CLI AST analyzer script
│   ├── benchmark.py                # Reproducible latency benchmark
│   └── run_demo.py                 # 1-second standalone verification demo
├── tests/
│   ├── test_sentinel_csrc.py       # C++ memory & invariant test suite
│   ├── test_simulation.py          # State fork simulation tests
│   ├── test_guard.py               # Session spend and rate-limiting tests
│   ├── test_fastmcp_tools.py       # FastMCP tool execution & schema tests
│   ├── test_safety_audit.py        # Automated AST compliance verification
│   ├── test_arc_config.py          # Arc USDC units, caps & exposure accounting
│   └── test_cli.py                 # CLI health check and demo tests
├── Makefile                        # Top-level build and test automation
├── pyproject.toml                  # Python package configuration
└── README.md                       # Institutional submission documentation
```

---

## License

MIT License. Engineered for deterministic safety and autonomous execution.
