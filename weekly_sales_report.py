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
    Checks if a barcode is a valid ISBN (starts with 978 or 979)
    """
    return barcode and (str(barcode).startswith('978') or str(barcode).startswith('979'))

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
                    'barcode': 'N/A',
                    'quantity': quantity,
                    'reason': 'No barcode'
                })
                continue
            
            # For non-ISBN items:
            if not is_valid_isbn(barcode):
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'barcode': barcode,  # Include the barcode
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

def send_email(report_filename, skipped_filename, start_date, end_date, skipped_items):
    """
    Sends the report as an email attachment using SendGrid.
    Now includes both the sales report and excluded items report.
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails = os.getenv('EMAIL_RECIPIENTS').split(',')

    if not api_key or not sender_email or not recipient_emails:
        logging.error("Error: Missing email configuration.")
        return

    output_dir = os.path.join(BASE_DIR, 'output')
    abs_report_path = os.path.join(output_dir, report_filename)
    abs_skipped_path = os.path.join(output_dir, skipped_filename)

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

ITEMS NOT INCLUDED IN REPORT:
"""
    for reason, quantity in skipped_summary.items():
        email_content += f"- {quantity} items: {reason}\n"

    email_content += "\nAttached files:\n"
    email_content += f"1. {report_filename} - NYT Bestseller sales report\n"
    email_content += f"2. {skipped_filename} - Detailed list of excluded items"

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

        # Run validations
        warnings = validate_sales_data(sales_data, skipped_items)
        
        # Add warnings to email content if any exist
        email_content = f"""Weekly Shopify Sales Report
    Report Period: {start_date} to {end_date}

    REPORT DEFINITIONS:
    - This report includes all completed sales of ISBN products (barcodes starting with '978')
    - Quantities reflect final sales after any refunds or cancellations
    - Each line includes the ISBN and the total quantity sold

    """

        if warnings:
            email_content += "\nVALIDATION WARNINGS:\n"
            for warning in warnings:
                email_content += f"{warning}\n"
                logging.warning(warning)  # Also log the warnings

    report_filename = f"shopify_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    skipped_filename = f"excluded_items_{datetime.now().strftime('%Y-%m-%d')}.csv"

    export_to_csv(sales_data, report_filename)
    export_skipped_line_items(skipped_items, skipped_filename)

    output_dir = os.path.join(BASE_DIR, 'output')
    report_path = os.path.join(output_dir, report_filename)
    skipped_path = os.path.join(output_dir, skipped_filename)

    logging.info(f"Report generated: {report_path}")
    logging.info(f"Skipped items logged: {skipped_path}")
    logging.info(f"Current working directory (BASE_DIR): {BASE_DIR}")

    send_email(
        report_filename,
        skipped_filename,
        start_date,
        end_date,
        skipped_items
    )

if __name__ == "__main__":
    main()