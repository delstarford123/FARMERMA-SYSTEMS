import os
import json
import stripe
import requests
import firebase_admin
import base64
from datetime import datetime
from functools import wraps 
from firebase_admin import credentials, auth, db as rtdb
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash

# 1. Internal Project Imports
from models import db, User, MarketData, Transaction 
from ai_logic.ai_engine import generate_price_forecast
from mpesa import initiate_stk_push

app = Flask(__name__)
app.secret_key = 'delstarford_works_secret_key' 

# ==========================================
# DATABASE & FIREBASE CONFIGURATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmerman.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

try:
    render_path = '/etc/secrets/serviceAccountKey.json'
    local_path = 'serviceAccountKey.json'
    cert_path = render_path if os.path.exists(render_path) else local_path

    cred = credentials.Certificate(cert_path)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://farmerman-systems-default-rtdb.firebaseio.com/'
    })
    print(f"Firebase securely initialized using: {cert_path}")
except Exception as e:
    print(f"Firebase Initialization Error: {e}")

with app.app_context():
    db.create_all()

# ==========================================
# PAYMENT API CONFIGURATION
# ==========================================
stripe.api_key = 'sk_test_your_stripe_secret_key_here'
MPESA_CONSUMER_KEY = 'your_consumer_key'
MPESA_CONSUMER_SECRET = 'your_consumer_secret'
MPESA_SHORTCODE = '174379'

# ==========================================
# CONTEXT PROCESSORS (Fixed UndefinedError)
# ==========================================
@app.context_processor
def inject_site_content():
    def get_site_content(page_id):
        try:
            content_ref = rtdb.reference(f'site_content/{page_id}')
            return content_ref.get()
        except Exception:
            return None
    return dict(get_site_content=get_site_content)

# ==========================================
# SECURITY DECORATORS (Fixed NameError)
# ==========================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("Access Denied: Administrator privileges required.")
            return redirect(url_for('client_login'))
        return f(*args, **kwargs)
    return decorated_function

def subscriber_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access premium AI tools.")
            return redirect(url_for('client_login'))
        if session.get('subscription_tier') != 'pro' and session.get('role') != 'admin':
            flash("Premium Feature: Please upgrade to Agribusiness Pro.")
            return redirect(url_for('pricing_subscription'))
        return f(*args, **kwargs)
    return decorated_function

def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token: return jsonify({"error": "Token missing"}), 401
        try:
            if token.startswith("Bearer "): token = token.split(" ")[1]
            request.user = auth.verify_id_token(token)
        except Exception: return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function

