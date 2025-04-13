from web3 import Web3
import json
import os

# Connect to mainnet fork
w3 = Web3(Web3.HTTPProvider(os.environ['TESTNET_URL']))
assert w3.is_connected(), "Failed to connect to node"

# Set up accounts
private_key = os.environ['PRIVATE_KEY']
admin = w3.eth.account.from_key(private_key)
w3.eth.default_account = admin.address

# Second account for testing
second_account = w3.eth.account.create()
print(f"Second account for testing: {second_account.address}")

# Load contract
with open('eth_vault_abi.json', 'r') as f:
    abi = json.load(f)
with open('contract_address.txt', 'r') as f:
    contract_address = f.read().strip()
contract = w3.eth.contract(address=contract_address, abi=abi)

# Check oracle price
try:
    oracle_price = contract.functions.get_latest_oracle_price().call()
    print(f"Current ETH/USD Price: {oracle_price / 10**8} USD")
except Exception as e:
    print(f"Oracle price check failed: {str(e)}")

# Test deposit below minimum
deposit_price_1 = int(oracle_price * 0.95)
deposit_amount_too_low = w3.to_wei(0.05, 'ether')
try:
    tx_hash = contract.functions.deposit(deposit_price_1, 100, 0).transact({'value': deposit_amount_too_low})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Deposit below minimum succeeded (unexpected!)")
except Exception as e:
    print(f"Deposit below minimum failed (expected): {str(e)}")

# Test deposit: 1 ETH, 0.5% slippage, 1% tip
deposit_amount_1 = w3.to_wei(1, 'ether')
slippage_bps_1 = 50
tip_bps_1 = 100
admin_balance_before = w3.eth.get_balance(admin.address)
tx_hash = contract.functions.deposit(deposit_price_1, slippage_bps_1, tip_bps_1).transact({'value': deposit_amount_1})
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
for log in receipt['logs']:
    if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="Deposit(address,uint256,uint256,uint256,uint256,uint256,uint256)").hex():
        eth_amount = int.from_bytes(log['data'][0:32], 'big')
        wsteth_amount = int.from_bytes(log['data'][32:64], 'big')
        event_slippage = int.from_bytes(log['data'][96:128], 'big')
        event_tip_bps = int.from_bytes(log['data'][128:160], 'big')
        event_tip_amount = int.from_bytes(log['data'][160:192], 'big')
        print(f"First Deposit: {eth_amount / 10**18} ETH for {wsteth_amount / 10**18} wstETH, price {deposit_price_1 / 10**8} USD, slippage {event_slippage} bps, tip {event_tip_bps} bps ({event_tip_amount / 10**18} ETH)")
        break
admin_balance_after = w3.eth.get_balance(admin.address)
print(f"Admin received tip: {(admin_balance_after - admin_balance_before) / 10**18} ETH")

# Test deposit with no tip
deposit_price_2 = int(oracle_price * 0.9)
deposit_amount_2 = w3.to_wei(2, 'ether')
slippage_bps_2 = 100
tip_bps_2 = 0
admin_balance_before = w3.eth.get_balance(admin.address)
tx_hash = contract.functions.deposit(deposit_price_2, slippage_bps_2, tip_bps_2).transact({'value': deposit_amount_2})
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
for log in receipt['logs']:
    if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="Deposit(address,uint256,uint256,uint256,uint256,uint256,uint256)").hex():
        eth_amount = int.from_bytes(log['data'][0:32], 'big')
        wsteth_amount = int.from_bytes(log['data'][32:64], 'big')
        event_slippage = int.from_bytes(log['data'][96:128], 'big')
        event_tip_bps = int.from_bytes(log['data'][128:160], 'big')
        event_tip_amount = int.from_bytes(log['data'][160:192], 'big')
        print(f"Second Deposit: {eth_amount / 10**18} ETH for {wsteth_amount / 10**18} wstETH, price {deposit_price_2 / 10**8} USD, slippage {event_slippage} bps, tip {event_tip_bps} bps ({event_tip_amount / 10**18} ETH)")
        break
admin_balance_after = w3.eth.get_balance(admin.address)
print(f"Admin received tip: {(admin_balance_after - admin_balance_before) / 10**18} ETH")

# Test withdrawal
try:
    tx_hash = contract.functions.withdraw().transact()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    for log in receipt['logs']:
        if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="Withdraw(address,uint256,uint256,uint256)").hex():
            eth_amount = int.from_bytes(log['data'][0:32], 'big')
            wsteth_amount = int.from_bytes(log['data'][32:64], 'big')
            event_slippage = int.from_bytes(log['data'][64:96], 'big')
            print(f"Withdrew: {wsteth_amount / 10**18} wstETH for {eth_amount / 10**18} ETH, slippage {event_slippage} bps")
            break
except Exception as e:
    print(f"Withdrawal failed: {str(e)}")

# Test emergency withdrawal (non-admin)
try:
    tx_hash = contract.functions.emergency_withdraw(admin.address).transact({'from': second_account.address})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Emergency withdraw by non-admin succeeded (unexpected!)")
except Exception as e:
    print(f"Emergency withdraw by non-admin failed (expected): {str(e)}")

# Test emergency withdrawal (admin)
try:
    tx_hash = contract.functions.emergency_withdraw(admin.address).transact()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    for log in receipt['logs']:
        if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="EmergencyWithdraw(address,uint256,address)").hex():
            wsteth_amount = int.from_bytes(log['data'][0:32], 'big')
            print(f"Emergency Withdraw: {wsteth_amount / 10**18} wstETH to {admin.address}")
            break
except Exception as e:
    print(f"Emergency withdraw failed: {str(e)}")

# Final balance check
balance = contract.functions.get_balance(admin.address).call()
stored_price = contract.functions.get_deposit_price(admin.address).call()
is_depositor = contract.functions.is_depositor(admin.address).call()
print(f"Final Balance: {balance / 10**18} wstETH")
print(f"Final Stored Deposit Price: {stored_price / 10**8} USD")
print(f"Final is_depositor: {is_depositor}")