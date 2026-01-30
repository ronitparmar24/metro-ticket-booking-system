"""
Utility Functions Module
"""

import hashlib
from datetime import datetime, date
from typing import Optional

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify if plain password matches hashed password"""
    return hash_password(plain_password) == hashed_password

def format_date(date_obj: Optional[date]) -> Optional[str]:
    """Format date object to string (YYYY-MM-DD)"""
    if date_obj is None:
        return None
    if isinstance(date_obj, datetime):
        return date_obj.strftime('%Y-%m-%d')
    return str(date_obj)

def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime object to string"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)

def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default: int = 0) -> int:
    """Safely convert value to int"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# Test the module
if __name__ == "__main__":
    # Test password hashing
    password = "mypassword123"
    hashed = hash_password(password)
    print(f"Original: {password}")
    print(f"Hashed: {hashed}")
    print(f"Verification: {verify_password(password, hashed)}")
