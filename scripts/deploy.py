from web3 import Web3
import json
import os
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to local Hardhat fork
w3 = Web3(Web3.HTTPProvider(os.environ.get('TESTNET_URL')))
if not w3.is_connected():
    raise Exception("Failed to connect to Ethereum node")

# Use private key from .env
private_key = os.environ.get('PRIVATE_KEY')
account = w3.eth.account.from_key(private_key)
w3.eth.default_account = account.address

# Compile contract
contract_path = 'contracts/eth_vault.vy'
with open(contract_path, 'r') as f:
    bytecode = subprocess.check_output(['vyper', contract_path]).decode().strip()

abi_path = 'scripts/eth_vault.json'
with open(abi_path, 'w') as f:
    subprocess.run(['vyper', '-f', 'abi', contract_path], stdout=f)

with open(abi_path, 'r') as f:
    abi = json.load(f)

# Deploy contract
contract = w3.eth.contract(abi=abi, bytecode=bytecode)
tx_hash = contract.constructor().transact({'gas': 2000000})
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(f"Contract deployed at: {tx_receipt.contractAddress}")

# Save contract address
with open('scripts/contract_address.txt', 'w') as f:
    f.write(tx_receipt.contractAddress)