# Publishing/Unpublishing Logic with Railway Deployment Architecture

## Core Publishing/Unpublishing Logic

The main logic is contained within the `usedBookManager.js` file, particularly in the `processInventoryChange` function:

1. **Inventory Change Detection**: The system monitors inventory levels for specific products (used books).

2. **Publishing Logic**:
   - When a product has inventory (is in stock), it gets published (made visible on the website)
   - When a product is out of stock (zero inventory), it gets unpublished (hidden from the website)

3. **Redirect Management**:
   - When a product is unpublished (out of stock), a 302 (temporary) redirect is created to point to the related "new" product
   - When a product is published (back in stock), any existing redirect is removed

4. **SEO Handling**: 
   - Canonical URLs for used books point to their "new" book equivalents to maintain SEO value

## Railway Deployment Architecture

The project uses Railway for cloud deployment with a CI/CD pipeline through GitHub integration:

1. **Repository Structure**:
   - GitHub repository contains all code and configuration
   - Railway connects directly to this repository for automatic deployments

2. **Railway Configuration**:
   - Configuration is defined in `railway.json` file which specifies:
     - Build commands: `npm install`
     - Start command: `npm start`
     - Health check path: `/health`
     - Restart policy: `ON_FAILURE` with max retries
     - Environment variables organized in groups

3. **Deployment Process**:
   - Code changes are pushed to GitHub
   - Railway automatically detects changes and triggers a new build
   - Environment variables are pulled from Railway's secure environment
   - The application is deployed as a container

4. **Environment Variables Management**:
   - All sensitive data (API keys, tokens) are managed in Railway's environment
   - Variables are grouped (shopify-credentials, notification-settings, etc.)
   - No secrets are stored in the repository

5. **Health Monitoring**:
   - Railway uses the `/health` endpoint to monitor application status
   - Automatic restarts on failures (configured in railway.json)
   - Logging and metrics managed through Railway's dashboard

6. **Railway Project Files**:
   - `railway.json`: Main configuration file
   - `Procfile`: Defines process types (web: node src/index.js)

## GitHub Integration

1. **CI/CD Workflow**:
   - Changes to main branch trigger automatic deployments
   - Production branch is used for live environment

2. **Backup and Versioning**:
   - GitHub provides versioning and backup of all code
   - Rollbacks possible through Railway's dashboard or by reverting commits

3. **Repository Organization**:
   - Code and configuration files in version control
   - Documentation (README.md, etc.) explaining the architecture

## Adaptation for Preorder Use Case

To adapt this for your preorder scenario within the same Railway architecture:

1. Create a new module similar to `usedBookManager.js` for handling preorder transitions
2. Implement the identification logic to find "released" preorder books
3. Implement collection removal and description update functions
4. Set up similar scheduled jobs or webhooks to trigger the process
5. Deploy to Railway using the same configuration approach

You can leverage the existing Railway configuration with minimal changes, as the deployment architecture is independent of the specific business logic being implemented.