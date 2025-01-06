#!/usr/bin/env python3
"""
Shopify GraphQL Sales Report Script
Version: 1.1.1
Description:
    - Supports multiple environments (production and test) by loading separate .env files.
    - Correctly initializes global variables for API connections.
    - Handles refunds by querying `refunds` as a list,
      subtracting refunded quantity from sales_data for items whose barcode starts with '978'.
    - Accurately accounts for line items with barcodes starting with '978'.
    - Last updated: 2025-01-06, includes environment selection and global variable fixes.
Author: Gil Calderon
Date: 2025-01-06
"""

import os
import requests
import csv
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv
import time
import random
import sys

# -----------------------------#
#         Configuration        #
# -----------------------------#

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

def load_environment(env):
    """
    Loads environment variables from the specified .env file based on the environment.
    """
    env_files = {
        'production': '.env.production',
        'test': '.env.test'
    }
    
    if env not in env_files:
        print(f"Error: Unknown environment '{env}'. Choose from 'production' or 'test'.")
        sys.exit(1)
    
    env_file = env_files[env]
    
    if not os.path.exists(env_file):
        print(f"Error: Environment file '{env_file}' does not exist.")
        sys.exit(1)
    
    load_dotenv(dotenv_path=env_file)
    print(f"Loaded environment variables from '{env_file}'.")
    logging.info(f"Loaded environment variables from '{env_file}'.")

# -----------------------------#
#          Helper Functions    #
# -----------------------------#

def run_query(query, variables=None):
    """
    Executes a GraphQL query against the Shopify API.
    Raises an exception if there's an error or invalid status code.
    """
    global GRAPHQL_URL, HEADERS  # Declare as global to access the variables
    payload = {
        "query": query,
        "variables": variables or {}
    }
    logging.debug(f"Sending GraphQL query with variables: {variables}")
    response = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS)
    logging.debug(f"Received response: {response.status_code} - {response.text}")
    if response.status_code != 200:
        logging.error(f"GraphQL query failed: {response.status_code} - {response.text}")
        raise Exception(f"GraphQL query failed: {response.status_code} - {response.text}")
    result = response.json()
    if "errors" in result:
        logging.error(f"GraphQL errors: {result['errors']}")
        raise Exception(f"GraphQL errors: {result['errors']}")
    return result['data']

