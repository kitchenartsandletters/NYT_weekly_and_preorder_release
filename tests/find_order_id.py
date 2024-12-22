import os
import requests
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Define SHOP_URL, API_VERSION, ACCESS_TOKEN, and GRAPHQL_ENDPOINT
SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'yourstore.myshopify.com'
API_VERSION = '2023-10'  # Ensure this matches your setup
ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token
GRAPHQL_ENDPOINT = f"https://{SHOP_URL}/admin/api/{API_VERSION}/graphql.json"

# Print API_VERSION for confirmation
print(f"Using API Version: {API_VERSION}")

# Set up headers for GraphQL request
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# Define a GraphQL query to fetch order by name
query = """
query($query: String!) {
  orders(first: 1, query: $query) {
    edges {
      node {
        id
        name
        createdAt
      }
    }
  }
}
"""

# Define variables for the query
variables = {
    "query": "name:#53779"  # Targeting the specific order by name
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
        # Extract and print the Order ID
        orders = result.get('data', {}).get('orders', {}).get('edges', [])
        if orders:
            order = orders[0]['node']
            print("\nOrder Details:")
            print(f"Order Name: {order['name']}")
            print(f"Order ID: {order['id']}")
            print(f"Created At: {order['createdAt']}")
        else:
            print("No orders found matching the query.")
else:
    print(f"HTTP Error {response.status_code}: {response.text}")