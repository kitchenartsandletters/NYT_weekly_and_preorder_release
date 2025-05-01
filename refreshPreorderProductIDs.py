import os
import json
import requests
import logging
from dotenv import load_dotenv
import certifi

# Load environment variables
load_dotenv('.env.production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREORDER_PRODUCT_IDS_FILE = os.path.join(BASE_DIR, 'controls', 'preorder_product_ids.json')
PREORDER_COLLECTION_HANDLE = "pre-order"

STOREFRONT_URL = f"https://{os.getenv('SHOP_URL')}/api/2023-10/graphql.json"
STOREFRONT_HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Storefront-Access-Token": os.getenv("STOREFRONT_ACCESS_TOKEN")
}

def run_storefront_query(query, variables=None):
    # Try to use system certificates first
    system_ca_paths = [
        '/etc/ssl/certs/ca-certificates.crt',
        '/etc/pki/tls/certs/ca-bundle.crt',
        '/etc/ssl/cert.pem',
        '/etc/ssl/certs'
    ]

    ca_path = None
    for path in system_ca_paths:
        if os.path.exists(path):
            ca_path = path
            print(f"Using system CA certificates: {ca_path}")
            break

    if not ca_path:
        ca_path = certifi.where()
        print(f"System CA certificates not found, using certifi: {ca_path}")

    os.environ['REQUESTS_CA_BUNDLE'] = ca_path

    try:
        response = requests.post(
            STOREFRONT_URL,
            json={"query": query, "variables": variables},
            headers=STOREFRONT_HEADERS,
            verify=ca_path
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"GraphQL request failed: {e}")
        return None

    try:
        return response.json()
    except ValueError:
        logging.error("Invalid JSON response")
        return None

def get_preorder_product_ids_by_collection_handle(handle):
    query = """
    query getCollectionProducts($handle: String!, $cursor: String) {
      collection(handle: $handle) {
        products(first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
          }
          edges {
            cursor
            node {
              id
            }
          }
        }
      }
    }
    """
    product_ids = []
    cursor = None
    has_next_page = True

    while has_next_page:
        variables = {
            "handle": handle,
            "cursor": cursor
        }
        data = run_storefront_query(query, variables)

        collection = data.get("data", {}).get("collection")
        if not collection or not collection.get("products"):
            logging.warning("Collection not found or contains no products.")
            return []

        products_data = collection["products"]
        edges = products_data.get("edges", [])

        for edge in edges:
            product_gid = edge["node"]["id"]  # gid://shopify/Product/1234567890
            product_id = product_gid.split("/")[-1]
            product_ids.append(product_id)

        has_next_page = products_data["pageInfo"]["hasNextPage"]
        if has_next_page:
            cursor = edges[-1]["cursor"]

    return product_ids

def save_preorder_product_ids(product_ids):
    with open(PREORDER_PRODUCT_IDS_FILE, 'w') as f:
        json.dump(product_ids, f)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Refreshing preorder product IDs...")

    preorder_product_ids = get_preorder_product_ids_by_collection_handle(PREORDER_COLLECTION_HANDLE)
    if preorder_product_ids:
        save_preorder_product_ids(preorder_product_ids)
        logging.info(f"✅ Saved {len(preorder_product_ids)} preorder product IDs.")
    else:
        logging.error("❌ No preorder products found for collection handle 'pre-order'.")

if __name__ == "__main__":
    main()
