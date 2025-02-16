import os
import sys
import csv
import time
import base64
import logging
import requests
import functools
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, date, timedelta
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from dotenv import load_dotenv

class Config:
    """Configuration management class"""
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.load_environment()
        self.setup_shopify()
        self.validate_config()

    def load_environment(self) -> None:
        """Load environment variables"""
        env_file = '.env.production'
        if not os.path.exists(env_file):
            raise FileNotFoundError(f"Environment file {env_file} not found")
        
        load_dotenv(env_file)
        self.shop_url = os.getenv('SHOP_URL')
        self.access_token = os.getenv('SHOPIFY_ACCESS_TOKEN')
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        self.email_sender = os.getenv('EMAIL_SENDER')
        self.email_recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')

    def setup_shopify(self) -> None:
        """Setup Shopify API configuration"""
        if self.shop_url:
            self.graphql_url = f"https://{self.shop_url}/admin/api/2025-01/graphql.json"
            self.headers = {
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.access_token
            }

    def validate_config(self) -> None:
        """Validate configuration"""
        required_vars = [
            'shop_url', 'access_token', 'sendgrid_api_key',
            'email_sender', 'email_recipients'
        ]
        missing_vars = [var for var in required_vars 
                       if not getattr(self, var, None)]
        if missing_vars:
            raise ValueError(f"Missing required configuration: {', '.join(missing_vars)}")

