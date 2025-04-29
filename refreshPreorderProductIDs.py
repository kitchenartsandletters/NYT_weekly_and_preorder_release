import os
import json
import requests
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.production')

# Configuration
SHOP_URL = os.getenv('SHOP_URL')
STOREFRONT_ACCESS_TOKEN = os.getenv('STOREFRONT_ACCESS_TOKEN')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREORDER_PRODUCT_IDS_FILE = os.path.join(BASE_DIR, 'controls', 'preorder_product_ids.json')

PREORDER_COLLECTION_HANDLE = "pre-order"

STOREFRONT_GRAPHQL_URL = f"https://{SHOP_URL}/api/2025-01/graphql.json"

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Storefront-Access-Token": STOREFRONT_ACCESS_TOKEN
}

def run_storefront_query(query, variables=None):
    response = requests.post(
        STOREFRONT_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=HEADERS
    )
    response.raise_for_status()
    return response.json()

def get_preorder_product_ids_by_collection_handle(collection_handle):
    product_ids = []
    cursor = None
    has_next_page = True

    query = """
    query getPreorderProducts($handle: String!, $cursor: String) {
      collection(handle: $handle) {
        products(first: 100, after: $cursor) {
          edges {
            cursor
            node {
              id
              title
            }
          }
          pageInfo {
            hasNextPage
          }
        }
      }
    }
    """

    while has_next_page:
        variables = {
            "handle": collection_handle,
            "cursor": cursor
        }
        data = run_storefront_query(query, variables)
        products = data.get("data", {}).get("collection", {}).get("products", {})
        edges = products.get("edges", [])

        if not edges:
            break

        for edge in edges:
            product_node = edge["node"]
            shopify_product_gid = product_node["id"]  # Format: gid://shopify/Product/1234567890
            product_id = shopify_product_gid.split("/")[-1]
            product_ids.append(product_id)
            cursor = edge["cursor"]

        has_next_page = products.get("pageInfo", {}).get("hasNextPage", False)

    return product_ids

def save_preorder_product_ids(product_ids):
    with open(PREORDER_PRODUCT_IDS_FILE, 'w') as f:
        json.dump(product_ids, f)

def main():
    logging.basicConfig(level=logging.INFO)
    preorder_product_ids = get_preorder_product_ids_by_collection_handle(PREORDER_COLLECTION_HANDLE)

    if not preorder_product_ids:
        logging.error(f"❌ No preorder products found for collection handle '{PREORDER_COLLECTION_HANDLE}'.")
        return

    save_preorder_product_ids(preorder_product_ids)
    logging.info(f"✅ Saved {len(preorder_product_ids)} preorder product IDs.")

if __name__ == "__main__":
    main()
