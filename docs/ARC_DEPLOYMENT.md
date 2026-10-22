# Deploying SentinelVault to Arc Mainnet

This runbook takes you from a clean checkout to a live vault on Arc Mainnet, a hosted
dashboard, and the on-chain evidence (contract address + USDC transaction hashes) that an
Arc Microgrants submission asks for.

> **Network facts used below** (from Arc's documentation; re-check before deploying):
> Arc Mainnet chain ID `5042`, RPC `https://rpc.mainnet.arc.io`, gas is paid in USDC.
> USDC's ERC-20 interface is `0x3600000000000000000000000000000000000000` (6 decimals);
> the same balance appears natively with 18 decimals. Arc Testnet is chain `5042002`
> (`https://rpc.testnet.arc.network`, faucet at <https://faucet.circle.com>).

## 0. Prerequisites

* [Foundry](https://getfoundry.sh) (`forge`, `cast`)
* Two wallets: an **owner** (a human; holds admin rights) and an **agent** (the AI's hot key).
  Keep them separate: the point of the vault is that the agent key cannot exceed policy.
* A small amount of USDC on Arc for the deployer, owner, and agent (gas is paid in USDC),
  plus whatever you want to fund the vault with.

```bash
git clone --recurse-submodules https://github.com/Ishant5436/fastmcp-sentinel.git
cd fastmcp-sentinel/contracts
forge build && forge test
```

## 1. Rehearse on Arc Testnet (recommended)

Get testnet USDC from <https://faucet.circle.com>, then run steps 2–5 with
`--rpc-url arc_testnet` and `?chain=5042002` in the app URL.

## 2. Import keys into an encrypted keystore

```bash
cast wallet import deployer --interactive   # paste the deployer private key once
cast wallet import agent --interactive      # only needed to sign agent payments via cast
```

Never put private keys in `.env` files or shell history.

## 3. Deploy

```bash
export ARC_RPC_URL=https://rpc.mainnet.arc.io
export VAULT_OWNER=0xYourOwnerAddress
export VAULT_AGENT=0xYourAgentAddress
export MAX_PER_TX=10000000        # 10 USDC (6 decimals)
export MAX_PER_PERIOD=50000000    # 50 USDC per period
export PERIOD_SECONDS=86400       # 1 day

forge script script/Deploy.s.sol --rpc-url arc_mainnet --account deployer --broadcast
```

The script prints the vault address; the transaction is recorded under
`contracts/broadcast/Deploy.s.sol/5042/run-latest.json`. Save the **vault address** and the
**deployment tx hash**.

Optional: verify the source on Arc's explorer if it supports Foundry verification
(`forge verify-contract --help` lists the verifier options).

## 4. Host the dashboard

The app is a single static file (`app/index.html`) with no build step.

* **GitHub Pages:** in the repository settings, set *Pages → Source* to **GitHub Actions**.
  The `Deploy web app` workflow publishes `app/` on every push to `main`. The live URL is
  `https://<user>.github.io/fastmcp-sentinel/?vault=<VAULT_ADDRESS>`.
* **Locally:** `make app`, then open `http://127.0.0.1:8000/?vault=<VAULT_ADDRESS>`.

## 5. Move USDC through the contract (submission evidence)

1. Open the dashboard with your vault address and **Connect wallet** (switches to Arc).
2. **Deposit** a few USDC from any wallet → this is an ERC-20 transfer into the vault.
3. Connect as the **agent** wallet and **Pay** a small amount to a recipient with a memo.
   The app first calls the contract's `check`, then sends `pay`; the confirmation line shows
   the tx hash, and the payment appears under *Recent payments*.

Equivalent with `cast`:

```bash
cast send $VAULT "pay(address,uint256,bytes32)" 0xRecipient 1000000 \
  $(cast format-bytes32-string demo-1) --account agent --rpc-url arc_mainnet
```

## 6. Let an AI agent use it through MCP

```json
{
  "mcpServers": {
    "fastmcp-sentinel": {
      "command": "fastmcp-sentinel",
      "args": ["serve"],
      "env": { "SENTINEL_VAULT_ADDRESS": "0xYourVault" }
    }
  }
}
```

The agent calls `sentinel_arc_vault` with `action: "prepare_payment"`, `to_address`, and
`amount_usdc`. Sentinel checks the on-chain policy, gates the calldata in the native core,
simulates the call from the agent address, estimates gas, and returns an **unsigned**
transaction. The agent's wallet signs and broadcasts it; the contract enforces the limits
regardless of what the agent does.

## 7. Record your evidence

| Item | Where to find it |
| :--- | :--- |
| Vault contract address | Output of step 3 |
| Deployment tx hash | `contracts/broadcast/Deploy.s.sol/5042/run-latest.json` |
| Deposit / payment tx hashes | Dashboard confirmation line or *Recent payments* |
| Live app URL | GitHub Pages URL from step 4 |

Paste them into [`SUBMISSION_ARC_MICROGRANTS.md`](../SUBMISSION_ARC_MICROGRANTS.md).
