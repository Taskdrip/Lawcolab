#!/usr/bin/env python3
"""
Debug script to test route accessibility
"""

import requests

def test_redirect_issue():
    base_url = "http://localhost:5000"
    
    # Test with session to simulate browser behavior
    session = requests.Session()
    
    print("=== Testing Routes with Session ===")
    
    for route in ["/about", "/contact"]:
        print(f"\n--- Testing {route} ---")
        try:
            # Follow redirects and track them
            response = session.get(f"{base_url}{route}", allow_redirects=True)
            print(f"Final Status: {response.status_code}")
            print(f"Final URL: {response.url}")
            print(f"Response Length: {len(response.content)} bytes")
            
            # Check if content contains expected elements
            content = response.text
            if route == "/about":
                if "About LawFirm" in content:
                    print("✓ About page content found")
                else:
                    print("✗ About page content missing")
                    if "Welcome back" in content:
                        print("! Found authenticated user welcome message")
                    if "Professional Legal Practice Management" in content:
                        print("! Found homepage content instead")
            elif route == "/contact":
                if "Contact Taskdrip" in content:
                    print("✓ Contact page content found")
                else:
                    print("✗ Contact page content missing")
                    if "Welcome back" in content:
                        print("! Found authenticated user welcome message")
                    if "Professional Legal Practice Management" in content:
                        print("! Found homepage content instead")
                        
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_redirect_issue()