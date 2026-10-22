# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/Ishant5436/fastmcp-sentinel/security/advisories/new)
rather than public issues. Include a reproduction and the affected version (`fastmcp-sentinel --version`).

## Threat model

FastMCP-Sentinel treats **the agent calling its tools as untrusted**. An agent may be confused,
prompt-injected, or adversarial, and may pass arbitrary values to any tool argument. The operator
who launches the server (and sets its environment) is trusted.

Guarantees the server aims to provide against an untrusted agent:

| Property | Mechanism |
| :--- | :--- |
| Value / gas ceilings cannot be bypassed by integer overflow | Inputs are validated as non-negative integers, rounded up to gwei, and saturated at `UINT64_MAX` before crossing into C++ (ctypes would otherwise wrap modulo 2^64). |
| ETH amounts are converted exactly | `Decimal` conversion; NaN, infinity, negatives, and sub-wei precision are rejected. |
| Malformed targets and calldata are rejected | Native checks for `0x` + 40-hex addresses and >= 4-byte selectors. |
| The agent cannot raise its own budget | `record` rejects negative values; `reset` requires `SENTINEL_ALLOW_AGENT_RESET=1`. |
| Check-then-spend races are impossible | `authorize` checks and reserves budget atomically under a lock. |
| Simulation cannot be faked | `mock://` backends require `SENTINEL_ALLOW_MOCK_RPC=1`. |
| No server-side request forgery via `rpc_url` | Only configured endpoints are reachable unless `SENTINEL_ALLOW_CUSTOM_RPC=1`; custom URLs must be http(s). |
| Cache returns what was stored, or nothing | Oversized keys/values are rejected (never truncated); re-writes replace in place; TTLs supported. |
| Native memory safety | Fixed arena, bounded loops, no heap; native tests run under ASan + UBSan; ABI version and struct layout are verified at load time; arena access is serialized. |

Every guard decision is logged to stderr (`fastmcp_sentinel.guard`) for auditing.

## Known limitations

* **Sentinel is advisory unless enforced at the signer.** If the agent can sign and broadcast
  without going through Sentinel, it can skip the checks. For hard guarantees, put the signing key
  behind a component that only signs transactions Sentinel has authorized.
* **Guard state is in-memory and per-process.** Restarting the server resets the session budget.
  Run one server per agent session, or persist state externally if budgets must survive restarts.
* **`arc_status` unit conversion.** The guard is denominated in the chain's native base unit (wei by
  default), while `arc_status` converts with USDC's 6 ERC-20 decimals. Configure the `SENTINEL_*_WEI`
  limits in the base unit your deployment actually uses and verify the reported USDC figures.
* **Simulation is a point-in-time `eth_call` against `latest`.** State can change between simulation
  and inclusion (front-running, price movement). Treat a successful simulation as necessary, not sufficient.
* **The Power of 10 audit is a lightweight static checker** (comment/string-aware pattern and
  brace analysis), not a full C++ parser. It complements compiler warnings and sanitizers.
