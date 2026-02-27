
# ==========================================
# MOBILE API: ADMIN HUB
# ==========================================
@app.route('/api/admin/subscribers', methods=['GET'])
@token_admin_required
def api_admin_subscribers():
    """Returns a JSON list of all users for the Flutter Admin Hub."""
    try:
        all_users = rtdb.reference('users').get()
        # Convert Firebase dictionary into a list and inject the UID into each record
        subscribers_list = [{'uid': uid, **data} for uid, data in all_users.items()] if all_users else []
        return jsonify(subscribers_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/update-user', methods=['POST'])
@token_admin_required
def api_admin_update_user():
    """Allows the Flutter Admin Hub to change a user's role or tier."""
    data = request.json
    uid = data.get('uid')
    new_role = data.get('role')
    new_tier = data.get('subscription_tier')
    
    if not uid or not new_role or not new_tier:
        return jsonify({"error": "Missing parameters"}), 400
        
    try:
        # Update the exact user in the Realtime Database
        rtdb.reference(f'users/{uid}').update({
            'role': new_role,
            'subscription_tier': new_tier
        })
        return jsonify({"success": True, "message": "User permissions synchronized."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# MOBILE API: CONTENT MANAGER
# ==========================================
@app.route('/api/admin/content-history', methods=['GET'])
@token_admin_required
def api_admin_content_history():
    """Returns a JSON list of recent website content edits."""
    try:
        history_ref = rtdb.reference('content_history')
        # Fetch the 20 most recent edits
        recent_edits = history_ref.order_by_key().limit_to_last(20).get()
        
        if recent_edits:
            edits_list = list(recent_edits.values())
            edits_list.reverse() # Put the newest edits at the top
            return jsonify(edits_list), 200
            
        return jsonify([]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/content', methods=['POST'])
@token_admin_required
def api_admin_update_content():
    """Allows the Flutter app to publish new text to the website."""
    data = request.json
    page_id = data.get('page_id')
    title = data.get('title')
    body = data.get('body')
    
    if not page_id or not title or not body:
        return jsonify({"error": "Missing page_id, title, or body"}), 400
        
    try:
        # 1. Update the live site content
        rtdb.reference(f'site_content/{page_id}').set({
            'title': title,
            'body': body,
            'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # 2. Add an entry to the history ledger
        rtdb.reference('content_history').push({
            'page': page_id,
            'summary': f"Updated {title[:20]}...",
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        return jsonify({"success": True, "message": "Content published"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==========================================
# MOBILE API: MARKET DATA MANAGER
# ==========================================
@app.route('/api/admin/data-manager', methods=['POST'])
@token_admin_required
def api_admin_add_market_data():
    """Allows the Flutter app to publish new market prices."""
    data = request.json
    commodity = data.get('commodity')
    region = data.get('region')
    price = data.get('price')
    
    if not commodity or not region or price is None:
        return jsonify({"error": "Missing commodity, region, or price"}), 400
        
    try:
        # Push the new record into the database with a server timestamp
        rtdb.reference('market_data').push({
            "commodity": commodity,
            "region": region,
            "price": float(price),
            "currency": data.get('currency', 'KES'),
            "trend": data.get('trend', 'stable'),
            "updated_at": {".sv": "timestamp"}
        })
        return jsonify({"success": True, "message": "Market data published"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/delete-market-data/<item_id>', methods=['DELETE'])
@token_admin_required
def api_admin_delete_market_data(item_id):
    """Allows the Flutter app to delete a market price entry."""
    try:
        # Target the specific ID and remove it
        rtdb.reference(f'market_data/{item_id}').delete()
        return jsonify({"success": True, "message": "Entry removed"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==========================================
# MOBILE API: BILLING & M-PESA
# ==========================================
@app.route('/api/process-mpesa', methods=['POST'])
@token_required
def api_process_mpesa():
    """Initiates an M-Pesa STK Push from the Flutter mobile app."""
    data = request.json
    phone = data.get('phone_number')
    amount = data.get('amount', 1)  # Defaulting to 1 for sandbox testing
    
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400
        
    try:
        # 1. Call your existing M-Pesa integration function
        res = initiate_stk_push(phone, amount)
        
        # 2. Check if Safaricom accepted the request
        if res.get('ResponseCode') == '0':
            checkout_request_id = res.get("CheckoutRequestID")
            
            # 3. Save the pending transaction using the secure UID from the token
            uid = request.user['uid'] 
            
            rtdb.reference(f'pending_transactions/{checkout_request_id}').set({
                'user_id': uid, 
                'amount': amount, 
                'status': 'pending',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            return jsonify({
                "success": True, 
                "message": "STK Push initiated successfully."
            }), 200
        else:
            # Safaricom rejected the request (e.g., invalid number)
            error_msg = res.get('errorMessage', 'Failed to initiate M-Pesa request.')
            return jsonify({"error": error_msg}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500






