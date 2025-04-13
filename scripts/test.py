from web3 import Web3
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to local Hardhat fork
w3 = Web3(Web3.HTTPProvider(os.environ.get('TESTNET_URL')))
assert w3.is_connected(), "Failed to connect to node"

# Use private key from .env
private_key = os.environ.get('PRIVATE_KEY')
account = w3.eth.account.from_key(private_key)
w3.eth.default_account = account.address

# Load contract
with open('scripts/eth_vault.json', 'r') as f:
    abi = json.load(f)
with open('scripts/contract_address.txt', 'r') as f:
    contract_address = f.read().strip()
contract = w3.eth.contract(address=contract_address, abi=abi)

# Test deposit below minimum
deposit_price_1 = 190000000000  # ~$1900, scaled by 10**8
deposit_amount_too_low = w3.to_wei(0.05, 'ether')
try:
    tx_hash = contract.functions.deposit(deposit_price_1).transact({'value': deposit_amount_too_low, 'gas': 500000})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Deposit below minimum succeeded (unexpected!)")
except Exception as e:
    print(f"Deposit below minimum failed (expected): {str(e)}")

# Test deposit: 1 ETH
deposit_amount = w3.to_wei(1, 'ether')
tx_hash = contract.functions.deposit(deposit_price_1).transact({'value': deposit_amount, 'gas': 500000})
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
for log in receipt['logs']:
    if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="Deposit(address,uint256,uint256)").hex():
        amount = int.from_bytes(log['data'][0:32], 'big')
        price_usd = int.from_bytes(log['data'][32:64], 'big')
        print(f"Deposited: {amount / 10**18} ETH, price {price_usd / 10**8} USD")
        break

# Check balance
balance = contract.functions.get_balance(account.address).call()
print(f"Balance: {balance / 10**18} ETH")

# Test withdrawal (may fail if price not met)
try:
    tx_hash = contract.functions.withdraw().transact({'gas': 500000})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    for log in receipt['logs']:
        if len(log['topics']) > 0 and log['topics'][0].hex() == w3.keccak(text="Withdraw(address,uint256)").hex():
            amount = int.from_bytes(log['data'][0:32], 'big')
            print(f"Withdrew: {amount / 10**18} ETH")
            break
except Exception as e:
    print(f"Withdrawal failed (expected if price not met): {str(e)}")

# Final balance check
balance = contract.functions.get_balance(account.address).call()
print(f"Final Balance: {balance / 10**18} ETH")