// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SentinelVault, IERC20} from "../src/SentinelVault.sol";

/// @notice Deploy a SentinelVault.
/// Environment:
///   VAULT_OWNER        owner (human) address                       (required)
///   VAULT_AGENT        agent hot-wallet address                    (required)
///   USDC_ADDRESS       ERC-20 USDC                                 (default: Arc USDC interface 0x3600..00)
///   MAX_PER_TX         per-transaction cap, USDC base units        (default: 10 USDC = 10_000_000)
///   MAX_PER_PERIOD     per-period cap, USDC base units             (default: 50 USDC = 50_000_000)
///   PERIOD_SECONDS     period length                               (default: 86400)
/// Usage:
///   forge script script/Deploy.s.sol --rpc-url arc_mainnet --broadcast --account <keystore>
contract Deploy is Script {
    address internal constant ARC_USDC = 0x3600000000000000000000000000000000000000;

    function run() external returns (SentinelVault vault) {
        address owner = vm.envAddress("VAULT_OWNER");
        address agent = vm.envAddress("VAULT_AGENT");
        address usdc = vm.envOr("USDC_ADDRESS", ARC_USDC);
        uint256 maxPerTx = vm.envOr("MAX_PER_TX", uint256(10_000_000));
        uint256 maxPerPeriod = vm.envOr("MAX_PER_PERIOD", uint256(50_000_000));
        uint64 period = uint64(vm.envOr("PERIOD_SECONDS", uint256(1 days)));

        vm.startBroadcast();
        vault = new SentinelVault(IERC20(usdc), owner, agent, maxPerTx, maxPerPeriod, period);
        vm.stopBroadcast();

        console2.log("SentinelVault deployed at", address(vault));
        console2.log("chainId", block.chainid);
        console2.log("owner", owner);
        console2.log("agent", agent);
        console2.log("token", usdc);
    }
}
