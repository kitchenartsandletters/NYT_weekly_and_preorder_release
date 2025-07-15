-- 📦 Preorder Product Metadata
CREATE TABLE preorders (
    isbn TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    vendor TEXT,
    pub_date DATE,
    tagged_preorder BOOLEAN DEFAULT FALSE,
    in_preorder_collection BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🛒 Presale Orders
CREATE TABLE presales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isbn TEXT REFERENCES preorders(isbn),
    order_id TEXT NOT NULL,
    qty INTEGER NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🚀 Release Records
CREATE TABLE releases (
    isbn TEXT PRIMARY KEY REFERENCES preorders(isbn),
    released_on DATE NOT NULL,
    approved_by TEXT,
    inventory_on_release INTEGER,
    total_presales INTEGER DEFAULT 0
);

-- ⚠️ Anomaly Logging
CREATE TABLE anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isbn TEXT REFERENCES preorders(isbn),
    issue_type TEXT NOT NULL,
    description TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🪵 Sync + Audit Logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file TEXT,
    payload JSONB,
    log_type TEXT,
    warnings TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 🗂️ NYT Report Export Archive (optional)
CREATE TABLE nyt_exports (
    export_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exported_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    included_isbns TEXT[],
    notes TEXT
);

-- 🗂️ Standard Sales Logging
CREATE TABLE IF NOT EXISTS sales_log (
    id SERIAL PRIMARY KEY,
    isbn TEXT NOT NULL,
    order_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_date TIMESTAMP NOT NULL,
    UNIQUE (order_id, isbn)
);

-- 🗂️ Shopify Refund Logging
CREATE TABLE IF NOT EXISTS refund_log (
    id SERIAL PRIMARY KEY,
    isbn TEXT NOT NULL,
    order_id TEXT NOT NULL,
    refunded_quantity INTEGER NOT NULL,
    refund_date TIMESTAMP NOT NULL,
    reason TEXT,
    UNIQUE (order_id, isbn)
);