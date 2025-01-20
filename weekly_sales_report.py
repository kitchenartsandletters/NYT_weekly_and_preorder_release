#!/usr/bin/env python3
"""
Shopify Weekly Sales Report Script with Email Integration and Logging
Version: 1.3.0
Description:
    - Generates a Shopify sales report for a given date range.
    - Sends the report via email using SendGrid.
    - Handles refunds by subtracting refunded quantities for items with barcodes starting with '978'.
    - Logs skipped line items into a separate CSV file.
Author: Gil Calderon
"""

import os
import requests
import csv
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import time
import random
import sys
import base64

# -----------------------------#
#         Configuration        #
# -----------------------------#

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

# -----------------------------#
#          Helper Functions    #
# -----------------------------#

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

def run_query(query, variables=None):
    """
    Executes a GraphQL query against the Shopify API.
    """
    global GRAPHQL_URL, HEADERS
    payload = {"query": query, "variables": variables or {}}
    response = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"GraphQL query failed: {response.status_code} - {response.text}")
    result = response.json()
    if "errors" in result:
        raise Exception(f"GraphQL errors: {result['errors']}")
    return result['data']

def run_query_with_retries(query, variables=None, max_retries=5):
    """
    Executes a GraphQL query with retries for transient errors.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return run_query(query, variables)
        except Exception as e:
            wait_time = 2 ** attempt + random.uniform(0, 1)
            print(f"Attempt {attempt} failed: {e}. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)
    raise Exception("Failed to execute GraphQL query after retries.")

def fetch_orders(start_date, end_date):
    """
    Fetches all orders within the specified date range using GraphQL.
    """
    orders = []
    has_next_page = True
    cursor = None

    query = """
    query($first: Int!, $query: String!, $after: String) {
      orders(first: $first, query: $query, after: $after) {
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
              refundLineItems(first: 100) {
                edges {
                  node {
                    lineItem {
                      id
                      variant {
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
        data = run_query_with_retries(query, variables)
        orders.extend([edge['node'] for edge in data['orders']['edges']])
        has_next_page = data['orders']['pageInfo']['hasNextPage']
        if has_next_page:
            cursor = data['orders']['edges'][-1]['cursor']
            variables['after'] = cursor

    return orders

def aggregate_sales(orders):
    """
    Aggregates sales and handles refunds for barcodes starting with '978'.
    Logs skipped line items for missing variants or invalid barcodes.
    """
    sales_data = {}
    skipped_line_items = []

    for order in orders:
        for edge in order['lineItems']['edges']:
            node = edge['node']
            if not node.get('variant'):
                skipped_line_items.append({
                    'order_id': order['id'],
                    'product_name': node['name'],
                    'quantity': node['quantity'],
                    'reason': 'Missing variant'
                })
                continue
            barcode = node['variant']['barcode']
            if barcode and barcode.startswith('978'):
                sales_data[barcode] = sales_data.get(barcode, 0) + node['quantity']
            else:
                skipped_line_items.append({
                    'order_id': order['id'],
                    'product_name': node['name'],
                    'quantity': node['quantity'],
                    'reason': 'Invalid barcode'
                })

        for refund in order.get('refunds', []):
            for edge in refund.get('refundLineItems', {}).get('edges', []):
                node = edge['node']
                barcode = node['lineItem']['variant']['barcode'] if node['lineItem'].get('variant') else None
                if barcode and barcode.startswith('978'):
                    sales_data[barcode] = max(sales_data.get(barcode, 0) - node['quantity'], 0)

    return sales_data, skipped_line_items

def export_skipped_line_items(skipped_line_items, filename):
    """
    Exports skipped line items to a CSV file.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Product Name', 'Quantity', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([item['order_id'], item['product_name'], item['quantity'], item['reason']])

def export_to_csv(sales_data, filename):
    """
    Exports the sales data to a CSV file.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])

def send_email(report_path):
    """
    Sends the report as an email attachment using SendGrid.
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails = os.getenv('EMAIL_RECIPIENTS').split(',')

    if not api_key or not sender_email or not recipient_emails:
        print("Error: Missing email configuration.")
        return

    sg = sendgrid.SendGridAPIClient(api_key)
    subject = "Weekly Shopify Sales Report"
    content = "Attached is the weekly Shopify sales report."

    message = Mail(
        from_email=sender_email,
        to_emails=recipient_emails,
        subject=subject,
        plain_text_content=content
    )

    try:
        with open(report_path, 'rb') as f:
            report_data = f.read()
            encoded_file = base64.b64encode(report_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(os.path.basename(report_path)),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        print(f"Error attaching report: {e}")
        logging.error(f"Error attaching report: {e}")
        return

    try:
        response = sg.send(message)
        print(f"Email sent! Status: {response.status_code}")
        logging.info(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        logging.error(f"Failed to send email: {e}")

# -----------------------------#
#             Main             #
# -----------------------------#

def main():
    parser = argparse.ArgumentParser(description='Generate and email a Shopify sales report.')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--env', choices=['production', 'test'], default='production', help="Environment")
    args = parser.parse_args()

    load_environment(args.env)

    global SHOP_URL, GRAPHQL_URL, HEADERS
    SHOP_URL = os.getenv('SHOP_URL')
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')

    if not SHOP_URL or not ACCESS_TOKEN:
        print("Error: Missing SHOP_URL or ACCESS_TOKEN.")
        return

    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2025-01/graphql.json"
    HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}

    orders = fetch_orders(args.start_date, args.end_date)
    if not orders:
        print("No orders found.")
        return

    sales_data, skipped_line_items = aggregate_sales(orders)

    skipped_items_path = "skipped_line_items.csv"
    export_skipped_line_items(skipped_line_items, skipped_items_path)

    report_path = f"shopify_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    export_to_csv(sales_data, report_path)
    print(f"Report generated: {report_path}")
    print(f"Skipped items logged: {skipped_items_path}")

    send_email(report_path)

if __name__ == "__main__":
    main()