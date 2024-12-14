import shopify
import os
from dotenv import load_dotenv
import logging
import time
import csv

# Configure logging
logging.basicConfig(
    filename='fetch_all_variants_test.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Load environment variables from .env file
load_dotenv()

SHOP_URL = os.getenv('SHOP_URL')
API_ACCESS_TOKEN = os.getenv('SHOPIFY_API_ACCESS_TOKEN')
API_VERSION = os.getenv('API_VERSION')  # Should be '2024-10'

# Initialize Shopify session using API Access Token
session = shopify.Session(SHOP_URL, API_VERSION, API_ACCESS_TOKEN)
shopify.ShopifyResource.activate_session(session)
print("Shopify session activated successfully.")

def fetch_all_variants():
    variants = []
    params = {'limit': 250}
    while True:
        try:
            batch = shopify.Variant.find(**params)
            if not batch:
                break
            variants.extend(batch)
            print(f"Fetched {len(batch)} variants.")
            logging.info(f"Fetched {len(batch)} variants.")
            
            # Get the 'Link' header to find the next page
            link_header = shopify.ShopifyResource.connection.response.headers.get('Link', '')
            if 'rel="next"' in link_header:
                # Extract the URL for the next page
                next_url = None
                links = link_header.split(',')
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link.split(';')[0].strip('<> ')
                        break
                if next_url:
                    # Extract the 'since_id' parameter from the next_url
                    from urllib.parse import urlparse, parse_qs
                    parsed_url = urlparse(next_url)
                    query_params = parse_qs(parsed_url.query)
                    since_id = query_params.get('since_id', [None])[0]
                    if since_id:
                        params = {'limit': 250, 'since_id': since_id}
                    else:
                        break
                else:
                    break
            else:
                break

            time.sleep(1)  # To respect rate limits
        except shopify.ShopifyError as e:
            logging.error(f"Shopify API error fetching variants: {e}", exc_info=True)
            print(f"Shopify API error fetching variants: {e}")
            break
        except Exception as e:
            logging.error(f"Unexpected error fetching variants: {e}", exc_info=True)
            print(f"Unexpected error fetching variants: {e}")
            break

    return variants

def main():
    variants = fetch_all_variants()
    print(f"Total variants fetched: {len(variants)}")
    logging.info(f"Total variants fetched: {len(variants)}")
    
    # Export variants to CSV
    with open('all_variants.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variant ID', 'Barcode'])
        for variant in variants:
            writer.writerow([variant.id, variant.barcode])
    
    print("All variants have been exported to 'all_variants.csv'.")

if __name__ == "__main__":
    main()