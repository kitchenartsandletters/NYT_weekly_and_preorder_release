#!/usr/bin/env python3
"""
Weekly Shopify Sales Report Script
Version: 1.1.0
Description: Fetches Shopify orders within a specified date range, maps variants to barcodes, 
             accumulates quantities, and exports the data to a CSV report.
Author: Gil Calderon
Date: 2024-12-10
"""

import shopify
import os
import pandas as pd
import logging
import time
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
import csv
from pyactiveresource.connection import ResourceNotFound
import argparse
from datetime import datetime

# -----------------------------#
#         Configuration        #
# -----------------------------#

# Load environment variables from .env file
load_dotenv()

SHOP_URL = os.getenv('SHOP_URL')  # e.g., 'your-shop-name.myshopify.com'
API_ACCESS_TOKEN = os.getenv('SHOPIFY_API_ACCESS_TOKEN')
API_VERSION = os.getenv('API_VERSION')  # e.g., '2024-10'

# Configure logging
logging.basicConfig(
    filename='weekly_sales_report.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# -----------------------------#
#      Shopify Session Setup   #
# -----------------------------#

def activate_shopify_session():
    """
    Activates the Shopify API session using the provided credentials.
    """
    try:
        session = shopify.Session(SHOP_URL, API_VERSION, API_ACCESS_TOKEN)
        shopify.ShopifyResource.activate_session(session)
        print("Shopify session activated successfully.")
        logging.info("Shopify session activated successfully.")
    except Exception as e:
        logging.error(f"Failed to activate Shopify session: {e}", exc_info=True)
        print(f"Failed to activate Shopify session: {e}")
        exit(1)

# -----------------------------#
#        Fetch Orders          #
# -----------------------------#

def fetch_orders(start_date=None, end_date=None):
    """
    Fetches all orders from Shopify within the specified date range.

    Args:
        start_date (str, optional): Start date in 'YYYY-MM-DD' format.
        end_date (str, optional): End date in 'YYYY-MM-DD' format.

    Returns:
        list: A list of Shopify Order objects.
    """
    orders = []
    page = 1
    since_id = None
    per_page = 250  # Maximum allowed per Shopify API

    print("Starting to fetch orders...")
    logging.info("Starting to fetch orders...")

    while True:
        try:
            params = {
                'limit': per_page,
                'status': 'any',  # Fetch all orders regardless of status
                'order': 'created_at desc'
            }

            if start_date:
                params['created_at_min'] = f"{start_date}T00:00:00-00:00"  # ISO 8601 format

            if end_date:
                params['created_at_max'] = f"{end_date}T23:59:59-00:00"  # ISO 8601 format

            if since_id:
                # Remove 'order' parameter when 'since_id' is present
                params.pop('order', None)
                params['since_id'] = since_id

            fetched_orders = shopify.Order.find(**params)
            orders.extend(fetched_orders)

            print(f"Fetched {len(fetched_orders)} orders from page {page}.")
            logging.info(f"Fetched {len(fetched_orders)} orders from page {page}.")

            if len(fetched_orders) < per_page:
                print("Fetched fewer than 250 orders. Assuming last page.")
                logging.info("Fetched fewer than 250 orders. Assuming last page.")
                break

            since_id = fetched_orders[-1].id
            page += 1
            time.sleep(1)  # To respect API rate limits
        except shopify.ShopifyError as e:
            logging.error(f"Shopify API error fetching orders: {e}", exc_info=True)
            print(f"Shopify API error fetching orders: {e}")
            break
        except Exception as e:
            logging.error(f"Unexpected error fetching orders: {e}", exc_info=True)
            print(f"Unexpected error fetching orders: {e}")
            break

    print(f"Total orders fetched: {len(orders)}")
    logging.info(f"Total orders fetched: {len(orders)}")
    return orders

# -----------------------------#
#      Fetch All Variants      #
# -----------------------------#

def fetch_all_variants(orders):
    """
    Fetch all unique variants from the orders and map variant_id to barcode.

    Args:
        orders (list): A list of Shopify Order objects.

    Returns:
        dict: A dictionary mapping variant_id to barcode.
    """
    variant_ids = set()
    for order in orders:
        for line_item in order.line_items:
            variant_ids.add(line_item.variant_id)

    print(f"Total unique variant_ids collected: {len(variant_ids)}")
    logging.info(f"Total unique variant_ids collected: {len(variant_ids)}")

    variant_barcodes = {}
    variant_ids = list(variant_ids)
    per_request = 50  # Shopify API allows up to 50 variants per request

    print("Starting to fetch variants individually...")
    logging.info("Starting to fetch variants individually...")

    for i in range(0, len(variant_ids), per_request):
        batch_ids = variant_ids[i:i + per_request]
        try:
            for variant_id in batch_ids:
                if variant_id is None:
                    logging.warning("Encountered a line item with variant_id=None.")
                    print("    [WARNING] Encountered a line item with variant_id=None.")
                    continue
                try:
                    variant = shopify.Variant.find(variant_id)
                    if variant is None:
                        logging.warning(f"Variant ID {variant_id} returned None.")
                        print(f"    [WARNING] Variant ID {variant_id} returned None.")
                        continue
                    barcode = getattr(variant, 'barcode', '')
                    if barcode is not None:
                        barcode = barcode.strip()
                    else:
                        barcode = ''
                    variant_barcodes[variant.id] = barcode

                    # Debugging statements
                    print(f"Fetched Variant ID: {variant.id}, Barcode: {barcode}")
                    logging.debug(f"Fetched Variant ID: {variant.id}, Barcode: {barcode}")
                except ResourceNotFound:
                    logging.error(f"Variant ID {variant_id} not found.")
                    print(f"    [ERROR] Variant ID {variant_id} not found.")
                except shopify.ShopifyError as e:
                    logging.error(f"Shopify API error fetching variant {variant_id}: {e}", exc_info=True)
                    print(f"    [ERROR] Shopify API error fetching variant {variant_id}: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error fetching variant {variant_id}: {e}", exc_info=True)
                    print(f"    [ERROR] Unexpected error fetching variant {variant_id}: {e}")
                finally:
                    time.sleep(0.2)  # Adjust as needed based on rate limits
        except Exception as e:
            logging.error(f"Unexpected error in variant batch: {e}", exc_info=True)
            print(f"    [ERROR] Unexpected error in variant batch: {e}")
            continue

    # Identify missing variant_ids
    fetched_variant_ids = set(variant_barcodes.keys())
    missing_variant_ids = set(filter(None, variant_ids)) - fetched_variant_ids
    if missing_variant_ids:
        print(f"Missing Variant IDs: {missing_variant_ids}")
        logging.warning(f"Missing Variant IDs: {missing_variant_ids}")
        # Log missing variant_ids to a separate file
        with open('missing_variant_ids.log', 'a') as f:
            for missing_id in missing_variant_ids:
                f.write(f"Missing Variant ID: {missing_id}\n")
    else:
        print("All variant_ids fetched successfully.")
        logging.info("All variant_ids fetched successfully.")

    return variant_barcodes

# -----------------------------#
#        Process Orders        #
# -----------------------------#

def process_orders(orders, variant_barcodes):
    """
    Processes orders to accumulate quantities per barcode.

    Args:
        orders (list): A list of Shopify Order objects.
        variant_barcodes (dict): A dictionary mapping variant_id to barcode.

    Returns:
        dict: A dictionary mapping barcode to total quantity sold.
    """
    sales_data = {}

    print("Starting to process orders...")
    logging.info("Starting to process orders...")

    for order in orders:
        # Filter orders by financial status and fulfillment status if needed
        # For example, only process 'paid' and 'fulfilled' orders
        if order.financial_status != 'paid':
            continue
        if order.fulfillment_status not in ['fulfilled', 'partial']:
            continue

        for line_item in order.line_items:
            variant_id = line_item.variant_id
            quantity = line_item.quantity

            if variant_id is None:
                logging.warning(f"Line item '{line_item.title}' has variant_id=None.")
                print(f"    [WARNING] Line item '{line_item.title}' has variant_id=None.")
                continue

            barcode = variant_barcodes.get(variant_id, '').strip()

            # Since all products have barcodes, we expect barcode to be present
            if not barcode:
                logging.warning(f"Variant ID {variant_id} not found or barcode is empty.")
                print(f"    [DEBUG] Variant ID {variant_id} not found or barcode is empty.")
                continue

            # Only include barcodes starting with '978'
            if barcode.startswith('978'):
                if barcode in sales_data:
                    sales_data[barcode] += quantity
                else:
                    sales_data[barcode] = quantity

                # Debugging statements
                print(f"  Line Item: {line_item.title}, Quantity: {quantity}, Barcode: {barcode}")
                logging.debug(f"  Line Item: {line_item.title}, Quantity: {quantity}, Barcode: {barcode}")

    print(f"Total products with sales > 0 and ISBN starting with '978': {len(sales_data)}")
    logging.info(f"Total products with sales > 0 and ISBN starting with '978': {len(sales_data)}")
    return sales_data

# -----------------------------#
#          Export CSV          #
# -----------------------------#

def export_to_csv(sales_data):
    """
    Exports the sales data to a CSV file.

    Args:
        sales_data (dict): A dictionary mapping barcode to total quantity sold.
    """
    date_str = time.strftime("%Y-%m-%d")
    filename = f"shopify_sales_report_{date_str}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Barcode', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])

    print(f"Report exported to {filename}")
    logging.info(f"Report exported to {filename}")

# -----------------------------#
#             Main             #
# -----------------------------#

def main():
    # Parse command-line arguments for date range
    parser = argparse.ArgumentParser(description='Generate Shopify Sales Report.')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format', required=False)
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format', required=False)
    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date

    # Validate date formats
    if start_date:
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            print("Error: Start date must be in YYYY-MM-DD format.")
            logging.error("Invalid start date format.")
            exit(1)

    if end_date:
        try:
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            print("Error: End date must be in YYYY-MM-DD format.")
            logging.error("Invalid end date format.")
            exit(1)

    # Ensure start_date is not after end_date
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        if start_dt > end_dt:
            print("Error: Start date cannot be after end date.")
            logging.error("Start date is after end date.")
            exit(1)

    activate_shopify_session()
    orders = fetch_orders(start_date, end_date)
    if not orders:
        print("No orders fetched. Exiting.")
        logging.info("No orders fetched. Exiting.")
        return

    variant_barcodes = fetch_all_variants(orders)
    if not variant_barcodes:
        print("No variants fetched. Exiting.")
        logging.info("No variants fetched. Exiting.")
        return

    sales_data = process_orders(orders, variant_barcodes)
    if sales_data:
        export_to_csv(sales_data)
    else:
        print("No sales data to export.")
        logging.info("No sales data to export.")

    # Clear Shopify session
    shopify.ShopifyResource.clear_session()
    print("Shopify session cleared.")
    logging.info("Shopify session cleared.")

if __name__ == "__main__":
    main()