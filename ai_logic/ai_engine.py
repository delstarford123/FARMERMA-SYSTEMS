import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import timedelta

def generate_price_forecast(historical_data, days_to_predict=7):
    """
    Takes historical commodity data and predicts future prices.
    
    :param historical_data: List of dictionaries [{'date': datetime, 'price': float}]
    :param days_to_predict: Number of future days to forecast
    :return: Dictionary containing future dates and predicted prices
    """
    # 1. Convert database records to a Pandas DataFrame
    df = pd.DataFrame(historical_data)
    
    # If there isn't enough data to train a model, return a fallback
    if len(df) < 5:
        return {"error": "Insufficient historical data for AI forecasting."}

    # 2. Feature Engineering
    # Convert dates to numerical values (e.g., days since the first record) for the ML model
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    base_date = df['date'].min()
    df['days_since_start'] = (df['date'] - base_date).dt.days

    X = df[['days_since_start']] # Features
    y = df['price']              # Target variable

    # 3. Train the AI Model (Random Forest is great for handling non-linear market trends)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 4. Generate Future Dates for Prediction
    last_date = df['date'].max()
    last_day_num = df['days_since_start'].max()
    
    future_days_num = np.array([[last_day_num + i] for i in range(1, days_to_predict + 1)])
    future_dates = [(last_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, days_to_predict + 1)]

    # 5. Make Predictions
    predicted_prices = model.predict(future_days_num)

    # 6. Format the output for the frontend Chart.js
    forecast_results = {
        "future_dates": future_dates,
        "predicted_prices": [round(price, 2) for price in predicted_prices],
        "trend_direction": "up" if predicted_prices[-1] > y.iloc[-1] else "down"
    }
    
    return forecast_results