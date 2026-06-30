from datetime import datetime, timedelta

def generate_price_forecast(historical_data, days_to_predict=7):
    """
    Takes historical commodity data and predicts future prices using simple linear regression (pure Python).
    
    :param historical_data: List of dictionaries [{'date': datetime, 'price': float}]
    :param days_to_predict: Number of future days to forecast
    :return: Dictionary containing future dates and predicted prices
    """
    if len(historical_data) < 5:
        return {"error": "Insufficient historical data for AI forecasting."}
        
    # Sort data by date
    sorted_data = sorted(historical_data, key=lambda x: x['date'])
    
    # Calculate days since start
    base_date = sorted_data[0]['date']
    if isinstance(base_date, str):
        try:
            base_date = datetime.strptime(base_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            base_date = datetime.strptime(base_date, "%Y-%m-%d")
    
    # Extract x (days since start) and y (price)
    x = []
    y = []
    for item in sorted_data:
        dt = item['date']
        if isinstance(dt, str):
            try:
                dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.strptime(dt, "%Y-%m-%d")
        
        days = (dt - base_date).days
        x.append(days)
        y.append(float(item['price']))
        
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(val_x * val_y for val_x, val_y in zip(x, y))
    sum_xx = sum(val_x * val_x for val_x in x)
    
    denominator = (n * sum_xx - sum_x * sum_x)
    if denominator == 0:
        # Fallback: simple average if all dates/prices are identical
        m = 0.0
        c = sum_y / n
    else:
        m = (n * sum_xy - sum_x * sum_y) / denominator
        c = (sum_y - m * sum_x) / n
        
    # Predict future prices
    last_date = sorted_data[-1]['date']
    if isinstance(last_date, str):
        try:
            last_date = datetime.strptime(last_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_date = datetime.strptime(last_date, "%Y-%m-%d")
            
    last_day_num = x[-1]
    
    future_dates = []
    predicted_prices = []
    for i in range(1, days_to_predict + 1):
        future_day = last_day_num + i
        predicted_price = m * future_day + c
        # Ensure prices don't drop below zero
        if predicted_price < 0:
            predicted_price = 0.0
        predicted_prices.append(round(predicted_price, 2))
        
        future_date = (last_date + timedelta(days=i)).strftime('%Y-%m-%d')
        future_dates.append(future_date)
        
    # Determine trend
    trend_direction = "up" if predicted_prices[-1] > y[-1] else "down"
    
    return {
        "future_dates": future_dates,
        "predicted_prices": predicted_prices,
        "trend_direction": trend_direction
    }