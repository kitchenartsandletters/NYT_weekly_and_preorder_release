#!/usr/bin/env python
"""
Process approved preorders from GitHub issues

This script reads GitHub approval issues and processes approved preorder books
"""
import os
import sys
import json
import logging
import argparse
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_pending_releases(file_path):
    """Load pending releases from JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logging.info(f"Loaded pending releases: {len(data.get('pending_releases', []))} books")
        return data
    except Exception as e:
        logging.error(f"Error loading pending releases: {e}")
        return None

def parse_issue_body(issue_body):
    """Parse GitHub issue body to extract approved books"""
    approved_isbns = []
    
    # Find checkboxes with [x] in the table
    lines = issue_body.split('\n')
    for line in lines:
        # Match lines that have a checked box
        if re.search(r'\|\s*\[x\]', line, re.IGNORECASE):
            # Extract ISBN from the line (assuming it's the second column)
            match = re.search(r'\|\s*\[x\]\s*\|\s*([0-9]+)', line, re.IGNORECASE)
            if match:
                isbn = match.group(1)
                approved_isbns.append(isbn)
    
    logging.info(f"Found {len(approved_isbns)} approved ISBNs in issue")
    return approved_isbns

def process_approvals(pending_data, approved_isbns, output_file=None):
    """Process the approvals and create the approved releases file"""
    if not output_file:
        timestamp = datetime.now().strftime('%Y-%m-%d')
        output_file = os.path.join(BASE_DIR, 'output', f'approved_releases_{timestamp}.json')
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Filter pending releases to only include approved ISBNs
    pending_releases = pending_data.get('pending_releases', [])
    approved_releases = []
    remaining_releases = []
    
    for book in pending_releases:
        isbn = book.get('isbn')
        if isbn in approved_isbns:
            # Mark as approved
            book['approved'] = True
            book['approval_date'] = datetime.now().strftime('%Y-%m-%d')
            approved_releases.append(book)
        else:
            remaining_releases.append(book)
    
    # Calculate totals
    total_approved_quantity = sum(book.get('quantity', 0) for book in approved_releases)
    
    # Create approved releases data
    approved_data = {
        'approved_releases': approved_releases,
        'total_approved_books': len(approved_releases),
        'total_approved_quantity': total_approved_quantity,
        'approval_date': datetime.now().strftime('%Y-%m-%d'),
        'remaining_releases': remaining_releases,
        'total_remaining_books': len(remaining_releases),
        'total_remaining_quantity': sum(book.get('quantity', 0) for book in remaining_releases)
    }
    
    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(approved_data, f, indent=2)
    
    logging.info(f"Wrote {len(approved_releases)} approved books to {output_file}")
    logging.info(f"Total approved quantity: {total_approved_quantity}")
    
    return output_file

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Process approved preorders from GitHub issues')
    parser.add_argument('--pending-file', required=True, help='Path to pending releases JSON file')
    parser.add_argument('--issue-body', required=True, help='Path to file containing GitHub issue body')
    parser.add_argument('--output-file', help='Path to output approved releases file')
    args = parser.parse_args()
    
    # Load pending releases
    pending_data = load_pending_releases(args.pending_file)
    if not pending_data:
        logging.error("Failed to load pending releases")
        return 1
    
    # Load issue body
    try:
        with open(args.issue_body, 'r', encoding='utf-8') as f:
            issue_body = f.read()
        
        logging.info(f"Loaded issue body ({len(issue_body)} chars)")
    except Exception as e:
        logging.error(f"Error loading issue body: {e}")
        return 1
    
    # Parse approved ISBNs
    approved_isbns = parse_issue_body(issue_body)
    if not approved_isbns:
        logging.warning("No approved books found in issue")
    
    # Process approvals
    output_file = process_approvals(pending_data, approved_isbns, args.output_file)
    
    logging.info("Approval processing complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())