import os
import requests
import csv
import logging
import argparse
from datetime import datetime, timedelta
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import time
import sys
import base64
from dotenv import load_dotenv
from process_approved_releases import process_approved_releases

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

def load_environment():
    """Loads environment variables from .env.production file"""
    try:
        load_dotenv('.env.production')
        logging.info("Environment variables successfully loaded.")
        logging.info(f"SHOP_URL present: {bool(os.getenv('SHOP_URL'))}")
        logging.info(f"SHOPIFY_ACCESS_TOKEN present: {bool(os.getenv('SHOPIFY_ACCESS_TOKEN'))}")
        logging.info(f"SENDGRID_API_KEY present: {bool(os.getenv('SENDGRID_API_KEY'))}")
        logging.info(f"EMAIL_SENDER present: {bool(os.getenv('EMAIL_SENDER'))}")
        logging.info(f"EMAIL_RECIPIENTS present: {bool(os.getenv('EMAIL_RECIPIENTS'))}")
    except Exception as e:
        logging.error(f"Error loading environment variables: {e}")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def load_pub_date_overrides(override_file='pub_date_overrides.csv'):
    """
    Loads manual overrides for publication dates from CSV file
    Returns a dictionary mapping ISBNs to corrected publication dates
    """
    overrides = {}
    
    override_path = os.path.join(BASE_DIR, 'controls', override_file)
    if not os.path.exists(override_path):
        logging.info(f"No override file found at {override_path}")
        return overrides
        
    try:
        with open(override_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'ISBN' in row and 'Corrected_Pub_Date' in row:
                    isbn = row['ISBN']
                    corrected_date = row['Corrected_Pub_Date']
                    overrides[isbn] = corrected_date
                    logging.info(f"Loaded pub date override for ISBN {isbn}: {corrected_date}")
    except Exception as e:
        logging.error(f"Error loading pub date overrides: {e}")
    
    logging.info(f"Loaded {len(overrides)} publication date overrides")
    return overrides

def run_query_with_retries(query, variables, max_retries=3, delay=1):
    """
    Runs a GraphQL query with retry logic
    """
    attempt = 0
    while attempt < max_retries:
        try:
            response = requests.post(
                GRAPHQL_URL,
                json={'query': query, 'variables': variables},
                headers=HEADERS
            )
            
            if response.status_code != 200:
                logging.error(f"Error: Received status code {response.status_code}")
                logging.error(f"Response: {response.text}")
                attempt += 1
                time.sleep(delay)
                continue
                
            data = response.json()
            
            if 'errors' in data:
                logging.error(f"GraphQL Errors: {data['errors']}")
                attempt += 1
                time.sleep(delay)
                continue
                
            return data['data']
            
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
            attempt += 1
            time.sleep(delay)
            
    raise Exception(f"Failed to execute query after {max_retries} attempts")

def fetch_orders(start_date, end_date):
    """
    Fetches basic order data without collections or metafields
    """
    orders = []
    has_next_page = True
    cursor = None

    # Update log file path to use output directory
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    log_file_path = os.path.join(output_dir, 'fetched_order_ids.log')

    try:
        with open(log_file_path, 'w') as log_file:
            logging.info(f"Opened {log_file_path} for writing.")

            query = """
            query($first: Int!, $query: String!, $after: String) {
                orders(first: $first, query: $query, after: $after, reverse: false) {
                    edges {
                        cursor
                        node {
                            id
                            name
                            createdAt
                            cancelledAt
                            
                            lineItems(first: 25) {
                                edges {
                                    node {
                                        id
                                        name
                                        quantity
                                        variant {
                                            id
                                            barcode
                                            product {
                                                id
                                                title
                                            }
                                        }
                                    }
                                }
                            }
                            
                            refunds {
                                id
                                createdAt
                                refundLineItems(first: 25) {
                                    edges {
                                        node {
                                            quantity
                                            lineItem {
                                                id
                                                name
                                                variant {
                                                    id
                                                    barcode
                                                }
                                            }
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

            variables = {
                "first": 250,
                "query": f'created_at:>="{start_date}" AND created_at:<="{end_date}"',
                "after": cursor
            }

            while has_next_page:
                try:
                    data = run_query_with_retries(query, variables)
                    fetched_orders = data['orders']['edges']
                    for edge in fetched_orders:
                        order = edge['node']
                        orders.append(order)

                        # Log each order's ID & creation date
                        order_id = order['id']
                        order_created_at = order['createdAt']
                        try:
                            log_file.write(f"{order_id}\t{order_created_at}\n")
                            logging.debug(f"Logged Order ID: {order_id}, Created At: {order_created_at}")
                        except Exception as e:
                            logging.error(f"Failed to write Order ID {order_id} to log: {e}")

                    has_next_page = data['orders']['pageInfo']['hasNextPage']
                    logging.info(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")

                    if has_next_page:
                        cursor = fetched_orders[-1]['cursor']
                        variables['after'] = cursor
                    else:
                        break

                except Exception as e:
                    logging.error(f"Failed to fetch orders after retries: {e}", exc_info=True)
                    break

    except Exception as e:
        logging.error(f"Failed to open {log_file_path} for writing: {e}")
        exit(1)

    logging.info(f"Total orders fetched: {len(orders)}")
    return orders

def fetch_product_details(product_ids):
    """
    Fetches both collections and pub dates for products
    """
    if not product_ids:
        logging.warning("fetch_product_details called with empty product_ids")
        return {}

    query = """
    query($ids: [ID!]!) {
        nodes(ids: $ids) {
            ... on Product {
                id
                title
                vendor
                collections(first: 4) {
                    edges {
                        node {
                            title
                        }
                    }
                }
                metafields(first: 10, namespace: "custom") {
                    edges {
                        node {
                            key
                            value
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
            }
        }
    }
    """
    
    try:
        # Split into chunks of 10 products to manage query cost
        chunk_size = 10
        all_product_details = {}
        
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i:i + chunk_size]
            variables = {"ids": chunk}
            
            logging.debug(f"Fetching details for product chunk {i//chunk_size + 1}: {chunk}")
            data = run_query_with_retries(query, variables)
            
            if not data or 'nodes' not in data:
                logging.warning(f"Invalid response data structure: {data}")
                continue
                
            for node in data.get('nodes', []):
                if not node:
                    logging.warning("Received null node in response")
                    continue
                    
                try:
                    product_id = node['id']
                    title = node.get('title', 'Unknown Title')
                    logging.debug(f"Processing product: {product_id} - {title}")
                    
                    # Initialize the product details dictionary with defaults
                    product_info = {
                        'title': title,
                        'vendor': node.get('vendor', 'Unknown'),
                        'collections': [],
                        'pub_date': None,
                        'inventory': 0
                    }
                    
                    # Extract collections
                    try:
                        if 'collections' in node and 'edges' in node['collections']:
                            product_info['collections'] = [
                                edge['node']['title'] 
                                for edge in node['collections']['edges'] 
                                if 'node' in edge and 'title' in edge['node']
                            ]
                            logging.debug(f"Extracted collections: {product_info['collections']}")
                    except Exception as coll_error:
                        logging.error(f"Error extracting collections for {product_id}: {coll_error}")
                    
                    # Extract inventory quantity
                    try:
                        if ('variants' in node and 'edges' in node['variants'] and 
                            len(node['variants']['edges']) > 0 and 
                            'node' in node['variants']['edges'][0]):
                            
                            variant_node = node['variants']['edges'][0]['node']
                            product_info['inventory'] = variant_node.get('inventoryQuantity', 0)
                            logging.debug(f"Extracted inventory: {product_info['inventory']}")
                    except Exception as inv_error:
                        logging.error(f"Error extracting inventory for {product_id}: {inv_error}")
                    
                    # Extract pub_date from metafields
                    try:
                        if 'metafields' in node and 'edges' in node['metafields']:
                            for edge in node['metafields']['edges']:
                                if ('node' in edge and 
                                    'key' in edge['node'] and 
                                    edge['node']['key'] == 'pub_date' and
                                    'value' in edge['node']):
                                    
                                    product_info['pub_date'] = edge['node']['value']
                                    logging.debug(f"Extracted pub_date: {product_info['pub_date']}")
                                    break
                    except Exception as meta_error:
                        logging.error(f"Error extracting metafields for {product_id}: {meta_error}")
                    
                    # Add to results
                    all_product_details[product_id] = product_info
                    logging.debug(f"Added product details for {product_id}: {product_info}")
                    
                except Exception as node_error:
                    logging.error(f"Error processing node: {node_error}")
                    # Continue to the next node
            
            # Add a small delay between chunks to avoid rate limiting
            if i + chunk_size < len(product_ids):
                time.sleep(1)
        
        logging.info(f"Successfully fetched details for {len(all_product_details)} products")
        return all_product_details
        
    except Exception as e:
        logging.error(f"Error in fetch_product_details: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {}
    
def get_product_ids_by_isbn(isbn):
    """
    Look up product IDs by ISBN using the Shopify GraphQL API
    Returns a list of product IDs (should normally be just one)
    """
    global GRAPHQL_URL, HEADERS
    
    # Ensure API settings are initialized
    if not GRAPHQL_URL or not HEADERS:
        shop_url = os.getenv('SHOP_URL')
        access_token = os.getenv('SHOPIFY_ACCESS_TOKEN')
        
        if not shop_url or not access_token:
            logging.error("Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN environment variables")
            return []
            
        GRAPHQL_URL = f"https://{shop_url}/admin/api/2025-01/graphql.json"
        HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": access_token}
    
    if not isbn:
        return []
        
    query = """
    query($query: String!) {
        products(first: 5, query: $query) {
            edges {
                node {
                    id
                    title
                }
            }
        }
    }
    """
    
    variables = {
        "query": f"barcode:{isbn}"
    }
    
    try:
        data = run_query_with_retries(query, variables)
        product_edges = data.get('products', {}).get('edges', [])
        
        product_ids = []
        for edge in product_edges:
            product_id = edge['node']['id']
            product_ids.append(product_id)
            
        if len(product_ids) > 1:
            logging.warning(f"Found multiple products ({len(product_ids)}) for ISBN {isbn}")
            
        return product_ids
        
    except Exception as e:
        logging.error(f"Error looking up product ID for ISBN {isbn}: {e}")
        return []

def is_valid_isbn(barcode):
    """
    Checks if a barcode is a valid ISBN (starts with 978 or 979)
    """
    return barcode and (str(barcode).startswith('978') or str(barcode).startswith('979'))

def clean_preorder_tracking_file(tracking_file='NYT_preorder_tracking.csv'):
    """Clean up formatting issues in the preorder tracking file"""
    preorders_dir = os.path.join(BASE_DIR, 'preorders')
    tracking_path = os.path.join(preorders_dir, tracking_file)
    temp_path = os.path.join(preorders_dir, 'temp_' + tracking_file)

    fieldnames = ['ISBN', 'Title', 'Pub Date', 'Quantity', 'Status']

    try:
        # Read all data from existing file
        rows = []
        with open(tracking_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header
            
            current_row = []
            for row in reader:
                # If we have a complete row (5 columns)
                if len(row) == 5:
                    if current_row:  # If we have pending data
                        rows.append(current_row)
                    current_row = row
                else:
                    # If this is part of the previous row that was split
                    if current_row:
                        rows.append(current_row)
                    current_row = row

            if current_row:
                rows.append(current_row)

        # Write cleaned data back
        with open(temp_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            writer.writerows(rows)

        # Replace original file with cleaned file
        os.replace(temp_path, tracking_path)
        logging.info(f"Successfully cleaned preorder tracking file. Total rows: {len(rows)}")

    except Exception as e:
        logging.error(f"Error cleaning preorder tracking file: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def track_preorder_sales(preorder_items, tracking_file='NYT_preorder_tracking.csv'):
    """Append new preorder items to tracking file"""
    preorders_dir = os.path.join(BASE_DIR, 'preorders')
    os.makedirs(preorders_dir, exist_ok=True)
    tracking_path = os.path.join(preorders_dir, tracking_file)

    # Add Order ID and Line Item ID to fieldnames
    fieldnames = ['ISBN', 'Title', 'Pub Date', 'Quantity', 'Status', 'Order ID', 'Order Name', 'Line Item ID']

    try:
        file_exists = os.path.exists(tracking_path) and os.path.getsize(tracking_path) > 0
        
        with open(tracking_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            
            if not file_exists:
                writer.writeheader()

            # Read existing entries to check for duplicates
            existing_orders = set()
            if file_exists:
                with open(tracking_path, 'r', newline='', encoding='utf-8') as read_f:
                    reader = csv.DictReader(read_f)
                    for row in reader:
                        # Create unique key using Order ID and Line Item ID
                        order_key = f"{row.get('Order ID')}_{row.get('Line Item ID')}"
                        existing_orders.add(order_key)

            # Append each new preorder item
            for item in preorder_items:
                order_key = f"{item['order_id']}_{item['line_item_id']}"
                if order_key not in existing_orders:
                    writer.writerow({
                        'ISBN': item['barcode'],
                        'Title': item['title'],
                        'Pub Date': item.get('pub_date', ''),
                        'Quantity': item['quantity'],
                        'Status': 'Preorder',
                        'Order ID': item['order_id'],
                        'Order Name': item['order_name'],
                        'Line Item ID': item['line_item_id']
                    })

        logging.info(f"Successfully processed preorder items")
        
    except Exception as e:
        logging.error(f"Error appending preorder items: {e}")
        raise

    return None

def calculate_total_preorder_quantities(as_of_date=None, pub_date_overrides=None, skip_date_check=False):
    """Calculate total preorder quantities for each ISBN"""
    tracking_path = os.path.join(BASE_DIR, 'preorders', 'NYT_preorder_tracking.csv')
    
    preorder_totals = {}
    
    try:
        with open(tracking_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Add debug logging for specific ISBN
                isbn = row.get('ISBN')
                if isbn == '9781324073796':
                    logging.info(f"Tracking row for 9781324073796: Pub Date={row.get('Pub Date')}, Quantity={row.get('Quantity')}")

                # Apply pub date override if available
                if pub_date_overrides and isbn in pub_date_overrides:
                    original_pub = row.get('Pub Date', '')
                    row['Pub Date'] = pub_date_overrides[isbn]
                    logging.info(f"Overrode pub date for ISBN {isbn}: {original_pub} → {row['Pub Date']}")

                # Only try to parse date if both as_of_date and a valid Pub Date exist,
                # and skip_date_check is not True
                if not skip_date_check and as_of_date and row.get('Pub Date'):
                    try:
                        pub_date = datetime.fromisoformat(row['Pub Date']).date()
                        if pub_date > as_of_date:
                            if isbn == '9781324073796':
                                logging.info(f"Skipping 9781324073796 due to future pub date {pub_date}")
                            continue
                    except ValueError:
                        logging.warning(f"Skipping date comparison for ISBN {row.get('ISBN', 'Unknown')}: Invalid pub date format: {row['Pub Date']}")
                
                try:
                    quantity = int(row.get('Quantity', 0))
                except ValueError:
                    logging.warning(f"Invalid quantity format for ISBN {isbn}: {row.get('Quantity')}. Using 0.")
                    quantity = 0
                
                if isbn:  # Only process if ISBN exists
                    if isbn not in preorder_totals:
                        preorder_totals[isbn] = 0
                    preorder_totals[isbn] += quantity
    
    except Exception as e:
        logging.error(f"Error calculating preorder totals: {e}")
        raise

    logging.debug(f"Preorder totals loaded for {len(preorder_totals)} ISBNs")
    logging.debug(f"Example keys: {list(preorder_totals.keys())[:10]}")
    
    return preorder_totals

def process_released_preorders(sales_data, pub_date_overrides=None):
    """Process released preorders and add to sales data"""
    current_date = datetime.now().date()
    preorder_totals = calculate_total_preorder_quantities(current_date, pub_date_overrides)    
    
    # Create dictionary to track books that were just released this week
    newly_released = {}
    
    # Add preorder quantities to sales data for released books
    # but only if they're no longer in preorder status
    for isbn, quantity in preorder_totals.items():
        # Get product details for this ISBN
        product_ids = get_product_ids_by_isbn(isbn)  # You'll need to implement this
        
        if not product_ids:
            logging.warning(f"Could not find product ID for ISBN {isbn}")
            continue
            
        product_details = fetch_product_details(product_ids)
        if not product_details:
            logging.warning(f"Could not fetch product details for ISBN {isbn}")
            continue
            
        # Use the first product (there should only be one with this ISBN)
        product_id = product_ids[0]
        details = product_details.get(product_id, {})
        details['barcode'] = isbn  # Add barcode to details for override lookup
        
        # Check if the book is still in preorder status (with overrides)
        is_preorder, reason = is_preorder_or_future_pub(details, pub_date_overrides)
        
        if not is_preorder:  # Only add to sales data if no longer in preorder
            logging.info(f"Found released preorder: ISBN {isbn}, Quantity {quantity}")
            sales_data[isbn] = sales_data.get(isbn, 0) + quantity
            newly_released[isbn] = quantity
    
    # Log information about newly released books
    if newly_released:
        logging.info(f"Added {len(newly_released)} newly released books to sales data")
        for isbn, qty in newly_released.items():
            logging.info(f"Released: ISBN {isbn} with {qty} copies")
    else:
        logging.info("No items released this week")
    
    return sales_data

def is_preorder_or_future_pub(product_details, pub_date_overrides=None):
    """
    Checks if a product is preorder or has future pub date
    Now considers both collection status, publication date, and inventory level
    """
    if not product_details:
        logging.debug("No product details provided")
        return False, None
        
    # Check if in Preorder collection
    collections = product_details.get('collections', [])
    is_in_preorder_collection = 'Preorder' in collections
    logging.info(f"Product collections: {collections}")
    logging.info(f"Is in Preorder collection: {is_in_preorder_collection}")
    
    # Get barcode/ISBN from product details if available
    barcode = None
    if 'barcode' in product_details:
        barcode = product_details['barcode']
    
    # Check inventory level
    inventory = product_details.get('inventory', 0)
    has_positive_inventory = inventory > 0
    logging.info(f"Inventory: {inventory}, Has positive inventory: {has_positive_inventory}")
    
    # Check for override first
    pub_date_str = None
    if pub_date_overrides and barcode and barcode in pub_date_overrides:
        pub_date_str = pub_date_overrides[barcode]
        logging.info(f"Using overridden pub date for ISBN {barcode}: {pub_date_str} (instead of {product_details.get('pub_date', 'unknown')})")
    else:
        # Use the original pub date from metadata
        pub_date_str = product_details.get('pub_date')
        
    logging.info(f"Product pub date: {pub_date_str}")
    
    # Check if publication date is in the future
    is_future_pub = False
    if pub_date_str:
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
            is_future_pub = pub_date > datetime.now().date()
            logging.info(f"Pub date {pub_date} is future: {is_future_pub}")
        except ValueError:
            logging.error(f"Invalid pub date format: {pub_date_str}")
    
    # If book is in preorder collection but pub date has passed, check inventory
    if is_in_preorder_collection and not is_future_pub and pub_date_str:
        logging.warning(f"Book {product_details.get('title')} (ISBN: {barcode}) has passed "
                       f"publication date {pub_date_str} but is still in Preorder collection.")
        
        # Only consider it ready for release if it has positive inventory
        if has_positive_inventory:
            return False, "Publication date passed but still in Preorder collection (has positive inventory)"
        else:
            logging.warning(f"Book has non-positive inventory ({inventory}), keeping as preorder")
            return True, "Publication date passed but still in Preorder collection (no inventory)"
    
    # Normal logic
    if is_in_preorder_collection:
        return True, 'Preorder Collection'
        
    if is_future_pub:
        return True, f'Future Pub Date: {pub_date_str}'
    
    return False, None

def process_refunds(order):
    """
    Process refunds for an order
    """
    refunded_quantities = {}
    refunds = order.get('refunds', [])
    for refund in refunds:
        refund_line_items = refund.get('refundLineItems', {}).get('edges', [])
        for refund_item in refund_line_items:
            refund_node = refund_item['node']
            quantity = refund_node['quantity']
            line_item = refund_node.get('lineItem', {})
            variant = line_item.get('variant')
            
            if variant and variant.get('barcode'):
                barcode = variant['barcode']
                if barcode not in refunded_quantities:
                    refunded_quantities[barcode] = 0
                refunded_quantities[barcode] += quantity
                
    return refunded_quantities

def aggregate_sales(orders, pub_date_overrides=None):
    """
    Aggregates sales data using two-phase approach
    Now includes tracking of preorder items and respects publication date overrides
    """
    sales_data = {}
    skipped_line_items = []
    preorder_items = []  # New list to track preorder items
    
    # First collect all unique product IDs
    product_ids = set()
    for order in orders:
        if order.get('cancelledAt'):
            continue
            
        for line_item in order.get('lineItems', {}).get('edges', []):
            variant = line_item['node'].get('variant')
            if variant and variant.get('product', {}).get('id'):
                product_ids.add(variant['product']['id'])
    
    # Fetch product details
    logging.info(f"Fetching details for {len(product_ids)} products")
    product_details = fetch_product_details(list(product_ids))
    
    # Process orders with product details
    for order in orders:
        if order.get('cancelledAt'):
            continue
            
        order_id = order['id']
        refunded_quantities = process_refunds(order)
        
        for line_item in order.get('lineItems', {}).get('edges', []):
            line_item_node = line_item['node']
            quantity = line_item_node['quantity']
            variant = line_item_node.get('variant')
            
            if not variant:
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'quantity': quantity,
                    'reason': 'No variant information'
                })
                continue
            
            barcode = variant.get('barcode')
            if not barcode:
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'barcode': 'N/A',
                    'quantity': quantity,
                    'reason': 'No barcode'
                })
                continue
            
            if not is_valid_isbn(barcode):
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'barcode': barcode,
                    'quantity': quantity,
                    'reason': 'Not an ISBN (does not start with 978 or 979)'
                })
                continue
            
            # Check preorder status using product details
            product = variant.get('product', {})
            product_id = product.get('id')
            details = product_details.get(product_id, {})
            
            # Add barcode to details for override lookup
            details['barcode'] = barcode
            
            # Pass pub_date_overrides to is_preorder_or_future_pub
            is_excluded, reason = is_preorder_or_future_pub(details, pub_date_overrides)
            if is_excluded:
                # If it's a preorder or future pub, track it
                if reason == 'Preorder Collection' or reason.startswith('Future Pub Date'):
                    logging.info(f"Found preorder item - Title: {product.get('title', 'Unknown')}")
                    logging.info(f"Order details - ID: {order.get('id')}, Name: {order.get('name')}")
                    logging.info(f"Line item details - ID: {line_item_node.get('id')}")
                    
                    preorder_items.append({
                        'barcode': barcode,
                        'title': product.get('title', 'Unknown'),
                        'quantity': quantity,
                        'pub_date': details.get('pub_date'),
                        'order_id': order.get('id'),
                        'order_name': order.get('name'),
                        'line_item_id': line_item_node.get('id')
                    })
                    
                    logging.info(f"Added preorder item to tracking list - ISBN: {barcode}, Quantity: {quantity}")
                
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': product.get('title', 'Unknown'),
                    'barcode': barcode,
                    'quantity': quantity,
                    'reason': reason
                })
                continue
            
            # Calculate final quantity after refunds
            refunded_qty = refunded_quantities.get(barcode, 0)
            final_qty = quantity - refunded_qty
            
            if final_qty > 0:
                sales_data[barcode] = sales_data.get(barcode, 0) + final_qty
    
    return sales_data, skipped_line_items, preorder_items

def export_skipped_line_items(skipped_line_items, filename):
    """
    Exports skipped line items to a CSV file with additional details.
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.join(output_dir, filename)
    
    logging.info(f"Exporting skipped items to CSV at path: {abs_path}")
    
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Product Name', 'Barcode/ISBN', 'Quantity', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([
                item['order_id'],
                item['product_name'],
                item.get('barcode', 'N/A'),  # Add barcode if available
                item['quantity'],
                item['reason']
            ])

def export_to_csv(sales_data, filename):
    """
    Exports the sales data to a CSV file.
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.join(output_dir, filename)
    
    logging.info(f"Exporting to CSV at path: {abs_path}")
    
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])

def send_email(report_filename, skipped_filename, preorder_filename, start_date, end_date, skipped_items, approved_releases=None):
    """
    Sends the report as an email attachment using SendGrid.
    Now includes information about approved preorders that were released
    
    Args:
        report_filename: Path to the main report CSV
        skipped_filename: Path to the excluded items CSV
        preorder_filename: Path to the preorder tracking CSV
        start_date: Start date of the report period (YYYY-MM-DD)
        end_date: End date of the report period (YYYY-MM-DD)
        skipped_items: List of items skipped from the report
        approved_releases: List of approved preorder releases (optional)
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails_raw = os.getenv('EMAIL_RECIPIENTS', '')
    
    # Improved recipient email parsing
    recipient_emails = []
    if recipient_emails_raw:
        # Split by comma, handle potential spaces
        for email in recipient_emails_raw.split(','):
            clean_email = email.strip()
            if clean_email:  # Only add non-empty emails
                recipient_emails.append(clean_email)
    
    if not api_key or not sender_email or not recipient_emails:
        logging.error(f"Error: Missing email configuration. API Key: {'Present' if api_key else 'Missing'}, "
                      f"Sender: {'Present' if sender_email else 'Missing'}, "
                      f"Recipients: {len(recipient_emails) if recipient_emails else 'Missing'}")
        if recipient_emails_raw:
            logging.error(f"Raw recipient string: '{recipient_emails_raw}'")
            logging.error(f"Parsed recipients: {recipient_emails}")
        return

    # Log email configuration
    logging.info(f"Sending email from: {sender_email}")
    logging.info(f"Sending to {len(recipient_emails)} recipients")
    
    output_dir = os.path.join(BASE_DIR, 'output')
    abs_report_path = os.path.join(output_dir, report_filename)
    abs_skipped_path = os.path.join(output_dir, skipped_filename)
    abs_preorder_path = os.path.join(BASE_DIR, 'preorders', preorder_filename)

    # Create summary of skipped items
    skipped_summary = {}
    for item in skipped_items:
        reason = item['reason']
        if reason not in skipped_summary:
            skipped_summary[reason] = 0
        skipped_summary[reason] += item['quantity']

    email_content = f"""NYT Bestseller Weekly Report
Report Period: Sunday {start_date} through Saturday {end_date}

REPORT DEFINITIONS:
- This report includes all completed sales of ISBN products (barcodes starting with '978' or '979')
- Quantities reflect final sales after any refunds or cancellations
- Each line includes the ISBN and the total quantity sold

"""

    # Add section for preorders released to report - NEW
    if approved_releases and len(approved_releases) > 0:
        email_content += "PREORDERS RELEASED TO REPORT:\n"
        for release in approved_releases:
            isbn = release.get('isbn', 'Unknown')
            title = release.get('title', 'Unknown')
            quantity = release.get('quantity', 0)
            pub_date = release.get('pub_date', 'Unknown')
            inventory = release.get('inventory', 0)
            
            email_content += f"- {title} (ISBN: {isbn})\n"
            email_content += f"  Preorder Quantity: {quantity}, Current Inventory: {inventory}, Release Date: {pub_date}\n"
        
        email_content += "\n"
    
    email_content += "ITEMS NOT INCLUDED IN REPORT:\n"
    for reason, quantity in skipped_summary.items():
        email_content += f"- {quantity} items: {reason}\n"

    email_content += "\nAttached files:\n"
    email_content += f"1. {report_filename} - NYT Bestseller sales report\n"
    email_content += f"2. {skipped_filename} - Detailed list of excluded items\n"
    email_content += f"3. {preorder_filename} - Preorder tracking log\n"

    sg = sendgrid.SendGridAPIClient(api_key)
    subject = f"NYT Bestseller Weekly Report ({start_date} to {end_date})"

    message = Mail(
        from_email=sender_email,
        to_emails=recipient_emails,
        subject=subject,
        plain_text_content=email_content
    )

    # Attach main report
    try:
        with open(abs_report_path, 'rb') as f:
            report_data = f.read()
            encoded_file = base64.b64encode(report_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(report_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching main report: {e}")
        return

    # Attach excluded items report
    try:
        with open(abs_skipped_path, 'rb') as f:
            skipped_data = f.read()
            encoded_file = base64.b64encode(skipped_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(skipped_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching excluded items report: {e}")
        return

    # Attach preorder tracking report
    try:
         # Use the path in the preorders directory
        abs_preorder_path = os.path.join(BASE_DIR, 'preorders', 'NYT_preorder_tracking.csv')
    
        with open(abs_preorder_path, 'rb') as f:
            preorder_data = f.read()
            encoded_file = base64.b64encode(preorder_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(preorder_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching preorder tracking report: {e}")
        return

    try:
        response = sg.send(message)
        logging.info(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def get_last_week_date_range():
    """
    Returns the date range for last week (Sunday through Saturday)
    For a report run on Monday Feb 3rd, 2025, this should return:
    Sunday Jan 26th through Saturday Feb 1st
    """
    today = datetime.now()
    
    # First, find the most recent Saturday (Feb 1st in our example)
    days_after_saturday = today.weekday() + 2  # Adding 2 because Sunday is 6 and we want to include the previous Saturday
    last_saturday = today - timedelta(days=days_after_saturday)
    
    # Then get the Sunday before that Saturday (Jan 26th in our example)
    last_sunday = last_saturday - timedelta(days=6)
    
    # Set times to ensure full day coverage
    last_sunday = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_saturday = last_saturday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return last_sunday.strftime('%Y-%m-%d'), last_saturday.strftime('%Y-%m-%d')

def validate_sales_data(sales_data, skipped_items):
    """
    Performs basic validation checks on sales data
    Returns a list of warnings if any issues are found
    """
    warnings = []
    
    # Basic volume checks
    total_quantity = sum(sales_data.values())
    if total_quantity == 0:
        warnings.append("WARNING: No sales recorded for this period")
    
    # ISBN format check
    invalid_isbns = [isbn for isbn in sales_data.keys() 
                    if not (str(isbn).startswith('978') or str(isbn).startswith('979'))]
    if invalid_isbns:
        warnings.append(f"WARNING: Found {len(invalid_isbns)} invalid ISBNs in sales data")
    
    # Unusual quantities check (more than 1000 of any single ISBN)
    large_quantities = [(isbn, qty) for isbn, qty in sales_data.items() if qty > 1000]
    if large_quantities:
        warnings.append(f"WARNING: Unusually large quantities found for {len(large_quantities)} ISBNs")
        for isbn, qty in large_quantities:
            warnings.append(f"         ISBN: {isbn}, Quantity: {qty}")
    
    # Check for negative quantities
    negative_quantities = [(isbn, qty) for isbn, qty in sales_data.items() if qty < 0]
    if negative_quantities:
        warnings.append(f"WARNING: Found {len(negative_quantities)} ISBNs with negative quantities")
    
    # Basic skipped items analysis
    if len(skipped_items) > 100:  # Arbitrary threshold
        warnings.append(f"WARNING: Large number of skipped items: {len(skipped_items)}")
    
    return warnings

def find_latest_approved_releases():
    """
    Find the most recent approved releases file
    Returns a tuple of (file_path, is_processed)
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return None, False
    
    # Find approved_releases files
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    
    if not approval_files:
        logging.info("No approved releases files found")
        return None, False
    
    # Sort by filename (which contains date) to get the most recent
    approval_files.sort(reverse=True)
    latest_file = os.path.join(output_dir, approval_files[0])
    
    # Check if file has already been processed
    processed_marker = latest_file + '.processed'
    if os.path.exists(processed_marker):
        logging.info(f"Latest approval file has already been processed: {latest_file}")
        return latest_file, True
    
    return latest_file, False

def generate_weekly_delta_log(tracking_file='NYT_preorder_tracking.csv'):
    import difflib
    preorders_dir = os.path.join(BASE_DIR, 'preorders')
    tracking_path = os.path.join(preorders_dir, tracking_file)
    output_dir = os.path.join(BASE_DIR, 'output')
    delta_path = os.path.join(output_dir, f"delta_log_{datetime.now().strftime('%Y-%m-%d')}.txt")
    # Find most recent previous file in artifacts or saved directory (if available)
    # For now, this checks for a .bak version from last run
    previous_path = tracking_path + '.bak'
    if not os.path.exists(previous_path):
        logging.info("No previous preorder tracking file found, skipping delta log generation.")
        return
    with open(previous_path, 'r', encoding='utf-8') as prev_file:
        prev_lines = prev_file.readlines()
    with open(tracking_path, 'r', encoding='utf-8') as curr_file:
        curr_lines = curr_file.readlines()
    diff = list(difflib.unified_diff(prev_lines, curr_lines, fromfile='previous', tofile='current', lineterm=''))
    if diff:
        with open(delta_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diff))
        logging.info(f"Weekly delta log written to {delta_path}")
    else:
        logging.info("No changes detected between current and previous preorder tracking file.")

def main():
    print(f"Script running from directory: {os.getcwd()}")
    print(f"BASE_DIR set to: {BASE_DIR}")
    print(f"Python version: {sys.version}")

    load_environment()

    # Load centralized automation controls (flags, tag rules, etc)
    automation_controls = load_automation_controls()

    # Automatically determine last week's date range
    start_date, end_date = get_last_week_date_range()
    print(f"Generating report for: {start_date} to {end_date}")

    global SHOP_URL, GRAPHQL_URL, HEADERS
    SHOP_URL = os.getenv('SHOP_URL')
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')

    if not SHOP_URL or not ACCESS_TOKEN:
        logging.error("Error: Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN.")
        return

    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2025-01/graphql.json"
    HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}

    # Load publication date overrides - NEW
    pub_date_overrides = load_pub_date_overrides()
    
    orders = fetch_orders(start_date, end_date)
    if not orders:
        logging.error("No orders found.")
        return

    # Pass the overrides to aggregate_sales
    sales_data, skipped_items, preorder_items = aggregate_sales(orders, pub_date_overrides)
    if not sales_data:
        logging.error("No sales data.")
        return

    # Add approved releases to sales data
    sales_data = process_approved_releases(sales_data, BASE_DIR)

    # Get the approved releases information for the email
    approved_releases = []
    latest_file, already_processed = find_latest_approved_releases()
    
    if latest_file:
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                approved_data = json.load(f)
            
            approved_releases = approved_data.get('approved_releases', [])
            logging.info(f"Found {len(approved_releases)} approved releases for email notification")
        except Exception as e:
            logging.error(f"Error loading approved releases data: {e}")

    # --- Backup current tracking file before overwriting (at top of main) ---
    preorder_csv_path = os.path.join(BASE_DIR, 'preorders', 'NYT_preorder_tracking.csv')
    preorder_backup_path = preorder_csv_path + '.bak'
    if os.path.exists(preorder_csv_path):
        import shutil
        shutil.copy(preorder_csv_path, preorder_backup_path)
        logging.info(f"Backed up existing preorder tracking file to {preorder_backup_path}")

    # Track preorder sales
    track_preorder_sales(preorder_items)

    # --- Generate delta log (after track_preorder_sales) ---
    generate_weekly_delta_log()
    
    # Process and add released preorders to sales data - pass overrides
    # sales_data = process_released_preorders(sales_data, pub_date_overrides)

    logging.info(f"Tracking {len(preorder_items)} new preorder items")
    logging.info("No items released this week")

    # Initialize released_items as empty dict before using it
    released_items = {}
    
    # Add released items to sales_data
    for isbn, quantity in released_items.items():
        sales_data[isbn] = sales_data.get(isbn, 0) + quantity

    # Run validations
    warnings = validate_sales_data(sales_data, skipped_items)

    # Create email content
    email_content = f"""Weekly Shopify Sales Report
Report Period: {start_date} to {end_date}

REPORT DEFINITIONS:
- This report includes all completed sales of ISBN products (barcodes starting with '978')
- Quantities reflect final sales after any refunds or cancellations
- Each line includes the ISBN and the total quantity sold

"""

    # Add warnings if any exist
    if warnings:
        email_content += "\nVALIDATION WARNINGS:\n"
        for warning in warnings:
            email_content += f"{warning}\n"
            logging.warning(warning)  # Also log the warnings

    # Add preorder tracking details to email
    email_content += "\nPREORDER TRACKING:\n"
    if preorder_items:
        email_content += f"Total Preorder Items Tracked: {len(preorder_items)}\n"
        preorder_summary = {}
        for item in preorder_items:
            title = item['title']
            if title not in preorder_summary:
                preorder_summary[title] = 0
            preorder_summary[title] += item['quantity']
        
        for title, qty in preorder_summary.items():
            email_content += f"- {title}: {qty} preorder copies\n"
    else:
        email_content += "No preorder items tracked this week.\n"

    # If there are any released items
    if released_items:
        email_content += "\nRELEASED PREORDER ITEMS:\n"
        for isbn, qty in released_items.items():
            email_content += f"- ISBN {isbn}: {qty} copies now included in sales report\n"

    report_filename = f"NYT_weekly_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    skipped_filename = f"NYT_excluded_items_{datetime.now().strftime('%Y-%m-%d')}.csv"
    preorder_filename = f"NYT_preorder_tracking.csv"

    export_to_csv(sales_data, report_filename)
    export_skipped_line_items(skipped_items, skipped_filename)

    # Set up paths for verification
    output_dir = os.path.join(BASE_DIR, 'output')
    report_path = os.path.join(output_dir, report_filename)
    skipped_path = os.path.join(output_dir, skipped_filename)
    preorder_path = os.path.join(BASE_DIR, 'preorders', preorder_filename)

    logging.info("=== File Verification ===")
    files_to_check = {
        'Weekly Sales Report': report_path,
        'Excluded Items': skipped_path,
        'Preorder Tracking': preorder_path
    }

    for file_type, path in files_to_check.items():
        if os.path.exists(path):
            logging.info(f"Verified {file_type} exists at: {path}")
        else:
            logging.error(f"Missing {file_type} at: {path}")

    # Additional environment verification logging
    logging.info("=== Environment Verification ===")
    logging.info(f"Python Version: {sys.version}")
    logging.info(f"Current Directory: {os.getcwd()}")
    logging.info(f"BASE_DIR: {BASE_DIR}")
    logging.info(f"Output Directory: {output_dir}")
    logging.info(f"Preorders Directory: {os.path.join(BASE_DIR, 'preorders')}")

    # Send email with all reports
    send_email(
        report_filename,
        skipped_filename,
        preorder_filename,
        start_date,
        end_date,
        skipped_items,
        approved_releases
    )

if __name__ == "__main__":
    main()