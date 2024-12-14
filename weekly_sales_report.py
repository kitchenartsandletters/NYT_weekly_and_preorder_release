#!/usr/bin/env python3
"""
Shopify GraphQL Sales Report Script
Version: 1.0.1
Description: Fetches Shopify orders within a specified date range using GraphQL, maps variants to barcodes, 
             accumulates quantities, and exports the data to a CSV report.
Author: Gil Calderon
Date: 2024-12-10
"""

import os
import requests
import csv
import logging
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

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

def fetch_orders(start_date, end_date):
    """
    Fetches all orders within the specified date range using GraphQL.
    
    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
    
    Returns:
        list: A list of orders with their line items.
    """
    orders = []
    has_next_page = True
    cursor = None

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
            data = run_query(query, variables)
            fetched_orders = data['orders']['edges']
            for edge in fetched_orders:
                order = edge['node']
                orders.append(order)
                cursor = edge['cursor']
            has_next_page = data['orders']['pageInfo']['hasNextPage']
            logging.info(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")
            print(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")
            if has_next_page:
                variables['after'] = cursor
            else:
                break
        except Exception as e:
            logging.error(f"Failed to fetch orders: {e}", exc_info=True)
            print(f"Failed to fetch orders: {e}")
            break

    logging.info(f"Total orders fetched: {len(orders)}")
    print(f"Total orders fetched: {len(orders)}")
    return orders

def aggregate_sales(orders):
    """
    Aggregates sales quantities per barcode.
    
    Args:
        orders (list): A list of Shopify Order objects.
    
    Returns:
        dict: A dictionary mapping barcode to total quantity sold.
    """
    sales_data = {}
    total_line_items = 0
    processed_line_items = 0

    for order in orders:
        for line_item_edge in order['lineItems']['edges']:
            line_item = line_item_edge['node']
            total_line_items += 1
            variant = line_item.get('variant')
            if not variant:
                logging.warning(f"Order {order['id']} Line Item {line_item['id']} has no variant.")
                print(f"    [WARNING] Order {order['id']} Line Item {line_item['id']} has no variant.")
                continue
            # Safely handle None barcodes
            barcode = variant.get('barcode')
            if not isinstance(barcode, str):
                barcode = ''  # Set to empty string if barcode is None or not a string
            else:
                barcode = barcode.strip()
            
            if not barcode:
                logging.warning(f"Variant ID {variant.get('id')} has an empty barcode.")
                print(f"    [WARNING] Variant ID {variant.get('id')} has an empty barcode.")
                continue  # Skip if barcode is empty after stripping
            
            # Only include barcodes starting with '978'
            if barcode.startswith('978'):
                quantity = line_item.get('quantity', 0)
                sales_data[barcode] = sales_data.get(barcode, 0) + quantity
                processed_line_items += 1
                # Debugging statements
                print(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order['id']}")
                logging.debug(f"  Line Item: {line_item['name']}, Quantity: {quantity}, Barcode: {barcode}, Order ID: {order['id']}")

    print(f"Total line items processed: {processed_line_items} out of {total_line_items}")
    logging.info(f"Total line items processed: {processed_line_items} out of {total_line_items}")
    print(f"Total products with sales > 0 and ISBN starting with '978': {len(sales_data)}")
    logging.info(f"Total products with sales > 0 and ISBN starting with '978': {len(sales_data)}")
    return sales_data

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
    

# -----------------------------#
#             Main             #
# -----------------------------#

def main():
    # Parse command-line arguments for date range
    parser = argparse.ArgumentParser(description='Generate Shopify Sales Report using GraphQL.')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format', required=True)
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format', required=True)
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
    sales_data = aggregate_sales(orders)

    if not sales_data:
        print("No sales data to export.")
        logging.info("No sales data to export.")
        return

    # Export to CSV
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"shopify_sales_report_{date_str}.csv"
    try:
        export_to_csv(sales_data, filename)
    except Exception as e:
        print(f"Failed to export report: {e}")
        logging.error(f"Failed to export report: {e}", exc_info=True)
        exit(1)

    print("Report generation completed successfully.")
    logging.info("Report generation completed successfully.")

if __name__ == "__main__":
    main()