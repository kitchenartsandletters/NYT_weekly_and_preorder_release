import os
import requests
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Define SHOP_URL, API_VERSION, ACCESS_TOKEN, and GRAPHQL_ENDPOINT
SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'yourstore.myshopify.com'
API_VERSION = '2023-10'  # Hardcoded to ensure correct version
ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token
GRAPHQL_ENDPOINT = f"https://{SHOP_URL}/admin/api/{API_VERSION}/graphql.json"

# Print API_VERSION for confirmation
print(f"Using API Version: {API_VERSION}")

# Set up headers for GraphQL request
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# Define a GraphQL query to fetch refunds for a specific order by ID
query = """
query($orderId: ID!) {
  order(id: $orderId) {
    id
    name
    createdAt
    refunds(first: 5) {  # Treating refunds as a list
      id
      createdAt
    }
  }
}
"""

# Define variables for the query
variables = {
    "orderId": "gid://shopify/Order/5306018103429"  # Replace with the actual Order ID
}

# Print the query and variables
print("GraphQL Query:")
print(query)
print("\nQuery Variables:")
print(json.dumps(variables, indent=2))

# Send the request to Shopify's GraphQL API
response = requests.post(
    GRAPHQL_ENDPOINT,
    json={'query': query, 'variables': variables},
    headers=headers
)

# Handle the response
if response.status_code == 200:
    result = response.json()
    if 'errors' in result:
        print("GraphQL Errors:", json.dumps(result['errors'], indent=2))
    else:
        # Extract and print refunds
        order = result.get('data', {}).get('order', {})
        if order:
            print("\nOrder Details:")
            print(f"Order Name: {order['name']}")
            print(f"Order ID: {order['id']}")
            print(f"Created At: {order['createdAt']}")
            refunds = order.get('refunds', [])
            if refunds:
                print("\nRefunds:")
                for refund in refunds:
                    print(f"  Refund ID: {refund['id']}")
                    print(f"  Created At: {refund['createdAt']}")
            else:
                print("\nNo refunds found for this order.")
        else:
            print("No order found with the specified ID.")
else:
    print(f"HTTP Error {response.status_code}: {response.text}")