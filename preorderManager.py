import os
import sys
import requests
import csv
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv('.env.production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHQL_URL = f"https://{os.getenv('SHOP_URL')}/admin/api/2025-01/graphql.json"
HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")
}

DRY_RUN = False  # Set to False when ready to perform live updates
FORCE_TEST_EMAIL = False  # Set to True to force test of email sending

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
    import certifi

    # Try to use system certificates first
    system_ca_paths = [
        '/etc/ssl/certs/ca-certificates.crt',  # Ubuntu/Debian
        '/etc/pki/tls/certs/ca-bundle.crt',    # CentOS/RHEL
        '/etc/ssl/cert.pem',                   # macOS/FreeBSD
        '/etc/ssl/certs'                       # Generic directory fallback
    ]

    ca_path = None
    for path in system_ca_paths:
        if os.path.exists(path):
            ca_path = path
            logging.info(f"Using system CA certificates: {ca_path}")
            break

    if not ca_path:
        ca_path = certifi.where()
        logging.info(f"System CA certificates not found, using certifi: {ca_path}")

    os.environ['REQUESTS_CA_BUNDLE'] = ca_path  # Optional: for transparency

    try:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=HEADERS,
            verify=ca_path
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

# --- NEW FUNCTION: unpublish_product_from_sales_channel ---
def unpublish_product_from_sales_channel(product_id, channel_id):
    """
    Unpublishes a product from a specific sales channel using the publishableUnpublish mutation.
    Returns any userErrors encountered.
    """
    mutation = """
    mutation publishableUnpublish($id: ID!, $input: [PublicationInput!]!) {
      publishableUnpublish(id: $id, input: $input) {
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "id": product_id,
        "input": [
            {
                "channelId": channel_id
            }
        ]
    }
    response = run_query(mutation, variables)
    if not response:
        logging.error(f"Failed to unpublish product {product_id} — no response from GraphQL.")
        return [{"field": ["mutation"], "message": "No response from GraphQL"}]

    errors = response.get('data', {}).get('publishableUnpublish', {}).get('userErrors', [])
    return errors

# --- NEW FUNCTION: update_product_description ---
def update_product_description(product_id, new_description_html):
    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          descriptionHtml
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
            "id": product_id,
            "descriptionHtml": new_description_html
        }
    }
    response = run_query(mutation, variables)
    errors = response.get('data', {}).get('productUpdate', {}).get('userErrors', [])
    return errors

def safe_update_product_description(product_id, new_description_html):
    """
    Attempts to update a product description with retry on failure.
    Retries once after 2 seconds if the first attempt fails.
    """
    errors = update_product_description(product_id, new_description_html)

    if errors:
        logging.warning(f"First attempt failed for '{product_id}'. Retrying in 2 seconds...")
        time.sleep(2)
        errors = update_product_description(product_id, new_description_html)
        if errors:
            logging.error(f"⚠️ Final attempt failed for '{product_id}': {errors}")
        else:
            logging.info(f"✅ Successfully updated '{product_id}' on retry.")
    else:
        logging.info(f"✅ Successfully updated '{product_id}' on first try.")

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
            descriptionHtml
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

def clean_preorder_description(description):
    if not description:
        return description  # Empty fallback

    cleaned = description

    # Remove preorder preamble
    preamble_marker = "this is a featured preorder"
    preamble_idx = cleaned.lower().find(preamble_marker)
    if preamble_idx != -1:
        # Find end of preamble paragraph and cut up to there
        end_of_preamble = cleaned.find("</p>", preamble_idx)
        if end_of_preamble != -1:
            cleaned = cleaned[end_of_preamble + len("</p>"):].lstrip()

    # Remove rewards footer
    rewards_marker = "* featured preorder books earn you an extra"
    rewards_idx = cleaned.lower().find(rewards_marker)
    if rewards_idx != -1:
        cleaned = cleaned[:rewards_idx].rstrip()

    return cleaned

def backup_preorder_tracking_csv():
    preorders_dir = os.path.join(BASE_DIR, 'preorders')
    source_path = os.path.join(preorders_dir, 'NYT_preorder_tracking.csv')
    backup_path = os.path.join(preorders_dir, 'NYT_preorder_tracking.csv.bak')

    if os.path.exists(source_path):
        try:
            import shutil
            shutil.copy2(source_path, backup_path)
            logging.info(f"✅ Backup created: {backup_path}")
        except Exception as e:
            logging.error(f"Failed to back up NYT preorder tracking file: {str(e)}")
    else:
        logging.warning(f"No NYT_preorder_tracking.csv found at {source_path} to back up.")

def extract_isbn(product):
    # Try to extract ISBN from barcode first
    barcode = product.get('barcode')
    if barcode and barcode.isdigit() and (len(barcode) == 10 or len(barcode) == 13):
        return barcode

    # Fall back to tags, but strictly match only ISBN-10 or ISBN-13 patterns
    tags = product.get('tags', [])
    for tag in tags:
        normalized = tag.replace("-", "").strip()
        if normalized.isdigit() and (len(normalized) == 10 or len(normalized) == 13):
            return normalized

    return ""

def send_admin_summary_email(cleaned_books, pending_review_books, released_from_preorder):
    """
    Sends an admin summary email reporting on cleaned book descriptions, pending review books, and released-from-preorder books via Mailtrap API.
    """
    MAILTRAP_API_TOKEN = os.getenv("MAILTRAP_API_TOKEN")
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS")

    if not MAILTRAP_API_TOKEN or not EMAIL_SENDER or not EMAIL_RECIPIENTS:
        logging.warning("Skipping email — required environment variables are not set.")
        return

    subject = "Preorder Manager Admin Summary" + (" (Releases Included)" if released_from_preorder else "")

    body_parts = []

    if cleaned_books:
        body_parts.append("<h2>✅ Cleaned Book Descriptions</h2><ul>")
        for book in cleaned_books:
            body_parts.append(f"<li>{book['title']} (ID: {book['id']}) - Pub Date: {book['pub_date']} - Inventory: {book['inventory']}</li>")
        body_parts.append("</ul>")

    if pending_review_books:
        body_parts.append("<h2>🛑 Books Pending Manual Review</h2><ul>")
        for book in pending_review_books:
            body_parts.append(f"<li>{book['title']} (ID: {book['id']}) - Pub Date: {book['pub_date']} - Inventory: {book['inventory']}</li>")
        body_parts.append("</ul>")

    if released_from_preorder:
        body_parts.append("<h2>🚚 Shipping Profile Adjustment Reminder</h2><ul>")
        for book in released_from_preorder:
            body_parts.append(f"<li>{book['title']} - Pub Date: {book['pub_date']}</li>")
        body_parts.append("</ul>")

    if not body_parts:
        logging.info("No content to send in admin summary email.")
        return

    body_html = "<html><body>" + "".join(body_parts) + "</body></html>"

    # Prepare API request
    to_addresses = [{"email": email.strip()} for email in EMAIL_RECIPIENTS.split(";") if email.strip()]
    payload = {
        "from": {"email": EMAIL_SENDER, "name": "Preorder Manager"},
        "to": to_addresses,
        "subject": subject,
        "html": body_html
    }

    headers = {
        "Authorization": f"Bearer {MAILTRAP_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://send.api.mailtrap.io/api/send", json=payload, headers=headers)
        if 200 <= response.status_code < 300:
            logging.info("Admin summary email sent successfully via Mailtrap API.")
        else:
            logging.error(f"Mailtrap API email failed: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error sending Mailtrap API email: {e}")

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info(f"Running preorder manager with DRY_RUN={DRY_RUN}")

    products = fetch_preorder_products()
    logging.info(f"Fetched {len(products)} preorder products")

    cleaned_books = []
    pending_review_books = []
    released_from_preorder = []

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

        today = datetime.now().date()
        try:
            parsed_pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
        except ValueError:
            parsed_pub_date = None

        # Clean description if pub date has passed
        if parsed_pub_date and parsed_pub_date <= today and 'preorder' in product.get('tags', []):
            original_description = product.get('descriptionHtml', '') or ''
            cleaned_description = clean_preorder_description(original_description)

            if DRY_RUN:
                if original_description != cleaned_description:
                    logging.info(f"[Dry Run] Would clean description for '{title}':\nBEFORE:\n{original_description[:500]}\nAFTER:\n{cleaned_description[:500]}")
                else:
                    logging.info(f"[Dry Run] No cleaning needed for '{title}'")
            else:
                if original_description != cleaned_description:
                    safe_update_product_description(id, cleaned_description)
                    cleaned_books.append({
                        "title": title,
                        "id": id,
                        "pub_date": pub_date_str,
                        "inventory": inventory,
                        "isbn": extract_isbn(product)
                    })
                else:
                    logging.info(f"No cleaning needed for '{title}' — description already clean.")

        # Determine preorder collection removal based on inventory and pub_date
        if parsed_pub_date and parsed_pub_date <= today:
            if inventory > 0:
                # Standard case: release book fully
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
                                released_from_preorder.append({
                                    "title": title,
                                    "isbn": extract_isbn(product),
                                    "pub_date": pub_date_str
                                })
                                # --- New: Unpublish from Weekly Sales Report Automation ---
                                channel_id = "gid://shopify/Publication/103510278277"
                                if DRY_RUN:
                                    logging.info(f"[Dry Run] Would unpublish '{title}' from Weekly Sales Report Automation (Channel ID: {channel_id})")
                                else:
                                    unpublish_errors = unpublish_product_from_sales_channel(id, channel_id)
                                    if unpublish_errors:
                                        logging.error(f"Failed to unpublish '{title}' from Weekly Sales Report Automation: {unpublish_errors}")
                                    else:
                                        logging.info(f"✅ Successfully unpublished '{title}' from Weekly Sales Report Automation")
                    else:
                        logging.warning(f"No Preorder collection ID found for '{title}'")
                else:
                    logging.info(f"No action needed for '{title}' (already not in Preorder collection)")
            else:
                # Special delayed case
                if 'Preorder' in collections:
                    logging.info(f"[Pending Approval] '{title}' (ISBN/ID: {id}) has passed pub date but inventory <= 0 — awaiting manual review for Preorder collection removal.")
                    pending_review_books.append({
                        "title": title,
                        "id": id,
                        "pub_date": pub_date_str,
                        "inventory": inventory,
                        "isbn": extract_isbn(product)
                    })
                else:
                    logging.info(f"'{title}' has passed pub date and has inventory <= 0, but is no longer in Preorder collection — no manual review needed.")
        else:
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
                                # --- New: Unpublish from Weekly Sales Report Automation ---
                                channel_id = "gid://shopify/Publication/103510278277"
                                if DRY_RUN:
                                    logging.info(f"[Dry Run] Would unpublish '{title}' from Weekly Sales Report Automation (Channel ID: {channel_id})")
                                else:
                                    unpublish_errors = unpublish_product_from_sales_channel(id, channel_id)
                                    if unpublish_errors:
                                        logging.error(f"Failed to unpublish '{title}' from Weekly Sales Report Automation: {unpublish_errors}")
                                    else:
                                        logging.info(f"✅ Successfully unpublished '{title}' from Weekly Sales Report Automation")
                    else:
                        logging.warning(f"No Preorder collection ID found for '{title}'")
                else:
                    logging.info(f"No action needed for '{title}' (already not in Preorder collection)")
            else:
                logging.info(f"No action needed for '{title}' (conditions not met)")

    if not DRY_RUN:
        if cleaned_books or pending_review_books or released_from_preorder:
            logging.info("Sending admin summary email...")
            send_admin_summary_email(cleaned_books, pending_review_books, released_from_preorder)
        else:
            logging.info("No admin summary to send (no actions performed).")
            if FORCE_TEST_EMAIL:
                logging.info("FORCE_TEST_EMAIL is enabled — sending test admin summary email with mock data...")
                test_cleaned = [{"title": "Test Title", "id": "gid://shopify/Product/1234567890", "pub_date": "2025-07-20", "inventory": 5, "isbn": "9781234567897"}]
                test_pending = [{"title": "Pending Title", "id": "gid://shopify/Product/0987654321", "pub_date": "2025-07-19", "inventory": 0, "isbn": "9789876543210"}]
                test_released = [{"title": "Released Title", "pub_date": "2025-07-18"}]
                send_admin_summary_email(test_cleaned, test_pending, test_released)

    # Perform backup after evaluation
    backup_preorder_tracking_csv()

if __name__ == "__main__":
    main()