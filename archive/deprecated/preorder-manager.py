# DEPRECATED
#!/usr/bin/env python
"""
Preorder Manager

A comprehensive script to manage the preorder workflow, handling both
identification of pending releases and processing of approved releases.

This script consolidates the functionality of multiple scripts to make the 
workflow more robust and reduce dependencies between components.
"""

import os
import sys
import json
import csv
import re
import logging
import argparse
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None
USE_TEST_DATA = False

def load_environment(env_file='.env.production'):
    """Load environment variables from .env file"""
    global GRAPHQL_URL, HEADERS, USE_TEST_DATA
    
    # Function to load variables from .env file
    try:
        env_path = os.path.join(BASE_DIR, env_file)
        env_vars = {}
        
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os.environ[key] = value
                        env_vars[key] = value
            
            logging.info(f"Loaded environment from {env_path}")
        else:
            logging.warning(f"Environment file {env_path} not found, using existing environment variables")
        
        # Set up global variables
        shop_url = os.getenv('SHOP_URL')
        access_token = os.getenv('SHOPIFY_ACCESS_TOKEN')
        use_test_data = os.getenv('USE_TEST_DATA', '').lower() in ('true', 't', '1', 'yes')
        
        USE_TEST_DATA = use_test_data
        
        if USE_TEST_DATA:
            logging.info("🧪 Running in TEST DATA mode - using simulated data")
            GRAPHQL_URL = "https://test-shop.myshopify.com/admin/api/2025-01/graphql.json"
            HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": "test-token"}
        elif shop_url and access_token:
            GRAPHQL_URL = f"https://{shop_url}/admin/api/2025-01/graphql.json"
            HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": access_token}
            logging.info(f"Initialized Shopify API with URL: {GRAPHQL_URL}")
        else:
            logging.error("Missing Shopify API credentials (SHOP_URL or SHOPIFY_ACCESS_TOKEN)")
            return False
        
        # Log loaded variables (mask sensitive values)
        for key, value in env_vars.items():
            if any(sensitive in key.lower() for sensitive in ['token', 'key', 'secret', 'password']):
                logging.info(f"✓ {key} is set (value masked)")
            else:
                logging.info(f"✓ {key} = {value}")
        
        return True
    
    except Exception as e:
        logging.error(f"Error loading environment: {e}")
        return False

def verify_directory_structure():
    """Ensure all required directories exist"""
    directories = ['output', 'preorders', 'overrides', 'audit']
    
    for directory in directories:
        dir_path = os.path.join(BASE_DIR, directory)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logging.info(f"Created directory: {dir_path}")
        else:
            logging.info(f"Directory exists: {dir_path}")

def find_latest_approved_releases():
    """Find the most recent approved releases file"""
    output_dir = os.path.join(BASE_DIR, 'output')
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return None
    
    # Find approved_releases files
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    
    if not approval_files:
        logging.info("No approved releases files found")
        return None
    
    # Sort by filename (which contains date) to get the most recent
    approval_files.sort(reverse=True)
    latest_file = os.path.join(output_dir, approval_files[0])
    
    # Check if file has already been processed
    processed_marker = latest_file + '.processed'
    if os.path.exists(processed_marker):
        logging.info(f"Latest approval file has already been processed: {latest_file}")
        # Return the file anyway, but indicate it's been processed
        return latest_file, True
    
    return latest_file, False

def is_preorder_reported(isbn, history_data):
    """Check if a preorder has already been reported"""
    reported_preorders = history_data.get('reported_preorders', [])
    
    for record in reported_preorders:
        if record.get('isbn') == isbn:
            return True, record
    
    return False, None

def add_to_preorder_history(isbn, quantity, title=None, report_date=None, history_data=None, history_file=None):
    """Add a preorder to the history"""
    if not report_date:
        report_date = datetime.now().strftime('%Y-%m-%d')
    
    if not history_data:
        if not history_file:
            history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        except Exception as e:
            logging.error(f"Error loading preorder history: {e}")
            return None
    
    # Check if ISBN already exists
    is_reported, existing_record = is_preorder_reported(isbn, history_data)
    
    if is_reported:
        # Update existing record with additional information
        existing_record['quantity'] = quantity
        existing_record['report_date'] = report_date
        existing_record['last_updated'] = datetime.now().isoformat()
        if title:
            existing_record['title'] = title
        logging.info(f"Updated history for ISBN {isbn} with quantity {quantity}")
    else:
        # Add new record
        new_record = {
            'isbn': isbn,
            'quantity': quantity,
            'report_date': report_date,
            'added': datetime.now().isoformat()
        }
        
        if title:
            new_record['title'] = title
        
        history_data['reported_preorders'].append(new_record)
        logging.info(f"Added new history record for ISBN {isbn} with quantity {quantity}")
    
    # Update last_updated timestamp
    history_data['last_updated'] = datetime.now().isoformat()
    
    # Save updated history
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history_data, f, indent=2)
    
    return history_data

