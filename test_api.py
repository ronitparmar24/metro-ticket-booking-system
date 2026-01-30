"""
Simple API Test Script
Test all Flask API endpoints
"""

import requests
import json

# Base URL
BASE_URL = "http://localhost:5000"

def print_result(test_name, response):
    """Print test result"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.json()

def test_api():
    """Run all API tests"""
    print("🧪 Metro API Testing")
    print("="*60)
    
    # Create a session to maintain cookies (for login)
    session = requests.Session()
    
    # Test 1: Health Check
    print("\n1️⃣  Testing Health Check...")
    response = session.get(f"{BASE_URL}/api/health")
    print_result("Health Check", response)
    
    # Test 2: Register a new user
    print("\n2️⃣  Testing User Registration...")
    register_data = {
        "username": "apitest123",
        "password": "password123"
    }
    response = session.post(f"{BASE_URL}/api/register", json=register_data)
    result = print_result("User Registration", response)
    
    if response.status_code == 400 and "already exists" in result.get('error', ''):
        print("ℹ️  User already exists, continuing with login...")
    
    # Test 3: Login
    print("\n3️⃣  Testing User Login...")
    login_data = {
        "username": "apitest123",
        "password": "password123"
    }
    response = session.post(f"{BASE_URL}/api/login", json=login_data)
    result = print_result("User Login", response)
    
    if response.status_code != 200:
        print("❌ Login failed! Cannot continue tests.")
        return
    
    # Test 4: Get current user
    print("\n4️⃣  Testing Get Current User...")
    response = session.get(f"{BASE_URL}/api/me")
    print_result("Get Current User", response)
    
    # Test 5: Recharge Wallet
    print("\n5️⃣  Testing Wallet Recharge...")
    recharge_data = {"amount": 500.0}
    response = session.post(f"{BASE_URL}/api/user/wallet/recharge", json=recharge_data)
    result = print_result("Wallet Recharge", response)
    
    if response.status_code == 200:
        print(f"✅ New Balance: Rs. {result.get('newBalance', 0):.2f}")
    
    # Test 6: Get Wallet Balance
    print("\n6️⃣  Testing Get Wallet Balance...")
    response = session.get(f"{BASE_URL}/api/user/wallet/balance")
    result = print_result("Get Wallet Balance", response)
    
    # Test 7: Get All Stations
    print("\n7️⃣  Testing Get All Stations...")
    response = session.get(f"{BASE_URL}/api/stations")
    result = print_result("Get All Stations", response)
    
    # Test 8: Book a Ticket
    print("\n8️⃣  Testing Ticket Booking...")
    book_data = {
        "source": "connaught_place",
        "destination": "rajiv_chowk",
        "passengers": 2,
        "travelDate": "2026-01-15"
    }
    response = session.post(f"{BASE_URL}/api/tickets/book", json=book_data)
    result = print_result("Book Ticket", response)
    
    ticket_id = None
    if response.status_code == 201:
        ticket_id = result['ticket']['ticketId']
        print(f"✅ Ticket booked! ID: {ticket_id}")
    
    # Test 9: View My Tickets
    print("\n9️⃣  Testing View My Tickets...")
    response = session.get(f"{BASE_URL}/api/tickets/my-tickets")
    result = print_result("View My Tickets", response)
    
    # Test 10: Submit Feedback
    print("\n🔟 Testing Submit Feedback...")
    feedback_data = {
        "text": "Great service!",
        "type": "feedback"
    }
    response = session.post(f"{BASE_URL}/api/feedback/submit", json=feedback_data)
    print_result("Submit Feedback", response)
    
    # Test 11: Get MetroCard Details
    print("\n1️⃣1️⃣  Testing Get MetroCard Details...")
    response = session.get(f"{BASE_URL}/api/metrocard/details")
    print_result("Get MetroCard Details", response)
    
    # Test 12: Cancel Ticket (if we booked one)
    if ticket_id:
        print(f"\n1️⃣2️⃣  Testing Cancel Ticket (ID: {ticket_id})...")
        response = session.post(f"{BASE_URL}/api/tickets/cancel/{ticket_id}")
        result = print_result("Cancel Ticket", response)
        
        if response.status_code == 200:
            print(f"✅ Refund: Rs. {result.get('refund', 0):.2f}")
    
    # Test 13: Logout
    print("\n1️⃣3️⃣  Testing Logout...")
    response = session.post(f"{BASE_URL}/api/logout")
    print_result("Logout", response)
    
    print("\n" + "="*60)
    print("✅ ALL API TESTS COMPLETED!")
    print("="*60)

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to Flask server!")
        print("Make sure Flask server is running:")
        print("  python app.py")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
