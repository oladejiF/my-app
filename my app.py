import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('business_records.db', check_same_thread=False)
    c = conn.cursor()
    # Products: Tracks physical vs book balance and pending collections
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    sku INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    physical_balance INTEGER,
                    book_balance INTEGER,
                    not_yet_collected INTEGER DEFAULT 0
                 )''')
    # Sales: Tracks transactions
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_name TEXT,
                    cost_price REAL,
                    quantity INTEGER,
                    total_price REAL,
                    timestamp DATETIME
                 )''')
    # Restock Logs: History of inventory updates
    c.execute('''CREATE TABLE IF NOT EXISTS restock_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku INTEGER,
                    added_qty INTEGER,
                    timestamp DATETIME
                 )''')
    conn.commit()
    return conn

conn = init_db()

# --- UI CONFIG ---
st.set_page_config(page_title="Stock & Sales Pro", layout="wide")
st.title("🚀 Inventory & Sales Control System")

menu = ["📊 Dashboard", "📦 Stock Management", "💰 Sales Terminal"]
choice = st.sidebar.selectbox("Main Menu", menu)

# --- HELPER FUNCTIONS ---
def get_data(query):
    return pd.read_sql_query(query, conn)

# --- 📊 DASHBOARD ---
if choice == "📊 Dashboard":
    st.header("Business Analytics")
    
    sales_df = get_data("SELECT * FROM sales")
    stock_df = get_data("SELECT * FROM products")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        total_rev = sales_df['total_price'].sum() if not sales_df.empty else 0
        st.metric("Total Revenue", f"${total_rev:,.2f}")
    with col2:
        low_stock = stock_df[stock_df['physical_balance'] < 100]
        st.metric("Low Stock Items", len(low_stock))
    with col3:
        pending = stock_df['not_yet_collected'].sum()
        st.metric("Pending Collections", pending)

    st.subheader("⚠️ Low Stock Alerts (Below 100 units)")
    if not low_stock.empty:
        st.warning("The following items need restocking:")
        st.table(low_stock[['name', 'physical_balance']])
    else:
        st.success("All stock levels are healthy!")

    st.divider()
    st.subheader("📈 Sales History")
    st.dataframe(sales_df, use_container_width=True)
    
    if not sales_df.empty:
        csv = sales_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Sales as CSV", data=csv, file_name="sales_report.csv", mime="text/csv")

# --- 📦 STOCK MANAGEMENT ---
elif choice == "📦 Stock Management":
    tab1, tab2 = st.tabs(["Add New Product", "Update & View Stock"])
    
    with tab1:
        st.subheader("Register New SKU")
        with st.form("new_prod"):
            name = st.text_input("Item Name")
            p_bal = st.number_input("Physical Balance", min_value=0)
            b_bal = st.number_input("Book Balance", min_value=0)
            if st.form_submit_button("Add Product"):
                try:
                    conn.execute("INSERT INTO products (name, physical_balance, book_balance) VALUES (?,?,?)", 
                                 (name, p_bal, b_bal))
                    conn.commit()
                    st.success(f"Product '{name}' registered successfully!")
                except sqlite3.IntegrityError:
                    st.error("This product name already exists (Duplicate SKU prevented).")

    with tab2:
        st.subheader("Current Inventory List")
        inventory = get_data("SELECT * FROM products")
        search = st.text_input("🔍 Search products...")
        if search:
            inventory = inventory[inventory['name'].str.contains(search, case=False)]
        st.dataframe(inventory, use_container_width=True)

        st.divider()
        st.subheader("Update Stock Levels")
        selected_item = st.selectbox("Select Product to Restock", inventory['name'].tolist())
        add_qty = st.number_input("Quantity to Add", min_value=1)
        
        if st.button("Update Balances"):
            conn.execute("""UPDATE products SET physical_balance = physical_balance + ?, 
                            book_balance = book_balance + ? WHERE name = ?""", (add_qty, add_qty, selected_item))
            # Log the restock
            prod_id = inventory[inventory['name'] == selected_item]['sku'].values[0]
            conn.execute("INSERT INTO restock_logs (sku, added_qty, timestamp) VALUES (?,?,?)",
                         (int(prod_id), add_qty, datetime.now()))
            conn.commit()
            st.rerun()

# --- 💰 SALES TERMINAL ---
elif choice == "💰 Sales Terminal":
    st.header("Point of Sale")
    
    # Load available products
    items = get_data("SELECT name, physical_balance, book_balance FROM products WHERE physical_balance > 0")
    
    if items.empty:
        st.error("No stock available in inventory!")
    else:
        with st.form("sale_form"):
            item_choice = st.selectbox("Select Item", items['name'].tolist())
            current_stock = items[items['name'] == item_choice]['physical_balance'].values[0]
            st.info(f"Available Stock: {current_stock}")
            
            qty = st.number_input("Quantity to Sell", min_value=1, max_value=int(current_stock))
            price = st.number_input("Unit Cost Price", min_value=0.0)
            
            if st.form_submit_button("Process Sale"):
                total = qty * price
                # 1. Update Product Table: Deduct Physical/Book, Increase "Not Yet Collected"
                conn.execute("""UPDATE products 
                                SET physical_balance = physical_balance - ?, 
                                    book_balance = book_balance - ?,
                                    not_yet_collected = not_yet_collected + ?
                                WHERE name = ?""", (qty, qty, qty, item_choice))
                
                # 2. Record the Sale
                conn.execute("""INSERT INTO sales (item_name, cost_price, quantity, total_price, timestamp) 
                                VALUES (?,?,?,?,?)""", 
                             (item_choice, price, qty, total, datetime.now()))
                
                conn.commit()
                st.success(f"Sale Complete! Total: ${total:,.2f}")
                st.balloons()
