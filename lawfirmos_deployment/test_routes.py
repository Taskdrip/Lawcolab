"""
Test script to verify routes are working
"""
import requests

def test_routes():
    base_url = "http://localhost:5000"
    routes_to_test = ["/", "/about", "/contact", "/landing", "/auth/login", "/auth/signup"]
    
    print("Testing routes...")
    for route in routes_to_test:
        try:
            response = requests.get(f"{base_url}{route}", allow_redirects=False)
            print(f"{route}: Status {response.status_code}")
            if response.status_code in [301, 302, 303, 307, 308]:
                print(f"  -> Redirects to: {response.headers.get('Location', 'Unknown')}")
        except Exception as e:
            print(f"{route}: ERROR - {e}")
    
if __name__ == "__main__":
    test_routes()