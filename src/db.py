import os
import pandas as pd

# Path to the data directory in the Lead's repository
DATA_DIR = r"c:\AIThucChien\K3-Day9-DingDong\data"

# Global dataframes for caching
df_orders = None
df_order_items = None
df_order_payments = None
df_sellers = None
df_products = None

def init_db():
    """Load CSV files into memory once to optimize performance."""
    global df_orders, df_order_items, df_order_payments, df_sellers, df_products
    
    if df_orders is not None:
        return
        
    print("Loading Olist datasets into memory...")
    df_orders = pd.read_csv(os.path.join(DATA_DIR, "olist_orders_dataset.csv"))
    df_order_items = pd.read_csv(os.path.join(DATA_DIR, "olist_order_items_dataset.csv"))
    df_order_payments = pd.read_csv(os.path.join(DATA_DIR, "olist_order_payments_dataset.csv"))
    df_sellers = pd.read_csv(os.path.join(DATA_DIR, "olist_sellers_dataset.csv"))
    df_products = pd.read_csv(os.path.join(DATA_DIR, "olist_products_dataset.csv"))
    print("Olist datasets loaded successfully!")

def get_order_context(order_id):
    """
    Retrieve all relevant information for a given order_id.
    Returns a dictionary of raw facts.
    """
    init_db()
    
    # 1. Get order details
    order_rows = df_orders[df_orders['order_id'] == order_id]
    if order_rows.empty:
        return None
    order_info = order_rows.iloc[0].to_dict()
    
    # 2. Get items details
    item_rows = df_order_items[df_order_items['order_id'] == order_id]
    items_list = []
    seller_ids = set()
    product_ids = set()
    for _, row in item_rows.iterrows():
        item_dict = row.to_dict()
        items_list.append(item_dict)
        seller_ids.add(item_dict['seller_id'])
        product_ids.add(item_dict['product_id'])
        
    # 3. Get payment details
    payment_rows = df_order_payments[df_order_payments['order_id'] == order_id]
    payments_list = []
    for _, row in payment_rows.iterrows():
        payments_list.append(row.to_dict())
        
    # 4. Get sellers info
    sellers_list = []
    if seller_ids:
        seller_rows = df_sellers[df_sellers['seller_id'].isin(seller_ids)]
        for _, row in seller_rows.iterrows():
            sellers_list.append(row.to_dict())
            
    # 5. Get products info
    products_list = []
    if product_ids:
        product_rows = df_products[df_products['product_id'].isin(product_ids)]
        for _, row in product_rows.iterrows():
            products_list.append(row.to_dict())
            
    return {
        "order_id": order_id,
        "order": order_info,
        "items": items_list,
        "payments": payments_list,
        "sellers": sellers_list,
        "products": products_list
    }

# Test block
if __name__ == "__main__":
    init_db()
    # Test with a sample order ID from EC_001
    sample_order_id = "e2a03ccf5ea816036608b2d8c3ab8e60"
    ctx = get_order_context(sample_order_id)
    if ctx:
        print("Success! Sample order status:", ctx['order']['order_status'])
        print("Payments count:", len(ctx['payments']))
        print("Items count:", len(ctx['items']))
    else:
        print("Order not found.")