class FileManager:
    """File operations management class"""
    def __init__(self, config: Config):
        self.config = config
        self.setup_directories()

    def setup_directories(self) -> None:
        """Create necessary directories"""
        for dir_name in ['output', 'logs', 'preorders']:
            dir_path = os.path.join(self.config.base_dir, dir_name)
            os.makedirs(dir_path, exist_ok=True)

    @staticmethod
    def safe_file_operation(func):
        """Decorator for safe file operations"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except FileNotFoundError as e:
                logging.error(f"File not found: {e}")
                raise
            except PermissionError as e:
                logging.error(f"Permission denied: {e}")
                raise
            except Exception as e:
                logging.error(f"Unexpected error during file operation: {e}")
                raise
        return wrapper

    def cleanup_old_files(self, days_to_keep: int = 30) -> None:
        """Clean up old report files"""
        current_time = datetime.now()
        for directory in ['output', 'logs']:
            dir_path = os.path.join(self.config.base_dir, directory)
            if not os.path.exists(dir_path):
                continue

            for filename in os.listdir(dir_path):
                file_path = os.path.join(dir_path, filename)
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (current_time - file_modified).days > days_to_keep:
                    try:
                        os.remove(file_path)
                        logging.info(f"Removed old file: {filename}")
                    except Exception as e:
                        logging.error(f"Failed to remove {filename}: {e}")

class ShopifyAPI:
    """Shopify API interaction class"""
    def __init__(self, config: Config):
        self.config = config

    def retry_on_error(max_retries: int = 3, delay: int = 1):
        """Decorator for retrying failed API calls"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        logging.warning(f"Attempt {attempt + 1} failed: {e}")
                        time.sleep(delay)
                return None
            return wrapper
        return decorator

    @retry_on_error(max_retries=3, delay=1)
    def run_query(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute GraphQL query"""
        response = requests.post(
            self.config.graphql_url,
            json={'query': query, 'variables': variables},
            headers=self.config.headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Query failed with status code: {response.status_code}")
            
        result = response.json()
        if 'errors' in result:
            raise Exception(f"GraphQL errors: {result['errors']}")
            
        return result['data']

    def fetch_orders(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch orders within date range"""
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

        while has_next_page:
            variables = {
                "first": 250,
                "query": f'created_at:>="{start_date}" AND created_at:<="{end_date}"',
                "after": cursor
            }

            try:
                data = self.run_query(query, variables)
                fetched_orders = data['orders']['edges']
                orders.extend([edge['node'] for edge in fetched_orders])
                
                has_next_page = data['orders']['pageInfo']['hasNextPage']
                if has_next_page:
                    cursor = fetched_orders[-1]['cursor']
                
                logging.info(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")
                
            except Exception as e:
                logging.error(f"Failed to fetch orders: {e}")
                break

        return orders

class SalesProcessor:
    """Sales data processing class"""
    def __init__(self, config: Config):
        self.config = config

    @staticmethod
    def validate_isbn(isbn: str) -> bool:
        """Validate ISBN format and checksum"""
        if not isbn or not isinstance(isbn, str):
            return False
            
        isbn = isbn.replace('-', '').replace(' ', '')
        if not (isbn.startswith('978') or isbn.startswith('979')):
            return False
            
        if len(isbn) != 13:
            return False
            
        try:
            total = sum((10 if x == 'X' else int(x)) * (1 if i % 2 == 0 else 3)
                        for i, x in enumerate(isbn[:-1]))
            check = (10 - (total % 10)) % 10
            return check == int(isbn[-1])
        except ValueError:
            return False

    def process_refunds(self, order: Dict[str, Any]) -> Dict[str, int]:
        """Process refunds for an order"""
        refunded_quantities = {}
        for refund in order.get('refunds', []):
            refund_line_items = refund.get('refundLineItems', {}).get('edges', [])
            for refund_item in refund_line_items:
                node = refund_item['node']
                quantity = node['quantity']
                line_item = node.get('lineItem', {})
                variant = line_item.get('variant')
                
                if variant and variant.get('barcode'):
                    barcode = variant['barcode']
                    refunded_quantities[barcode] = refunded_quantities.get(barcode, 0) + quantity
                    
        return refunded_quantities

    def aggregate_sales(self, orders: List[Dict[str, Any]]) -> Tuple[Dict[str, int], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Aggregate sales data from orders"""
        sales_data = {}
        skipped_items = []
        preorder_items = []

        for order in orders:
            if order.get('cancelledAt'):
                continue

            refunded_quantities = self.process_refunds(order)
            
            for line_item in order.get('lineItems', {}).get('edges', []):
                node = line_item['node']
                quantity = node['quantity']
                variant = node.get('variant')
                
                if not variant or not variant.get('barcode'):
                    skipped_items.append({
                        'order_id': order['id'],
                        'product_name': node.get('name', 'Unknown'),
                        'quantity': quantity,
                        'reason': 'Missing variant or barcode'
                    })
                    continue
                    
                barcode = variant['barcode']
                if not self.validate_isbn(barcode):
                    skipped_items.append({
                        'order_id': order['id'],
                        'product_name': node.get('name', 'Unknown'),
                        'barcode': barcode,
                        'quantity': quantity,
                        'reason': 'Invalid ISBN'
                    })
                    continue

                # Process final quantity after refunds
                final_qty = quantity - refunded_quantities.get(barcode, 0)
                if final_qty > 0:
                    sales_data[barcode] = sales_data.get(barcode, 0) + final_qty

        return sales_data, skipped_items, preorder_items

class ReportGenerator:
    """Report generation and email sending class"""
    def __init__(self, config: Config):
        self.config = config
        self.file_manager = FileManager(config)

    def generate_report(self, sales_data: Dict[str, int], 
                       skipped_items: List[Dict[str, Any]], 
                       start_date: str, end_date: str) -> None:
        """Generate and send sales report"""
        # Generate report files
        report_filename = f"NYT_weekly_sales_report_{datetime.now():%Y-%m-%d}.csv"
        skipped_filename = f"NYT_excluded_items_{datetime.now():%Y-%m-%d}.csv"
        
        self.export_sales_data(sales_data, report_filename)
        self.export_skipped_items(skipped_items, skipped_filename)
        
        # Send email with reports
        self.send_email(report_filename, skipped_filename, start_date, end_date, skipped_items)

    @FileManager.safe_file_operation
    def export_sales_data(self, sales_data: Dict[str, int], filename: str) -> None:
        """Export sales data to CSV"""
        filepath = os.path.join(self.config.base_dir, 'output', filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ISBN', 'QTY'])
            for isbn, qty in sales_data.items():
                writer.writerow([isbn, qty])

    @FileManager.safe_file_operation
    def export_skipped_items(self, skipped_items: List[Dict[str, Any]], filename: str) -> None:
        """Export skipped items to CSV"""
        filepath = os.path.join(self.config.base_dir, 'output', filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Order ID', 'Product Name', 'Barcode/ISBN', 'Quantity', 'Reason'])
            for item in skipped_items:
                writer.writerow([
                    item['order_id'],
                    item['product_name'],
                    item.get('barcode', 'N/A'),
                    item['quantity'],
                    item['reason']
                ])

    def send_email(self, report_filename: str, skipped_filename: str, 
                   start_date: str, end_date: str, skipped_items: List[Dict[str, Any]]) -> None:
        """Send email with report attachments"""
        try:
            sg = sendgrid.SendGridAPIClient(self.config.sendgrid_api_key)
            
            # Create email content
            email_content = self.create_email_content(start_date, end_date, skipped_items)
            
            # Create message
            message = Mail(
                from_email=self.config.email_sender,
                to_emails=self.config.email_recipients,
                subject=f"NYT Bestseller Weekly Report ({start_date} to {end_date})",
                plain_text_content=email_content
            )
            
            # Attach files
            self.attach_file(message, report_filename, 'output')
            self.attach_file(message, skipped_filename, 'output')
            
            # Send email
            response = sg.send(message)
            logging.info(f"Email sent successfully. Status code: {response.status_code}")
            
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            raise

    def create_email_content(self, start_date: str, end_date: str, 
                           skipped_items: List[Dict[str, Any]]) -> str:
        """Create email content for the report"""
        # Summarize skipped items
        skipped_summary = {}
        for item in skipped_items:
            reason = item['reason']
            if reason not in skipped_summary:
                skipped_summary[reason] = 0
            skipped_summary[reason] += item['quantity']

        # Create email content
        content = f"""NYT Bestseller Weekly Report
Report Period: Sunday {start_date} through Saturday {end_date}

REPORT DEFINITIONS:
- This report includes all completed sales of ISBN products (barcodes starting with '978' or '979')
- Quantities reflect final sales after any refunds or cancellations
- Each line includes the ISBN and the total quantity sold

ITEMS NOT INCLUDED IN REPORT:
"""
        for reason, quantity in skipped_summary.items():
            content += f"- {quantity} items: {reason}\n"

        return content

    @FileManager.safe_file_operation
    def attach_file(self, message: Mail, filename: str, subdirectory: str) -> None:
        """Attach file to email message"""
        filepath = os.path.join(self.config.base_dir, subdirectory, filename)
        with open(filepath, 'rb') as f:
            file_data = f.read()
            encoded_file = base64.b64encode(file_data).decode()
            
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)

def setup_logging() -> None:
    """Configure logging settings"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                os.path.join(log_dir, f'sales_report_{datetime.now():%Y-%m-%d}.log')
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )

def get_date_range() -> Tuple[str, str]:
    """Get date range for last week (Sunday through Saturday)"""
    today = datetime.now()
    days_after_saturday = today.weekday() + 2
    last_saturday = today - timedelta(days=days_after_saturday)
    last_sunday = last_saturday - timedelta(days=6)
    
    last_sunday = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_saturday = last_saturday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return last_sunday.strftime('%Y-%m-%d'), last_saturday.strftime('%Y-%m-%d')

def main() -> None:
    """Main execution function"""
    try:
        # Setup logging
        setup_logging()
        logging.info("Starting weekly sales report generation")
        
        # Initialize configuration
        config = Config()
        logging.info("Configuration loaded successfully")
        
        # Initialize components
        file_manager = FileManager(config)
        shopify_api = ShopifyAPI(config)
        sales_processor = SalesProcessor(config)
        report_generator = ReportGenerator(config)
        
        # Get date range
        start_date, end_date = get_date_range()
        logging.info(f"Generating report for period: {start_date} to {end_date}")
        
        # Fetch orders
        orders = shopify_api.fetch_orders(start_date, end_date)
        if not orders:
            logging.error("No orders found for the specified period")
            return
        
        # Process sales data
        sales_data, skipped_items, preorder_items = sales_processor.aggregate_sales(orders)
        if not sales_data:
            logging.error("No sales data to report")
            return
        
        # Generate and send report
        report_generator.generate_report(sales_data, skipped_items, start_date, end_date)
        
        # Cleanup old files
        file_manager.cleanup_old_files()
        
        logging.info("Weekly sales report generated successfully")
        
    except Exception as e:
        logging.error(f"Error generating weekly sales report: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()