#!/usr/bin/env python3
"""
Shopify GraphQL Sales Report Script
Version: 1.0.3
Description: Fetches Shopify orders within a specified date range using GraphQL, maps variants to barcodes, 
             accumulates quantities, logs fetched order IDs with creation dates, handles missing data, 
             and exports the data to a CSV report.
Author: Gil Calderon
Date: 2024-12-14
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

# -----------------------------#
#         Configuration        #
# -----------------------------#

# Load environment variables from .env file
load_dotenv()

SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'your-shop-name.myshopify.com'
ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')  # Your private app access token

# Configure logging
logging.basicConfig(
    filename='weekly_sales_report_graphql.log',
    level=logging.DEBUG,  # Set to DEBUG for detailed logs
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Shopify GraphQL endpoint
GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2024-10/graphql.json"

# Headers for authentication
HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": ACCESS_TOKEN
}

# -----------------------------#
#          Helper Functions     #
# -----------------------------#

def run_query(query, variables=None):
    """
    Executes a GraphQL query against the Shopify API.
    
    Args:
        query (str): The GraphQL query string.
        variables (dict, optional): Variables for the GraphQL query.
    
    Returns:
        dict: The JSON response from Shopify.
    """
    payload = {
        "query": query,
        "variables": variables or {}
    }
    response = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS)
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
    Executes a GraphQL query with retry logic in case of failures.
    
    Args:
        query (str): The GraphQL query string.
        variables (dict, optional): Variables for the GraphQL query.
        max_retries (int): Maximum number of retry attempts.
    
    Returns:
        dict: The JSON response from Shopify.
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
    Fetches all orders within the specified date range using GraphQL,
    including refund information, and logs fetched order IDs with creation dates.
    
    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
    
    Returns:
        list: A list of orders with their line items and refunds.
    """
    orders = []
    has_next_page = True
    cursor = None

    # Initialize the log file for fetched order IDs using a context manager
    log_file_path = 'fetched_order_ids.log'

    try:
        with open(log_file_path, 'w') as log_file:
            logging.info("Opened fetched_order_ids.log for writing.")
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
                    refunds(first: 50) {  # Adjust the number as needed
                      edges {
                        node {
                          id
                          createdAt
                          processedAt
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
                  }
                }
                pageInfo {
                  hasNextPage
                }
              }
            }
            """

            variables = {
                "first": 250,  # Maximum number of orders per request
                "query": f"created_at:>={start_date} created_at:<={end_date}",
                "after": cursor
            }

            while has_next_page:
                try:
                    data = run_query_with_retries(query, variables)
                    fetched_orders = data['orders']['edges']
                    for edge in fetched_orders:
                        order = edge['node']
                        orders.append(order)
                        order_id = order['id']
                        order_created_at = order['createdAt']
                        # Log the fetched order ID and creation date
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
    Aggregates net sales quantities per barcode by accounting for refunds,
    and categorizes skipped line items.
    
    Args:
        orders (list): A list of Shopify Order objects.
    
    Returns:
        tuple: A dictionary mapping barcode to net quantity sold and a list of skipped line items.
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

        # Aggregate quantities from line items
        for line_item_edge in order['lineItems']['edges']:
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
            # Safely handle None barcodes
            barcode = variant.get('barcode')
            if not isinstance(barcode, str):
                barcode = ''  # Set to empty string if barcode is None or not a string
            else:
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
                continue  # Skip if barcode is empty after stripping
            
            # Only include barcodes starting with '978'
            if barcode.startswith('978'):
                quantity = line_item.get('quantity', 0)
                sales_data[barcode] = sales_data.get(barcode, 0) + quantity
                processed_line_items += 1
                # Debugging statements
                print(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order_id}")
                logging.debug(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order_id}")
            else:
                # Optionally handle barcodes not starting with '978'
                skipped_line_items.append({
                    'order_id': order_id,
                    'line_item_id': line_item.get('id', 'Unknown Line Item ID'),
                    'product_name': line_item.get('name', 'Unknown Product'),
                    'reason': 'Barcode does not start with 978'
                })
                logging.info(f"Barcode {barcode} for Product '{line_item['name']}' does not start with '978'. Skipping.")
                print(f"    [INFO] Barcode {barcode} for Product '{line_item['name']}' does not start with '978'. Skipping.")

        # Process refunds associated with the order
        refunds = order.get('refunds', {}).get('edges', [])
        for refund_edge in refunds:
            refund = refund_edge['node']
            refund_id = refund.get('id', 'Unknown Refund ID')
            refund_created_at = refund.get('createdAt', 'Unknown Refund Date')
            logging.debug(f"  Processing Refund ID: {refund_id}, Created At: {refund_created_at}")
            print(f"  Processing Refund ID: {refund_id}, Created At: {refund_created_at}")

            for refund_line_item_edge in refund.get('refundLineItems', {}).get('edges', []):
                refund_line_item = refund_line_item_edge['node']
                refunded_line_item = refund_line_item.get('lineItem', {})
                refunded_quantity = refund_line_item.get('quantity', 0)
                variant = refunded_line_item.get('variant')

                if not variant:
                    refunded_line_item_id = refunded_line_item.get('id', 'Unknown Line Item ID')
                    refunded_product_name = refunded_line_item.get('name', 'Unknown Product')
                    logging.warning(f"Refund {refund_id} Line Item {refunded_line_item_id} ('{refunded_product_name}') has no variant.")
                    print(f"    [WARNING] Refund {refund_id} Line Item {refunded_line_item_id} ('{refunded_product_name}') has no variant.")
                    skipped_line_items.append({
                        'order_id': order_id,
                        'line_item_id': refunded_line_item_id,
                        'product_name': refunded_product_name,
                        'reason': 'No variant in refund'
                    })
                    continue

                # Safely handle None barcodes
                refunded_barcode = variant.get('barcode')
                if not isinstance(refunded_barcode, str):
                    refunded_barcode = ''  # Set to empty string if barcode is None or not a string
                else:
                    refunded_barcode = refunded_barcode.strip()
                
                if not refunded_barcode:
                    refunded_variant_id = variant.get('id', 'Unknown Variant ID')
                    refunded_product_name = refunded_line_item.get('name', 'Unknown Product')
                    logging.warning(f"Variant ID {refunded_variant_id} for Product '{refunded_product_name}' has an empty barcode in refund.")
                    print(f"    [WARNING] Variant ID {refunded_variant_id} for Product '{refunded_product_name}' has an empty barcode in refund.")
                    skipped_line_items.append({
                        'order_id': order_id,
                        'line_item_id': refunded_line_item.get('id', 'Unknown Line Item ID'),
                        'product_name': refunded_product_name,
                        'reason': 'Empty barcode in refund'
                    })
                    continue  # Skip if barcode is empty after stripping
                
                # Only include barcodes starting with '978' in refunds
                if refunded_barcode.startswith('978'):
                    # Subtract refunded quantity and ensure it doesn't go negative
                    net_quantity = sales_data.get(refunded_barcode, 0) - refunded_quantity
                    sales_data[refunded_barcode] = max(net_quantity, 0)
                    processed_line_items += 1
                    # Debugging statements
                    print(f"  Refund Line Item: {refunded_line_item.get('name')}, Refunded Quantity: {refunded_quantity}, Barcode: {refunded_barcode}, Refund ID: {refund_id}, Net Qty: {sales_data[refunded_barcode]}")
                    logging.debug(f"  Refund Line Item: {refunded_line_item.get('name')}, Refunded Quantity: {refunded_quantity}, Barcode: {refunded_barcode}, Refund ID: {refund_id}, Net Qty: {sales_data[refunded_barcode]}")
                else:
                    # Optionally handle barcodes not starting with '978' in refunds
                    skipped_line_items.append({
                        'order_id': order_id,
                        'line_item_id': refunded_line_item.get('id', 'Unknown Line Item ID'),
                        'product_name': refunded_line_item.get('name', 'Unknown Product'),
                        'reason': 'Barcode does not start with 978 in refund'
                    })
                    logging.info(f"Refund Barcode {refunded_barcode} for Product '{refunded_line_item.get('name')}' does not start with '978'. Skipping.")
                    print(f"    [INFO] Refund Barcode {refunded_barcode} for Product '{refunded_line_item.get('name')}' does not start with '978'. Skipping.")

    print(f"Total line items processed: {processed_line_items} out of {total_line_items}")
    logging.info(f"Total line items processed: {processed_line_items} out of {total_line_items}")
    print(f"Total products with net sales > 0 and ISBN starting with '978': {len(sales_data)}")
    logging.info(f"Total products with net sales > 0 and ISBN starting with '978': {len(sales_data)}")
    print(f"Total skipped line items: {len(skipped_line_items)}")
    logging.info(f"Total skipped line items: {len(skipped_line_items)}")
    return sales_data, skipped_line_items

def export_to_csv(sales_data, filename):
    """
    Exports the sales data to a CSV file.
    
    Args:
        sales_data (dict): A dictionary mapping barcode to total quantity sold.
        filename (str): The filename for the CSV export.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Barcode', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])
    logging.info(f"Report exported to {filename}")
    print(f"Report exported to {filename}")