def token_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token: return jsonify({"error": "Token missing"}), 401
        try:
            if token.startswith("Bearer "): token = token.split(" ")[1]
            decoded_token = auth.verify_id_token(token)
            uid = decoded_token['uid']
            user_data = rtdb.reference(f'users/{uid}').get()
            if not user_data or user_data.get('role') != 'admin':
                return jsonify({"error": "Admin required"}), 403
            request.uid = uid
        except Exception: return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# AUTHENTICATION LOGIC (WEB)
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('fullName')
        try:
            user = auth.create_user(email=email, password=password, display_name=full_name)
            rtdb.reference(f'users/{user.uid}').set({
                'full_name': full_name, 'email': email, 'role': 'client', 
                'subscription_tier': 'free', 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            session.update({'user_id': user.uid, 'user_email': email, 'role': 'client'})
            flash("Account created!")
            return redirect(url_for('subscriber_checkout'))
        except Exception as e: flash(f"Error: {str(e)}")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def client_login():
    if request.method == 'POST':
        email = request.form.get('email')
        try:
            user = auth.get_user_by_email(email)
            profile = rtdb.reference(f'users/{user.uid}').get() or {}
            session.update({
                'user_id': user.uid, 'user_email': user.email,
                'role': profile.get('role', 'client'),
                'subscription_tier': profile.get('subscription_tier', 'free')
            })
            flash(f"Logged in as {session['role'].upper()}")
            return redirect(url_for('admin_dashboard' if session['role'] == 'admin' else 'dashboard'))
        except Exception: flash("Invalid credentials.")
    return render_template('client login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ==========================================
# CLIENT DASHBOARD & BILLING
# ==========================================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('client_login'))
    profile = rtdb.reference(f'users/{session["user_id"]}').get()
    return render_template('dashboard.html', profile=profile)

@app.route('/billing')
def billing(): 
    if 'user_id' not in session: return redirect(url_for('client_login'))
    uid = session['user_id']
    profile = rtdb.reference(f'users/{uid}').get() or {}
    txns = rtdb.reference(f'completed_transactions/{uid}').get()
    txn_list = sorted(txns.values(), key=lambda x: x.get('date', ''), reverse=True) if txns else []
    return render_template('billing.html', profile=profile, transactions=txn_list)
@app.route('/market-intelligence')
def market_intelligence():
    """
    Main portal for Market Intelligence. 
    Displays the overview of available AI tools, price trackers, 
    and links to live market data.
    """
    try:
        # We can pass specific featured data to the landing page if needed
        market_ref = rtdb.reference('market_data')
        # Fetching a snapshot of the top 3 items to show as a preview
        featured_items = market_ref.order_by_key().limit_to_last(3).get()
        
        preview_list = []
        if featured_items:
            preview_list = [{'id': k, **v} for k, v in featured_items.items()]
            preview_list.reverse()

        return render_template('market intelligence.html', preview=preview_list)
        
    except Exception as e:
        print(f"Market Portal Error: {e}")
        # Fallback to the basic template if Firebase fetch fails
        return render_template('market intelligence.html', preview=[])
@app.route('/checkout')
def subscriber_checkout():
    if 'user_id' not in session: return redirect(url_for('register'))
    return render_template('subscriber checkout.html')

@app.route('/settings')
def account_settings(): 
    """
    Displays the user's profile and subscription details.
    Passes the 'profile' variable to the template to fix the UndefinedError.
    """
    # 1. Check if user is logged in
    if 'user_id' not in session:
        flash("Please log in to access your settings.")
        return redirect(url_for('client_login'))
    
    try:
        # 2. Fetch the user's current profile from Firebase RTDB
        uid = session['user_id']
        user_ref = rtdb.reference(f'users/{uid}')
        profile_data = user_ref.get()
        
        # 3. Handle cases where the profile might be missing in RTDB
        if not profile_data:
            profile_data = {'full_name': 'User', 'email': session.get('user_email', '')}

        # 4. Pass the 'profile' variable to the template
        return render_template('accounts&subscription settings.html', profile=profile_data)

    except Exception as e:
        print(f"Settings Error: {e}")
        flash("Error loading profile data.")
        return redirect(url_for('dashboard'))
    

# ==========================================
# MARKET INTELLIGENCE & AI
# ==========================================
@app.route('/live-market-prices')
def live_market_prices():
    items = MarketData.query.order_by(MarketData.commodity.asc()).all()
    return render_template('live market prices.html', market_items=items)

@app.route('/trends-forecasts')
def trends_forecasts():
    records = MarketData.query.filter_by(commodity="Maize (90kg)").all()
    hist = [{'date': r.updated_at, 'price': r.price} for r in records]
    labels = [r.updated_at.strftime('%b %d') for r in records]
    prices = [r.price for r in records]
    ai = generate_price_forecast(hist, 5) if len(hist) >= 5 else {}
    if ai and "error" not in ai:
        labels.extend(ai['future_dates']); prices.extend(ai['predicted_prices'])
    return render_template('trends&forecasts.html', labels=labels, prices=prices, ai_insight=ai)

# ==========================================
# ADMIN MANAGEMENT (Fixed AssertionError)
# ==========================================
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard(): 
    users = rtdb.reference('users').get() or {}
    market = rtdb.reference('market_data').get() or {}
    txns = rtdb.reference('completed_transactions').get() or {}
    rev = 0.0; recent = []
    for uid, u_txns in txns.items():
        u_info = users.get(uid, {})
        for t in u_txns.values():
            rev += float(t.get('amount', 0))
            recent.append({'name': u_info.get('full_name', 'User'), 'date': t.get('date', ''), 'plan': t.get('plan', 'Pro')})
    recent.sort(key=lambda x: x['date'], reverse=True)
    return render_template('admin dashboard.html', total_subscribers=len(users), active_feeds=len(market), total_revenue=rev, recent_transactions=recent[:5])

@app.route('/admin/data-manager', methods=['GET', 'POST'])
@admin_required
def market_data_manager():
    if request.method == 'POST':
        rtdb.reference('market_data').push({
            "commodity": request.form.get('commodity'), "region": request.form.get('region'),
            "price": float(request.form.get('price')), "currency": request.form.get('currency', 'KES'),
            "trend": request.form.get('trend'), "updated_at": {".sv": "timestamp"}
        })
        flash("Market data published!")
    items = rtdb.reference('market_data').get() or {}
    market_list = [{'id': k, **v} for k, v in items.items()]
    return render_template('market data manager.html', market_items=reversed(market_list))

@app.route('/admin/delete-market-data/<item_id>', methods=['POST'])
@admin_required
def delete_market_data(item_id):
    try: rtdb.reference(f'market_data/{item_id}').delete(); flash("Removed.")
    except Exception: flash("Error.")
    return redirect(url_for('market_data_manager'))
@app.route('/admin/content', methods=['GET', 'POST'])
@admin_required
def content_manager():
    """
    CMS Controller: Allows admins to update site content (Home, About, Impact)
    and logs the history of changes in Firebase.
    """
    cms_ref = rtdb.reference('site_content')
    history_ref = rtdb.reference('content_history')

    if request.method == 'POST':
        page_id = request.form.get('page_selection')
        title = request.form.get('content_title')
        body = request.form.get('body_text')

        # 1. Update the actual site content in RTDB
        cms_ref.child(page_id).set({
            'title': title,
            'body': body,
            'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # 2. Log this edit in the history ledger
        history_ref.push({
            'page': page_id,
            'summary': f"Updated {title[:20]}...",
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        flash(f"Content for '{page_id}' successfully synchronized to live servers.", "success")
        return redirect(url_for('content_manager'))

    # GET logic: Fetch the 5 most recent edits for the history table
    recent_edits = history_ref.order_by_key().limit_to_last(5).get()
    edits_list = []
    if recent_edits:
        edits_list = list(recent_edits.values())
        edits_list.reverse() # Show newest first

    return render_template('content manager.html', recent_edits=edits_list)

@app.route('/admin/subscribers')
@admin_required
def subscriber_management():
    """
    Fetches all registered users from Firebase RTDB and displays them 
    in the Subscriber Management dashboard for administrative review.
    """
    try:
        # 1. Reference the 'users' node in Firebase
        users_ref = rtdb.reference('users')
        all_users = users_ref.get()
        
        subscribers_list = []
        
        # 2. Transform the Firebase dictionary into a list for the HTML table
        if all_users:
            for uid, data in all_users.items():
                # Inject the UID into the dictionary so we can use it for updates/deletes
                data['uid'] = uid
                subscribers_list.append(data)
        
        # 3. Render the template with the list of subscribers
        return render_template('subscriber management.html', subscribers=subscribers_list)
        
    except Exception as e:
        print(f"Admin Error: {e}")
        flash("Could not load the subscribers list. Please check your Firebase connection.", "danger")
        return redirect(url_for('admin_dashboard'))


# ==========================================
# MOBILE API
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def api_market_prices():
    items = rtdb.reference('market_data').get() or {}
    return jsonify([{'id': k, **v} for k, v in items.items()]), 200

# ==========================================
# PAYMENTS & CALLBACKS
# ==========================================
@app.route('/process-mpesa', methods=['POST'])
def process_mpesa():
    phone = request.form.get('phone_number')
    res = initiate_stk_push(phone, 1)
    if res.get('ResponseCode') == '0':
        rtdb.reference(f'pending_transactions/{res.get("CheckoutRequestID")}').set({
            'user_id': session['user_id'], 'amount': 1, 'status': 'pending'
        })
        flash("Check your phone!"); return redirect(url_for('payment_success'))
    flash("Error initiating M-Pesa."); return redirect(url_for('subscriber_checkout'))

@app.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    data = request.json
    stk = data.get('Body', {}).get('stkCallback', {})
    if stk.get('ResultCode') == 0:
        meta = stk.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((i['Value'] for i in meta if i['Name'] == 'MpesaReceiptNumber'), 'UNKNOWN')
        pending = rtdb.reference(f'pending_transactions/{stk.get("CheckoutRequestID")}').get()
        if pending:
            uid = pending.get('user_id')
            rtdb.reference(f'users/{uid}').update({'subscription_tier': 'pro'})
            rtdb.reference(f'completed_transactions/{uid}').push({
                'receipt_number': receipt, 'amount': pending.get('amount'),
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'plan': 'Pro Monthly'
            })
            rtdb.reference(f'pending_transactions/{stk.get("CheckoutRequestID")}').delete()
    return jsonify({"ResultCode": 0}), 200

@app.route('/success')
def payment_success():
    return render_template('success.html')

# ==========================================
# STATIC ROUTES
# ==========================================
@app.route('/')
def home(): return render_template('home.html')

@app.route('/about')
def about_us(): return render_template('about us.html')

@app.route('/impact')
def impact_initiatives(): return render_template('impact&initiatives.html')

@app.route('/pricing')
def pricing_subscription(): return render_template('pricing.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact_us(): 
    if request.method == 'POST':
        rtdb.reference('contact_inquiries').push({
            'name': request.form.get('name'), 'email': request.form.get('email'),
            'message': request.form.get('message'), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash("Message sent!"); return redirect(url_for('contact_us'))
    return render_template('contact us.html')

@app.route('/services')
def services(): return render_template('our services.html')

@app.route('/privacy-policy')
def privacy_policy(): return render_template('privacy policy.html')

@app.route('/terms-of-service')
def terms_of_service(): return render_template('terms of service.html')

@app.route('/refund-policy')
def refund_policy(): return render_template('subscription&refund policy.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)