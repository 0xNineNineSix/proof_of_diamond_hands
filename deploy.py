# @version ^0.3.7

# Chainlink Aggregator V3 Interface
interface AggregatorV3Interface:
    def latestRoundData() -> (uint80, int256, uint256, uint256, uint80): view

# Uniswap V3 Swap Router Interface
interface UniswapV3Router:
    def exactInputSingle(params: ExactInputSingleParams) -> uint256: nonpayable

# ERC-20 Interface for wstETH transfers
interface ERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable

# Struct for Uniswap V3 exactInputSingle parameters
struct ExactInputSingleParams:
    tokenIn: address
    tokenOut: address
    fee: uint24
    recipient: address
    deadline: uint256
    amountIn: uint256
    amountOutMinimum: uint256
    sqrtPriceLimitX96: uint160

# Mainnet addresses
PRICE_FEED_ETH_USD: constant(address) = 0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419  # Chainlink ETH/USD
PRICE_FEED_WSTETH_ETH: constant(address) = 0x524299aCeDB6d4A39b6b8D6E229dE7f644f12122  # Chainlink wstETH/ETH
UNISWAP_ROUTER: constant(address) = 0xE592427A0AEce92De3Edee1F18E0157C05861564  # Uniswap V3 SwapRouter
WSTETH: constant(address) = 0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0  # Lido wstETH

# Minimum and maximum deposit amounts (in wei)
MIN_DEPOSIT: constant(uint256) = 100000000000000000  # 0.1 ETH
MAX_DEPOSIT: constant(uint256) = 100000000000000000000  # 100 ETH

# Uniswap V3 pool fee (0.01% for ETH/wstETH pair)
UNISWAP_FEE: constant(uint24) = 100  # Changed from 3000 (0.3%) to 100 (0.01%)

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

# Multi-sig governance address
admin: immutable(address)

# Mapping to store user balances (in wstETH)
balances: public(HashMap[address, uint256])

# Mapping to store the price specified during deposit
deposit_prices: public(HashMap[address, uint256])

# Mapping to track active depositors
is_depositor: public(HashMap[address, bool])

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
def __init__(admin_addr: address):
    admin = admin_addr

@external
@payable
def deposit(price_usd: uint256, slippage_bps: uint256, tip_bps: uint256):
    """
    Swaps ETH to wstETH via Uniswap V3 with user-specified slippage and optional tip to admin.
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

    # Swap ETH to wstETH via Uniswap V3
    router: UniswapV3Router = UniswapV3Router(UNISWAP_ROUTER)
    params: ExactInputSingleParams = ExactInputSingleParams({
        tokenIn: empty(address),  # ETH
        tokenOut: WSTETH,
        fee: UNISWAP_FEE,
        recipient: self,
        deadline: block.timestamp + 15,
        amountIn: swap_amount,
        amountOutMinimum: min_wsteth_out,
        sqrtPriceLimitX96: 0
    })
    wsteth_received: uint256 = router.exactInputSingle(params)

    # Store wstETH balance, price, and mark as depositor
    self.balances[msg.sender] = wsteth_received
    self.deposit_prices[msg.sender] = price_usd
    self.is_depositor[msg.sender] = True

    log Deposit(msg.sender, msg.value, wsteth_received, price_usd, slippage_bps, tip_bps, tip_amount)

@external
def withdraw():
    """
    Swaps wstETH to ETH with default 1% slippage if ETH/USD price exceeds deposit price and data is fresh.
    """
    assert self.balances[msg.sender] > 0, "No balance to withdraw"

    # Check ETH/USD oracle
    oracle_eth: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_ETH_USD)
    (round_id_e, answer_e, started_at_e, updated_at_e, answered_in_round_e) = oracle_eth.latestRoundData()
    assert answer_e > 0, "Invalid ETH/USD price"
    assert block.timestamp <= updated_at_e + MAX_ORACLE_AGE, "ETH/USD oracle too old"
    current_price: uint256 = convert(answer_e, uint256)
    assert current_price > self.deposit_prices[msg.sender], "Oracle price too low"

    # Default slippage
    slippage_bps: uint256 = 100
    self._withdraw_with_slippage(slippage_bps)

@external
def withdraw_with_slippage(slippage_bps: uint256):
    """
    Swaps wstETH to ETH with user-specified slippage if ETH/USD price exceeds deposit price and data is fresh.
    @param slippage_bps Slippage tolerance in basis points (e.g., 100 = 1%).
    """
    assert self.balances[msg.sender] > 0, "No balance to withdraw"
    assert slippage_bps >= MIN_SLIPPAGE_BPS, "Slippage too low"
    assert slippage_bps <= MAX_SLIPPAGE_BPS, "Slippage too high"

    # Check ETH/USD oracle
    oracle_eth: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED_ETH_USD)
    (round_id_e, answer_e, started_at_e, updated_at_e, answered_in_round_e) = oracle_eth.latestRoundData()
    assert answer_e > 0, "Invalid ETH/USD price"
    assert block.timestamp <= updated_at_e + MAX_ORACLE_AGE, "ETH/USD oracle too old"
    current_price: uint256 = convert(answer_e, uint256)
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

    # Approve Uniswap router
    raw_call(
        WSTETH,
        method_id("approve(address,uint256)", bytes[4]) +
        convert(UNISWAP_ROUTER, bytes32) +
        convert(wsteth_amount, bytes32),
        is_delegate_call=False
    )

    # Swap wstETH to ETH
    router: UniswapV3Router = UniswapV3Router(UNISWAP_ROUTER)
    params: ExactInputSingleParams = ExactInputSingleParams({
        tokenIn: WSTETH,
        tokenOut: empty(address),
        fee: UNISWAP_FEE,
        recipient: msg.sender,
        deadline: block.timestamp + 15,
        amountIn: wsteth_amount,
        amountOutMinimum: min_eth_out,
        sqrtPriceLimitX96: 0
    })
    eth_received: uint256 = router.exactInputSingle(params)

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
    Fallback to receive ETH from Uniswap swaps.
    """
    pass