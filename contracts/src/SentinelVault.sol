// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal ERC-20 surface used by the vault (USDC on Arc exposes this at
///         0x3600000000000000000000000000000000000000 with 6 decimals).
interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @title SentinelVault
/// @notice On-chain spend policy for an autonomous AI agent paying in USDC.
/// @dev The owner (a human) funds the vault and sets policy. The agent key can only move
///      funds through `pay`, which enforces a per-transaction cap, a per-period cap, an
///      optional recipient allowlist, and a pause switch. This makes the FastMCP-Sentinel
///      off-chain guard *enforceable*: a compromised or prompt-injected agent cannot spend
///      beyond policy even if it bypasses the MCP server entirely.
///      All amounts are in the token's base units (USDC: 6 decimals).
contract SentinelVault {
    /// @notice Result codes for `check`, mirroring the off-chain guard where they overlap.
    enum Status {
        OK,
        PAUSED,
        INVALID_RECIPIENT,
        INVALID_AMOUNT,
        EXCEEDS_SINGLE_LIMIT,
        EXCEEDS_PERIOD_LIMIT,
        NOT_ALLOWLISTED,
        INSUFFICIENT_BALANCE
    }

    struct Policy {
        address owner;
        address agent;
        address token;
        uint256 maxPerTx;
        uint256 maxPerPeriod;
        uint64 periodSeconds;
        uint64 periodStart;
        uint256 spentInPeriod;
        bool allowlistEnabled;
        bool paused;
        uint256 balance;
    }

    IERC20 public immutable token;
    address public owner;
    address public pendingOwner;
    address public agent;

    uint256 public maxPerTx;
    uint256 public maxPerPeriod;
    uint64 public periodSeconds;
    uint64 public periodStart;
    uint256 public spentInPeriod;

    bool public allowlistEnabled;
    bool public paused;
    mapping(address => bool) public isAllowedRecipient;

    uint256 public paymentCount;
    uint256 private _locked = 1;

    event Payment(uint256 indexed id, address indexed to, uint256 amount, bytes32 indexed memo, uint256 spentInPeriod);
    event AgentUpdated(address indexed previousAgent, address indexed newAgent);
    event LimitsUpdated(uint256 maxPerTx, uint256 maxPerPeriod, uint64 periodSeconds);
    event RecipientUpdated(address indexed recipient, bool allowed);
    event AllowlistToggled(bool enabled);
    event Paused(address indexed by);
    event Unpaused(address indexed by);
    event Withdrawn(address indexed to, uint256 amount);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error NotOwner();
    error NotAgent();
    error NotPendingOwner();
    error ZeroAddress();
    error InvalidToken();
    error InvalidLimits();
    error PaymentRejected(Status status);
    error TransferFailed();
    error Reentrancy();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_locked != 1) revert Reentrancy();
        _locked = 2;
        _;
        _locked = 1;
    }

    constructor(
        IERC20 token_,
        address owner_,
        address agent_,
        uint256 maxPerTx_,
        uint256 maxPerPeriod_,
        uint64 periodSeconds_
    ) {
        if (address(token_) == address(0) || owner_ == address(0) || agent_ == address(0)) {
            revert ZeroAddress();
        }
        // A codeless token would make every low-level transfer "succeed" without moving funds.
        if (address(token_).code.length == 0) revert InvalidToken();
        token = token_;
        owner = owner_;
        agent = agent_;
        _setLimits(maxPerTx_, maxPerPeriod_, periodSeconds_);
        periodStart = uint64(block.timestamp);
        emit OwnershipTransferred(address(0), owner_);
        emit AgentUpdated(address(0), agent_);
    }

    // ---------------------------------------------------------------------------------
    // Agent
    // ---------------------------------------------------------------------------------

    /// @notice Pay `amount` of the token to `to`. Only callable by the agent, within policy.
    /// @param memo Opaque reference (e.g. invoice id or hash of the agent's intent) for audit.
    function pay(address to, uint256 amount, bytes32 memo) external nonReentrant returns (uint256 id) {
        if (msg.sender != agent) revert NotAgent();
        _rollPeriod();
        Status status = _check(to, amount);
        if (status != Status.OK) revert PaymentRejected(status);

        spentInPeriod += amount;
        id = ++paymentCount;
        emit Payment(id, to, amount, memo, spentInPeriod);
        _safeTransfer(to, amount);
    }

    /// @notice Dry-run of `pay`: returns the status `pay` would produce right now and the
    ///         amount still spendable in the current period.
    function check(address to, uint256 amount) external view returns (Status status, uint256 remaining) {
        remaining = remainingInPeriod();
        status = _checkWith(to, amount, _effectiveSpent());
    }

    // ---------------------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------------------

    function remainingInPeriod() public view returns (uint256) {
        uint256 spent = _effectiveSpent();
        return spent >= maxPerPeriod ? 0 : maxPerPeriod - spent;
    }

    function currentPeriodEnd() public view returns (uint64) {
        return _isPeriodOver() ? uint64(block.timestamp) + periodSeconds : periodStart + periodSeconds;
    }

    function policy() external view returns (Policy memory p) {
        p = Policy({
            owner: owner,
            agent: agent,
            token: address(token),
            maxPerTx: maxPerTx,
            maxPerPeriod: maxPerPeriod,
            periodSeconds: periodSeconds,
            periodStart: _isPeriodOver() ? uint64(block.timestamp) : periodStart,
            spentInPeriod: _effectiveSpent(),
            allowlistEnabled: allowlistEnabled,
            paused: paused,
            balance: token.balanceOf(address(this))
        });
    }

    // ---------------------------------------------------------------------------------
    // Owner
    // ---------------------------------------------------------------------------------

    function setAgent(address newAgent) external onlyOwner {
        if (newAgent == address(0)) revert ZeroAddress();
        emit AgentUpdated(agent, newAgent);
        agent = newAgent;
    }

    function setLimits(uint256 maxPerTx_, uint256 maxPerPeriod_, uint64 periodSeconds_) external onlyOwner {
        _setLimits(maxPerTx_, maxPerPeriod_, periodSeconds_);
    }

    function setAllowlistEnabled(bool enabled) external onlyOwner {
        allowlistEnabled = enabled;
        emit AllowlistToggled(enabled);
    }

    function setRecipient(address recipient, bool allowed) external onlyOwner {
        if (recipient == address(0)) revert ZeroAddress();
        isAllowedRecipient[recipient] = allowed;
        emit RecipientUpdated(recipient, allowed);
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }

    /// @notice Owner can always recover funds, regardless of pause or agent policy.
    function withdraw(address to, uint256 amount) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddress();
        emit Withdrawn(to, amount);
        _safeTransfer(to, amount);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }

    // ---------------------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------------------

    function _setLimits(uint256 maxPerTx_, uint256 maxPerPeriod_, uint64 periodSeconds_) private {
        if (maxPerTx_ == 0 || maxPerTx_ > maxPerPeriod_ || periodSeconds_ == 0) revert InvalidLimits();
        maxPerTx = maxPerTx_;
        maxPerPeriod = maxPerPeriod_;
        periodSeconds = periodSeconds_;
        emit LimitsUpdated(maxPerTx_, maxPerPeriod_, periodSeconds_);
    }

    function _isPeriodOver() private view returns (bool) {
        return block.timestamp >= uint256(periodStart) + periodSeconds;
    }

    function _effectiveSpent() private view returns (uint256) {
        return _isPeriodOver() ? 0 : spentInPeriod;
    }

    function _rollPeriod() private {
        if (_isPeriodOver()) {
            periodStart = uint64(block.timestamp);
            spentInPeriod = 0;
        }
    }

    function _check(address to, uint256 amount) private view returns (Status) {
        return _checkWith(to, amount, spentInPeriod);
    }

    function _checkWith(address to, uint256 amount, uint256 spent) private view returns (Status) {
        if (paused) return Status.PAUSED;
        if (to == address(0) || to == address(this)) return Status.INVALID_RECIPIENT;
        if (amount == 0) return Status.INVALID_AMOUNT;
        if (allowlistEnabled && !isAllowedRecipient[to]) return Status.NOT_ALLOWLISTED;
        if (amount > maxPerTx) return Status.EXCEEDS_SINGLE_LIMIT;
        if (spent + amount > maxPerPeriod) return Status.EXCEEDS_PERIOD_LIMIT;
        if (token.balanceOf(address(this)) < amount) return Status.INSUFFICIENT_BALANCE;
        return Status.OK;
    }

    function _safeTransfer(address to, uint256 amount) private {
        (bool ok, bytes memory ret) = address(token).call(abi.encodeCall(IERC20.transfer, (to, amount)));
        if (!ok) {
            if (ret.length == 0) revert TransferFailed();
            // Bubble up the token's revert reason so failures stay diagnosable.
            assembly ("memory-safe") {
                revert(add(ret, 32), mload(ret))
            }
        }
        if (ret.length != 0 && !abi.decode(ret, (bool))) revert TransferFailed();
    }
}