def process_approved_releases(sales_data=None):
    """
    Process approved releases and add to sales data
    
    Args:
        sales_data: Dictionary mapping ISBNs to quantities (optional)
        
    Returns:
        Updated sales data with approved releases included
    """
    if sales_data is None:
        sales_data = {}
    
    # Log initial sales data
    logging.info(f"Initial sales data before processing approved releases: {sales_data}")
    
    # Find the latest approvals file
    latest_file, already_processed = find_latest_approved_releases()
    
    if not latest_file:
        logging.info("No approved releases files found")
        return sales_data
    
    try:
        logging.info(f"Processing approved releases from: {latest_file}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            approved_data = json.load(f)
        
        approved_books = approved_data.get('approved_releases', [])
        is_test_data = approved_data.get('test_data', False)
        
        if not approved_books:
            logging.info("No approved books found in file")
            return sales_data
        
        logging.info(f"Found {len(approved_books)} approved books to include in report")
        logging.info(f"Is test data: {is_test_data}")
        
        # Load preorder history to check for duplicates
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        # Track new books added to the report
        newly_reported_books = []
        skipped_books = []
        
        # Add approved books to sales data
        for book in approved_books:
            isbn = book.get('isbn')
            quantity = book.get('quantity', 0)
            
            if isbn and quantity > 0:
                # Check if this ISBN has already been reported
                already_reported, record = is_preorder_reported(isbn, history_data)
                
                if already_reported:
                    # Skip this book as it's already been reported
                    logging.info(f"Skipping ISBN {isbn} - already reported on {record.get('report_date')} with quantity {record.get('quantity')}")
                    skipped_books.append({
                        'isbn': isbn,
                        'title': book.get('title', 'Unknown'),
                        'quantity': quantity,
                        'prev_report_date': record.get('report_date'),
                        'prev_quantity': record.get('quantity')
                    })
                else:
                    # Add to sales data and track for history
                    sales_data[isbn] = sales_data.get(isbn, 0) + quantity
                    logging.info(f"Added {quantity} copies of ISBN {isbn} from approved releases")
                    
                    newly_reported_books.append({
                        'isbn': isbn,
                        'quantity': quantity,
                        'title': book.get('title', 'Unknown')
                    })
        
        # Add newly reported books to history (skip for test data)
        if newly_reported_books and not is_test_data:
            report_date = datetime.now().strftime('%Y-%m-%d')
            batch_add_to_history(newly_reported_books, report_date)
            logging.info(f"Added {len(newly_reported_books)} books to preorder history")
        elif newly_reported_books and is_test_data:
            logging.info(f"SKIPPING addition of {len(newly_reported_books)} books to preorder history because this is test data")
        
        # Mark file as processed only if not test data and not already processed
        if not is_test_data and not already_processed:
            processed_marker = latest_file + '.processed'
            with open(processed_marker, 'w') as f:
                f.write(datetime.now().isoformat())
            logging.info(f"Marked approval file as processed: {processed_marker}")
        elif already_processed:
            logging.info(f"File was already marked as processed")
        else:
            logging.info(f"Skipping processed marker creation because this is test data")
        
        # Log summary of processing
        logging.info(f"Processing summary:")
        logging.info(f"  - Total approved books: {len(approved_books)}")
        logging.info(f"  - Added to report: {len(newly_reported_books)}")
        logging.info(f"  - Skipped (already reported): {len(skipped_books)}")
        if skipped_books:
            for book in skipped_books:
                logging.info(f"    - Skipped: {book['title']} (ISBN: {book['isbn']}) - Previously reported on {book['prev_report_date']}")
    
        # Log updated sales data at the end
        logging.info(f"Final sales data after processing approved releases: {sales_data}")
        
    except Exception as e:
        logging.error(f"Error processing approved releases: {e}")
    
    return sales_data

def create_approved_releases(isbns, titles=None, quantities=None, is_test=False):
    """
    Create an approved releases file with specified ISBNs
    
    Args:
        isbns: List of ISBNs to include
        titles: List of book titles (optional, will use placeholders if not provided)
        quantities: List of quantities (optional, will use default of 5 if not provided)
        is_test: Whether this is test data
        
    Returns:
        Path to the created file
    """
    # Set up default values
    if titles is None:
        titles = [f"Book Title for ISBN {isbn}" for isbn in isbns]
    elif len(titles) < len(isbns):
        # Extend titles list with placeholders if needed
        titles.extend([f"Book Title for ISBN {isbn}" for isbn in isbns[len(titles):]])
    
    if quantities is None:
        quantities = [5] * len(isbns)
    elif len(quantities) < len(isbns):
        # Extend quantities list with defaults if needed
        quantities.extend([5] * (len(isbns) - len(quantities)))
    
    # Create approved releases data
    approved_releases = []
    total_quantity = 0
    timestamp = datetime.now().strftime('%Y-%m-%d')
    
    for i, isbn in enumerate(isbns):
        quantity = quantities[i]
        title = titles[i]
        total_quantity += quantity
        
        approved_releases.append({
            "isbn": isbn,
            "title": title,
            "quantity": quantity,
            "approved": True,
            "approval_date": timestamp
        })
    
    approved_data = {
        "approved_releases": approved_releases,
        "total_approved_books": len(approved_releases),
        "total_approved_quantity": total_quantity,
        "approval_date": timestamp,
        "test_data": is_test
    }
    
    # Create output directory if needed
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    # Write to file
    output_file = os.path.join(output_dir, f'approved_releases_{timestamp}.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(approved_data, f, indent=2)
    
    logging.info(f"Created approved releases file: {output_file}")
    logging.info(f"Books included: {len(approved_releases)}")
    logging.info(f"Total quantity: {total_quantity}")
    logging.info(f"Test data: {is_test}")
    
    return output_file

def create_pending_releases(isbns, titles=None, quantities=None, pub_dates=None, is_test=False):
    """
    Create a pending releases file with specified ISBNs
    
    Args:
        isbns: List of ISBNs to include
        titles: List of book titles (optional, will use placeholders if not provided)
        quantities: List of quantities (optional, will use default of 5 if not provided)
        pub_dates: List of publication dates (optional, will use today's date if not provided)
        is_test: Whether this is test data
        
    Returns:
        Path to the created file
    """
    # Set up default values
    if titles is None:
        titles = [f"Book Title for ISBN {isbn}" for isbn in isbns]
    elif len(titles) < len(isbns):
        # Extend titles list with placeholders if needed
        titles.extend([f"Book Title for ISBN {isbn}" for isbn in isbns[len(titles):]])
    
    if quantities is None:
        quantities = [5] * len(isbns)
    elif len(quantities) < len(isbns):
        # Extend quantities list with defaults if needed
        quantities.extend([5] * (len(isbns) - len(quantities)))
    
    if pub_dates is None:
        today = datetime.now().strftime('%Y-%m-%d')
        pub_dates = [today] * len(isbns)
    elif len(pub_dates) < len(isbns):
        # Extend pub dates list with today's date if needed
        today = datetime.now().strftime('%Y-%m-%d')
        pub_dates.extend([today] * (len(isbns) - len(pub_dates)))
    
    # Create pending releases data
    pending_releases = []
    total_quantity = 0
    timestamp = datetime.now().strftime('%Y-%m-%d')
    
    for i, isbn in enumerate(isbns):
        quantity = quantities[i]
        title = titles[i]
        pub_date = pub_dates[i]
        total_quantity += quantity
        
        pending_releases.append({
            "isbn": isbn,
            "title": title,
            "quantity": quantity,
            "pub_date": pub_date
        })
    
    pending_data = {
        "pending_releases": pending_releases,
        "error_cases": [],
        "total_quantity": total_quantity,
        "run_date": timestamp,
        "total_pending_books": len(pending_releases),
        "test_data": is_test
    }
    
    # Create output directory if needed
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    # Write to file
    output_file = os.path.join(output_dir, f'pending_releases_{timestamp}.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(pending_data, f, indent=2)
    
    logging.info(f"Created pending releases file: {output_file}")
    logging.info(f"Books included: {len(pending_releases)}")
    logging.info(f"Total quantity: {total_quantity}")
    logging.info(f"Test data: {is_test}")
    
    return output_file

def extract_approved_books_from_issue(issue_body):
    """
    Extract approved books from a GitHub issue body
    
    Args:
        issue_body: Text content of the GitHub issue
        
    Returns:
        List of dictionaries with book details
    """
    approved_books = []
    
    # Parse the issue body to extract approved books (lines with [x])
    lines = issue_body.split('\n')
    
    # Get the data file path from the issue body
    data_file = None
    data_file_match = re.search(r'Data file: `(.+?)`', issue_body)
    if data_file_match:
        data_file = data_file_match.group(1)
        logging.info(f"Found data file reference in issue: {data_file}")
    
    # First, extract all ISBNs that have been approved
    approved_isbns = []
    for line in lines:
        # Match lines that have a checked box in a table row format
        if re.search(r'\|\s*\[x\]', line, re.IGNORECASE):
            # Extract ISBN from the line (second column in the table)
            match = re.search(r'\|\s*\[x\]\s*\|\s*([0-9]+)', line, re.IGNORECASE)
            if match:
                isbn = match.group(1)
                logging.info(f"Found approved ISBN: {isbn}")
                approved_isbns.append(isbn)
    
    # Now, try to get more details for each approved ISBN
    if data_file and os.path.exists(data_file):
        # If we have the data file, load it to get full details
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                pending_data = json.load(f)
            
            pending_releases = pending_data.get('pending_releases', [])
            
            # Filter to only include approved books
            for book in pending_releases:
                if book.get('isbn') in approved_isbns:
                    approved_books.append(book)
        except Exception as e:
            logging.error(f"Error loading data file: {e}")
    
    # If we couldn't get details from the data file, extract them from the table
    if not approved_books:
        for line in lines:
            for isbn in approved_isbns:
                if isbn in line:
                    # Parse the table row to extract title, quantity, etc.
                    columns = line.split('|')
                    if len(columns) >= 5:
                        # Table format: | Approve | ISBN | Title | Quantity | Pub Date |
                        title = columns[3].strip() if len(columns) > 3 else f"Book with ISBN {isbn}"
                        
                        # Try to parse quantity
                        quantity = 5  # Default
                        if len(columns) > 4:
                            try:
                                quantity_text = columns[4].strip()
                                quantity = int(re.search(r'\d+', quantity_text).group(0))
                            except (ValueError, AttributeError):
                                pass
                        
                        # Try to parse pub date
                        pub_date = datetime.now().strftime('%Y-%m-%d')  # Default
                        if len(columns) > 5:
                            try:
                                pub_date_text = columns[5].strip()
                                # Try to parse date in various formats
                                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y']:
                                    try:
                                        date_obj = datetime.strptime(pub_date_text, fmt)
                                        pub_date = date_obj.strftime('%Y-%m-%d')
                                        break
                                    except ValueError:
                                        continue
                            except Exception:
                                pass
                        
                        approved_books.append({
                            'isbn': isbn,
                            'title': title,
                            'quantity': quantity,
                            'pub_date': pub_date
                        })
                        
                        break
    
    return approved_books

def generate_weekly_report():
    """Generate the weekly sales report"""
    # Process approved releases
    sales_data = process_approved_releases()
    
    # Generate report file
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d')
    report_file = os.path.join(output_dir, f'NYT_weekly_sales_report_{timestamp}.csv')
    
    # Export to CSV
    with open(report_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for isbn, qty in sales_data.items():
            writer.writerow([isbn, qty])
    
    logging.info(f"Generated weekly report: {report_file}")
    logging.info(f"Total ISBNs: {len(sales_data)}")
    logging.info(f"Total quantity: {sum(sales_data.values())}")
    
    return report_file, sales_data

def create_output_from_issue(issue_file, is_test=False):
    """
    Process a GitHub issue file and create the appropriate output files
    
    Args:
        issue_file: Path to file containing GitHub issue body
        is_test: Whether to mark the output as test data
        
    Returns:
        Path to the approved releases file
    """
    try:
        # Read the issue body
        with open(issue_file, 'r', encoding='utf-8') as f:
            issue_body = f.read()
        
        # Extract approved books
        approved_books = extract_approved_books_from_issue(issue_body)
        
        if not approved_books:
            logging.warning("No approved books found in the issue")
            return None
        
        # Create approved releases file
        isbns = [book['isbn'] for book in approved_books]
        titles = [book.get('title', f"Book with ISBN {book['isbn']}") for book in approved_books]
        quantities = [book.get('quantity', 5) for book in approved_books]
        
        output_file = create_approved_releases(isbns, titles, quantities, is_test)
        
        return output_file
    
    except Exception as e:
        logging.error(f"Error creating output from issue: {e}")
        return None

def manual_approve_isbns(isbns, titles=None, quantities=None, is_test=False):
    """
    Manually create an approved releases file with specified ISBNs
    
    Args:
        isbns: List of ISBNs to approve
        titles: Optional list of titles
        quantities: Optional list of quantities
        is_test: Whether to mark as test data
        
    Returns:
        Path to the approved releases file
    """
    try:
        if isinstance(isbns, str):
            # Split comma-separated string
            isbns = [isbn.strip() for isbn in isbns.split(',')]
        
        if not isbns:
            logging.error("No ISBNs provided")
            return None
        
        output_file = create_approved_releases(isbns, titles, quantities, is_test)
        
        return output_file
    
    except Exception as e:
        logging.error(f"Error approving ISBNs: {e}")
        return None

def batch_add_to_history(preorders, report_date=None):
    """Add multiple preorders to the history in a batch"""
    if not report_date:
        report_date = datetime.now().strftime('%Y-%m-%d')
    
    history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        logging.error(f"Error loading preorder history: {e}")
        return None
    
    for preorder in preorders:
        isbn = preorder.get('isbn')
        quantity = preorder.get('quantity', 0)
        title = preorder.get('title')
        
        if isbn and quantity > 0:
            add_to_preorder_history(isbn, quantity, title, report_date, history_data, history_file)
    
    return history_data

def verify_preorder_history():
    """Verify and initialize preorder history file if needed"""
    history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    if not os.path.exists(history_file):
        logging.info("Creating initial preorder history file")
        
        default_history = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
        
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(default_history, f, indent=2)
        
        logging.info(f"Created preorder history file: {history_file}")
    else:
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # Check if the file has valid structure
            if not isinstance(history_data, dict) or "reported_preorders" not in history_data:
                logging.warning("Preorder history file has invalid structure, creating backup and resetting")
                
                # Create backup of invalid file
                backup_file = f"{history_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(history_data, f, indent=2)
                
                # Reset to default structure
                default_history = {
                    "reported_preorders": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(default_history, f, indent=2)
                
                logging.info(f"Reset preorder history file and saved backup to: {backup_file}")
            else:
                logging.info(f"Verified preorder history file with {len(history_data.get('reported_preorders', []))} records")
        
        except Exception as e:
            logging.error(f"Error verifying preorder history file: {e}")
            
            # Create backup of invalid file
            backup_file = f"{history_file}.error.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                with open(history_file, 'r') as src, open(backup_file, 'w') as dst:
                    dst.write(src.read())
                
                # Reset to default structure
                default_history = {
                    "reported_preorders": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(default_history, f, indent=2)
                
                logging.info(f"Reset preorder history file and saved backup to: {backup_file}")
            
            except Exception as backup_error:
                logging.error(f"Error creating backup of invalid history file: {backup_error}")
                return False
    
    return True

def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description='Preorder Manager')
    
    # Add subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Create pending releases command
    pending_parser = subparsers.add_parser('create-pending', help='Create pending releases file')
    pending_parser.add_argument('--isbns', nargs='+', required=True, help='List of ISBNs to include')
    pending_parser.add_argument('--titles', nargs='+', help='List of book titles (optional)')
    pending_parser.add_argument('--quantities', nargs='+', type=int, help='List of quantities (optional)')
    pending_parser.add_argument('--pub-dates', nargs='+', help='List of publication dates (optional)')
    pending_parser.add_argument('--test', action='store_true', help='Mark as test data')
    
    # Create approved releases command
    approved_parser = subparsers.add_parser('create-approved', help='Create approved releases file')
    approved_parser.add_argument('--isbns', nargs='+', required=True, help='List of ISBNs to include')
    approved_parser.add_argument('--titles', nargs='+', help='List of book titles (optional)')
    approved_parser.add_argument('--quantities', nargs='+', type=int, help='List of quantities (optional)')
    approved_parser.add_argument('--test', action='store_true', help='Mark as test data')
    
    # Process issue command
    issue_parser = subparsers.add_parser('process-issue', help='Process GitHub issue')
    issue_parser.add_argument('--issue-file', required=True, help='Path to file containing GitHub issue body')
    issue_parser.add_argument('--test', action='store_true', help='Mark as test data')
    
    # Generate report command
    report_parser = subparsers.add_parser('generate-report', help='Generate weekly report')
    
    # Verify-preorder-history command
    history_parser = subparsers.add_parser('verify-history', help='Verify preorder history file')
    
    args = parser.parse_args()
    
    # Initialize environment
    success = load_environment()
    if not success:
        logging.error("Failed to load environment variables")
        return 1
    
    # Create directory structure
    verify_directory_structure()
    
    # Verify preorder history file
    verify_preorder_history()
    
    # Execute requested command
    if args.command == 'create-pending':
        create_pending_releases(args.isbns, args.titles, args.quantities, args.pub_dates, args.test)
    
    elif args.command == 'process-issue':
        create_output_from_issue(args.issue_file, args.test)
    
    elif args.command == 'generate-report':
        generate_weekly_report()
    
    elif args.command == 'verify-history':
        verify_preorder_history()
    
    else:
        logging.error("No command specified. Run with -h for help.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())