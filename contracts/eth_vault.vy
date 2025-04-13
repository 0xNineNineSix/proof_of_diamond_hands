# @version ^0.3.7

# Chainlink Aggregator V3 Interface
interface AggregatorV3Interface:
    def latestRoundData() -> (uint80, int256, uint256, uint256, uint80): view

# 1inch AggregationRouterV5 Interface (simplified for Vyper)
interface OneInchRouter:
    def swap(
        executor: address,
        desc: SwapDescription,
        permit: bytes,
        data: bytes
    ) -> (uint256, uint256): nonpayable

# ERC-20 Interface for wstETH transfers
interface ERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable

# Struct for 1inch swap description
struct SwapDescription:
    srcToken: address
    dstToken: address
    srcReceiver: address
    dstReceiver: address
    amount: uint256
    minReturnAmount: uint256
    flags: uint256

# Struct for deposit info return
struct DepositInfo:
    depositor: address
    wsteth_amount: uint256
    price_usd: uint256

# Mainnet addresses
PRICE_FEED_ETH_USD: constant(address) = 0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419  # Chainlink ETH/USD
PRICE_FEED_WSTETH_ETH: constant(address) = 0x524299aCeDB6d4A39b6b8D6E229dE7f644f12122  # Chainlink wstETH/ETH
INCH_ROUTER: constant(address) = 0x1111111254EEB25477B68fb85Ed929f73A960582  # 1inch AggregationRouterV5
WSTETH: constant(address) = 0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0  # Lido wstETH

# Minimum and maximum deposit amounts (in wei)
MIN_DEPOSIT: constant(uint256) = 100000000000000000  # 0.1 ETH
MAX_DEPOSIT: constant(uint256) = 100000000000000000000  # 100 ETH

# Basis points denominator
BPS_DENOMINATOR: constant(uint256) = 10000  # 100% = 10000 bps

# Slippage constraints
MIN_SLIPPAGE_BPS: constant(uint256) = 10  # 0.1%
MAX_SLIPPAGE_BPS: constant(uint256) = 500  # 5%

# Tip constraints
MAX_TIP_BPS: constant(uint256) = 500  # 5%

# Oracle staleness threshold (15 minutes = 900 seconds)
MAX_ORACLE_AGE: constant(uint256) = 900  # 15 minutes

# Maximum depositors per batch emergency withdrawal
MAX_BATCH_SIZE: constant(uint256) = 50

# Maximum deposits returned by get_all_deposits
MAX_DEPOSITS_RETURN: constant(uint256) = 100

# Multi-sig governance address
admin: immutable(address)

# Mapping to store user balances (in wstETH)
balances: public(HashMap[address, uint256])

# Mapping to store the price specified during deposit
deposit_prices: public(HashMap[address, uint256])

# Mapping to track active depositors
is_depositor: public(HashMap[address, bool])

# Array to store depositor addresses
depositors: public(address[MAX_DEPOSITORS])

# Number of active depositors
depositor_count: public(uint256)

# Event for deposits
event Deposit:
    sender: indexed(address)
    eth_amount: uint256
    wsteth_amount: uint256
    price_usd: uint256
    slippage_bps: uint256
    tip_bps: uint256
    tip_amount: uint256

# Event for withdrawals
event Withdraw:
    sender: indexed(address)
    eth_amount: uint256
    wsteth_amount: uint256
    slippage_bps: uint256

# Event for emergency withdrawals
event EmergencyWithdraw:
    depositor: indexed(address)
    wsteth_amount: uint256
    initiated_by: indexed(address)

@external
@view
def get_all_deposits() -> DynArray[DepositInfo, MAX_DEPOSITS_RETURN]:
    """
    Returns a list of all active depositors with their balances and price levels.
    @return An array of DepositInfo structs (depositor, wsteth_amount, price_usd).
    """
    deposits: DynArray[DepositInfo, MAX_DEPOSITS_RETURN] = []
    for i in range(MAX_DEPOSITORS):
        if i >= self.depositor_count:
            break
        depositor: address = self.depositors[i]
        if depositor == empty(address) or self.balances[depositor] == 0:
            continue
        deposits.append(DepositInfo({
            depositor: depositor,
            wsteth_amount: self.balances[depositor],
            price_usd: self.deposit_prices[depositor]
        }))
    return deposits

@external
def __init__(admin_addr: address):
    admin = admin_addr

