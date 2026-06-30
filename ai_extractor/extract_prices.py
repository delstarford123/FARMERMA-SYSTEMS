import os
import sys
import re
import json
import uuid
from datetime import datetime, timezone, timedelta
import pandas as pd
try:
    import fitz
except ImportError:
    fitz = None

# Calculate absolute paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)

# Add the parent directory (Flask app root) to Python PATH
sys.path.append(PARENT_DIR)

# Change working directory so main.py finds serviceAccountKey.json
os.chdir(PARENT_DIR)

# Import Flask context and database models
from main import app, sqlalchemy_db, rtdb
from models import MarketData, User

UPLOADS_DIR = os.path.join(SCRIPT_DIR, 'uploads')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')

def extract_price_value(price_str):
    """Extracts the first numeric value from a string (e.g. '$30-55' -> 30.0)"""
    match = re.search(r'\$?(\d+(\.\d+)?)', price_str)
    if match:
        return float(match.group(1))
    return 0.0

def process_file(file_path):
    if file_path.lower().endswith('.pdf') and fitz:
        doc = fitz.open(file_path)
        lines = []
        for page in doc:
            lines.extend(page.get_text("text").split('\n'))
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
    market_records = []
    current_market = "General Market"
    current_region = "Zimbabwe"
    current_category = "General"
    extracted_date = None
    
    for line in lines:
        line = line.strip()
        
        # Extract date from strings like "Mass Market Grapevine 17 June 2026"
        date_match = re.search(r'(\d{1,2}\s+[a-zA-Z]+\s+202\d)', line)
        if date_match and not extracted_date:
            extracted_date = date_match.group(1)
            
        # Skip empty lines, page numbers, or generic footers
        if not line or line.isdigit() or "Mass Market Grapevine" in line:
            continue
            
        # Detect MARKET headings (e.g., "LUSAKA MARKET – HIGHFIELD")
        if "MARKET" in line.upper() and ("–" in line or "-" in line):
            parts = re.split(r'[-–]', line)
            current_market = parts[0].strip().title()
            if len(parts) > 1:
                current_region = parts[1].strip().title()
            continue
            
        # Detect Categories (Uppercase, no $, short length)
        if line.isupper() and "$" not in line and len(line) < 30 and not any(char.isdigit() for char in line):
            current_category = line.title()
            continue
            
        # Detect Items with Prices
        # E.g. "Tomatoes $30-$55" or "Cabbage 50c"
        match = re.search(r'^([^$]+)(\$.*|.*c/.*)$', line)
        if match:
            item_name = match.group(1).strip().strip(":")
            price_info = match.group(2).strip()
            
            if not item_name.startswith("N.B"):
                market_records.append({
                    "region": current_region,
                    "market": current_market,
                    "category": current_category,
                    "commodity": item_name,
                    "price_raw": price_info,
                    "price_val": extract_price_value(price_info),
                    "extracted_date": extracted_date
                })
    
    return market_records

def export_and_insert(all_records):
    # 1. Export to Excel using Pandas
    df = pd.DataFrame(all_records)
    excel_path = os.path.join(RESULTS_DIR, "market_prices.xlsx")
    df.to_excel(excel_path, index=False)
    print(f"✅ Excel Export Successful: {excel_path}")
    
    # 1.5. Export to beautifully formatted JSON for easy reading
    json_path = os.path.join(RESULTS_DIR, "market_prices.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, indent=4)
    print(f"✅ JSON/Text Export Successful: {json_path}")
    
    # 2. Fetch existing market data for trend calculation
    history_map = {}
    try:
        existing_data = rtdb.reference('market_data').get() or {}
        for k, v in existing_data.items():
            key = (v.get('commodity', ''), v.get('market', ''))
            history_map[key] = float(v.get('price', 0))
    except Exception as e:
        print(f"⚠️ Could not fetch history for trends: {e}")
        
    # 3. Insert to SQLAlchemy and Firebase (Zimbot)
    with app.app_context():
        # Find an Admin User to act as the publisher
        admin_user = User.query.filter_by(role='admin').first()
        if not admin_user:
            admin_user = User.query.first() # Fallback to any user
            
        if not admin_user:
            print("⚠️ No users found in database. Please register a user first. Skipping database insertion.")
            return
            
        inserted_count = 0
        for rec in all_records:
            new_price = rec['price_val']
            
            # Trend calculation
            hist_key = (rec['commodity'], rec['market'])
            old_price = history_map.get(hist_key)
            if old_price is None or old_price == 0:
                trend_val = 'stable'
            elif new_price > old_price:
                trend_val = 'up'
            elif new_price < old_price:
                trend_val = 'down'
            else:
                trend_val = 'stable'
                
            # Date extraction fallback
            if rec.get('extracted_date'):
                try:
                    dt = datetime.strptime(rec['extracted_date'], "%d %B %Y")
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    timestamp = rec['extracted_date']
            else:
                timestamp = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S")
        
            # A) Insert into Local SQLite (SQLAlchemy)
            new_data = MarketData(
                commodity=rec['commodity'],
                region=f"{rec['market']} - {rec['region']}",
                price=new_price,
                currency='USD',
                trend=trend_val,
                posted_by=admin_user.id
            )
            sqlalchemy_db.session.add(new_data)
            
            # B) Push to Firebase Realtime Database for Zimbot
            safe_node_name = re.sub(r'[^a-zA-Z0-9]', '_', rec['commodity'].lower())
            market_node = f"{safe_node_name}_{uuid.uuid4().hex[:6]}"
            
            rtdb.reference(f"market_data/{market_node}").set({
                "commodity": rec['commodity'],
                "category": rec['category'],
                "market": rec['market'],
                "region": rec['region'],
                "price": new_price,
                "currency": "USD",
                "unit": rec['price_raw'],
                "trend": trend_val,
                "country": "Zimbabwe",
                "updated_at": timestamp
            })
            inserted_count += 1
            
        # Commit SQLite transactions
        sqlalchemy_db.session.commit()
        print(f"✅ Successfully inserted {inserted_count} records into the Database and Zimbot (Firebase).")

def main():
    if not os.path.exists(UPLOADS_DIR): os.makedirs(UPLOADS_DIR)
    if not os.path.exists(RESULTS_DIR): os.makedirs(RESULTS_DIR)
    
    all_records = []
    # Read text files
    for filename in os.listdir(UPLOADS_DIR):
        if filename.lower().endswith(".txt") or filename.lower().endswith(".pdf"):
            file_path = os.path.join(UPLOADS_DIR, filename)
            print(f"Processing {filename}...")
            records = process_file(file_path)
            all_records.extend(records)
            
    if all_records:
        export_and_insert(all_records)
    else:
        print("No records extracted. Please ensure your uploads folder has valid market .txt files.")

if __name__ == "__main__":
    print("Starting Advanced Market Extractor Pipeline...")
    main()