def run_query_with_retries(query, variables=None, max_retries=5):
    """
    Executes a GraphQL query with simple exponential-backoff retries.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return run_query(query, variables)
        except Exception as e:
            wait_time = 2 ** attempt + random.uniform(0, 1)
            logging.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait_time:.2f} seconds...")
            print(f"    [WARNING] Attempt {attempt} failed: {e}. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)
    logging.error(f"All {max_retries} attempts failed.")
    raise Exception(f"Failed to execute GraphQL query after {max_retries} attempts.")

def fetch_orders(start_date, end_date):
    """
    Fetches all orders within the specified date range using GraphQL 
    and logs fetched order IDs with creation dates to 'fetched_order_ids.log'.
    """
    orders = []
    has_next_page = True
    cursor = None

    # Log file for storing fetched order IDs & creation dates
    log_file_path = 'fetched_order_ids.log'

    try:
        with open(log_file_path, 'w') as log_file:
            logging.info("Opened fetched_order_ids.log for writing.")

            # Updated query with 'AND' and quotes
            query = """
            query($first: Int!, $query: String!, $after: String) {
              orders(first: $first, query: $query, after: $after, reverse: false) {
                edges {
                  cursor
                  node {
                    id
                    name
                    createdAt
                    
                    lineItems(first: 100) {
                      edges {
                        node {
                          id
                          name
                          quantity
                          variant {
                            id
                            barcode
                          }
                        }
                      }
                    }
                    
                    refunds {
                      id
                      createdAt
                      refundLineItems(first: 100) {
                        edges {
                          node {
                            lineItem {
                              id
                              name
                              variant {
                                id
                                barcode
                              }
                            }
                            quantity
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
                            print(f"    [ERROR] Failed to write Order ID {order_id} to log: {e}")

                    has_next_page = data['orders']['pageInfo']['hasNextPage']
                    logging.info(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")
                    print(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")

                    if has_next_page:
                        cursor = fetched_orders[-1]['cursor']
                        variables['after'] = cursor
                    else:
                        break

                except Exception as e:
                    logging.error(f"Failed to fetch orders after retries: {e}", exc_info=True)
                    print(f"Failed to fetch orders after retries: {e}")
                    break

    except Exception as e:
        logging.error(f"Failed to open {log_file_path} for writing: {e}")
        print(f"    [ERROR] Failed to open {log_file_path} for writing: {e}")
        exit(1)

    logging.info(f"Total orders fetched: {len(orders)}")
    print(f"Total orders fetched: {len(orders)}")
    return orders

def aggregate_sales(orders):
    """
    Aggregates net sales quantities per barcode,
    also subtracting refunded quantities for barcodes starting with '978'.
    """
    sales_data = {}
    skipped_line_items = []

    total_line_items = 0
    processed_line_items = 0

    for order in orders:
        order_id = order.get('id', 'Unknown Order ID')
        order_created_at = order.get('createdAt', 'Unknown Creation Date')
        logging.debug(f"Processing Order ID: {order_id}, Created At: {order_created_at}")
        print(f"Processing Order ID: {order_id}, Created At: {order_created_at}")

        # 1) Tally up line items
        line_items = order.get('lineItems', {}).get('edges', [])
        for line_item_edge in line_items:
            line_item = line_item_edge['node']
            total_line_items += 1

            variant = line_item.get('variant')
            if not variant:
                line_item_id = line_item.get('id', 'Unknown Line Item ID')
                product_name = line_item.get('name', 'Unknown Product')
                logging.warning(f"Order {order_id} Line Item {line_item_id} ('{product_name}') has no variant.")
                print(f"    [WARNING] Order {order_id} Line Item {line_item_id} ('{product_name}') has no variant.")
                skipped_line_items.append({
                    'order_id': order_id,
                    'line_item_id': line_item_id,
                    'product_name': product_name,
                    'reason': 'No variant'
                })
                continue

            # Barcode might be None or a non-string
            barcode = variant.get('barcode') or ''
            if not isinstance(barcode, str):
                barcode = ''

            barcode = barcode.strip()
            if not barcode:
                variant_id = variant.get('id', 'Unknown Variant ID')
                product_name = line_item.get('name', 'Unknown Product')
                logging.warning(f"Variant ID {variant_id} for Product '{product_name}' has an empty barcode.")
                print(f"    [WARNING] Variant ID {variant_id} for Product '{product_name}' has an empty barcode.")
                skipped_line_items.append({
                    'order_id': order_id,
                    'line_item_id': line_item.get('id', 'Unknown Line Item ID'),
                    'product_name': product_name,
                    'reason': 'Empty barcode'
                })
                continue

            # Only track barcodes starting with '978'
            if barcode.startswith('978'):
                quantity = line_item.get('quantity', 0)
                sales_data[barcode] = sales_data.get(barcode, 0) + quantity
                processed_line_items += 1

                print(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order_id}")
                logging.debug(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order_id}")
            else:
                skipped_line_items.append({
                    'order_id': order_id,
                    'line_item_id': line_item.get('id', 'Unknown Line Item ID'),
                    'product_name': line_item.get('name', 'Unknown Product'),
                    'reason': 'Barcode does not start with 978'
                })
                logging.info(f"Barcode {barcode} for Product '{line_item['name']}' does not start with '978'. Skipping.")
                print(f"    [INFO] Barcode {barcode} for Product '{line_item['name']}' does not start with '978'. Skipping.")

        # 2) Subtract refunded items that also start with '978'
        refunds = order.get('refunds', [])  # It's a list, not a connection
        for refund_obj in refunds:
            refund_id = refund_obj.get('id', 'Unknown Refund ID')
            refund_created_at = refund_obj.get('createdAt', 'Unknown Refund CreatedAt')

            logging.debug(f"  Processing Refund ID: {refund_id}, Created At: {refund_created_at}")
            print(f"  Processing Refund ID: {refund_id}, Created At: {refund_created_at}")

            # refundLineItems is a connection
            rli_edges = refund_obj.get('refundLineItems', {}).get('edges', [])
            for rli_edge in rli_edges:
                rli_node = rli_edge.get('node', {})
                refunded_qty = rli_node.get('quantity', 0)

                refunded_line_item = rli_node.get('lineItem', {})
                variant = refunded_line_item.get('variant')
                if not variant:
                    # If no variant, we skip
                    rli_id = refunded_line_item.get('id', 'Unknown RefundLineItem ID')
                    product_name = refunded_line_item.get('name', 'Unknown Product')
                    logging.warning(f"Refund {refund_id} line item {rli_id} has no variant.")
                    print(f"    [WARNING] Refund {refund_id} line item {rli_id} has no variant.")
                    skipped_line_items.append({
                        'order_id': order_id,
                        'line_item_id': rli_id,
                        'product_name': product_name,
                        'reason': 'No variant in refund'
                    })
                    continue

                # Check the barcode, if it starts with '978', subtract from sales_data
                r_barcode = variant.get('barcode') or ''
                if not isinstance(r_barcode, str):
                    r_barcode = ''
                r_barcode = r_barcode.strip()

                if r_barcode.startswith('978'):
                    current_val = sales_data.get(r_barcode, 0)
                    # Subtract refunded quantity, but don't let it go below zero
                    new_val = max(current_val - refunded_qty, 0)
                    sales_data[r_barcode] = new_val

                    processed_line_items += 1
                    r_product_name = refunded_line_item.get('name', 'Unknown Product')
                    print(f"  Refund LineItem: {r_product_name}, Refunded Qty: {refunded_qty}, Barcode: {r_barcode}, => Net = {new_val}")
                    logging.debug(f"  Refund: {refund_id} Product: {r_product_name}, Refunded Qty: {refunded_qty}, Barcode: {r_barcode}, Net: {new_val}")
                else:
                    # If the refunded item doesn't start with '978', skip
                    r_product_name = refunded_line_item.get('name', 'Unknown Product')
                    skipped_line_items.append({
                        'order_id': order_id,
                        'line_item_id': refunded_line_item.get('id', 'Unknown ID'),
                        'product_name': r_product_name,
                        'reason': 'Barcode not 978 in refund'
                    })
                    logging.info(f"Refund item with barcode '{r_barcode}' doesn't start with '978'. Skipping.")
                    print(f"    [INFO] Refund item with barcode '{r_barcode}' doesn't start with '978'. Skipping.")

    print(f"Total line items processed: {processed_line_items} out of {total_line_items}")
    logging.info(f"Total line items processed: {processed_line_items} out of {total_line_items}")

    # Count how many barcodes have net > 0
    positive_sales_barcodes = {k: v for k, v in sales_data.items() if v > 0}
    print(f"Total products with net sales > 0 and ISBN starting with '978': {len(positive_sales_barcodes)}")
    logging.info(f"Total products with net sales > 0 and ISBN starting with '978': {len(positive_sales_barcodes)}")

    print(f"Total skipped line items: {len(skipped_line_items)}")
    logging.info(f"Total skipped line items: {len(skipped_line_items)}")

    # Return only barcodes that have net > 0
    final_sales_data = {k: v for k, v in sales_data.items() if v > 0}

    return final_sales_data, skipped_line_items

def export_to_csv(sales_data, filename):
    """
    Exports the final net sales data (barcode -> quantity) to a CSV file.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])
    logging.info(f"Report exported to {filename}")
    print(f"Report exported to {filename}")

def export_skipped_line_items(skipped_line_items, filename='skipped_line_items.log'):
    """
    Exports the skipped line items to a CSV file or log.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Line Item ID', 'Product Name', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([
                item.get('order_id', ''),
                item.get('line_item_id', ''),
                item.get('product_name', ''),
                item.get('reason', '')
            ])
    logging.info(f"Skipped line items logged to {filename}")
    print(f"Skipped line items logged to {filename}")

def compare_order_ids(manual_ids_file, fetched_ids_file, output_missing, output_extra):
    """
    Optional function: Compares manual order IDs with fetched order IDs,
    writing missing & extra to files.
    """
    try:
        with open(manual_ids_file, 'r') as f:
            manual_ids = set(line.strip() for line in f if line.strip())

        with open(fetched_ids_file, 'r') as f:
            # each line might look like "gid://shopify/Order/12345    2024-12-02T12:00:00Z"
            # so we split by tab and only keep the first piece
            fetched_ids = set(line.strip().split('\t')[0] for line in f if line.strip())

    except Exception as e:
        logging.error(f"Error reading order IDs files: {e}")
        print(f"    [ERROR] Error reading order IDs files: {e}")
        return

    missing_ids = manual_ids - fetched_ids
    extra_ids = fetched_ids - manual_ids

    try:
        with open(output_missing, 'w') as f:
            for id_ in missing_ids:
                f.write(f"{id_}\n")

        with open(output_extra, 'w') as f:
            for id_ in extra_ids:
                f.write(f"{id_}\n")

        logging.info(f"Comparison complete. Missing IDs: {len(missing_ids)}, Extra IDs: {len(extra_ids)}")
        print(f"Comparison complete. Missing IDs: {len(missing_ids)}, Extra IDs: {len(extra_ids)}")

    except Exception as e:
        logging.error(f"Error writing comparison results: {e}")
        print(f"    [ERROR] Error writing comparison results: {e}")

def test_api_credentials():
    """
    Tests API credentials by querying the shop name.
    """
    global GRAPHQL_URL, HEADERS  # Declare as global to access the variables
    test_query = """
    query {
      shop {
        name
      }
    }
    """
    try:
        data = run_query(test_query)
        shop_name = data['shop']['name']
        print(f"Successfully connected to Shopify store: {shop_name}")
        logging.info(f"Successfully connected to Shopify store: {shop_name}")
    except Exception as e:
        print(f"API Credentials Test Failed: {e}")
        logging.error(f"API Credentials Test Failed: {e}", exc_info=True)
        sys.exit(1)

# -----------------------------#
#             Main             #
# -----------------------------#

def main():
    parser = argparse.ArgumentParser(description='Generate Shopify Sales Report (GraphQL) with optional refunds.')
    parser.add_argument('--start-date', type=str, required=True,
                        help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, required=True,
                        help='End date in YYYY-MM-DD format')
    parser.add_argument('--manual-order-ids', type=str, required=False,
                        help='Optional path to a file containing manual order IDs for comparison')
    parser.add_argument('--env', type=str, choices=['production', 'test'], default='production',
                        help="Environment to use: 'production' or 'test'. Defaults to 'production'.")
    args = parser.parse_args()

    # Load the appropriate environment
    load_environment(args.env)

    # Load environment variables
    global SHOP_URL, ACCESS_TOKEN, GRAPHQL_URL, HEADERS  # Declare as global to access in helper functions
    SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'your-shop-name.myshopify.com'
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token

    if not SHOP_URL or not ACCESS_TOKEN:
        print("Error: SHOP_URL and SHOPIFY_ACCESS_TOKEN must be set in the .env file.")
        logging.error("SHOP_URL and SHOPIFY_ACCESS_TOKEN not set in the .env file.")
        sys.exit(1)

    # Configure logging
    log_filename = 'weekly_sales_report_graphql.log'
    logging.basicConfig(
        filename=log_filename,
        level=logging.DEBUG,  # Set to DEBUG for detailed logs
        format='%(asctime)s:%(levelname)s:%(message)s'
    )
    logging.info(f"Script started with environment: {args.env}")

    # Shopify GraphQL endpoint
    # Ensure that the API version is valid. Update as needed.
    API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2025-01')  # Default to '2025-01' if not set
    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/{API_VERSION}/graphql.json"

    # Headers for authentication
    HEADERS = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }

    # Print and log the environment being used (masking sensitive info)
    print(f"Using environment: {args.env}")
    logging.info(f"Using environment: {args.env}")
    logging.debug(f"SHOP_URL: {SHOP_URL}")
    logging.debug(f"ACCESS_TOKEN: {ACCESS_TOKEN[:4]}****")  # Mask the token

    # Validate date formats
    start_date = args.start_date
    end_date = args.end_date

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
    except ValueError:
        print("Error: Start date must be in YYYY-MM-DD format.")
        logging.error("Invalid start date format.")
        exit(1)

    try:
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        print("Error: End date must be in YYYY-MM-DD format.")
        logging.error("Invalid end date format.")
        exit(1)

    # Ensure start_date <= end_date
    if start_date > end_date:
        print("Error: Start date cannot be after end date.")
        logging.error("Start date is after end date.")
        exit(1)

    # 1) Test API credentials
    test_api_credentials()

    # 2) Fetch orders
    try:
        orders = fetch_orders(start_date, end_date)
    except Exception as e:
        print(f"Failed to fetch orders: {e}")
        logging.error(f"Failed to fetch orders: {e}", exc_info=True)
        exit(1)

    if not orders:
        print("No orders fetched. Exiting.")
        logging.info("No orders fetched. Exiting.")
        return

    # 3) Aggregate net sales (including refunds)
    sales_data, skipped_line_items = aggregate_sales(orders)

    if not sales_data:
        print("No sales data to export.")
        logging.info("No sales data to export.")
        return

    # 4) Export "skipped line items" if any
    if skipped_line_items:
        export_skipped_line_items(skipped_line_items, filename='skipped_line_items.log')

    # 5) Export the final net sales data
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_filename = f"shopify_sales_report_{date_str}.csv"
    try:
        export_to_csv(sales_data, report_filename)
    except Exception as e:
        print(f"Failed to export report: {e}")
        logging.error(f"Failed to export report: {e}", exc_info=True)
        exit(1)

    # 6) Optionally compare order IDs
    if args.manual_order_ids:
        compare_order_ids(
            manual_ids_file=args.manual_order_ids,
            fetched_ids_file='fetched_order_ids.log',
            output_missing='missing_order_ids.txt',
            output_extra='extra_order_ids.txt'
        )

    print("Report generation completed successfully.")
    logging.info("Report generation completed successfully.")

if __name__ == "__main__":
    main()