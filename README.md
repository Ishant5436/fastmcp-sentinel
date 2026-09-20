# FastMCP-Sentinel

**Deterministic Safety Gateway & Sandboxing Kernel for Enterprise, Industrial IoT, and Distributed Autonomous AI Agents**

[![CI](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Ishant5436/fastmcp-sentinel/actions/workflows/ci.yml)
[![Safety Standard](https://img.shields.io/badge/Safety_Invariants-Power_of_10-00E599.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![Architecture: ARM64](https://img.shields.io/badge/Architecture-ARM64%20Apple%20Silicon-blue.svg)](https://github.com/Ishant5436/fastmcp-sentinel)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![C++20](https://img.shields.io/badge/Language-C%2B%2B20-00599C.svg)](https://isocpp.org)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://python.org)
[![FastMCP](https://img.shields.io/badge/Protocol-FastMCP%20v1.29-FF6B6B.svg)](https://modelcontextprotocol.io)

FastMCP-Sentinel is a high-performance, deterministic safety gateway for autonomous AI agents. Built for mission-critical enterprise workflows, industrial IoT actuator interfaces, and distributed blockchain networks, it couples a compiled C++20 vectorized invariant kernel running on ARM64 Apple Silicon with a standard FastMCP server. It prevents LLM hallucinations, financial leakage, out-of-bounds actuator commands, and infrastructure rate-limit exhaustion.

```
+-------------------------------------------------------------------+
|                   Autonomous Agent Environment                    |
|             (Claude Code / Gemini CLI / Cursor / AGY)             |
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
|  |  - Sub-millisecond circular LRU cache (1024 slots)          |  |
|  |  - 4-byte selector decoding & invariant validation (<15 µs)  |  |
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

### 1. Applied AI for Real-World Impact & Enterprise Integration
Autonomous LLM agents interacting with enterprise APIs (ERP, database mutations, cloud infrastructure) suffer from catastrophic hallucinated parameters. FastMCP-Sentinel serves as a deterministic policy sandbox:
* **Spend & Parameter Sandboxing:** Enforces per-session cumulative operation caps, single-call parameter limits, and whitelisted destination endpoints.
* **Token-Bucket Throttling:** Restricts automated agent polling loops, preventing accidental DDoS against rate-limited enterprise services.
* **Universal FastMCP Protocol:** Plugs natively into any MCP-compliant agent host (Claude Code, Antigravity, Cursor, LangChain).

### 2. Industrial AI, IoT & Safety-Critical Actuation
In robotic process automation and Industrial IoT (SCADA, PLC, actuator controllers), out-of-range tool calls can cause physical damage or process disruption:
* **Vectorized C++ Kernel:** Sub-15 microsecond zero-copy parameter validation on ARM64 ensures hard real-time execution bounds compatible with low-latency control loops.
* **Pre-Flight Invariant Simulation:** Every mutating command is validated in a zero-mutation state fork before physical or transactional dispatch.

### 3. Developer Tooling & Safety-Critical Verification
* **Sub-Millisecond Ring Cache:** Fixed 1024-slot circular LRU cache eliminates up to 80% of redundant static state reads.
* **Automated AST Audit Tooling:** Includes a standalone static analyzer (`scripts/audit_safety_invariants.py`) mechanically validating Holzmann Power of 10 invariants.

### 3. Security & Safety-Critical Verification
Built upon Gerard J. Holzmann's **Power of 10 Safety Invariants**, eliminating memory corruption and non-deterministic behavior:
* **Pre-Flight Zero-Mutation State Fork Simulation:** Executes transactions via dry-run before authorizing onchain signing, catching reverts, out-of-gas conditions, and slippage violations.
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

FastMCP-Sentinel exposes 5 tools via the Model Context Protocol stdio transport:

### 1. `sentinel_validate_calldata`
Validates EVM transaction parameters and calldata against safety invariants in < 15 µs.
* **Arguments:**
  * `to_address` (str): Target contract or recipient address.
  * `value_eth` (float): Value in Ether (enforces < 100 ETH ceiling).
  * `gas_limit` (int): Gas allocation (enforces < 15M block ceiling).
  * `calldata_hex` (str): Hex-encoded calldata (enforces <= 32KB buffer ceiling).
* **Returns:** `is_valid`, `status_code`, `reason`, `function_selector`, `latency_us`.

### 2. `sentinel_simulate_transaction`
Simulates transaction execution against an EVM JSON-RPC state fork without mutation.
* **Arguments:**
  * `to_address` (str): Target contract address.
  * `from_address` (str): Prospective sender address.
  * `value_wei` (int): Transaction value in wei.
  * `data` (str): Hex calldata.
  * `gas` (int): Gas limit.
  * `rpc_url` (str): Upstream JSON-RPC endpoint.
* **Returns:** `success`, `revert_reason`, `gas_used`, `return_data`.

### 3. `sentinel_rpc_cache`
Manages the sub-millisecond C++ ring-buffer LRU cache for static RPC reads.
* **Arguments:**
  * `action` (str): `"get"`, `"put"`, or `"stats"`.
  * `key` (str): Cache lookup key (e.g. `eth_chainId:[]`).
  * `value` (str): Value to store in cache.
* **Returns:** Cached data, status code, and capacity statistics.

### 4. `sentinel_agent_guard`
Enforces session-wide financial spend limits and rate limiting.
* **Arguments:**
  * `action` (str): `"check"`, `"record"`, `"status"`, or `"reset"`.
  * `to_address` (str): Intended recipient address.
  * `value_wei` (int): Transaction value in wei.
  * `tx_hash` (str): Hash of executed transaction (for `"record"`).
* **Returns:** Permission decision, remaining session budget, and token bucket state.

### 5. `sentinel_audit_invariants`
Executes mechanical static AST analysis of the C++ codebase, verifying Power of 10 compliance.
* **Arguments:** None.
* **Returns:** Compliance boolean, violations list, audited functions, and per-rule breakdown.

---

## Quickstart & Verification

### Prerequisites
* macOS Apple Silicon (ARM64)
* Clang++ with C++20 support
* Python 3.12 (`uv` recommended)

### Build & Run Tests (< 2 Seconds)

#### Option A: Build via CMake
```bash
# Configure and build native C++ core
cmake -B build && cmake --build build

# Run Power of 10 AST safety audit
cmake --build build --target audit

# Run complete test suite (24 tests)
cmake --build build --target run_tests
```

#### Option B: Build via Make
```bash
# Build native C++ dynamic library
make csrc

# Run complete test suite (24 tests)
make test

# Run Power of 10 AST safety audit
make audit

# Run 1-second live end-to-end demonstration
make demo
```

---

## MCP Server Configuration

To register FastMCP-Sentinel with your AI assistant or agent host, add the following entry to your `mcp_config.json` (or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "fastmcp-sentinel": {
      "command": "/Users/ishantpanchal/fastmcp-sentinel/venv/bin/python",
      "args": ["-m", "fastmcp_sentinel.cli", "serve"],
      "env": {
        "PYTHONPATH": "/Users/ishantpanchal/fastmcp-sentinel/src"
      }
    }
  }
}
```

---

## Performance Benchmarks

Measured on Apple Silicon M5 Pro:

| Subsystem | Latency | Memory Footprint | Invariant |
| :--- | :--- | :--- | :--- |
| **Vectorized Calldata Validation** | 9.8 µs | 0 heap allocations | Rule 3 & 4 |
| **Ring-Buffer LRU Cache Read** | 5.8 µs | Fixed 1024 slots (640 KB arena) | Rule 2 & 3 |
| **State Fork Simulation (Dry-Run)** | Network-dependent (< 45 ms) | Zero onchain state mutation | Pure read |
| **Token-Bucket Rate Limiter** | 1.2 µs | Minimal scalar state | Thread-safe |
| **AST Invariant Compliance Audit** | 8.1 ms | Ephemeral static analysis | Holzmann Rules 1-10 |

---

## Repository Structure

```
fastmcp-sentinel/
├── csrc/
│   ├── sentinel_core.hpp           # Power of 10 structs, arena bounds, error codes
│   ├── sentinel_core.cpp           # Vectorized validation kernel & ring cache
│   └── Makefile                    # Apple Silicon ARM64 Clang build
├── src/
│   └── fastmcp_sentinel/
│       ├── __init__.py
│       ├── bridge.py               # ctypes zero-copy wrapper to C++ core
│       ├── simulation.py           # EVM transaction simulation & revert decoding
│       ├── guard.py                # Stateful spend limits & token-bucket limiter
│       ├── server.py               # FastMCP server exposing the 5 tools
│       ├── audit.py                # Power of 10 static AST analysis engine
│       └── cli.py                  # Unified terminal runner (serve / check / demo)
├── scripts/
│   ├── audit_safety_invariants.py  # Standalone CLI AST analyzer script
│   └── run_demo.py                 # 1-second standalone verification demo
├── tests/
│   ├── test_sentinel_csrc.py       # C++ memory & invariant test suite
│   ├── test_simulation.py          # State fork simulation tests
│   ├── test_guard.py               # Session spend and rate-limiting tests
│   ├── test_fastmcp_tools.py       # FastMCP tool execution & schema tests
│   ├── test_safety_audit.py        # Automated AST compliance verification
│   └── test_cli.py                 # CLI health check and demo tests
├── Makefile                        # Top-level build and test automation
├── pyproject.toml                  # Python package configuration
└── README.md                       # Institutional submission documentation
```

---

## License

MIT License. Engineered for deterministic safety and autonomous execution.
