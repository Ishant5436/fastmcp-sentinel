# DoraHacks Submission Dossier: FastMCP-Sentinel

## 1. Hackathon Target Profile
* **Active Target:** [MunichTech Innovation Hackathon 2026 – Build Applied Solutions for Industry](https://dorahacks.io/hackathon/2019/tracks)
  * **Tracks:** Applied AI for Real-World Impact (AI Agents & Workflow Automation) & Corporate Challenge Track
  * **BUIDL Profile:** [#48828](https://dorahacks.io/buidl/48828)
  * **Eligibility:** Code-only submission with working C++20 engine, tests, and live demo
* **Co-Target:** [KeeperHub - The Agent Economy Hackathon](https://dorahacks.io/hackathon)
  * **Focus:** AI Agents, Autonomous Systems, Model Context Protocol (MCP)
  * **Prize Pool:** $5,000 USD

---

## 2. BUIDL Profile & Form Fields (Copy-Paste Ready)

### Project Name
`FastMCP-Sentinel: Deterministic Safety & RPC Gateway for Autonomous Agents`

### Tagline (One-Liner)
A high-performance C++20 and FastMCP safety gateway enforcing Holzmann's Power of 10 invariants, zero-mutation state simulations, and session spend sandboxing for enterprise and onchain AI agents.

### Repository URL
`https://github.com/Ishant5436/fastmcp-sentinel`

### Primary Track
`Applied AI for Real-World Impact / Enterprise AI Integration / AI Agents`

---

## 3. Project Description (Markdown Form Text)

### Problem Statement
When autonomous AI agents interact with blockchain networks and JSON-RPC infrastructure via LLM tool-calling interfaces (Claude Code, Gemini CLI, Cursor, Antigravity), they suffer from three critical failure vectors:
1. **Unbounded Calldata & Financial Leakage:** Hallucinated transaction parameters, unchecked slippage, or unbounded values drain agent balances or trigger MEV sandwich exploitation.
2. **RPC Rate Exhaustion & Polling Churn:** High-frequency polling loops (`eth_blockNumber`, `eth_getTransactionReceipt`) spam nodes, incurring HTTP 429 errors and high infrastructure costs.
3. **Non-Deterministic Execution Overhead:** Pure Python wrappers introduce garbage collection latency, uncontrolled heap allocations, and silent error suppression on the transaction path.

### The Solution: FastMCP-Sentinel
FastMCP-Sentinel is a dual-engine deterministic gateway that sits between autonomous AI agents and distributed networks:
* **Compiled C++20 Vectorized Invariant Kernel:** Running natively on ARM64 Apple Silicon with zero dynamic heap allocations on the hot path, enforcing Gerard J. Holzmann's Power of 10 Safety Invariants.
* **Standard FastMCP Server:** Exposes 5 native safety and caching tools to any MCP-compliant agent host via stdio.

### Key Capabilities & Exposed Tools
1. `sentinel_validate_calldata`: Sub-millisecond (9.8 µs) zero-copy calldata verification, 4-byte selector decoding, and hard bounded limits (< 32KB buffer, < 100 ETH value, < 15M gas).
2. `sentinel_simulate_transaction`: Zero-mutation state fork simulation against EVM JSON-RPC endpoints with automatic ABI revert decoding (`Error(string)` and `Panic(uint256)`).
3. `sentinel_rpc_cache`: Fixed 1024-slot circular ring-buffer LRU cache eliminating up to 80% of redundant static RPC queries in 5.8 µs.
4. `sentinel_agent_guard`: Stateful session spend limiter and token-bucket rate limiter preventing unconstrained agent balance drain.
5. `sentinel_audit_invariants`: Automated static AST analyzer verifying Power of 10 compliance across all C++ source files on every run.

### Mission-Critical Architectural Invariants
* **Control Flow Determinism:** Single-path execution guarantees; zero `goto`, `setjmp`, `longjmp`, or recursion.
* **Bounded Execution Horizons:** All loops and ring-buffer traversals bounded by compile-time constants (1024 slots) ensuring guaranteed $O(1)$ worst-case latency.
* **Zero-Allocation Hot Path:** Zero dynamic heap allocations (`malloc`, `new`, `free`, `delete`) during runtime; fixed memory arena allocated at initialization.
* **Atomic Function Geometry:** Maximum function length bounded to $\le 44$ lines for auditable cognitive clarity and instruction cache locality.
* **Continuous Invariant Assertions:** Minimum 2 runtime assertions per function strictly validating pointer non-nullness and buffer bounds.
* **Zero-Macro Hygiene:** Zero function-like preprocessor macros or conditional `#ifdef` compilation branches, preventing AST divergence.
* **Single-Indirection Pointer Safety:** Maximum 1 level of pointer indirection; complete prohibition of raw function pointers.
* **Pedantic Static Compilation Gate:** 100% warning-free compilation under `-Wall -Wextra -Werror -std=c++20 -O3` validated by static AST analysis.

### Verification & Performance Evidence
* **CI/CD Matrix:** GitHub Actions workflow passing on `macos-14` (ARM64 Apple Silicon) and `ubuntu-latest`.
* **Automated Test Suite:** 24/24 tests pass in 0.17 seconds (`pytest tests/ -v`).
* **Validation Latency:** 9.8 µs (Zero-Copy C++ kernel).
* **Cache Latency:** 5.8 µs (1024 circular arena).
* **Instant Demo:** Runs end-to-end live verification of all 5 security gates in < 1 second (`make demo`).

---

## 4. Local Execution & Evaluation Commands (For Judges)

```bash
git clone https://github.com/Ishant5436/fastmcp-sentinel.git
cd fastmcp-sentinel

# Build native C++ invariant core
make csrc

# Run complete 24-test suite
make test

# Run Power of 10 static AST audit
make audit

# Run 1-second live end-to-end demo
make demo
```
