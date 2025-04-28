#!/usr/bin/env python
"""
Audit script to check for publication date issues in preorders
and identify books that are about to be released
"""
import os
import sys
import csv
import json
import logging
import argparse
from datetime import datetime, timedelta
import requests
import time
import pytz
from datetime import timezone

# Import the new environment loading module
from env_loader import load_environment_variables, initialize_api_credentials
from preorder_history_tracker import is_preorder_reported

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables with defaults
GRAPHQL_URL = None
HEADERS = None
USE_TEST_DATA = False

# Import functions from compatibility module
from audit_compatibility import (
    BASE_DIR, load_environment, fetch_product_details, 
    run_query_with_retries, GRAPHQL_URL, HEADERS,
    load_pub_date_overrides, is_preorder_or_future_pub,
    calculate_total_preorder_quantities, get_product_ids_by_isbn
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def run_query_with_retries(query, variables, max_retries=3, delay=1):
    """
    Runs a GraphQL query with retry logic
    """
    global GRAPHQL_URL, HEADERS, USE_TEST_DATA
    
    # If in test data mode, return simulated data
    if USE_TEST_DATA:
        logging.info("🧪 Test mode active - returning simulated data instead of making API call")
        
        # Determine what type of query this is and return appropriate test data
        if "collectionByHandle" in query and "preorder" in query:
            # This is a query for preorder products
            return generate_test_preorder_data()
        
        # Default test response
        return {"data": {"dummy": "response"}}
    
    attempt = 0
    while attempt < max_retries:
        try:
            # Debug the API request
            logging.debug(f"Making API request to: {GRAPHQL_URL}")
            logging.debug(f"Headers: {HEADERS}")
            logging.debug(f"Query: {query[:100]}...")  # First 100 chars of query
            logging.debug(f"Variables: {variables}")
            
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

def fetch_preorder_products():
    """Fetch all products in the Preorder collection"""
    global GRAPHQL_URL, HEADERS, USE_TEST_DATA

    # For test mode, use the generated test data directly
    if USE_TEST_DATA:
        logging.info("🧪 Test mode active - using simulated preorder data")
        test_data = generate_test_preorder_data()
        product_edges = test_data.get('collectionByHandle', {}).get('products', {}).get('edges', [])
        
        products = []
        for edge in product_edges:
            product = edge['node']
            
            # Get barcode (ISBN)
            barcode = None
            inventory = 0
            if product.get('variants', {}).get('edges'):
                variant = product['variants']['edges'][0]['node']
                barcode = variant.get('barcode')
                inventory = variant.get('inventoryQuantity', 0)
            
            # Get pub_date
            pub_date = None
            metafields = product.get('metafields', {}).get('edges', [])
            for metafield in metafields:
                if metafield['node']['key'] == 'pub_date':
                    pub_date = metafield['node']['value']
                    break
            
            products.append({
                'id': product['id'],
                'title': product['title'],
                'barcode': barcode,
                'pub_date': pub_date,
                'vendor': product.get('vendor', 'Unknown'),
                'inventory': inventory
            })
        
        return products
    
    # Ensure API settings are initialized
    if not GRAPHQL_URL or not HEADERS:
        shop_url = os.getenv('SHOP_URL')
        access_token = os.getenv('SHOPIFY_ACCESS_TOKEN')
        
        if not shop_url or not access_token:
            logging.error("Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN environment variables")
            return []
            
        GRAPHQL_URL = f"https://{shop_url}/admin/api/2025-01/graphql.json"
        HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": access_token}
        
    logging.info(f"Using GraphQL URL: {GRAPHQL_URL}")
    
    query = """
    query {
        collectionByHandle(handle: "pre-order") {
            products(first: 250) {
                edges {
                    node {
                        id
                        title
                        vendor
                        variants(first: 1) {
                            edges {
                                node {
                                    barcode
                                    inventoryQuantity
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
                    }
                }
            }
        }
    }
    """
    
    try:
        # Enhanced error checking with comprehensive logging
        logging.info("About to run GraphQL query for preorder products")
        
        try:
            data = run_query_with_retries(query, {})
            logging.info("Query executed successfully")
        except Exception as e:
            logging.error(f"Error in run_query_with_retries: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            logging.error("Returning empty product list due to query failure")
            return []

        # Check if data is None (shouldn't happen if exception is raised, but checking anyway)
        if data is None:
            logging.error("API query returned None despite not raising exception")
            return []
            
        # Check if collectionByHandle exists
        if 'collectionByHandle' not in data:
            logging.error(f"Missing 'collectionByHandle' in API response. Available keys: {list(data.keys())}")
            logging.error(f"Response data preview: {str(data)[:200]}...")
            return []
            
        # Check if collection exists but is null
        if data['collectionByHandle'] is None:
            logging.error("Collection 'preorder' not found in shop")
            return []

        # Check if products exist in collection
        if 'products' not in data['collectionByHandle']:
            logging.error("Collection found but missing 'products' field")
            logging.error(f"Collection data: {data['collectionByHandle']}")
            return []
            
        # Check if edges exist in products
        if 'edges' not in data['collectionByHandle']['products']:
            logging.error("Products found but missing 'edges' field")
            logging.error(f"Products data: {data['collectionByHandle']['products']}")
            return []

        product_edges = data['collectionByHandle']['products']['edges']
        logging.info(f"Found {len(product_edges)} product edges in the response")

        products = []
        for edge in product_edges:
            product = edge['node']
            
            # Get barcode (ISBN)
            barcode = None
            inventory = 0
            if product.get('variants', {}).get('edges'):
                variant = product['variants']['edges'][0]['node']
                barcode = variant.get('barcode')
                inventory = variant.get('inventoryQuantity', 0)
            
            # Get pub_date
            pub_date = None
            metafields = product.get('metafields', {}).get('edges', [])
            for metafield in metafields:
                if metafield['node']['key'] == 'pub_date':
                    pub_date = metafield['node']['value']
                    break
            
            products.append({
                'id': product['id'],
                'title': product['title'],
                'barcode': barcode,
                'pub_date': pub_date,
                'vendor': product.get('vendor', 'Unknown'),
                'inventory': inventory
            })
        
        return products
        
    except Exception as e:
        logging.error(f"Unexpected error in fetch_preorder_products: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return []


def check_suspicious_pub_dates(products):
    """
    Check for suspicious publication dates:
    1. Books with pub dates in the past
    2. Books with very recent pub dates (might have just released)
    3. Books with pub dates within the next week (about to release)
    4. Books with no pub date
    """
    import pytz
    eastern = pytz.timezone('US/Eastern')
    today = datetime.now(eastern).date()
    one_week_ago = today - timedelta(days=7)
    one_week_ahead = today + timedelta(days=7)
    
    past_pub_dates = []
    recent_releases = []
    upcoming_releases = []
    missing_pub_dates = []
    malformed_dates = []
    
    for product in products:
        pub_date_str = product.get('pub_date')
        
        if not pub_date_str:
            missing_pub_dates.append(product)
            continue
            
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
            
            if pub_date < today:
                past_pub_dates.append(product)
                
                if pub_date >= one_week_ago:
                    recent_releases.append(product)
            
            elif pub_date <= one_week_ahead:
                upcoming_releases.append(product)
                
        except ValueError:
            malformed_dates.append(product)
    
    return {
        'past_pub_dates': past_pub_dates,
        'recent_releases': recent_releases,
        'upcoming_releases': upcoming_releases,
        'missing_pub_dates': missing_pub_dates,
        'malformed_dates': malformed_dates
    }

# === Begin preorder grouping logic for KIT-84 ===
def group_preorder_titles(products, preorder_tracking, current_date):
    """
    Groups preorder titles into multiple categories:
    - Releasing this week
    - Releasing next week
    - Early Stock Arrivals (exceptions)
    - All preorders (sorted by pub date)
    """
    import pytz
    eastern = pytz.timezone('US/Eastern')
    # Ensure current_date is in US/Eastern timezone
    if isinstance(current_date, datetime):
        today = current_date.astimezone(eastern).date()
    else:
        # Assume it's a date, not datetime
        now_et = datetime.now(eastern)
        today = now_et.date()

    this_week = []
    next_week = []
    early_arrivals = []
    all_preorders = []

    pub_date_overrides = load_pub_date_overrides()

    # Debug: show available tracked ISBNs
    logging.debug(f"Sample tracked ISBNs: {[row['ISBN'] for row in preorder_tracking[:10]]}")

    for product in products:
        isbn = str(product.get('barcode')).strip()
        if isbn:
            exists_in_tracking = isbn in preorder_tracking
            logging.info(f"Product ISBN '{isbn}' — Exists in tracking: {exists_in_tracking}")
        else:
            logging.warning(f"Product missing ISBN: {product.get('title', 'Unknown Title')}")
        title = product.get('title', 'Unknown')
        inventory = product.get('inventory', 0)
        pub_date_str = product.get('pub_date')
        pub_date = None
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
        except Exception:
            pub_date = None

        presold_qty = preorder_tracking.get(isbn, 0)
        if isbn not in preorder_tracking:
            logging.warning(f"ISBN not found in preorder_tracking: {isbn}")
        else:
            logging.debug(f"Matched presale qty for ISBN {isbn}: {presold_qty}")
        if presold_qty == 0:
            logging.debug(f"No presold quantity found for ISBN {isbn} — defaulting to 0")
        tagged = True  # Placeholder — update if logic to fetch tags is built
        in_collection = True  # All come from preorder collection

        record = {
            'isbn': isbn,
            'title': title,
            'quantity': presold_qty,       # Keep for backward compatibility or possible uses
            'presold_qty': presold_qty,    # Revert to original field name
            'inventory': inventory,
            'pub_date': pub_date_str,
            'tagged': tagged,
            'in_collection': in_collection,
        }

        all_preorders.append(record.copy())

        if pub_date:
            # Determine the true start and end of this NYT reporting week (Sunday to Saturday)
            # today.weekday(): Monday=0, Sunday=6
            # So for Sunday (6), start_of_week = today
            # Otherwise, go back (weekday + 1) days to get to Sunday
            start_of_week = today - timedelta(days=today.weekday() + 1) if today.weekday() != 6 else today
            end_of_week = start_of_week + timedelta(days=6)

            if start_of_week <= pub_date <= end_of_week:
                this_week.append(record.copy())
            elif start_of_week + timedelta(days=7) <= pub_date <= end_of_week + timedelta(days=7):
                next_week.append(record.copy())
            elif pub_date > today and inventory > 0:
                reasons = []
                if not tagged:
                    reasons.append("No preorder tag")
                if not in_collection:
                    reasons.append("Removed from preorder collection")
                reasons.append("Inventory received early")
                record["reason"] = "; ".join(reasons)
                early_arrivals.append(record.copy())

    all_preorders.sort(key=lambda b: b.get("pub_date", "9999-12-31"))

    return {
        "release_this_week": this_week,
        "releases_next_week": next_week,
        "early_stock_arrivals": early_arrivals,
        "all_preorders": all_preorders
    }
# === End preorder grouping logic for KIT-84 ===

def generate_audit_report(audit_results, output_file=None):
    """Generate CSV reports for audit results"""
    if not output_file:
        audit_dir = os.path.join(BASE_DIR, 'audit')
        os.makedirs(audit_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d')
        output_file = os.path.join(audit_dir, f'pub_date_audit_{timestamp}.csv')
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Category', 'ISBN', 'Title', 'Pub Date', 'Status', 'Action Needed', 'Severity'])
        
        # Past pub dates
        for product in audit_results['past_pub_dates']:
            writer.writerow([
                'Past Pub Date',
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                'Suspicious',
                'Verify if already released or incorrect date',
                'High'
            ])
        
        # Recent releases
        for product in audit_results['recent_releases']:
            writer.writerow([
                'Recent Release',
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                'Info',
                'Check if preorders should be included in weekly report',
                'Medium'
            ])
        
        # Upcoming releases
        for product in audit_results['upcoming_releases']:
            writer.writerow([
                'Upcoming Release',
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                'Info',
                'Will be included in weekly report after this date',
                'Low'
            ])
        
        # Missing pub dates
        for product in audit_results['missing_pub_dates']:
            writer.writerow([
                'Missing Pub Date',
                product.get('barcode'),
                product.get('title'),
                'N/A',
                'Warning',
                'Add publication date metadata',
                'High'
            ])
        
        # Malformed dates
        for product in audit_results['malformed_dates']:
            writer.writerow([
                'Malformed Date',
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                'Error',
                'Fix date format (should be YYYY-MM-DD)',
                'High'
            ])
    
    logging.info(f"Audit report generated: {output_file}")
    return output_file

def suggest_overrides(audit_results, output_file=None):
    """Generate suggested overrides based on audit results"""
    if not output_file:
        override_dir = os.path.join(BASE_DIR, 'overrides')
        os.makedirs(override_dir, exist_ok=True)
        output_file = os.path.join(override_dir, 'suggested_overrides.csv')
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'Title', 'Current_Pub_Date', 'Suggested_Pub_Date', 'Action', 'Notes', 'Priority'])
        
        # Past pub dates that might need correction
        for product in audit_results['past_pub_dates']:
            # Suggest a date 30 days in the future as a reasonable default
            suggested_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            writer.writerow([
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                suggested_date,
                'Verify date',
                'Date in past but still in preorder collection',
                'High'
            ])
        
        # Missing pub dates
        for product in audit_results['missing_pub_dates']:
            # Suggest a date 30 days in the future as a reasonable default
            suggested_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            writer.writerow([
                product.get('barcode'),
                product.get('title'),
                'Missing',
                suggested_date,
                'Add date',
                'Required for proper preorder handling',
                'High'
            ])
        
        # Malformed dates
        for product in audit_results['malformed_dates']:
            writer.writerow([
                product.get('barcode'),
                product.get('title'),
                product.get('pub_date'),
                'YYYY-MM-DD',
                'Fix format',
                'Should be YYYY-MM-DD',
                'High'
            ])
    
    logging.info(f"Suggested overrides generated: {output_file}")
    return output_file

def get_inventory_level(product_id):
    """Get current inventory level for a product"""
    # If in test mode, return a random inventory number
    if USE_TEST_DATA:
        import random
        return random.randint(0, 50)
        
    query = """
    query($id: ID!) {
        product(id: $id) {
            variants(first: 1) {
                edges {
                    node {
                        inventoryQuantity
                    }
                }
            }
        }
    }
    """
    
    try:
        variables = {"id": product_id}
        data = run_query_with_retries(query, variables)
        
        variant_edges = data.get('product', {}).get('variants', {}).get('edges', [])
        if variant_edges:
            return variant_edges[0]['node'].get('inventoryQuantity', 0)
        
        return 0
    except Exception as e:
        logging.error(f"Error fetching inventory: {e}")
        return 0

def identify_pending_releases(pub_date_overrides=None, audit_results=None, grouped_output=None):
    """
    Identify books that are about to be released based on their pub dates
    and determine which preorders should be moved to the regular sales report.
    Now explicitly checks the Preorder collection in addition to tracked preorders.
    """
    # Debug ISBN - set to your specific ISBN
    debug_isbn = "9781954210561"
    
    # Default empty audit results if not provided
    if audit_results is None:
        audit_results = {
            'past_pub_dates': [],
            'recent_releases': [],
            'upcoming_releases': [],
            'missing_pub_dates': [],
            'malformed_dates': []
        }
    
    # Use override_today if present in globals for test consistency
    current_date = globals().get("override_today", datetime.now().date())
    
    # Debug log for test mode
    is_test_mode = os.environ.get('USE_TEST_DATA', '').lower() in ('true', '1', 't', 'yes')
    logging.info(f"identify_pending_releases running in {'TEST' if is_test_mode else 'PRODUCTION'} mode")
    
    # Load and log preorder history
    from preorder_history_tracker import load_preorder_history, is_preorder_reported
    history_data = load_preorder_history()
    history_count = len(history_data.get('reported_preorders', []))
    logging.info(f"Loaded preorder history with {history_count} entries")
    
    # Log a sample of history entries if available
    if history_count > 0:
        sample_size = min(3, history_count)
        logging.info(f"Sample of history entries (first {sample_size}):")
        for i in range(sample_size):
            entry = history_data['reported_preorders'][i]
            logging.info(f"  - ISBN: {entry.get('isbn')}, Quantity: {entry.get('quantity')}, Reported: {entry.get('report_date')}")
    
    # STEP 1: Get ALL books from Preorder collection
    all_preorder_products = fetch_preorder_products()
    logging.info(f"Fetched {len(all_preorder_products)} products from Preorder collection")
    
    # STEP 2: Get tracked preorders from the tracking file
    preorder_totals = calculate_total_preorder_quantities(current_date)
    logging.info(f"Found {len(preorder_totals)} ISBNs in preorder tracking file")
    logging.debug(f"Tracked ISBNs from preorder history: {list(preorder_totals.keys())[:10]}")

    if debug_isbn not in preorder_totals:
        logging.debug(f"DEBUG ISBN {debug_isbn} not found in preorder tracking.")
    
    # STEP 3: Check for the debug ISBN in both sources
    if debug_isbn:
        found_in_collection = False
        for product in all_preorder_products:
            if product.get('barcode') == debug_isbn:
                found_in_collection = True
                logging.info(f"DEBUG ISBN {debug_isbn} found in Preorder collection")
                logging.info(f"Title: {product.get('title')}")
                logging.info(f"Pub date: {product.get('pub_date')}")
                logging.info(f"Inventory: {product.get('inventory')}")
                break
        
        if not found_in_collection:
            logging.info(f"DEBUG ISBN {debug_isbn} NOT found in Preorder collection")
        
        if debug_isbn in preorder_totals:
            logging.info(f"DEBUG ISBN {debug_isbn} found in tracking with quantity {preorder_totals[debug_isbn]}")
        else:
            logging.info(f"DEBUG ISBN {debug_isbn} NOT found in tracking file")
    
    # STEP 4: Process both sources
    pending_releases = []
    error_cases = []
    total_quantity = 0
    processed_isbns = set()  # Track ISBNs we've already processed
    
    # First process tracked preorders
    for isbn, quantity in preorder_totals.items():
        is_debug_isbn = (isbn == debug_isbn)
        if is_debug_isbn:
            logging.info(f"Processing tracked ISBN {isbn} with quantity {quantity}")
        
        try:
            # Check if already reported in history
            already_reported, record = is_preorder_reported(isbn, history_data)
            if is_debug_isbn:
                if already_reported:
                    logging.info(f"Already reported on {record.get('report_date')} with quantity {record.get('quantity')}")
                else:
                    logging.info(f"Not previously reported")
                    
            if already_reported:
                if is_debug_isbn:
                    logging.info(f"Skipping due to previous reporting")
                continue
            
            # Get product IDs
            product_ids = get_product_ids_by_isbn(isbn)
            if is_debug_isbn:
                logging.info(f"Product IDs: {product_ids}")
                
            if not product_ids:
                if is_debug_isbn:
                    logging.info(f"No product IDs found for ISBN {isbn}")
                error_cases.append({
                    'isbn': isbn,
                    'quantity': quantity,
                    'error': 'Product not found in Shopify'
                })
                continue
            
            # Get product details
            product_details = fetch_product_details(product_ids)
            if is_debug_isbn:
                if product_details:
                    logging.info(f"Product details fetched successfully")
                else:
                    logging.info(f"Could not fetch product details")
                
            if not product_details:
                error_cases.append({
                    'isbn': isbn,
                    'quantity': quantity,
                    'error': 'Could not fetch product details'
                })
                continue
                
            product_id = product_ids[0]
            details = product_details.get(product_id, {})
            details['barcode'] = isbn
            
            # Get vendor and inventory information directly from product details
            vendor = details.get('vendor', 'Unknown')
            inventory = details.get('inventory', 0)
            
            if is_debug_isbn:
                logging.info(f"Details: title={details.get('title', 'Unknown')}, vendor={vendor}, inventory={inventory}")
                logging.info(f"Collections: {details.get('collections', [])}")
                logging.info(f"Pub date: {details.get('pub_date', 'Unknown')}")
            
            # Check if the book is no longer in preorder status (with overrides)
            is_preorder, reason = is_preorder_or_future_pub(details, pub_date_overrides)
            
            if is_debug_isbn:
                logging.info(f"Is preorder: {is_preorder}, Reason: {reason}")
                
                # Additional checks for debugging
                if is_preorder:
                    logging.info(f"Still considered preorder, won't be added to pending releases")
                else:
                    logging.info(f"No longer in preorder status, eligible for release")
            
            if not is_preorder:
                # This book is ready to be released
                pending_releases.append({
                    'isbn': isbn,
                    'title': details.get('title', 'Unknown'),
                    'quantity': quantity,
                    'pub_date': details.get('pub_date', 'Unknown'),  # For GitHub issue display
                    'original_pub_date': details.get('pub_date', 'Unknown'),
                    'overridden_pub_date': pub_date_overrides.get(isbn) if pub_date_overrides else None,
                    'reason': reason or 'No longer in preorder status',
                    'inventory': inventory,
                    'vendor': vendor,
                    'source': 'tracking'
                })
                if is_debug_isbn:
                    logging.info(f"Added tracked book to pending releases!")
                total_quantity += quantity
                processed_isbns.add(isbn)  # Mark as processed
        except Exception as e:
            if is_debug_isbn:
                logging.error(f"Error processing ISBN {isbn}: {e}")
                import traceback
                logging.error(traceback.format_exc())
            error_cases.append({
                'isbn': isbn,
                'quantity': quantity,
                'error': str(e)
            })
    
    # Then process books from collection that weren't in tracking
    for product in all_preorder_products:
        isbn = product.get('barcode')
        
        if not isbn or isbn in processed_isbns:
            continue  # Skip if already processed or no ISBN
        
        is_debug_isbn = (isbn == debug_isbn)
        if is_debug_isbn:
            logging.info(f"Processing collection-only ISBN {isbn}")
        
        try:
            # Check if already reported
            already_reported, record = is_preorder_reported(isbn, history_data)
            if already_reported:
                if is_debug_isbn:
                    logging.info(f"Skipping collection ISBN {isbn} - already reported")
                continue
                
            # Get product details (should be available since we got it from collection)
            product_ids = get_product_ids_by_isbn(isbn)
            if not product_ids:
                if is_debug_isbn:
                    logging.info(f"No product IDs found for collection ISBN {isbn}")
                continue
                
            product_details = fetch_product_details(product_ids)
            if not product_details:
                if is_debug_isbn:
                    logging.info(f"Could not fetch product details for collection ISBN {isbn}")
                continue
                
            product_id = product_ids[0]
            details = product_details.get(product_id, {})
            details['barcode'] = isbn
            
            vendor = details.get('vendor', 'Unknown')
            inventory = product.get('inventory', 0)  # Get inventory directly from collection data
            
            if is_debug_isbn:
                logging.info(f"Collection book details: title={details.get('title', 'Unknown')}, vendor={vendor}")
                logging.info(f"Inventory: {inventory}")
                logging.info(f"Pub date: {details.get('pub_date', 'Unknown')}")
            
            # Check preorder status with dual criteria
            is_preorder, reason = is_preorder_or_future_pub(details, pub_date_overrides)
            
            if is_debug_isbn:
                logging.info(f"Collection book preorder status: {is_preorder}, reason: {reason}")
            
            if not is_preorder:
                # For collection-only books, add with quantity of 0
                pending_releases.append({
                    'isbn': isbn,
                    'title': details.get('title', 'Unknown'),
                    'quantity': 0,  # Use 0 for books not in tracking to avoid inflating numbers
                    'pub_date': details.get('pub_date', 'Unknown'),  # For GitHub issue display
                    'original_pub_date': details.get('pub_date', 'Unknown'),
                    'overridden_pub_date': pub_date_overrides.get(isbn) if pub_date_overrides else None,
                    'reason': reason or 'Found in collection but not in tracking',
                    'inventory': inventory,
                    'vendor': vendor,
                    'source': 'collection'
                })
                if is_debug_isbn:
                    logging.info(f"Added collection-only book to pending releases!")
        except Exception as e:
            if is_debug_isbn:
                logging.error(f"Error processing collection ISBN {isbn}: {e}")
                import traceback
                logging.error(traceback.format_exc())
    
    # Format problematic books data for the issue
    problematic_books = {
        'past_pub_dates': [
            {
                'isbn': product.get('barcode'),
                'title': product.get('title'),
                'pub_date': product.get('pub_date'),
                'issue': 'Past publication date'
            } for product in audit_results['past_pub_dates']
        ],
        'missing_pub_dates': [
            {
                'isbn': product.get('barcode'),
                'title': product.get('title'),
                'issue': 'Missing publication date'
            } for product in audit_results['missing_pub_dates']
        ],
        'malformed_dates': [
            {
                'isbn': product.get('barcode'),
                'title': product.get('title'),
                'pub_date': product.get('pub_date'),
                'issue': 'Malformed date format'
            } for product in audit_results['malformed_dates']
        ]
    }
    
    # Add metadata about problematic books count
    total_problematic = (
        len(problematic_books['past_pub_dates']) +
        len(problematic_books['missing_pub_dates']) +
        len(problematic_books['malformed_dates'])
    )
    
    result = {
        'pending_releases': pending_releases,
        'error_cases': error_cases,
        'total_quantity': total_quantity,
        'run_date': datetime.now().strftime('%Y-%m-%d'),
        'total_pending_books': len(pending_releases),
        'problematic_books': problematic_books,
        'total_problematic_books': total_problematic,
        'test_data': is_test_mode  # Include test data flag
    }
    
    # Add KIT-84 groups to final result
    if grouped_output:
        result.update(grouped_output)

    return result

def save_pending_releases(pending_data, output_file=None):
    """Save pending releases to a JSON file"""
    if not output_file:
        output_dir = os.path.join(BASE_DIR, 'output')  # Changed from 'audit' to 'output'
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f'pending_releases_{datetime.now().strftime("%Y-%m-%d")}.json')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(pending_data, f, indent=2)
    
    logging.info(f"Pending releases saved to: {output_file}")
    return output_file

def main():
    """Main function to run the audit"""
    parser = argparse.ArgumentParser(description='Audit publication dates and identify pending releases')
    parser.add_argument('--output-releases', help='Output file for pending releases (JSON)')
    parser.add_argument('--output-audit', help='Output file for audit report (CSV)')
    parser.add_argument('--output-suggested', help='Output file for suggested overrides (CSV)')
    parser.add_argument('--test-mode', action='store_true', help='Run in test data mode without API calls')
    args = parser.parse_args()
    
    logging.info("Starting publication date audit")
    
    # Set test mode if specified via command line
    if args.test_mode:
        os.environ['USE_TEST_DATA'] = 'true'
        logging.info("Test mode enabled via command line argument")
    
    # Initialize API credentials
    global GRAPHQL_URL, HEADERS, USE_TEST_DATA
    
    api_config = initialize_api_credentials()
    if not api_config:
        logging.error("Failed to initialize API credentials. Cannot proceed.")
        return 1
    
    # Update global variables
    GRAPHQL_URL = api_config['GRAPHQL_URL']
    HEADERS = api_config['HEADERS']
    USE_TEST_DATA = api_config.get('TEST_MODE', False)
    
    logging.info(f"API initialized with URL: {GRAPHQL_URL}")
    if USE_TEST_DATA:
        logging.info("🧪 Running in TEST DATA mode - using simulated data")
    
    # Load publication date overrides
    pub_date_overrides = load_pub_date_overrides()
    logging.info(f"Loaded {len(pub_date_overrides)} publication date overrides")
    
    # Fetch all preorder products
    logging.info("Fetching preorder products")
    products = fetch_preorder_products()
    logging.info(f"Found {len(products)} preorder products")

    # Use Eastern Time Zone for current date
    import pytz
    eastern = pytz.timezone('US/Eastern')
    now_et = datetime.now(eastern)
    today_et = now_et.date()

    # Load preorder tracking as a list of rows (ledger style)
    preorder_rows = []
    with open(os.path.join(BASE_DIR, 'preorders/NYT_preorder_tracking.csv'), newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            preorder_rows.append(row)
    logging.info(f"Loaded {len(preorder_rows)} preorder tracking rows.")

    # Group preorder titles into structured categories for GitHub issue rendering
    grouped_output = group_preorder_titles(products, preorder_rows, today_et)
    globals()['grouped_output'] = grouped_output
    
    # Check for suspicious pub dates
    logging.info("Analyzing publication dates")
    audit_results = check_suspicious_pub_dates(products)
    
    # Print summary statistics
    logging.info("=== Audit Results ===")
    logging.info(f"Total preorder products: {len(products)}")
    logging.info(f"Products with past pub dates: {len(audit_results['past_pub_dates'])}")
    logging.info(f"Products with recent releases: {len(audit_results['recent_releases'])}")
    logging.info(f"Products with upcoming releases: {len(audit_results['upcoming_releases'])}")
    logging.info(f"Products with missing pub dates: {len(audit_results['missing_pub_dates'])}")
    logging.info(f"Products with malformed dates: {len(audit_results['malformed_dates'])}")
    
    # Generate reports
    audit_report = generate_audit_report(audit_results, args.output_audit)
    suggestions = suggest_overrides(audit_results, args.output_suggested)
    
    # Identify and save pending releases - PASS AUDIT RESULTS
    logging.info("Identifying pending releases from preorders")
    pending_data = identify_pending_releases(pub_date_overrides, audit_results, grouped_output)
    pending_file = save_pending_releases(pending_data, args.output_releases)
    
    # Print pending release summary
    logging.info("=== Pending Releases ===")
    logging.info(f"Books ready to be released: {pending_data['total_pending_books']}")
    logging.info(f"Total quantity to be released: {pending_data['total_quantity']}")
    logging.info(f"Books with issues requiring attention: {pending_data.get('total_problematic_books', 0)}")
    
    if pending_data['pending_releases']:
        logging.info("Books pending release:")
        for book in pending_data['pending_releases']:
            logging.info(f"  - {book['title']} (ISBN: {book['isbn']}): {book['quantity']} copies")
    
    logging.info("===== Audit Complete =====")
    logging.info(f"Audit report: {audit_report}")
    logging.info(f"Suggested overrides: {suggestions}")
    logging.info(f"Pending releases: {pending_file}")
    
    # Return non-zero exit code if there are issues requiring attention
    if (len(audit_results['past_pub_dates']) > 0 or 
        len(audit_results['malformed_dates']) > 0 or 
        len(pending_data['error_cases']) > 0):
        logging.warning("Issues were detected that require attention!")
    #    return 1
    
    return 0

def generate_test_preorder_data():
    """Generate test data for preorder products"""
    import pytz
    eastern = pytz.timezone('US/Eastern')
    today = datetime.now(eastern).date()
    future_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    recent_date = (today - timedelta(days=3)).strftime('%Y-%m-%d')
    past_date = (today - timedelta(days=60)).strftime('%Y-%m-%d')
    malformed_date = "Coming Soon"
    
    test_products = [
        {
            "id": "gid://shopify/Product/1111111111",
            "title": "Future Release Book",
            "barcode": "9781234567890",
            "pub_date": future_date,
            "vendor": "Test Publisher",
            "inventory": 25
        },
        {
            "id": "gid://shopify/Product/2222222222",
            "title": "Recent Release Book",
            "barcode": "9781234567891",
            "pub_date": recent_date,
            "vendor": "Example Press",
            "inventory": 15
        },
        {
            "id": "gid://shopify/Product/3333333333",
            "title": "Past Due Book",
            "barcode": "9781234567892",
            "pub_date": past_date,
            "vendor": "Sample Publishing",
            "inventory": 10
        },
        {
            "id": "gid://shopify/Product/4444444444",
            "title": "Missing Date Book",
            "barcode": "9781234567893",
            "pub_date": None,
            "vendor": "Unknown Publisher",
            "inventory": 5
        },
        {
            "id": "gid://shopify/Product/5555555555",
            "title": "Malformed Date Book",
            "barcode": "9781234567894",
            "pub_date": malformed_date,
            "vendor": "Demo Books",
            "inventory": 0
        }
    ]
    
    # Match the structure expected by the calling code
    edges = []
    for product in test_products:
        node = {
            "id": product["id"],
            "title": product["title"],
            "vendor": product["vendor"],
            "variants": {
                "edges": [
                    {
                        "node": {
                            "barcode": product["barcode"],
                            "inventoryQuantity": product["inventory"]
                        }
                    }
                ]
            },
            "metafields": {
                "edges": []
            }
        }
        
        # Add pub_date metafield if it exists
        if product["pub_date"]:
            node["metafields"]["edges"].append({
                "node": {
                    "key": "pub_date",
                    "value": product["pub_date"]
                }
            })
        
        edges.append({"node": node})
    
    return {
        "collectionByHandle": {
            "products": {
                "edges": edges
            }
        }
    }

if __name__ == "__main__":
    sys.exit(main())