import os
import requests
import logging
from datetime import datetime
import time
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def load_environment():
    """
    Loads environment variables from .env.production file
    """
    try:
        load_dotenv('.env.production')
        logging.info("Environment variables successfully loaded.")
        logging.info(f"SHOP_URL present: {bool(os.getenv('SHOP_URL'))}")
        logging.info(f"SHOPIFY_ACCESS_TOKEN present: {bool(os.getenv('SHOPIFY_ACCESS_TOKEN'))}")
    except Exception as e:
        logging.error(f"Error loading environment variables: {e}")

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

def fetch_product_pub_dates(product_ids):
    """
    Fetches publication dates for specific products
    """
    query = """
    query($ids: [ID!]!) {
        nodes(ids: $ids) {
            ... on Product {
                id
                title
                metafields(first: 10, namespace: "custom") {
                    edges {
                        node {
                            key
                            value
                        }
                    }
                }
            }
        }
    }
    """
    
    try:
        # Split into chunks of 10 products to manage query cost
        chunk_size = 10
        all_pub_dates = {}
        
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i:i + chunk_size]
            variables = {"ids": chunk}
            
            data = run_query_with_retries(query, variables)
            logging.debug(f"Raw response for chunk {i//chunk_size + 1}: {data}")
            
            for node in data.get('nodes', []):
                if node:  # some nodes might be null
                    product_id = node['id']
                    title = node['title']
                    metafields = node.get('metafields', {}).get('edges', [])
                    
                    logging.debug(f"Processing product: {title}")
                    logging.debug(f"Found {len(metafields)} metafields")
                    
                    for metafield in metafields:
                        key = metafield['node']['key']
                        value = metafield['node']['value']
                        logging.debug(f"Metafield: {key} = {value}")
                        
                        if key == 'pub_date':
                            all_pub_dates[product_id] = {
                                'title': title,
                                'pub_date': value
                            }
                            logging.info(f"Found pub_date for {title}: {value}")
                            break
            
            # Add a small delay between chunks
            if i + chunk_size < len(product_ids):
                time.sleep(1)
        
        return all_pub_dates
        
    except Exception as e:
        logging.error(f"Error fetching pub dates: {e}")
        return {}

def main():
    global GRAPHQL_URL, HEADERS
    
    load_environment()
    
    SHOP_URL = os.getenv('SHOP_URL')
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')
    
    if not SHOP_URL or not ACCESS_TOKEN:
        logging.error("Missing required environment variables")
        return
        
    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2025-01/graphql.json"
    HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}
    
    # Test with a few known product IDs that should have pub_dates
    test_product_ids = [
        "gid://shopify/Product/7115639619717",  # Replace with actual product IDs
        "gid://shopify/Product/7115571003525"
    ]
    
    logging.info("Starting pub date fetch test")
    pub_dates = fetch_product_pub_dates(test_product_ids)
    
    if pub_dates:
        logging.info("Successfully fetched pub dates:")
        for product_id, data in pub_dates.items():
            logging.info(f"Product: {data['title']}, Pub Date: {data['pub_date']}")
    else:
        logging.warning("No pub dates found")

if __name__ == "__main__":
    main()