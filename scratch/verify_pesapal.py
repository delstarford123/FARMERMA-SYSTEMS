import sys
import os
import requests

sys.path.append(r'c:\FARMERMAN_SYSTEMS')

PESAPAL_CONSUMER_KEY = "21cMLGoP4OuajH2wRJDqnT6P8uOAKcAJ"
PESAPAL_CONSUMER_SECRET = "azy0ubCURwiWYAFH7wbxZiks3dA="

def test_auth_endpoint(url_name, base_url):
    print(f"Testing authentication against {url_name} endpoint ({base_url})...")
    api_url = f"{base_url}/api/Auth/RequestToken"
    payload = {
        "consumer_key": PESAPAL_CONSUMER_KEY,
        "consumer_secret": PESAPAL_CONSUMER_SECRET
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=15)
        res_data = r.json()
        if r.status_code == 200 and (res_data.get('status') == '200' or 'token' in res_data):
            print(f"  [SUCCESS] Authenticated! Token: {res_data.get('token')[:20]}...")
            return True
        else:
            print(f"  [FAILED] Response code {r.status_code}, response: {res_data}")
            return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def main():
    # Test Sandbox BQA
    sandbox_ok = test_auth_endpoint("Sandbox (BQA)", "https://cybqa.pesapal.com/pesapalv3")
    
    # Test Production Live
    production_ok = test_auth_endpoint("Production (Live)", "https://pay.pesapal.com/v3")
    
    if sandbox_ok or production_ok:
        print("\nCREDENTIALS ARE WORKING!")
    else:
        print("\nAUTHENTICATION FAILED ON BOTH ENDPOINTS.")

if __name__ == "__main__":
    main()