def export_skipped_line_items(skipped_line_items, filename='skipped_line_items.log'):
    """
    Exports the skipped line items to a CSV file.
    
    Args:
        skipped_line_items (list): A list of dictionaries containing skipped line item details.
        filename (str): The filename for the skipped line items export.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Line Item ID', 'Product Name', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([item['order_id'], item['line_item_id'], item['product_name'], item['reason']])
    logging.info(f"Skipped line items logged to {filename}")
    print(f"Skipped line items logged to {filename}")

def compare_order_ids(manual_ids_file, fetched_ids_file, output_missing, output_extra):
    """
    Compares manual order IDs with fetched order IDs and outputs missing and extra IDs.
    
    Args:
        manual_ids_file (str): Path to the manual order IDs file.
        fetched_ids_file (str): Path to the fetched order IDs log file.
        output_missing (str): Path to the output file for missing IDs.
        output_extra (str): Path to the output file for extra IDs.
    """
    try:
        with open(manual_ids_file, 'r') as f:
            manual_ids = set(line.strip() for line in f if line.strip())
        with open(fetched_ids_file, 'r') as f:
            fetched_ids = set(line.strip().split('\t')[0] for line in f if line.strip())
    except Exception as e:
        logging.error(f"Error reading order IDs files: {e}")
        print(f"    [ERROR] Error reading order IDs files: {e}")
        return

    missing_ids = manual_ids - fetched_ids
    extra_ids = fetched_ids - manual_ids

    try:
        with open(output_missing, 'w') as f:
            for id in missing_ids:
                f.write(f"{id}\n")
        with open(output_extra, 'w') as f:
            for id in extra_ids:
                f.write(f"{id}\n")
        logging.info(f"Comparison complete. Missing IDs: {len(missing_ids)}, Extra IDs: {len(extra_ids)}")
        print(f"Comparison complete. Missing IDs: {len(missing_ids)}, Extra IDs: {len(extra_ids)}")
    except Exception as e:
        logging.error(f"Error writing comparison results: {e}")
        print(f"    [ERROR] Error writing comparison results: {e}")

# -----------------------------#
#             Main             #
# -----------------------------#

def main():
    # Parse command-line arguments for date range and optional comparison
    parser = argparse.ArgumentParser(description='Generate Shopify Sales Report using GraphQL.')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format', required=True)
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format', required=True)
    parser.add_argument('--manual-order-ids', type=str, help='Path to manual order IDs file', required=False)
    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date

    # Validate date formats
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

    # Ensure start_date is not after end_date
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    if start_dt > end_dt:
        print("Error: Start date cannot be after end date.")
        logging.error("Start date is after end date.")
        exit(1)

    # Fetch orders
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

    # Aggregate sales
    sales_data, skipped_line_items = aggregate_sales(orders)

    if not sales_data:
        print("No sales data to export.")
        logging.info("No sales data to export.")
        return

    # Export skipped line items to CSV
    if skipped_line_items:
        export_skipped_line_items(skipped_line_items, 'skipped_line_items.log')

    # Export to CSV
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"shopify_sales_report_{date_str}.csv"
    try:
        export_to_csv(sales_data, filename)
    except Exception as e:
        print(f"Failed to export report: {e}")
        logging.error(f"Failed to export report: {e}", exc_info=True)
        exit(1)

    # Optionally, perform comparison with manual order IDs if provided
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