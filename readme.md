#  Farmerman Systems 

**Pan-African Agribusiness Intelligence & AI Crop Diagnostics Platform**

Farmerman Systems is a comprehensive digital ecosystem designed to bridge the gap between agricultural biotechnology and machine learning. Developed under **Delstarford Works**, this platform empowers farmers, researchers, and agribusinesses with real-time market intelligence, predictive agronomy, and cutting-edge AI diagnostics.

## Core Architecture & Features

### UKULIMA SAFI AI Diagnostics Engine
* **Memory-Optimized Inference:** Utilizes a custom TensorFlow Lite (`.tflite`) neural network to analyze crop pathology directly in server RAM, ensuring zero disk I/O latency and enhanced security.
* **Integrated Agronomy Advisory:** Maps AI-detected anomalies to localized treatment protocols and disease advisory datasets.
* **Interactive UI:** Features high-end GSAP (GreenSock) animations for a seamless, futuristic "scanning" user experience.

###  Market Intelligence & Forecasting
* **Live Data Terminals:** Real-time tracking of agricultural commodities across multiple regions.
* **Predictive Analytics:** Python-driven historical data analysis to forecast price trends, giving farmers a strategic market advantage.

###  Automated SaaS Billing Architecture
* **Safaricom M-Pesa Integration:** Fully automated Daraja API integration utilizing STK Push and asynchronous Server-to-Server (S2S) webhooks.
* **Instant Provisioning:** Successful transactions automatically upgrade user accounts to the `Agribusiness Pro` tier within the Firebase Realtime Database.

# Secure Role-Based Access Control (RBAC)
* **Custom Flask Decorators:** Built with strict `@admin_required` and `@subscriber_required` routing to protect premium AI endpoints and administrative command centers.
* **Firebase Authentication:** Secure, token-based user credential management.

##  Technology Stack

* **Frontend:** HTML5, Bootstrap 5.3, GSAP 3.12, Canvas-Confetti
* **Backend:** Python 3, Flask, Werkzeug
* **AI / Machine Learning:** TensorFlow, Pillow (PIL), NumPy
* **Database:** Firebase Realtime Database (NoSQL), SQLite (SQLAlchemy)
* **Payment Gateway:** Safaricom Daraja API (M-Pesa)

## Local Development Setup

To run this project locally, you will need Python installed on your machine.

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/delstarford123/FARMERMA-SYSTEMS.git](https://github.com/delstarford123/FARMERMA-SYSTEMS.git)
   cd "FARMERMAN SYSTEMS"