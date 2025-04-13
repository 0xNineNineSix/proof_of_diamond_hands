# @version ^0.3.7

# Chainlink Aggregator V3 Interface
interface AggregatorV3Interface:
    def latestRoundData() -> (uint80, int256, uint256, uint256, uint80): view

# Mainnet addresses
PRICE_FEED: constant(address) = 0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419  # Chainlink ETH/USD

# Constants
MIN_DEPOSIT: constant(uint256) = 100000000000000000  # 0.1 ETH
MAX_DEPOSIT: constant(uint256) = 100000000000000000000  # 100 ETH
MAX_ORACLE_AGE: constant(uint256) = 900  # 15 minutes

# Storage
balances: public(HashMap[address, uint256])  # ETH balance per user
deposit_prices: public(HashMap[address, uint256])  # USD price threshold per user

# Events
event Deposit:
    sender: indexed(address)
    amount: uint256
    price_usd: uint256

event Withdraw:
    sender: indexed(address)
    amount: uint256

@external
def __init__():
    pass

@external
@payable
def deposit(price_usd: uint256):
    """
    Deposits ETH with a price threshold.
    @param price_usd The ETH/USD price threshold for withdrawal (scaled by 10**8).
    """
    assert msg.value >= MIN_DEPOSIT, "Deposit too low"
    assert msg.value <= MAX_DEPOSIT, "Deposit too high"
    assert price_usd > 0, "Invalid price"
    assert self.balances[msg.sender] == 0, "Existing deposit"

    self.balances[msg.sender] = msg.value
    self.deposit_prices[msg.sender] = price_usd

    log Deposit(msg.sender, msg.value, price_usd)

@external
def withdraw():
    """
    Withdraws ETH if current ETH/USD price exceeds deposit price.
    """
    assert self.balances[msg.sender] > 0, "No balance"

    # Check Chainlink price
    oracle: AggregatorV3Interface = AggregatorV3Interface(PRICE_FEED)
    price_data: (uint80, int256, uint256, uint256, uint80) = oracle.latestRoundData()
    assert price_data[1] > 0, "Invalid price"
    assert block.timestamp <= price_data[3] + MAX_ORACLE_AGE, "Oracle too old"
    current_price: uint256 = convert(price_data[1], uint256)
    assert current_price > self.deposit_prices[msg.sender], "Price too low"

    amount: uint256 = self.balances[msg.sender]
    self.balances[msg.sender] = 0
    self.deposit_prices[msg.sender] = 0

    send(msg.sender, amount)

    log Withdraw(msg.sender, amount)

@external
@view
def get_balance(user: address) -> uint256:
    """
    Returns the ETH balance of a user.
    """
    return self.balances[user]

@external
@view
def get_deposit_price(user: address) -> uint256:
    """
    Returns the deposit price threshold of a user.
    """
    return self.deposit_prices[user]

@external
@payable
def __default__():
    """
    Fallback to prevent accidental ETH transfers.
    """
    assert False, "Use deposit function"