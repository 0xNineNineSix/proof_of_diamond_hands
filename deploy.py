from web3 import Web3
import json
import os
import subprocess

# Connect to mainnet fork (set TESTNET_URL in Replit Secrets)
w3 = Web3(Web3.HTTPProvider(os.environ.get('TESTNET_URL')))
if not w3.is_connected():
    raise Exception("Failed to connect to Ethereum node")

# Use environment variables for sensitive data
private_key = os.environ.get('PRIVATE_KEY')
account = w3.eth.account.from_key(private_key)
w3.eth.default_account = account.address

# Admin address (multi-sig or test address)
admin_address = account.address  # Replace with Gnosis Safe for mainnet

# Compile contract
with open('eth_vault.vy', 'r') as f:
    bytecode = subprocess.check_output(['vyper', 'eth_vault.vy']).decode().strip()

with open('eth_vault.json', 'w') as f:
    subprocess.run(['vyper', '-f', 'abi', 'eth_vault.vy'], stdout=f)

with open('eth_vault.json', 'r') as f:
    abi = json.load(f)

# Deploy contract
contract = w3.eth.contract(abi=abi, bytecode=bytecode)
tx_hash = contract.constructor(admin_address).transact()
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(f"Contract deployed at: {tx_receipt.contractAddress}")

# Save contract address
with open('contract_address.txt', 'w') as f:
    f.write(tx_receipt.contractAddress)