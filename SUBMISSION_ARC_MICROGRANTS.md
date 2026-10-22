# Arc Microgrants Submission: FastMCP-Sentinel

> Fill in every `TODO` before submitting. Items marked **required** are listed as
> requirements on the current round's page; re-read the round page before submitting,
> since rounds differ.

## Program fit

| Round | Status (as of 2026-10-22) | What it asks for |
| :--- | :--- | :--- |
| [Arc Microgrants](https://dorahacks.io/hackathon/arc-microgrants) | Closed (Oct 14, 2026) | Working mini app live on Arc Mainnet, live link + public repo. 20 × $500 USDC. |
| [Arc Microgrants: Built with Arc Studio](https://dorahacks.io/hackathon/arc-microgrants-2) | Open until Nov 2, 2026 (04:59 UTC) | Built with **Arc Studio**; contracts on Arc Mainnet; a working app that calls them; ≥ 1 mainnet transaction moving USDC through the contract and app; contract addresses, example tx hash, public repo, video walkthrough. 8 × $500 USDC. |

For the Arc Studio round, use Arc Studio for part of the build (for example to extend the
contract, its tests, or the dashboard) and describe that use in the form and the video.

## Form fields

**Project name:** FastMCP-Sentinel: On-chain spend policy for AI agents on Arc

**One-liner:** A USDC vault on Arc that lets an AI agent pay for things, but only within
per-transaction and per-day limits enforced by the contract, plus an MCP server that
pre-checks and simulates every payment before the agent signs.

**Problem.** Agents with a wallet key can be prompt-injected, misconfigured, or simply wrong,
and one bad tool call can drain the wallet. Off-chain guardrails help, but an agent that
holds the key can skip them.

**Solution.**
1. **`SentinelVault` (Solidity, Arc Mainnet):** holds the agent's USDC. The agent key can only
   call `pay`, which enforces a per-transaction cap, a per-period cap, an optional recipient
   allowlist, and an owner pause switch. The owner can always withdraw. Every payment emits an
   auditable `Payment` event with a memo.
2. **FastMCP-Sentinel server:** MCP tools any agent host can call. `sentinel_arc_vault`
   `prepare_payment` checks the on-chain policy, validates the calldata in a native C++ core,
   simulates the call from the agent address, estimates gas, and returns an unsigned
   transaction, so the agent never signs something that will revert or break policy.
3. **Dashboard (static web app):** shows the vault's live policy, spend meter, and payment
   history from Arc, and lets humans deposit USDC, pay as the agent, or pause and withdraw
   as the owner.

**Why Arc.** USDC is the gas token, so an agent needs to hold only one asset to pay and
transact. Fees are dollar-denominated and predictable, which suits programmatic spend limits.

## Evidence (required)

| Item | Value |
| :--- | :--- |
| Public repository | https://github.com/Ishant5436/fastmcp-sentinel |
| Live app | TODO `https://ishant5436.github.io/fastmcp-sentinel/?vault=0x…` |
| SentinelVault (Arc Mainnet) | TODO `0x…` |
| Deployment tx | TODO `0x…` |
| Example USDC tx through contract + app | TODO `0x…` (a `pay` from the dashboard) |
| Video walkthrough | TODO link |

How to produce each item: [`docs/ARC_DEPLOYMENT.md`](docs/ARC_DEPLOYMENT.md).

## Suggested video outline (2–3 minutes)

1. The problem in one sentence; open the dashboard with the live vault.
2. Show the policy: 10 USDC per tx, 50 USDC per day, the spend meter.
3. In an MCP host, have the agent call `sentinel_arc_vault` `prepare_payment` for 2 USDC: show
   the policy check, simulation, and unsigned tx.
4. Sign and send; show the payment in the dashboard and on the explorer.
5. Ask for 15 USDC: the tool reports `EXCEEDS_SINGLE_LIMIT`, and the contract would revert it anyway.
6. Owner presses **Pause**: payments stop; owner withdraws.
7. Mention where Arc Studio was used (Arc Studio round).

## Verification for reviewers

```bash
git clone --recurse-submodules https://github.com/Ishant5436/fastmcp-sentinel.git
cd fastmcp-sentinel
cd contracts && forge test && cd ..          # 20 contract tests incl. fuzzing
pip install -e ".[dev]" && make csrc
pytest                                        # Python suite; vault/app integration runs if anvil is on PATH
```

CI runs: contract unit + fuzz tests, Python 3.12/3.13 on Linux and macOS, the vault client and
the dashboard in a real browser against a local Arc-like chain (anvil), native C++ tests under
ASan/UBSan, and a wheel install smoke test.
