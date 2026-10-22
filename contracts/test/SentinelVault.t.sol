// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SentinelVault, IERC20} from "../src/SentinelVault.sol";

/// @dev 6-decimal ERC-20 standing in for USDC's ERC-20 interface on Arc.
contract MockUSDC is IERC20 {
    mapping(address => uint256) public override balanceOf;
    bool public returnFalse;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function setReturnFalse(bool v) external {
        returnFalse = v;
    }

    function transfer(address to, uint256 amount) external virtual override returns (bool) {
        if (returnFalse) return false;
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

    /// @dev Token whose transfer re-enters the vault, to exercise the reentrancy lock.
    contract ReentrantToken is MockUSDC {
        SentinelVault public vault;

        function setVault(SentinelVault v) external {
            vault = v;
        }

        function transfer(address to, uint256 amount) external override returns (bool) {
            if (address(vault) != address(0) && msg.sender == address(vault)) {
                vault.pay(to, amount, keccak256("reenter"));
            }
            balanceOf[msg.sender] -= amount;
            balanceOf[to] += amount;
            return true;
        }

        function startPay(address to, uint256 amount) external {
            vault.pay(to, amount, keccak256("start"));
        }
    }

    contract SentinelVaultTest is Test {
        uint256 internal constant USDC = 1e6;

        MockUSDC internal usdc;
        SentinelVault internal vault;
        address internal owner = makeAddr("owner");
        address internal agent = makeAddr("agent");
        address internal merchant = makeAddr("merchant");

        event Payment(
            uint256 indexed id, address indexed to, uint256 amount, bytes32 indexed memo, uint256 spentInPeriod
        );

        function memo(string memory tag) internal pure returns (bytes32) {
            return keccak256(bytes(tag));
        }

        function setUp() public {
            usdc = new MockUSDC();
            vault = new SentinelVault(usdc, owner, agent, 10 * USDC, 50 * USDC, 1 days);
            usdc.mint(address(vault), 100 * USDC);
        }

        // --- construction -------------------------------------------------------

        function test_constructor_rejectsZeroAddresses() public {
            vm.expectRevert(SentinelVault.ZeroAddress.selector);
            new SentinelVault(IERC20(address(0)), owner, agent, 1, 1, 1);
            vm.expectRevert(SentinelVault.ZeroAddress.selector);
            new SentinelVault(usdc, address(0), agent, 1, 1, 1);
            vm.expectRevert(SentinelVault.ZeroAddress.selector);
            new SentinelVault(usdc, owner, address(0), 1, 1, 1);
        }

        function test_constructor_rejectsCodelessToken() public {
            vm.expectRevert(SentinelVault.InvalidToken.selector);
            new SentinelVault(IERC20(makeAddr("eoa")), owner, agent, 1, 1, 1);
        }

        function test_constructor_rejectsInvalidLimits() public {
            vm.expectRevert(SentinelVault.InvalidLimits.selector);
            new SentinelVault(usdc, owner, agent, 0, 1, 1);
            vm.expectRevert(SentinelVault.InvalidLimits.selector);
            new SentinelVault(usdc, owner, agent, 2, 1, 1);
            vm.expectRevert(SentinelVault.InvalidLimits.selector);
            new SentinelVault(usdc, owner, agent, 1, 1, 0);
        }

        // --- pay ----------------------------------------------------------------

        function test_pay_movesFundsAndEmits() public {
            vm.expectEmit(true, true, true, true, address(vault));
            emit Payment(1, merchant, 7 * USDC, memo("inv-1"), 7 * USDC);
            vm.prank(agent);
            uint256 id = vault.pay(merchant, 7 * USDC, memo("inv-1"));

            assertEq(id, 1);
            assertEq(usdc.balanceOf(merchant), 7 * USDC);
            assertEq(usdc.balanceOf(address(vault)), 93 * USDC);
            assertEq(vault.spentInPeriod(), 7 * USDC);
            assertEq(vault.remainingInPeriod(), 43 * USDC);
        }

        function test_pay_onlyAgent() public {
            vm.prank(owner);
            vm.expectRevert(SentinelVault.NotAgent.selector);
            vault.pay(merchant, 1, bytes32(0));
        }

        function test_pay_enforcesSingleLimit() public {
            vm.prank(agent);
            vm.expectRevert(
                abi.encodeWithSelector(
                    SentinelVault.PaymentRejected.selector, SentinelVault.Status.EXCEEDS_SINGLE_LIMIT
                )
            );
            vault.pay(merchant, 10 * USDC + 1, bytes32(0));
        }

        function test_pay_enforcesPeriodLimitAndRolls() public {
            vm.startPrank(agent);
            for (uint256 i = 0; i < 5; i++) {
                vault.pay(merchant, 10 * USDC, bytes32(i));
            }
            vm.expectRevert(
                abi.encodeWithSelector(
                    SentinelVault.PaymentRejected.selector, SentinelVault.Status.EXCEEDS_PERIOD_LIMIT
                )
            );
            vault.pay(merchant, 1, bytes32(0));

            vm.warp(block.timestamp + 1 days);
            assertEq(vault.remainingInPeriod(), 50 * USDC);
            vault.pay(merchant, 10 * USDC, memo("next"));
            vm.stopPrank();
            assertEq(vault.spentInPeriod(), 10 * USDC);
        }

        function test_pay_rejectsInvalidRecipientAndAmount() public {
            vm.startPrank(agent);
            vm.expectRevert(
                abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, SentinelVault.Status.INVALID_RECIPIENT)
            );
            vault.pay(address(0), 1, bytes32(0));
            vm.expectRevert(
                abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, SentinelVault.Status.INVALID_RECIPIENT)
            );
            vault.pay(address(vault), 1, bytes32(0));
            vm.expectRevert(
                abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, SentinelVault.Status.INVALID_AMOUNT)
            );
            vault.pay(merchant, 0, bytes32(0));
            vm.stopPrank();
        }

        function test_pay_allowlist() public {
            vm.prank(owner);
            vault.setAllowlistEnabled(true);

            vm.prank(agent);
            vm.expectRevert(
                abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, SentinelVault.Status.NOT_ALLOWLISTED)
            );
            vault.pay(merchant, 1, bytes32(0));

            vm.prank(owner);
            vault.setRecipient(merchant, true);
            vm.prank(agent);
            vault.pay(merchant, 1, bytes32(0));
            assertEq(usdc.balanceOf(merchant), 1);
        }

        function test_pay_insufficientBalance() public {
            vm.prank(owner);
            vault.withdraw(owner, 95 * USDC);
            vm.prank(agent);
            vm.expectRevert(
                abi.encodeWithSelector(
                    SentinelVault.PaymentRejected.selector, SentinelVault.Status.INSUFFICIENT_BALANCE
                )
            );
            vault.pay(merchant, 6 * USDC, bytes32(0));
        }

        function test_pause_blocksAgentButNotOwnerWithdraw() public {
            vm.prank(owner);
            vault.pause();
            vm.prank(agent);
            vm.expectRevert(abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, SentinelVault.Status.PAUSED));
            vault.pay(merchant, 1, bytes32(0));

            vm.prank(owner);
            vault.withdraw(owner, 100 * USDC);
            assertEq(usdc.balanceOf(owner), 100 * USDC);

            vm.prank(owner);
            vault.unpause();
            assertFalse(vault.paused());
        }

        function test_transferReturningFalseReverts() public {
            usdc.setReturnFalse(true);
            vm.prank(agent);
            vm.expectRevert(SentinelVault.TransferFailed.selector);
            vault.pay(merchant, 1, bytes32(0));
            assertEq(vault.spentInPeriod(), 0, "state rolled back");
        }

        function test_reentrancyBlocked() public {
            ReentrantToken evil = new ReentrantToken();
            SentinelVault v = new SentinelVault(evil, owner, address(evil), 10, 100, 1 days);
            evil.setVault(v);
            evil.mint(address(v), 100);
            vm.expectRevert(SentinelVault.Reentrancy.selector);
            evil.startPay(merchant, 5);
            assertEq(evil.balanceOf(address(v)), 100, "no funds moved");
            assertEq(v.spentInPeriod(), 0);
        }

        // --- owner --------------------------------------------------------------

        function test_ownerOnlyAdmin() public {
            vm.startPrank(agent);
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.setAgent(agent);
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.setLimits(1, 1, 1);
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.withdraw(agent, 1);
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.pause();
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.setAllowlistEnabled(false);
            vm.expectRevert(SentinelVault.NotOwner.selector);
            vault.transferOwnership(agent);
            vm.stopPrank();
        }

        function test_setAgentRotatesKey() public {
            address newAgent = makeAddr("newAgent");
            vm.prank(owner);
            vault.setAgent(newAgent);
            vm.prank(agent);
            vm.expectRevert(SentinelVault.NotAgent.selector);
            vault.pay(merchant, 1, bytes32(0));
            vm.prank(newAgent);
            vault.pay(merchant, 1, bytes32(0));
        }

        function test_twoStepOwnership() public {
            address newOwner = makeAddr("newOwner");
            vm.prank(owner);
            vault.transferOwnership(newOwner);
            assertEq(vault.owner(), owner);

            vm.prank(agent);
            vm.expectRevert(SentinelVault.NotPendingOwner.selector);
            vault.acceptOwnership();

            vm.prank(newOwner);
            vault.acceptOwnership();
            assertEq(vault.owner(), newOwner);
            assertEq(vault.pendingOwner(), address(0));
        }

        function test_policySnapshot() public {
            vm.prank(agent);
            vault.pay(merchant, 3 * USDC, bytes32(0));
            SentinelVault.Policy memory p = vault.policy();
            assertEq(p.owner, owner);
            assertEq(p.agent, agent);
            assertEq(p.token, address(usdc));
            assertEq(p.maxPerTx, 10 * USDC);
            assertEq(p.maxPerPeriod, 50 * USDC);
            assertEq(p.periodSeconds, 1 days);
            assertEq(p.spentInPeriod, 3 * USDC);
            assertEq(p.balance, 97 * USDC);
            assertFalse(p.paused);

            vm.warp(block.timestamp + 1 days);
            assertEq(vault.policy().spentInPeriod, 0, "expired period reads as zero");
        }

        function test_checkAndPeriodEndViews() public {
            (SentinelVault.Status status, uint256 remaining) = vault.check(merchant, 5 * USDC);
            assertEq(uint8(status), uint8(SentinelVault.Status.OK));
            assertEq(remaining, 50 * USDC);
            uint64 end = vault.currentPeriodEnd();
            assertEq(end, vault.periodStart() + 1 days);
            vm.warp(end + 10);
            assertEq(vault.currentPeriodEnd(), uint64(block.timestamp) + 1 days);
        }

        // --- fuzz ---------------------------------------------------------------

        /// `check` must predict `pay` exactly.
        function testFuzz_checkPredictsPay(uint256 amount, uint32 elapsed, bool allowlist, bool allowMerchant) public {
            amount = bound(amount, 0, 120 * USDC);
            vm.prank(agent);
            vault.pay(owner, 9 * USDC, memo("pre"));
            vm.startPrank(owner);
            vault.setAllowlistEnabled(allowlist);
            vault.setRecipient(merchant, allowMerchant);
            vm.stopPrank();
            vm.warp(block.timestamp + elapsed);

            (SentinelVault.Status status,) = vault.check(merchant, amount);
            vm.prank(agent);
            if (status == SentinelVault.Status.OK) {
                vault.pay(merchant, amount, bytes32(0));
            } else {
                vm.expectRevert(abi.encodeWithSelector(SentinelVault.PaymentRejected.selector, status));
                vault.pay(merchant, amount, bytes32(0));
            }
        }

        /// Spend inside any single period never exceeds the period cap.
        function testFuzz_periodCapHolds(uint256[8] memory amounts, uint16[8] memory gaps) public {
            uint256 spentThisPeriod;
            uint256 periodStartTs = block.timestamp;
            for (uint256 i = 0; i < amounts.length; i++) {
                vm.warp(block.timestamp + gaps[i]);
                if (block.timestamp >= periodStartTs + 1 days) {
                    periodStartTs = block.timestamp;
                    spentThisPeriod = 0;
                }
                uint256 amt = bound(amounts[i], 1, 10 * USDC);
                usdc.mint(address(vault), amt);
                vm.prank(agent);
                try vault.pay(merchant, amt, bytes32(i)) {
                    spentThisPeriod += amt;
                } catch {}
                assertLe(spentThisPeriod, 50 * USDC);
                assertLe(vault.spentInPeriod(), 50 * USDC);
            }
        }
    }
