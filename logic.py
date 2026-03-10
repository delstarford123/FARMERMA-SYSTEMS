from datetime import datetime
from firebase_admin import db

def analyze_weather_and_generate_alerts(temp, humidity, wind_speed, condition, region):
    """
    Advanced Agronomic Decision Engine.
    Cross-references weather parameters to generate highly specific, actionable farming advice.
    """
    alerts = []
    timestamp = datetime.now().strftime("%b %d, %H:%M")
    condition_lower = condition.lower()

    # ==========================================
    # 1. CRITICAL THREATS (Priority: Highest)
    # ==========================================
    
    # Frost & Freezing Risk
    if temp <= 4:
        alerts.append({
            'title': 'Frost Warning ',
            'advice': f'Temperatures have dropped to {temp}°C. Immediate risk of frost damage to sensitive crops. Deploy frost covers, use smudge pots, or run irrigation to protect blossoms.',
            'alert_type': 'danger', 
            'timestamp': timestamp,
            'region': region
        })
        
    # Severe Heat & Pollen Sterility
    elif temp >= 35:
        alerts.append({
            'title': 'Extreme Heat Stress ',
            'advice': f'Temperatures at {temp}°C can cause pollen sterility in maize and tomatoes. Halt all field labor for safety. Ensure emergency shading and ad-lib water for all livestock.',
            'alert_type': 'danger',
            'timestamp': timestamp,
            'region': region
        })

    # Structural & Crop Damage
    if wind_speed >= 30:
        alerts.append({
            'title': 'Gale Force Winds ',
            'advice': f'Winds at {wind_speed} km/h risk lodging (flattening) tall crops like maize and damaging greenhouses. Secure loose structures and drop greenhouse side-curtains.',
            'alert_type': 'danger',
            'timestamp': timestamp,
            'region': region
        })

    # ==========================================
    # 2. DISEASE & PEST VECTORS
    # ==========================================
    
    # Warm + High Humidity = Blight/Rot
    if humidity >= 85 and 20 <= temp <= 30:
        alerts.append({
            'title': 'High Fungal Disease Risk ',
            'advice': f'High humidity ({humidity}%) combined with {temp}°C heat creates the perfect incubator for Late Blight and Rust. Apply preventative fungicides and ensure greenhouse ventilation.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })
        
    # Cool + High Humidity = Mildew/Botrytis
    elif humidity >= 80 and 10 <= temp < 20:
        alerts.append({
            'title': 'Mildew & Botrytis Watch ',
            'advice': f'Cool, damp conditions ({temp}°C, {humidity}% RH) strongly favor Powdery Mildew and Gray Mold. Reduce overhead watering and prune lower leaves for airflow.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })
        
    # Hot + Dry = Spider Mites
    elif temp >= 28 and humidity < 40:
        alerts.append({
            'title': 'Pest Outbreak Alert ',
            'advice': f'Hot and dry conditions ({humidity}% RH) trigger rapid breeding of Spider Mites and Thrips. Scout undersides of leaves immediately and consider misting to raise localized humidity.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })

    # ==========================================
    # 3. FIELD OPERATIONS & SOIL MANAGEMENT
    # ==========================================
    
    # Spraying Safety (Chemical Drift)
    if 15 < wind_speed < 30:
        alerts.append({
            'title': 'Chemical Drift Hazard ',
            'advice': f'Wind speeds ({wind_speed} km/h) make spraying illegal and ineffective. Suspend all herbicide and foliar fertilizer applications until winds drop below 10 km/h.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })
        
    # Nutrient Leaching (Heavy Rain)
    if 'heavy' in condition_lower or 'thunder' in condition_lower or 'storm' in condition_lower:
        alerts.append({
            'title': 'Nutrient Leaching Risk ',
            'advice': 'Heavy rainfall detected. Do NOT apply soil fertilizers today as they will wash away. Check contour ridges and drainage trenches to prevent topsoil erosion.',
            'alert_type': 'danger',
            'timestamp': timestamp,
            'region': region
        })
    elif 'rain' in condition_lower or 'drizzle' in condition_lower:
        alerts.append({
            'title': 'Precipitation Noted ',
            'advice': 'Light to moderate rain. Great for natural irrigation. Suspend chemical spraying to prevent wash-off.',
            'alert_type': 'info',
            'timestamp': timestamp,
            'region': region
        })

    # ==========================================
    # 4. OPTIMAL WINDOWS (Green Alerts)
    # ==========================================
    
    # Perfect Spraying Window
    if wind_speed <= 10 and 15 <= temp <= 25 and 'rain' not in condition_lower and 'thunder' not in condition_lower:
        # Check if we already added a danger/warning alert to prevent conflicting advice
        if not any(a['alert_type'] in ['danger', 'warning'] for a in alerts):
            alerts.append({
                'title': 'Perfect Spraying Window ',
                'advice': f'Ideal conditions for field operations. Low wind ({wind_speed} km/h) and moderate temps ({temp}°C) ensure maximum chemical absorption with zero drift.',
                'alert_type': 'success',
                'timestamp': timestamp,
                'region': region
            })

    # Default fallback if nothing triggered
    if not alerts:
        alerts.append({
            'title': 'Stable Agronomic Conditions ',
            'advice': 'Weather parameters are within normal ranges. Proceed with standard daily crop management, harvesting, and livestock feeding schedules.',
            'alert_type': 'info',
            'timestamp': timestamp,
            'region': region
        })

    return alerts

def update_firebase_alerts(user_id, alerts):
    """
    Overwrites the old alerts for THIS SPECIFIC USER and pushes the newly generated ones.
    """
    if not user_id:
        return False
        
    try:
        # Target the specific user's private alert folder
        ref = db.reference(f'climate_alerts/{user_id}')
        
        # .set() replaces the whole node for this user instantly with the new list
        ref.set(alerts) 
        return True
    except Exception as e:
        print(f"Firebase Update Error: {e}")
        return False