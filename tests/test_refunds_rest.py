import os
import requests
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Define SHOP_URL, API_VERSION, ACCESS_TOKEN, and REST_ENDPOINT
SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'castironbooks.myshopify.com'
API_VERSION = '2023-10'  # Hardcoded to ensure correct version
ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token

# Specific Order ID to fetch refunds for
ORDER_ID = '5306018103429'  # Replace with the actual Order ID for #53779

REST_ENDPOINT = f"https://{SHOP_URL}/admin/api/{API_VERSION}/orders/{ORDER_ID}/refunds.json"

# Set up headers for REST request
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# Send the request to Shopify's REST API
response = requests.get(
    REST_ENDPOINT,
    headers=headers
)

# Handle the response
if response.status_code == 200:
    result = response.json()
    print("Full REST API Response:")
    print(json.dumps(result, indent=2))
else:
    print(f"HTTP Error {response.status_code}: {response.text}")