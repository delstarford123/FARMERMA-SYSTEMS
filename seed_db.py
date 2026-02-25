import pandas as pd
from datetime import datetime
from main import app, db
from models import MarketData, User  # <-- This is the crucial fix!

def load_csv_to_db(filepath):
    # Read the CSV using the newly installed pandas library
    df = pd.read_csv(filepath)
    
    with app.app_context():
        # Check if we have an admin user to attach the data to
        admin = User.query.first()
        if not admin:
            # Create a dummy admin if one doesn't exist
            admin = User(full_name="System Admin", email="admin@farmermansystems.com", password_hash="dummy")
            db.session.add(admin)
            db.session.commit()

        # Loop through the CSV and create database records
        for index, row in df.iterrows():
            date_obj = datetime.strptime(row['date'], '%Y-%m-%d')
            
            # Create a new MarketData record
            new_data = MarketData(
                commodity=row['commodity'],
                region=row['region'],
                price=row['price'],
                currency=row['currency'],
                updated_at=date_obj,
                posted_by=admin.id
            )
            db.session.add(new_data)
        
        # Save all records to the database
        db.session.commit()
        print(f"Successfully loaded {len(df)} records from {filepath} into the database!")

if __name__ == "__main__":
    # Ensure your database tables exist
    with app.app_context():
        db.create_all()
        
    # Load both CSV files
    load_csv_to_db('data/maize_prices.csv')
    load_csv_to_db('data/beans_prices.csv')