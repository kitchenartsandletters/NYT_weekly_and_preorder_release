name: Tag Preorder Orders

on:
  schedule:
    - cron: '0 * * * *' # Every hour, at minute 0
  workflow_dispatch:

jobs:
  tag-preorder-orders:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install python-dotenv requests

      - name: Run preorderOrderTagger script
        env:
          SHOP_URL: ${{ secrets.SHOP_URL }}
          SHOPIFY_ACCESS_TOKEN: ${{ secrets.SHOPIFY_ACCESS_TOKEN }}
        run: |
          python preorderOrderTagger.py