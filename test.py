"""
Quick Test Script - Run this to check if everything works
"""

print("=" * 60)
print("METRO BACKEND TESTING")
print("=" * 60)

# Test 1: Import config
print("\n1. Testing config.py...")
try:
    from config import Config
    print("   ✅ config.py imported successfully!")
    print(f"   Database: {Config.DB_CONFIG['database']}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 2: Import utils
print("\n2. Testing utils.py...")
try:
    from utils import hash_password, verify_password
    test_hash = hash_password("test123")
    print("   ✅ utils.py imported successfully!")
    print(f"   Sample hash: {test_hash[:20]}...")
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 3: Import ds
print("\n3. Testing ds.py...")
try:
    from ds import Queue, MetroDataStore
    q = Queue()
    q.enqueue("test")
    print("   ✅ ds.py imported successfully!")
    print(f"   Queue test: {q.dequeue()}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 4: Import and test db
print("\n4. Testing db.py...")
try:
    import db
    print("   ✅ db.py imported successfully!")
    
    # Test connection
    print("\n5. Testing database connection...")
    conn = db.get_db_connection()
    if conn.is_connected():
        print("   ✅ Database connection successful!")
        conn.close()
    else:
        print("   ❌ Cannot connect to database")
        exit(1)
    
    # Test setup
    print("\n6. Setting up database tables...")
    if db.setup_database():
        print("   ✅ All tables created successfully!")
    
    # Test user operations
    print("\n7. Testing user operations...")
    test_username = "quicktest123"
    
    if not db.username_exists(test_username):
        if db.insert_user(test_username, hash_password("pass123"), 50.0, "USER"):
            print(f"   ✅ User '{test_username}' created!")
    else:
        print(f"   ℹ️  User '{test_username}' already exists")
    
    user = db.get_user_by_username(test_username)
    if user:
        print(f"   ✅ User retrieved: {user['username']} (Balance: Rs.{user['walletBalance']})")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED! Your setup is working correctly!")
print("=" * 60)
print("\nNext steps:")
print("  1. You can now create models.py")
print("  2. Then create app.py (Flask API)")
print("  3. Finally create HTML/CSS frontend")
