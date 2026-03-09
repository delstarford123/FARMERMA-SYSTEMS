from datetime import datetime
from firebase_admin import db

def analyze_weather_and_generate_alerts(temp, humidity, wind_speed, condition, region):
    """
    Analyzes live weather data and generates actionable farming advice.
    Returns a list of alert dictionaries.
    """
    alerts = []
    # Format time nicely for the UI
    timestamp = datetime.now().strftime("%b %d, %H:%M")

    # RULE 1: Wind Speed (Spraying Safety)
    # Wind over 15 km/h causes chemical drift
    if wind_speed > 15:
        alerts.append({
            'title': 'High Wind Warning',
            'advice': f'Wind speeds are at {wind_speed} km/h. Strictly avoid spraying pesticides or foliar fertilizers to prevent chemical drift and waste.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })

    # RULE 2: Precipitation (Field Operations)
    if 'rain' in condition.lower() or 'drizzle' in condition.lower() or 'thunder' in condition.lower():
        alerts.append({
            'title': 'Precipitation Alert',
            'advice': 'Rain detected in your area. Halt chemical spraying. Ensure field drainage channels are clear to prevent crop waterlogging.',
            'alert_type': 'info',  # Maps to your success/info color in HTML
            'timestamp': timestamp,
            'region': region
        })

    # RULE 3: Fungal Risk (High Humidity + Warm Temps)
    # Fungi thrive in warm, highly moist environments
    if humidity >= 80 and temp >= 18:
        alerts.append({
            'title': 'High Fungal Disease Risk',
            'advice': f'High humidity ({humidity}%) and warm temperatures are highly favorable for fungal diseases like Blight and Rust. Scout crops closely.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })

    # RULE 4: Heat Stress (High Temp + Clear Sky)
    if temp >= 30 and 'clear' in condition.lower():
        alerts.append({
            'title': 'Heat Stress Watch',
            'advice': f'Temperatures reaching {temp}°C. Increase irrigation frequency for shallow-rooted vegetables and provide adequate shade/water for livestock.',
            'alert_type': 'warning',
            'timestamp': timestamp,
            'region': region
        })

    # RULE 5: Default Optimal Conditions
    if not alerts:
        alerts.append({
            'title': 'Optimal Farming Conditions',
            'advice': 'Current weather conditions are stable and favorable for standard field operations, including weeding, harvesting, and soil preparation.',
            'alert_type': 'success',
            'timestamp': timestamp,
            'region': region
        })

    return alerts
# In logic.py
def update_firebase_alerts(user_id, alerts):
    """
    Overwrites the old alerts for THIS SPECIFIC USER and pushes the newly generated ones.
    """
    if not user_id:
        return False
        
    # Target the specific user's private alert folder
    ref = db.reference(f'climate_alerts/{user_id}')
    
    # .set() replaces the whole node for this user instantly with the new list
    ref.set(alerts) 
        
    return True