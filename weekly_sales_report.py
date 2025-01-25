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

# -----------------------------#
#         Configuration       #
# -----------------------------#

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

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
    Fetches all orders within the specified date range using GraphQL 
    and logs fetched order IDs with creation dates to 'fetched_order_ids.log'.
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

def is_valid_isbn(barcode):
    """
    Checks if a barcode is a valid ISBN (starts with 978)
    """
    return barcode and str(barcode).startswith('978')

def aggregate_sales(orders):
    """
    Aggregates sales data from the orders.
    Only includes valid ISBN products and excludes refunded/cancelled items.
    """
    sales_data = {}  # Dictionary to store barcode -> quantity
    skipped_line_items = []  # List to store items that couldn't be processed
    
    for order in orders:
        # Skip cancelled orders
        if order.get('cancelledAt'):
            continue
            
        line_items = order.get('lineItems', {}).get('edges', [])
        order_id = order['id']
        
        # Track refunded quantities per barcode for this order
        refunded_quantities = {}
        
        # First, process refunds to track what's been refunded
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
        
        # Process regular line items
        for line_item in line_items:
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
                    'quantity': quantity,
                    'reason': 'No barcode'
                })
                continue
            
            # Skip if not a valid ISBN
            if not is_valid_isbn(barcode):
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'quantity': quantity,
                    'reason': 'Not an ISBN (does not start with 978)'
                })
                continue
            
            # Subtract any refunded quantity for this barcode
            refunded_qty = refunded_quantities.get(barcode, 0)
            final_qty = quantity - refunded_qty
            
            if final_qty > 0:
                sales_data[barcode] = sales_data.get(barcode, 0) + final_qty
    
    return sales_data, skipped_line_items

def export_skipped_line_items(skipped_line_items, filename):
    """
    Exports skipped line items to a CSV file.
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.join(output_dir, filename)
    
    logging.info(f"Exporting skipped items to CSV at path: {abs_path}")
    
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Product Name', 'Quantity', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([
                item['order_id'],
                item['product_name'],
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

def send_email(report_filename):
    """
    Sends the report as an email attachment using SendGrid.
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails = os.getenv('EMAIL_RECIPIENTS').split(',')

    if not api_key or not sender_email or not recipient_emails:
        logging.error("Error: Missing email configuration.")
        return

    output_dir = os.path.join(BASE_DIR, 'output')
    abs_report_path = os.path.join(output_dir, report_filename)

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
        logging.error(f"Error attaching report: {e}")
        return

    try:
        response = sg.send(message)
        logging.info(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def get_last_week_date_range():
    """
    Returns the date range for last week (Monday to Sunday)
    Ensures we're always getting previous week regardless of when script runs
    """
    today = datetime.now()
    # First, get last Sunday
    last_sunday = today - timedelta(days=(today.weekday() + 1))
    # Then get the Monday before that
    last_monday = last_sunday - timedelta(days=6)
    
    # Set times to ensure full day coverage
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_sunday = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return last_monday.strftime('%Y-%m-%d'), last_sunday.strftime('%Y-%m-%d')

def main():
    print(f"Script running from directory: {os.getcwd()}")
    print(f"BASE_DIR set to: {BASE_DIR}")
    print(f"Python version: {sys.version}")

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

    orders = fetch_orders(start_date, end_date)
    if not orders:
        logging.error("No orders found.")
        return

    sales_data, skipped_items = aggregate_sales(orders)
    if not sales_data:
        logging.error("No sales data.")
        return

    report_filename = f"shopify_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    skipped_filename = "skipped_line_items.csv"

    export_to_csv(sales_data, report_filename)
    export_skipped_line_items(skipped_items, skipped_filename)

    output_dir = os.path.join(BASE_DIR, 'output')
    report_path = os.path.join(output_dir, report_filename)
    skipped_path = os.path.join(output_dir, skipped_filename)

    logging.info(f"Report generated: {report_path}")
    logging.info(f"Skipped items logged: {skipped_path}")
    logging.info(f"Current working directory (BASE_DIR): {BASE_DIR}")

    send_email(report_filename)

if __name__ == "__main__":
    main()