import os
import json
import requests
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import certifi
import time

print(f"Using SSL cert from: {os.environ.get('SSL_CERT_FILE')}")

# Load environment variables
load_dotenv('.env.production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHQL_URL = f"https://{os.getenv('SHOP_URL')}/admin/api/2025-01/graphql.json"
HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")
}

PREORDER_PRODUCT_IDS_FILE = os.path.join(BASE_DIR, 'controls', 'preorder_product_ids.json')
PARSED_ORDERS_FILE = os.path.join(BASE_DIR, 'controls', 'parsed_orders.json')

DRY_RUN = False  # Set True to simulate, False to live tag

def run_query(query, variables=None):
    try:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=HEADERS,
            verify=os.environ.get("SSL_CERT_FILE", certifi.where())  # Ensure SSL verification with env override
        )
    except requests.exceptions.RequestException as e:
        logging.error(f"GraphQL request failed: {e}")
        return None

    if response.status_code != 200:
        logging.error(f"GraphQL request failed with status {response.status_code}: {response.text}")
        return None
    try:
        response_json = response.json()
    except ValueError:
        logging.error(f"GraphQL response could not be decoded as JSON: {response.text}")
        return None

    if 'errors' in response_json:
        logging.error(f"GraphQL errors: {json.dumps(response_json['errors'], indent=2)}")
        return None

    return response_json

def load_preorder_product_ids():
    if os.path.exists(PREORDER_PRODUCT_IDS_FILE):
        with open(PREORDER_PRODUCT_IDS_FILE) as f:
            return json.load(f)
    else:
        logging.error(f"No preorder_product_ids.json found at {PREORDER_PRODUCT_IDS_FILE}")
        return []

def load_parsed_orders():
    if os.path.exists(PARSED_ORDERS_FILE):
        with open(PARSED_ORDERS_FILE) as f:
            return set(json.load(f))
    else:
        return set()

def save_parsed_orders(parsed_orders):
    with open(PARSED_ORDERS_FILE, 'w') as f:
        json.dump(list(parsed_orders), f)

def fetch_recent_orders():
    created_at_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    query_string = f"created_at:>={created_at_cutoff}"

    query = """
    query ($cursor: String, $query: String!) {
      orders(first: 50, query: $query, after: $cursor) {
        edges {
          cursor
          node {
            id
            name
            tags
            lineItems(first: 50) {
              edges {
                node {
                  product {
                    id
                  }
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
    orders = []
    cursor = None
    has_next_page = True

    while has_next_page:
        variables = {
            "cursor": cursor,
            "query": query_string
        }
        data = run_query(query, variables)
        if data is None:
            break
        edges = data['data']['orders']['edges']
        for edge in edges:
            orders.append(edge['node'])
        has_next_page = data['data']['orders']['pageInfo']['hasNextPage']
        if has_next_page:
            cursor = edges[-1]['cursor']

    return orders

def tag_order_with_preorder(order_id, existing_tags):
    new_tags = list(existing_tags)
    if "preorder" not in [tag.lower() for tag in existing_tags]:
        new_tags.append("preorder")

    mutation = """
    mutation orderUpdate($input: OrderInput!) {
      orderUpdate(input: $input) {
        order {
          id
          tags
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "id": order_id,
            "tags": new_tags
        }
    }
    response = run_query(mutation, variables)
    if response is None:
        return [{"field": ["unknown"], "message": "No response from server"}]

    errors = response.get('data', {}).get('orderUpdate', {}).get('userErrors', [])
    return errors

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info(f"Running preorderOrderTagger with DRY_RUN={DRY_RUN}")

    preorder_product_ids = load_preorder_product_ids()
    parsed_orders = load_parsed_orders()

    logging.info(f"Loaded {len(preorder_product_ids)} active preorder product IDs")
    logging.info(f"Loaded {len(parsed_orders)} previously parsed orders")

    recent_orders = fetch_recent_orders()
    logging.info(f"Fetched {len(recent_orders)} recent orders")

    updated_orders = 0

    for order in recent_orders:
        if order['id'] in parsed_orders:
            continue

        line_item_product_ids = []
        for item_edge in order['lineItems']['edges']:
            product = item_edge['node']['product']
            if product:
                shopify_product_gid = product['id']  # gid://shopify/Product/1234567890
                product_id = shopify_product_gid.split("/")[-1]
                line_item_product_ids.append(product_id)

        matches_preorder = any(pid in preorder_product_ids for pid in line_item_product_ids)

        if matches_preorder:
            logging.info(f"Order {order['name']} contains a preorder item")
            if DRY_RUN:
                logging.info(f"[Dry Run] Would tag order {order['name']} with 'preorder'")
            else:
                errors = tag_order_with_preorder(order['id'], order['tags'])
                if errors:
                    logging.error(f"Failed to update tags for order {order['name']}: {errors}")
                else:
                    logging.info(f"✅ Tagged order {order['name']} with 'preorder'")
                    updated_orders += 1
        else:
            logging.info(f"Order {order['name']} does not contain any preorder items")

        parsed_orders.add(order['id'])

    save_parsed_orders(parsed_orders)
    logging.info(f"✅ Finished processing. {updated_orders} orders tagged with 'preorder'.")

if __name__ == "__main__":
    main()