BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 001

CREATE TABLE catalog_skus (
    variant_id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    seller_id UUID NOT NULL, 
    sku VARCHAR(80) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    CONSTRAINT pk_catalog_skus PRIMARY KEY (variant_id), 
    CONSTRAINT uq_catalog_skus_sku UNIQUE (sku)
);

CREATE INDEX ix_catalog_skus_seller_active ON catalog_skus (seller_id, is_active);

CREATE TABLE warehouses (
    id UUID NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    address_reference VARCHAR(200), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    CONSTRAINT pk_warehouses PRIMARY KEY (id), 
    CONSTRAINT uq_warehouses_code UNIQUE (code)
);

CREATE INDEX ix_warehouses_active_name ON warehouses (is_active, name);

CREATE TABLE inventory_items (
    id UUID NOT NULL, 
    warehouse_id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    variant_id UUID NOT NULL, 
    seller_id UUID NOT NULL, 
    sku VARCHAR(80) NOT NULL, 
    on_hand_quantity INTEGER DEFAULT '0' NOT NULL, 
    reserved_quantity INTEGER DEFAULT '0' NOT NULL, 
    low_stock_threshold INTEGER DEFAULT '5' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    CONSTRAINT pk_inventory_items PRIMARY KEY (id), 
    CONSTRAINT ck_inventory_items_ck_inventory_items_on_hand_non_negative CHECK (on_hand_quantity >= 0), 
    CONSTRAINT ck_inventory_items_ck_inventory_items_reserved_non_negative CHECK (reserved_quantity >= 0), 
    CONSTRAINT ck_inventory_items_ck_inventory_items_reserved_not_abov_1c2d CHECK (reserved_quantity <= on_hand_quantity), 
    CONSTRAINT ck_inventory_items_ck_inventory_items_threshold_non_negative CHECK (low_stock_threshold >= 0), 
    CONSTRAINT fk_inventory_items_warehouse_id_warehouses FOREIGN KEY(warehouse_id) REFERENCES warehouses (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_inventory_items_warehouse_sku UNIQUE (warehouse_id, sku)
);

CREATE INDEX ix_inventory_items_sku ON inventory_items (sku);

CREATE INDEX ix_inventory_items_seller_sku ON inventory_items (seller_id, sku);

CREATE TABLE inventory_reservations (
    id UUID NOT NULL, 
    inventory_item_id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    cart_reference VARCHAR(120), 
    order_reference VARCHAR(120), 
    quantity INTEGER NOT NULL, 
    status VARCHAR(9) DEFAULT 'active' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    CONSTRAINT pk_inventory_reservations PRIMARY KEY (id), 
    CONSTRAINT ck_inventory_reservations_ck_inventory_reservations_res_e9d2 CHECK (quantity > 0), 
    CONSTRAINT fk_inventory_reservations_inventory_item_id_inventory_items FOREIGN KEY(inventory_item_id) REFERENCES inventory_items (id) ON DELETE RESTRICT
);

CREATE INDEX ix_reservations_status_expiry ON inventory_reservations (status, expires_at);

CREATE INDEX ix_reservations_order ON inventory_reservations (order_reference);

CREATE INDEX ix_reservations_owner ON inventory_reservations (customer_id, status);

CREATE TABLE inventory_movements (
    id UUID NOT NULL, 
    inventory_item_id UUID NOT NULL, 
    movement_type VARCHAR(11) NOT NULL, 
    reason VARCHAR(19) NOT NULL, 
    on_hand_delta INTEGER DEFAULT '0' NOT NULL, 
    reserved_delta INTEGER DEFAULT '0' NOT NULL, 
    resulting_on_hand INTEGER NOT NULL, 
    resulting_reserved INTEGER NOT NULL, 
    reference_type VARCHAR(60), 
    reference_id VARCHAR(120), 
    actor_id UUID NOT NULL, 
    note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_inventory_movements PRIMARY KEY (id), 
    CONSTRAINT ck_inventory_movements_ck_inventory_movements_movement__6d3f CHECK (on_hand_delta <> 0 OR reserved_delta <> 0), 
    CONSTRAINT fk_inventory_movements_inventory_item_id_inventory_items FOREIGN KEY(inventory_item_id) REFERENCES inventory_items (id) ON DELETE RESTRICT
);

CREATE INDEX ix_movements_item_created ON inventory_movements (inventory_item_id, created_at);

CREATE INDEX ix_movements_reference ON inventory_movements (reference_type, reference_id);

CREATE TABLE audit_logs (
    id UUID NOT NULL, 
    actor_id UUID NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    resource_type VARCHAR(80) NOT NULL, 
    resource_id UUID NOT NULL, 
    before_data JSONB, 
    after_data JSONB, 
    request_id VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id)
);

CREATE INDEX ix_audit_resource ON audit_logs (resource_type, resource_id);

CREATE TABLE outbox_events (
    id UUID NOT NULL, 
    aggregate_type VARCHAR(80) NOT NULL, 
    aggregate_id UUID NOT NULL, 
    event_type VARCHAR(160) NOT NULL, 
    payload JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    published_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_outbox_events PRIMARY KEY (id)
);

CREATE INDEX ix_outbox_pending ON outbox_events (published_at, created_at);

CREATE TABLE idempotency_records (
    id UUID NOT NULL, 
    actor_id UUID NOT NULL, 
    idempotency_key VARCHAR(100) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    resource_type VARCHAR(60) NOT NULL, 
    resource_id UUID, 
    response_body TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_idempotency_records PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_idempotency_actor_key ON idempotency_records (actor_id, idempotency_key);

INSERT INTO alembic_version (version_num) VALUES ('001') RETURNING alembic_version.version_num;

COMMIT;