@external
@payable
def deposit(price_usd: uint256, slippage_bps: uint256, tip_bps: uint256):
    """
    Swaps ETH to wstETH via 1inch with user-specified slippage and optional tip to admin.
    @param price_usd The price (in USD, scaled by 10**8) for withdrawal condition.
    @param slippage_bps Slippage tolerance in basis points (e.g., 100 = 1%).
    @param tip_bps Tip in basis points (e.g., 100 = 1%) to send to admin, optional.
    """
    assert msg.value >= MIN_DEPOSIT, "Deposit below minimum"
    assert msg.value <= MAX_DEPOSIT, "Deposit above maximum"
    assert price_usd > 0, "Price must be greater than 0"
    assert slippage_bps >= MIN_SLIPPAGE_BPS, "Slippage too low"
    assert slippage_bps <= MAX_SLIPPAGE_BPS, "Slippage too high"
    assert tip_bps <= MAX_TIP_BPS, "Tip too high"
    assert self.balances[msg.sender] == 0, "Existing deposit must be withdrawn first"

    # Calculate and send tip
    tip_amount: uint256 = (msg.value * tip_bps) / BPS_DENOMINATOR
    swap_amount: uint256 = msg.value - tip_amount
    assert swap_amount > 0, "Swap amount too low"

    if tip_amount > 0:
        send(admin, tip_amount)

    # Check wstETH/ETH oracle for slippage calculation
    oracle_wsteth: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_WSTETH_ETH)
    (round_id_w, answer_w, started_at_w, updated_at_w, answered_in_round_w) = oracle_wsteth.latestRoundData()
    assert answer_w > 0, "Invalid wstETH/ETH price"
    assert block.timestamp <= updated_at_w + MAX_ORACLE_AGE, "wstETH/ETH oracle too old"
    wsteth_per_eth: uint256 = convert(answer_w, uint256)  # wstETH per ETH, scaled by 10**18

    # Estimate minimum wstETH output
    min_wsteth_out: uint256 = (swap_amount * wsteth_per_eth) / 10**18
    min_wsteth_out = min_wsteth_out * (BPS_DENOMINATOR - slippage_bps) / BPS_DENOMINATOR

    # Swap ETH to wstETH via 1inch
    router: OneInchRouter = OneInchRouter(INCH_ROUTER)
    desc: SwapDescription = SwapDescription({
        srcToken: empty(address),  # ETH
        dstToken: WSTETH,
        srcReceiver: self,
        dstReceiver: self,
        amount: swap_amount,
        minReturnAmount: min_wsteth_out,
        flags: 0  # Default flags
    })
    (return_amount, spent_amount) = router.swap(empty(address), desc, b"", b"")
    wsteth_received: uint256 = return_amount

    # Store wstETH balance and price
    self.balances[msg.sender] = wsteth_received
    self.deposit_prices[msg.sender] = price_usd
    self.is_depositor[msg.sender] = True

    log Deposit(msg.sender, msg.value, wsteth_received, price_usd, slippage_bps, tip_bps, tip_amount)

@external
def withdraw():
    """
    Swaps wstETH back to ETH via 1inch with default slippage (1%) if oracle price exceeds deposit price and data is fresh.
    """
    assert self.balances[msg.sender] > 0, "No balance to withdraw"

    # Check Chainlink oracle price and freshness
    oracle: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_ETH_USD)
    (round_id, answer, started_at, updated_at, answered_in_round) = oracle.latestRoundData()
    assert answer > 0, "Invalid oracle price"
    assert block.timestamp <= updated_at + MAX_ORACLE_AGE, "Oracle data too old"
    current_price: uint256 = convert(answer, uint256)
    assert current_price > self.deposit_prices[msg.sender], "Oracle price too low"

    # Use default slippage of 1% (100 bps)
    slippage_bps: uint256 = 100
    self._withdraw_with_slippage(slippage_bps)

@external
def withdraw_with_slippage(slippage_bps: uint256):
    """
    Swaps wstETH back to ETH via 1inch with user-specified slippage if oracle price exceeds deposit price and data is fresh.
    @param slippage_bps Slippage tolerance in basis points (e.g., 100 = 1%).
    """
    assert self.balances[msg.sender] > 0, "No balance to withdraw"
    assert slippage_bps >= MIN_SLIPPAGE_BPS, "Slippage too low"
    assert slippage_bps <= MAX_SLIPPAGE_BPS, "Slippage too high"

    # Check Chainlink oracle price and freshness
    oracle: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_ETH_USD)
    (round_id, answer, started_at, updated_at, answered_in_round) = oracle.latestRoundData()
    assert answer > 0, "Invalid oracle price"
    assert block.timestamp <= updated_at + MAX_ORACLE_AGE, "Oracle data too old"
    current_price: uint256 = convert(answer, uint256)
    assert current_price > self.deposit_prices[msg.sender], "Oracle price too low"

    self._withdraw_with_slippage(slippage_bps)

