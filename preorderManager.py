import os
import sys
import requests
import csv
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHQL_URL = f"https://{os.getenv('SHOP_URL')}/admin/api/2025-01/graphql.json"
HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")
}

DRY_RUN = False  # Set to False when ready to perform live updates

def load_early_stock_exceptions():
    exceptions_path = os.path.join(BASE_DIR, 'controls', 'early_stock_exceptions.csv')
    exceptions = set()
    if os.path.exists(exceptions_path):
        with open(exceptions_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                exceptions.add(row['Product ID'])
        logging.info(f"Loaded {len(exceptions)} early stock exceptions")
    else:
        logging.warning(f"No early_stock_exceptions.csv found at {exceptions_path}")
    return exceptions

def run_query(query, variables=None):
    response = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=HEADERS
    )
    if response.status_code != 200:
        raise Exception(f"GraphQL error: {response.text}")
    return response.json()

def remove_product_from_collection(collection_id, product_id):
    mutation = """
    mutation collectionRemoveProducts($id: ID!, $productIds: [ID!]!) {
      collectionRemoveProducts(id: $id, productIds: $productIds) {
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "id": collection_id,
        "productIds": [product_id]
    }
    response = run_query(mutation, variables)
    errors = response.get('data', {}).get('collectionRemoveProducts', {}).get('userErrors', [])
    return errors

def fetch_preorder_products():
    query = """
    query($cursor: String) {
      products(first: 100, query: "tag:preorder", after: $cursor) {
        edges {
          cursor
          node {
            id
            title
            tags
            publishedAt
            collections(first: 5) {
              edges {
                node {
                  id
                  title
                }
              }
            }
            variants(first: 1) {
              edges {
                node {
                  inventoryQuantity
                }
              }
            }
            metafields(first: 5, namespace: "custom") {
              edges {
                node {
                  key
                  value
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
        }
      }
    }
    """
    products = []
    cursor = None
    has_next_page = True

    while has_next_page:
        data = run_query(query, {"cursor": cursor})
        edges = data['data']['products']['edges']
        for edge in edges:
            products.append(edge['node'])
        has_next_page = data['data']['products']['pageInfo']['hasNextPage']
        if has_next_page:
            cursor = edges[-1]['cursor']

    return products

import re

def extract_pub_date(product):
    # Check metafields first
    metafields = product.get('metafields', {})
    for edge in metafields.get('edges', []):
        if edge['node']['key'] == 'pub_date':
            return edge['node']['value']
    
    # Fall back to tags
    tags = product.get('tags', [])
    date_pattern = r'^\d{2}-\d{2}-\d{4}$'
    for tag in tags:
        if re.match(date_pattern, tag):
            # Convert MM-DD-YYYY to YYYY-MM-DD
            month, day, year = tag.split('-')
            return f"{year}-{month}-{day}"
    
    # Nothing found
    return None

def should_remove_from_preorder_collection(product, early_stock_exceptions=None):
    if early_stock_exceptions and product['id'] in early_stock_exceptions:
        logging.info(f"Force treating '{product['title']}' as early stock arrival due to override")
        return True

    inventory = 0
    try:
        inventory = product['variants']['edges'][0]['node']['inventoryQuantity']
    except Exception:
        pass

    pub_date_str = extract_pub_date(product)
    if pub_date_str:
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
        except ValueError:
            logging.warning(f"Invalid pub_date format for {product['title']}: {pub_date_str}")
            pub_date = None
    else:
        pub_date = None

    today = datetime.now().date()

    if inventory > 0 and (pub_date is None or pub_date > today):
        return True
    return False

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info(f"Running preorder manager with DRY_RUN={DRY_RUN}")

    products = fetch_preorder_products()
    logging.info(f"Fetched {len(products)} preorder products")

    early_stock_exceptions = load_early_stock_exceptions()

    for product in products:
        title = product['title']
        id = product['id']
        collections = [edge['node']['title'] for edge in product['collections']['edges']]

        # Extract inventory and pub_date for better logging
        inventory = 0
        try:
            inventory = product['variants']['edges'][0]['node']['inventoryQuantity']
        except Exception:
            pass

        pub_date_str = extract_pub_date(product) or "N/A"

        logging.info(f"Evaluating '{title}' — Inventory: {inventory} — Pub Date: {pub_date_str}")

        if should_remove_from_preorder_collection(product, early_stock_exceptions):
            if 'Preorder' in collections:
                preorder_collection_edge = next((edge for edge in product['collections']['edges'] if edge['node']['title'] == 'Preorder'), None)
                if preorder_collection_edge:
                    preorder_collection_id = preorder_collection_edge['node']['id']
                    if DRY_RUN:
                        logging.info(f"[Dry Run] Would remove '{title}' (Product ID: {id}) from Preorder collection (Collection ID: {preorder_collection_id})")
                    else:
                        errors = remove_product_from_collection(preorder_collection_id, id)
                        if errors:
                            logging.error(f"Failed to remove '{title}' from Preorder collection: {errors}")
                        else:
                            logging.info(f"✅ Removed '{title}' (Product ID: {id}) from Preorder collection (Collection ID: {preorder_collection_id})")
                else:
                    logging.warning(f"No Preorder collection ID found for '{title}'")
            else:
                logging.info(f"No action needed for '{title}' (already not in Preorder collection)")
        else:
            logging.info(f"No action needed for '{title}' (conditions not met)")

if __name__ == "__main__":
    main()