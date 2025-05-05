# DEPRECATED
#!/usr/bin/env python
"""
GitHub Issue Parser

This script extracts approved books from a GitHub issue body and creates a proper approved_releases file.
It can be used to manually process approved issues if the automated workflow fails.
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def extract_approved_isbns(issue_body):
    """
    Extract approved ISBNs from a GitHub issue body
    Looks for checked boxes [x] in table rows and extracts the corresponding ISBN
    """
    approved_isbns = []
    
    # Split the issue body into lines
    lines = issue_body.split('\n')
    
    for line in lines:
        # Match lines that have a checked box in a table row format
        if re.search(r'\|\s*\[x\]', line, re.IGNORECASE):
            # Extract ISBN from the line (should be the second column)
            match = re.search(r'\|\s*\[x\]\s*\|\s*([0-9]+)', line, re.IGNORECASE)
            if match:
                isbn = match.group(1)
                logging.info(f"Found approved ISBN: {isbn}")
                approved_isbns.append(isbn)
    
    return approved_isbns

def get_data_file_path(issue_body):
    """
    Extract the path to the pending releases data file from the issue body
    """
    match = re.search(r'Data file: `(.+?)`', issue_body)
    if match:
        return match.group(1)
    return None

def process_approved_isbns(approved_isbns, pending_file_path):
    """
    Process approved ISBNs by filtering the pending releases file 
    and creating an approved releases file
    """
    if not os.path.exists(pending_file_path):
        logging.error(f"Pending releases file not found: {pending_file_path}")
        return None
    
    try:
        # Load the pending releases data
        with open(pending_file_path, 'r', encoding='utf-8') as f:
            pending_data = json.load(f)
        
        pending_releases = pending_data.get('pending_releases', [])
        
        # Filter to only include approved books
        approved_releases = [
            book for book in pending_releases 
            if book.get('isbn') in approved_isbns
        ]
        
        # Mark books as approved
        for book in approved_releases:
            book['approved'] = True
            book['approval_date'] = datetime.now().strftime('%Y-%m-%d')
        
        # Create approved releases data
        timestamp = datetime.now().strftime('%Y-%m-%d')
        approved_data = {
            'approved_releases': approved_releases,
            'total_approved_books': len(approved_releases),
            'total_approved_quantity': sum(book.get('quantity', 0) for book in approved_releases),
            'approval_date': timestamp
        }
        
        # Create output path
        output_dir = os.path.dirname(pending_file_path)
        output_file = os.path.join(output_dir, f'approved_releases_{timestamp}.json')
        
        # Save the approved releases file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(approved_data, f, indent=2)
        
        logging.info(f"Created approved releases file: {output_file}")
        logging.info(f"Approved books: {len(approved_releases)}")
        logging.info(f"Total quantity: {approved_data['total_approved_quantity']}")
        
        return output_file
    
    except Exception as e:
        logging.error(f"Error processing approved ISBNs: {e}")
        return None

def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description='Parse GitHub issue and create approved releases file')
    parser.add_argument('--issue-file', required=True, help='Path to a file containing the GitHub issue body')
    parser.add_argument('--output-dir', default='./output', help='Directory to save the approved releases file')
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    try:
        # Read the issue body from file
        with open(args.issue_file, 'r', encoding='utf-8') as f:
            issue_body = f.read()
        
        # Extract approved ISBNs
        approved_isbns = extract_approved_isbns(issue_body)
        
        if not approved_isbns:
            logging.warning("No approved ISBNs found in the issue body")
            return 1
        
        logging.info(f"Found {len(approved_isbns)} approved ISBNs")
        
        # Get the data file path from the issue body
        data_file = get_data_file_path(issue_body)
        
        if not data_file:
            logging.warning("Could not find data file reference in issue body")
            # Look for the most recent pending_releases file in the output directory
            pending_files = [f for f in os.listdir(args.output_dir) 
                           if f.startswith('pending_releases_') and f.endswith('.json')]
            
            if pending_files:
                pending_files.sort(reverse=True)
                data_file = os.path.join(args.output_dir, pending_files[0])
                logging.info(f"Using most recent pending releases file: {data_file}")
            else:
                logging.error("No pending releases files found")
                return 1
        
        # Process approved ISBNs and create approved releases file
        output_file = process_approved_isbns(approved_isbns, data_file)
        
        if output_file:
            logging.info(f"Successfully created approved releases file: {output_file}")
            return 0
        else:
            logging.error("Failed to create approved releases file")
            return 1
    
    except Exception as e:
        logging.error(f"Error processing issue: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())