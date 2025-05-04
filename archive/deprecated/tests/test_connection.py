import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define SHOP_URL, API_VERSION, ACCESS_TOKEN, and GRAPHQL_ENDPOINT
SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'castironbooks.myshopify.com'
API_VERSION = os.getenv('API_VERSION')  # e.g., '2023-10'
ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token
GRAPHQL_ENDPOINT = f"https://{SHOP_URL}/admin/api/{API_VERSION}/graphql.json"

# Set up headers for GraphQL request
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# Define a simple GraphQL query to fetch shop information
query = """
{
  shop {
    name
    email
  }
}
"""

# Send the request to Shopify's GraphQL API
response = requests.post(
    GRAPHQL_ENDPOINT,
    json={'query': query},
    headers=headers
)

# Handle the response
if response.status_code == 200:
    result = response.json()
    if 'errors' in result:
        print("GraphQL Errors:", result['errors'])
    else:
        shop_info = result.get('data', {}).get('shop', {})
        print("Shop Name:", shop_info.get('name'))
        print("Shop Email:", shop_info.get('email'))
else:
    print(f"HTTP Error {response.status_code}: {response.text}")