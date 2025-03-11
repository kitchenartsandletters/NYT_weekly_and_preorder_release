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

# Import the new environment loading module
from env_loader import load_environment_variables, initialize_api_credentials

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
        
    logging.info(f"Using GraphQL URL: {GRAPHQL_URL}")
    
    query = """
    query {
        collectionByHandle(handle: "preorder") {
            products(first: 250) {
                edges {
                    node {
                        id
                        title
                        variants(first: 1) {
                            edges {
                                node {
                                    barcode
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
        data = run_query_with_retries(query, {})
        product_edges = data.get('collectionByHandle', {}).get('products', {}).get('edges', [])
        
        products = []
        for edge in product_edges:
            product = edge['node']
            
            # Get barcode (ISBN)
            barcode = None
            if product.get('variants', {}).get('edges'):
                barcode = product['variants']['edges'][0]['node'].get('barcode')
            
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
                'pub_date': pub_date
            })
        
        return products
        
    except Exception as e:
        logging.error(f"Error fetching preorder products: {e}")
        return []

def check_suspicious_pub_dates(products):
    """
    Check for suspicious publication dates:
    1. Books with pub dates in the past
    2. Books with very recent pub dates (might have just released)
    3. Books with pub dates within the next week (about to release)
    4. Books with no pub date
    """
    today = datetime.now().date()
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

def identify_pending_releases(pub_date_overrides=None):
    """
    Identify books that are about to be released based on their pub dates
    and determine which preorders should be moved to the regular sales report
    """
    current_date = datetime.now().date()
    preorder_totals = calculate_total_preorder_quantities(current_date)
    
    pending_releases = []
    error_cases = []
    total_quantity = 0
    
    for isbn, quantity in preorder_totals.items():
        try:
            product_ids = get_product_ids_by_isbn(isbn)
            if not product_ids:
                error_cases.append({
                    'isbn': isbn,
                    'quantity': quantity,
                    'error': 'Product not found in Shopify'
                })
                continue
                
            product_details = fetch_product_details(product_ids)
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
            
            # Check if the book is no longer in preorder status (with overrides)
            is_preorder, reason = is_preorder_or_future_pub(details, pub_date_overrides)
            
            if not is_preorder:
                # This book is ready to be released
                pending_releases.append({
                    'isbn': isbn,
                    'title': details.get('title', 'Unknown'),
                    'quantity': quantity,
                    'original_pub_date': details.get('pub_date', 'Unknown'),
                    'overridden_pub_date': pub_date_overrides.get(isbn) if pub_date_overrides else None,
                    'reason': 'No longer in preorder status'
                })
                total_quantity += quantity
        except Exception as e:
            error_cases.append({
                'isbn': isbn,
                'quantity': quantity,
                'error': str(e)
            })
    
    result = {
        'pending_releases': pending_releases,
        'error_cases': error_cases,
        'total_quantity': total_quantity,
        'run_date': datetime.now().strftime('%Y-%m-%d'),
        'total_pending_books': len(pending_releases)
    }
    
    return result

def save_pending_releases(pending_data, output_file=None):
    """Save pending releases to a JSON file"""
    if not output_file:
        output_dir = os.path.join(BASE_DIR, 'audit')
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
    
    # Identify and save pending releases
    logging.info("Identifying pending releases from preorders")
    pending_data = identify_pending_releases(pub_date_overrides)
    pending_file = save_pending_releases(pending_data, args.output_releases)
    
    # Print pending release summary
    logging.info("=== Pending Releases ===")
    logging.info(f"Books ready to be released: {pending_data['total_pending_books']}")
    logging.info(f"Total quantity to be released: {pending_data['total_quantity']}")
    
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
        return 1
    
    return 0

def generate_test_preorder_data():
    """Generate test data for preorder products"""
    # Create a realistic simulated response with different kinds of publication date issues
    today = datetime.now().date()
    future_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    recent_date = (today - timedelta(days=3)).strftime('%Y-%m-%d')
    past_date = (today - timedelta(days=60)).strftime('%Y-%m-%d')
    malformed_date = "Coming Soon"
    
    test_products = [
        {
            "id": "gid://shopify/Product/1111111111",
            "title": "Future Release Book",
            "barcode": "9781234567890",
            "pub_date": future_date
        },
        {
            "id": "gid://shopify/Product/2222222222",
            "title": "Recent Release Book",
            "barcode": "9781234567891",
            "pub_date": recent_date
        },
        {
            "id": "gid://shopify/Product/3333333333",
            "title": "Past Due Book",
            "barcode": "9781234567892",
            "pub_date": past_date
        },
        {
            "id": "gid://shopify/Product/4444444444",
            "title": "Missing Date Book",
            "barcode": "9781234567893",
            "pub_date": None
        },
        {
            "id": "gid://shopify/Product/5555555555",
            "title": "Malformed Date Book",
            "barcode": "9781234567894",
            "pub_date": malformed_date
        }
    ]
    
    # Match the structure expected by the calling code
    edges = []
    for product in test_products:
        node = {
            "id": product["id"],
            "title": product["title"],
            "variants": {
                "edges": [
                    {
                        "node": {
                            "barcode": product["barcode"]
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