import os
import json
import requests
import logging
from dotenv import load_dotenv
import certifi

# Load environment variables
load_dotenv('.env.production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREORDER_COLLECTION_HANDLE = "pre-order"

STOREFRONT_URL = f"https://{os.getenv('SHOP_URL')}/api/2023-10/graphql.json"
STOREFRONT_HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Storefront-Access-Token": os.getenv("STOREFRONT_ACCESS_TOKEN")
}

def run_storefront_query(query, variables=None):
    response = requests.post(
        STOREFRONT_URL,
        json={"query": query, "variables": variables},
        headers=STOREFRONT_HEADERS,
        verify=certifi.where()
    )
    print("Status Code:", response.status_code)
    print("Response Text:")
    print(response.text)  # FULL raw response for debugging
    response.raise_for_status()
    return response.json()

def main():
    print("SHOP_URL (raw) =", os.getenv("SHOP_URL"))
    print("STOREFRONT_URL =", f"https://{os.getenv('SHOP_URL')}/api/2023-10/graphql.json")
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Running debug storefront query...")

    query = """
    query getCollectionProducts($handle: String!) {
      collection(handle: $handle) {
        id
        title
        products(first: 1) {
          edges {
            node {
              id
            }
          }
        }
      }
    }
    """
    variables = {"handle": PREORDER_COLLECTION_HANDLE}
    run_storefront_query(query, variables)

print("SHOP_URL =", os.getenv("SHOP_URL"))
print("STOREFRONT_URL =", f"https://{os.getenv('SHOP_URL')}/api/2023-10/graphql.json")

if __name__ == "__main__":
    main()