@internal
def _withdraw_with_slippage(slippage_bps: uint256):
    """
    Internal function to perform wstETH to ETH swap with specified slippage.
    """
    wsteth_amount: uint256 = self.balances[msg.sender]
    self.balances[msg.sender] = 0
    self.deposit_prices[msg.sender] = 0
    self.is_depositor[msg.sender] = False

    # Check wstETH/ETH oracle for slippage
    oracle_wsteth: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_WSTETH_ETH)
    (round_id_w, answer_w, started_at_w, updated_at_w, answered_in_round_w) = oracle_wsteth.latestRoundData()
    assert answer_w > 0, "Invalid wstETH/ETH price"
    assert block.timestamp <= updated_at_w + MAX_ORACLE_AGE, "wstETH/ETH oracle too old"
    wsteth_per_eth: uint256 = convert(answer_w, uint256)  # wstETH per ETH, scaled by 10**18

    # Estimate minimum ETH output
    eth_per_wsteth: uint256 = (10**36) / wsteth_per_eth  # ETH per wstETH, scaled by 10**18
    min_eth_out: uint256 = (wsteth_amount * eth_per_wsteth) / 10**18
    min_eth_out = min_eth_out * (BPS_DENOMINATOR - slippage_bps) / BPS_DENOMINATOR

    # Approve 1inch router to spend wstETH
    raw_call(
        WSTETH,
        method_id("approve(address,uint256)", bytes[4]) +
        convert(INCH_ROUTER, bytes32) +
        convert(wsteth_amount, bytes32),
        is_delegate_call=False
    )

    # Swap wstETH to ETH via 1inch
    router: OneInchRouter = OneInchRouter(INCH_ROUTER)
    desc: SwapDescription = SwapDescription({
        srcToken: WSTETH,
        dstToken: empty(address),  # ETH
        srcReceiver: self,
        dstReceiver: msg.sender,
        amount: wsteth_amount,
        minReturnAmount: min_eth_out,
        flags: 0  # Default flags
    })
    (return_amount, spent_amount) = router.swap(empty(address), desc, b"", b"")
    eth_received: uint256 = return_amount

    log Withdraw(msg.sender, eth_received, wsteth_amount, slippage_bps)

@external
def emergency_withdraw(depositor: address):
    """
    Allows the admin to return wstETH to a specific depositor without swapping.
    @param depositor The address to withdraw wstETH for.
    """
    assert msg.sender == admin, "Only admin can call"
    assert self.is_depositor[depositor], "Not a depositor"
    assert self.balances[depositor] > 0, "No balance"

    wsteth_amount: uint256 = self.balances[depositor]
    self.balances[depositor] = 0
    self.deposit_prices[depositor] = 0
    self.is_depositor[depositor] = False

    ERC20(WSTETH).transfer(depositor, wsteth_amount)
    log EmergencyWithdraw(depositor, wsteth_amount, msg.sender)

@external
def emergency_withdraw_batch(depositors: address[MAX_BATCH_SIZE]):
    """
    Allows the admin to return wstETH to multiple depositors without swapping.
    @param depositors Array of depositor addresses (up to MAX_BATCH_SIZE).
    """
    assert msg.sender == admin, "Only admin can call"

    for i in range(MAX_BATCH_SIZE):
        depositor: address = depositors[i]
        if depositor == empty(address):
            break
        if not self.is_depositor[depositor] or self.balances[depositor] == 0:
            continue
        wsteth_amount: uint256 = self.balances[depositor]
        self.balances[depositor] = 0
        self.deposit_prices[depositor] = 0
        self.is_depositor[depositor] = False
        ERC20(WSTETH).transfer(depositor, wsteth_amount)
        log EmergencyWithdraw(depositor, wsteth_amount, msg.sender)

@external
@view
def get_balance(user: address) -> uint256:
    """
    Returns the wstETH balance of a user.
    @param user The address to query.
    @return The user's balance in wstETH (wei).
    """
    return self.balances[user]

@external
@view
def get_deposit_price(user: address) -> uint256:
    """
    Returns the deposit price of a user.
    @param user The address to query.
    @return The user's deposit price in USD (scaled by 10**8).
    """
    return self.deposit_prices[user]

@external
@view
def get_latest_oracle_price() -> uint256:
    """
    Returns the latest ETH/USD price from the Chainlink oracle.
    @return The price scaled by 10**8.
    """
    oracle: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_ETH_USD)
    (round_id, answer, started_at, updated_at, answered_in_round) = oracle.latestRoundData()
    assert answer > 0, "Invalid ETH/USD price"
    assert block.timestamp <= updated_at + MAX_ORACLE_AGE, "ETH/USD oracle too old"
    return convert(answer, uint256)

@external
@payable
def __default__():
    """
    Fallback to receive ETH from 1inch swaps.
    """
    pass