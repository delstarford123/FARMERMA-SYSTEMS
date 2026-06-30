from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize the database instance
db = SQLAlchemy()

# ==========================================
# 1. USER & SUBSCRIBER MODEL
# ==========================================
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Professional Profile
    organization = db.Column(db.String(150), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True) # Crucial for M-Pesa
    
    # Access & Permissions
    role = db.Column(db.String(20), default='client') # 'client' or 'admin'
    
    # Subscription Details
    subscription_tier = db.Column(db.String(50), default='free') # 'smallholder', 'pro', 'enterprise'
    subscription_status = db.Column(db.String(20), default='inactive') # 'active', 'pending', 'expired'
    subscription_expiry = db.Column(db.DateTime, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships (Links a user to their transactions and posted data)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    market_data_posted = db.relationship('MarketData', backref='admin', lazy=True)
    subscriptions = db.relationship('Subscription', backref='user', lazy=True)

    def __repr__(self):
        return f"<User {self.email} - {self.subscription_tier}>"

# ==========================================
# 2. LIVE MARKET DATA MODEL
# ==========================================
class MarketData(db.Model):
    __tablename__ = 'market_data'

    id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(100), nullable=False) # e.g., "Maize (90kg)"
    region = db.Column(db.String(100), nullable=False)    # e.g., "Rift Valley"
    
    # Pricing
    price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='KES')
    trend = db.Column(db.String(20), default='stable')    # 'up', 'down', 'stable'
    
    # Metadata
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Which admin posted this data? (Foreign Key)
    posted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f"<MarketData {self.commodity} in {self.region}: {self.price} {self.currency}>"

# ==========================================
# 3. TRANSACTION & BILLING MODEL
# ==========================================
class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    
    # Which user made this payment? (Foreign Key)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Payment Details
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    payment_method = db.Column(db.String(50), nullable=False) # 'mpesa', 'stripe', 'paypal', 'bank'
    transaction_reference = db.Column(db.String(100), unique=True, nullable=True) # e.g., M-Pesa receipt number
    
    # Status
    status = db.Column(db.String(20), default='pending') # 'success', 'pending', 'failed'
    description = db.Column(db.String(200), nullable=True) # e.g., "Agribusiness Pro - Monthly"
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Transaction {self.transaction_reference} - {self.status}>"

# ==========================================
# 4. SUBSCRIPTION TRACKING MODEL
# ==========================================
class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Package Info
    package_tier = db.Column(db.String(50), nullable=False) # 'seed', 'growth', 'harvest'
    
    # Status
    status = db.Column(db.String(20), default='pending') # 'active', 'expired', 'pending'
    
    # Timeline
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=True)
    
    # Auto-Renew / Reminder Tracking
    reminder_sent = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Subscription {self.package_tier} for User {self.user_id} - {self.status}>"