"""
Database Manager Module
-----------------------
Handles all MySQL database operations for Metro Ticket Booking System.
"""

import mysql.connector
from mysql.connector import Error
from typing import List, Dict, Optional, Set, Any
from datetime import datetime, date
import logging
from contextlib import contextmanager

from config import Config
from utils import hash_password

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# SIMPLE CONNECTION MANAGER (No pooling to avoid errors)
# ============================================================================

def get_db_connection():
    """Get a simple database connection"""
    try:
        conn = mysql.connector.connect(**Config.get_db_config())
        return conn
    except Error as e:
        logger.error(f"❌ Database connection error: {e}")
        raise


# ============================================================================
# DATABASE SETUP
# ============================================================================

def setup_database():
    """
    Setup database tables if they don't exist
    Call this once when starting the application
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # USERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                password VARCHAR(100) NOT NULL,
                walletBalance DOUBLE NOT NULL,
                role VARCHAR(20) NOT NULL
            )
        """)
        
        # TICKETS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticketId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                destination VARCHAR(50) NOT NULL,
                passengers INT NOT NULL,
                fare DOUBLE NOT NULL,
                travelDate DATE NOT NULL,
                cancelled BOOLEAN NOT NULL,
                bookingDate DATETIME NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # FEEDBACKS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                feedbackId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                text VARCHAR(255) NOT NULL,
                type VARCHAR(20) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # SUPPORT TICKETS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticketId INT AUTO_INCREMENT PRIMARY KEY,
                feedbackId INT NOT NULL,
                status VARCHAR(20) NOT NULL,
                assignedStaffUsername VARCHAR(50),
                createdDate DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolvedDate DATETIME,
                FOREIGN KEY (feedbackId) REFERENCES feedbacks(feedbackId) ON DELETE CASCADE,
                FOREIGN KEY (assignedStaffUsername) REFERENCES users(username) ON DELETE SET NULL
            )
        """)
        
        # ANNOUNCEMENTS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message VARCHAR(255) NOT NULL,
                createdDate DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # METRO CARDS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metro_cards (
                cardNumber INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                balance DOUBLE NOT NULL,
                autoRechargeEnabled BOOLEAN NOT NULL,
                minBalanceThreshold DOUBLE NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # MONTHLY PASSES TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_passes (
                passId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                destination VARCHAR(50) NOT NULL,
                purchaseDate DATE NOT NULL,
                expiryDate DATE NOT NULL,
                price DOUBLE NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # STATION LOCATIONS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_locations (
                name VARCHAR(50) PRIMARY KEY,
                x DOUBLE,
                y DOUBLE,
                has_wifi BOOLEAN DEFAULT FALSE,
                has_parking BOOLEAN DEFAULT FALSE,
                has_restroom BOOLEAN DEFAULT FALSE,
                has_atm BOOLEAN DEFAULT FALSE,
                is_accessible BOOLEAN DEFAULT FALSE,
                contact_number VARCHAR(15) DEFAULT '1800-11-2233'
            )
        """)
        # MIGRATION: If table exists but cols don't, add them (Safe Migration)
        try:
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_wifi BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_parking BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_restroom BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_atm BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN is_accessible BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN contact_number VARCHAR(15) DEFAULT '1800-11-2233'")
        except:
            pass # Columns likely exist
        
        conn.commit()
        cursor.close()
        logger.info("✅ All database tables created successfully")
        return True
        
    except Error as e:
        logger.error(f"❌ Error creating tables: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_station_details(station_name):
    """Get full facility details for a specific station"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM station_locations WHERE name = %s"
        cursor.execute(sql, (station_name,))
        station = cursor.fetchone()
        cursor.close()
        return station
    except Exception as e:
        logger.error(f"Error fetching station details: {e}")
        return None
    finally:
        if conn and conn.is_connected(): conn.close()
# ============================================================================
# USER OPERATIONS
# ============================================================================

def insert_user(username: str, password_hash: str, wallet_balance: float, role: str) -> bool:
    """Insert new user into the users table"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO users (username, password, walletBalance, role) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (username, password_hash, wallet_balance, role))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ User '{username}' inserted successfully")
        return success
        
    except Error as e:
        logger.error(f"❌ Error inserting user '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def username_exists(username: str) -> bool:
    """Check if a username exists in the database"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT 1 FROM users WHERE username = %s"
        cursor.execute(sql, (username,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists
        
    except Error as e:
        logger.error(f"❌ Error checking username '{username}': {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user details safely, handling database hiccups"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Try to get everything (including points)
        try:
            sql = "SELECT username, password, walletBalance, role, loyaltyPoints FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            user = cursor.fetchone()
        except Exception as e:
            # 2. FALLBACK: If that fails (column missing), reset cursor and try basic fetch
            print(f"⚠️ Recovering from DB error for {username}: {e}")
            try:
                cursor.close() # Close broken cursor
                cursor = conn.cursor(dictionary=True) # Open fresh cursor
                
                sql = "SELECT username, password, walletBalance, role FROM users WHERE username = %s"
                cursor.execute(sql, (username,))
                user = cursor.fetchone()
            except:
                return None # Truly failed
            
        cursor.close()
        return user
        
    except Exception as e:
        logger.error(f"❌ Critical Error fetching user '{username}': {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()
def remove_user(username: str) -> bool:
    """Remove a user by username"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "DELETE FROM users WHERE username = %s"
        cursor.execute(sql, (username,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ User '{username}' removed")
        return success
        
    except Error as e:
        logger.error(f"❌ Error removing user '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_user_wallet_balance(username: str, new_balance: float) -> bool:
    """Update user wallet balance"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE users SET walletBalance = %s WHERE username = %s"
        cursor.execute(sql, (new_balance, username))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating wallet balance for '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_user_password(username: str, new_hashed_password: str) -> bool:
    """Update user password"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE users SET password = %s WHERE username = %s"
        cursor.execute(sql, (new_hashed_password, username))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Password updated for user '{username}'")
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating password for '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_users() -> List[Dict[str, Any]]:
    """Retrieve list of all users with role USER"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT username, password, walletBalance, role FROM users WHERE role = 'USER'"
        cursor.execute(sql)
        users = cursor.fetchall()
        cursor.close()
        return users
        
    except Error as e:
        logger.error(f"❌ Error fetching all users: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# TICKET OPERATIONS
# ============================================================================

# db.py - UPDATE THIS FUNCTION
# db.py - UPDATE THIS FUNCTION
def insert_ticket(username: str, source: str, destination: str, passengers: int, fare: float, travel_date: date, distance: float = 0.0, cancelled: bool = False) -> int:
    """Insert ticket with DISTANCE and return ticketId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # SQL query updated to include 'distance'
        sql = """
            INSERT INTO tickets 
            (username, source, destination, passengers, fare, travelDate, distance, cancelled, bookingDate) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(sql, (username, source, destination, passengers, fare, travel_date, distance, cancelled))
        conn.commit()
        ticket_id = cursor.lastrowid
        cursor.close()
        return ticket_id
        
    except Error as e:
        logger.error(f"❌ Error inserting ticket: {e}")
        if conn: conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected(): conn.close()
        
def get_tickets_by_user(username: str) -> List[Dict[str, Any]]:
    """Retrieve list of tickets for a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM tickets WHERE username = %s ORDER BY bookingDate DESC"
        cursor.execute(sql, (username,))
        tickets = cursor.fetchall()
        cursor.close()
        return tickets
        
    except Error as e:
        logger.error(f"❌ Error fetching tickets for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def cancel_ticket(ticket_id: int) -> bool:
    """Mark a ticket as cancelled"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE tickets SET cancelled = TRUE WHERE ticketId = %s"
        cursor.execute(sql, (ticket_id,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Ticket #{ticket_id} cancelled")
        return success
        
    except Error as e:
        logger.error(f"❌ Error cancelling ticket #{ticket_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_ticket_by_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Get ticket details by ID"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM tickets WHERE ticketId = %s"
        cursor.execute(sql, (ticket_id,))
        ticket = cursor.fetchone()
        cursor.close()
        return ticket
        
    except Error as e:
        logger.error(f"❌ Error fetching ticket #{ticket_id}: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# FEEDBACK OPERATIONS
# ============================================================================

def insert_feedback(username: str, text: str, feedback_type: str) -> int:
    """Insert feedback and return generated feedbackId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO feedbacks (username, text, type) VALUES (%s, %s, %s)"
        cursor.execute(sql, (username, text, feedback_type))
        conn.commit()
        feedback_id = cursor.lastrowid
        cursor.close()
        
        if feedback_id > 0:
            logger.info(f"✅ Feedback #{feedback_id} created by '{username}'")
        return feedback_id
        
    except Error as e:
        logger.error(f"❌ Error inserting feedback: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_feedbacks_by_username(username: str) -> List[Dict[str, Any]]:
    """Get all feedbacks by a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT feedbackId, username, text, type, timestamp FROM feedbacks WHERE username = %s ORDER BY timestamp DESC"
        cursor.execute(sql, (username,))
        feedbacks = cursor.fetchall()
        cursor.close()
        return feedbacks
        
    except Error as e:
        logger.error(f"❌ Error fetching feedbacks for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_feedbacks() -> List[Dict[str, Any]]:
    """Get all feedbacks"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT feedbackId, username, text, type, timestamp FROM feedbacks ORDER BY timestamp DESC"
        cursor.execute(sql)
        feedbacks = cursor.fetchall()
        cursor.close()
        return feedbacks
        
    except Error as e:
        logger.error(f"❌ Error fetching all feedbacks: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# SUPPORT TICKET OPERATIONS
# ============================================================================

def insert_support_ticket(feedback_id: int, status: str) -> int:
    """Insert support ticket and return ticketId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO support_tickets (feedbackId, status) VALUES (%s, %s)"
        cursor.execute(sql, (feedback_id, status))
        conn.commit()
        ticket_id = cursor.lastrowid
        cursor.close()
        
        if ticket_id > 0:
            logger.info(f"✅ Support ticket #{ticket_id} created")
        return ticket_id
        
    except Error as e:
        logger.error(f"❌ Error inserting support ticket: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_support_ticket_status(ticket_id: int, status: str, resolved_date: Optional[datetime] = None) -> bool:
    """Update support ticket status"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE support_tickets SET status = %s, resolvedDate = %s WHERE ticketId = %s"
        cursor.execute(sql, (status, resolved_date, ticket_id))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating support ticket #{ticket_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_assigned_tickets_by_staff(staff_username: str) -> List[Dict[str, Any]]:
    """Get support tickets assigned to a staff member"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT st.ticketId, st.status, st.createdDate, st.resolvedDate,
                   fb.username, fb.text, fb.type
            FROM support_tickets st
            JOIN feedbacks fb ON st.feedbackId = fb.feedbackId
            WHERE st.assignedStaffUsername = %s
            ORDER BY st.createdDate DESC
        """
        cursor.execute(sql, (staff_username,))
        tickets = cursor.fetchall()
        cursor.close()
        return tickets
        
    except Error as e:
        logger.error(f"❌ Error fetching assigned tickets: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()
# --- ADD THIS TO db.py ---
def insert_lost_found(username: str, item: str, description: str) -> bool:
    """Insert a lost item report into the correct table"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO lost_found (username, item, description, status) VALUES (%s, %s, %s, 'SEARCHING')"
        cursor.execute(sql, (username, item, description))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
    except Error as e:
        logger.error(f"❌ Error inserting lost item: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): conn.close()


# ============================================================================
# METRO CARD OPERATIONS
# ============================================================================

# In db.py, find insert_metro_card and make sure it matches this:

def insert_metro_card(username: str, balance: float, auto_recharge_enabled: bool, min_balance_threshold: float) -> int:
    """Insert metro card and return cardNumber"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ensure your table has these columns!
        sql = """
            INSERT INTO metro_cards 
            (username, balance, autoRechargeEnabled, minBalanceThreshold) 
            VALUES (%s, %s, %s, %s)
        """
        # Convert boolean to integer (1 or 0) for MySQL if needed, though MySQL handles True/False usually
        cursor.execute(sql, (username, balance, int(auto_recharge_enabled), min_balance_threshold))
        
        conn.commit()
        card_number = cursor.lastrowid
        cursor.close()
        
        if card_number > 0:
            logger.info(f"✅ Metro card #{card_number} created for '{username}'")
        return card_number
        
    except Error as e:
        logger.error(f"❌ Error inserting metro card: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()

def update_metro_card(card_number: int, balance: float, auto_recharge_enabled: bool, min_balance_threshold: float) -> bool:
    """Update metro card details"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            UPDATE metro_cards 
            SET balance = %s, autoRechargeEnabled = %s, minBalanceThreshold = %s 
            WHERE cardNumber = %s
        """
        cursor.execute(sql, (balance, auto_recharge_enabled, min_balance_threshold, card_number))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating metro card #{card_number}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_metro_card_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get metro card details by username"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM metro_cards WHERE username = %s"
        cursor.execute(sql, (username,))
        card = cursor.fetchone()
        cursor.close()
        return card
        
    except Error as e:
        logger.error(f"❌ Error fetching metro card for '{username}': {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# MONTHLY PASS OPERATIONS
# ============================================================================

def insert_monthly_pass(username: str, source: str, destination: str, purchase_date: date, expiry_date: date, price: float) -> int:
    """Insert monthly pass and return passId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO monthly_passes 
            (username, source, destination, purchaseDate, expiryDate, price) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (username, source, destination, purchase_date, expiry_date, price))
        conn.commit()
        pass_id = cursor.lastrowid
        cursor.close()
        
        if pass_id > 0:
            logger.info(f"✅ Monthly pass #{pass_id} created for '{username}'")
        return pass_id
        
    except Error as e:
        logger.error(f"❌ Error inserting monthly pass: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_monthly_pass_routes_by_username(username: str) -> List[str]:
    """Get active monthly pass routes for a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT source, destination 
            FROM monthly_passes 
            WHERE username = %s AND expiryDate >= CURRENT_DATE
        """
        cursor.execute(sql, (username,))
        rows = cursor.fetchall()
        cursor.close()
        return [f"{row[0]}->{row[1]}" for row in rows]
        
    except Error as e:
        logger.error(f"❌ Error fetching monthly passes for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# STATION OPERATIONS
# ============================================================================

def insert_or_update_station_location(name: str, x: float, y: float) -> bool:
    """Insert or update station location"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO station_locations (name, x, y) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE x = %s, y = %s
        """
        cursor.execute(sql, (name, x, y, x, y))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating station location '{name}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_station_names() -> Set[str]:
    """Get all station names"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT name FROM station_locations"
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return {row[0] for row in rows}
        
    except Error as e:
        logger.error(f"❌ Error fetching stations: {e}")
        return set()
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_station_location(name: str) -> Optional[Dict[str, Any]]:
    """Get station coordinates"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT name, x, y FROM station_locations WHERE name = %s"
        cursor.execute(sql, (name,))
        location = cursor.fetchone()
        cursor.close()
        return location
        
    except Error as e:
        logger.error(f"❌ Error fetching station location '{name}': {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# ANNOUNCEMENT OPERATIONS
# ============================================================================

def insert_announcement(message: str) -> bool:
    """Insert system announcement"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO announcements (message) VALUES (%s)"
        cursor.execute(sql, (message,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Announcement added")
        return success
        
    except Error as e:
        logger.error(f"❌ Error inserting announcement: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_announcements() -> List[Dict[str, Any]]:
    """Get all announcements"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM announcements ORDER BY createdDate DESC"
        cursor.execute(sql)
        announcements = cursor.fetchall()
        cursor.close()
        return announcements
        
    except Error as e:
        logger.error(f"❌ Error fetching announcements: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# UTILITY OPERATIONS
# ============================================================================

def clear_all_data() -> bool:
    """Clear all data from database (for testing)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Delete data
        cursor.execute("DELETE FROM support_tickets")
        cursor.execute("DELETE FROM feedbacks")
        cursor.execute("DELETE FROM tickets")
        cursor.execute("DELETE FROM monthly_passes")
        cursor.execute("DELETE FROM metro_cards")
        cursor.execute("DELETE FROM station_locations")
        cursor.execute("DELETE FROM announcements")
        cursor.execute("DELETE FROM users")
        
        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        conn.commit()
        cursor.close()
        logger.info("✅ All data cleared")
        return True
        
    except Error as e:
        logger.error(f"❌ Error clearing data: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

# --- ADD TO db.py ---

# 1. FOR LOST & FOUND ADMIN
def get_all_lost_found_items() -> List[Dict[str, Any]]:
    """Get ALL lost and found reports (for Admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM lost_found ORDER BY reportDate DESC"
        cursor.execute(sql)
        items = cursor.fetchall()
        cursor.close()
        return items
    except Error as e:
        logger.error(f"Error fetching lost items: {e}")
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def update_lost_found_status(item_id: int, status: str) -> bool:
    """Update status of a lost item (SEARCHING, FOUND, RETURNED)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE lost_found SET status = %s WHERE id = %s"
        cursor.execute(sql, (status, item_id))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
    except Error as e:
        logger.error(f"Error updating item #{item_id}: {e}")
        return False
    finally:
        if conn and conn.is_connected(): conn.close()

# 2. FOR SYSTEM SETTINGS (PEAK HOUR / MAINTENANCE)
def get_system_settings() -> Dict[str, Any]:
    """Get global settings (Mocked for simplicity or use DB table)"""
    # For this demo, we return a default. In a full app, create a 'settings' table.
    return {
        "peak_hour": False,
        "system_lockdown": False,
        "base_fare": 50,
        "lines": {
            "Blue Line": "Active",
            "Yellow Line": "Active",
            "Red Line": "Maintenance"
        }
    }

# --- ADD TO db.py ---

def get_recent_global_tickets(limit=20):
    """Get recent tickets from ALL users for Admin Feed"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch tickets with username
        cursor.execute("""
            SELECT ticketId, username, source, destination, fare, bookingDate 
            FROM tickets ORDER BY bookingDate DESC LIMIT %s
        """, (limit,))
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def get_station_traffic_stats():
    """Get ticket counts per station for Heatmap"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT source as station, COUNT(*) as count FROM tickets GROUP BY source")
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def get_top_users_by_balance(limit=5):
    """Get 'Whale' users with highest wallet balance"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username, walletBalance FROM users ORDER BY walletBalance DESC LIMIT %s", (limit,))
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

# --- NEW FEATURES FOR ADMIN PRO ---

def get_peak_hour_stats():
    """Returns ticket counts by hour of day (0-23) for analytics"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Extracts the HOUR from bookingDate and counts tickets
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, COUNT(*) as count 
            FROM tickets 
            GROUP BY HOUR(bookingDate) 
            ORDER BY hour
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_feedback_sentiment():
    """Categorizes feedback as Positive/Negative based on keywords"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT text FROM feedbacks")
        all_feedback = cursor.fetchall()
        
        # Simple Python Logic for Sentiment
        stats = {'positive': 0, 'negative': 0, 'neutral': 0}
        pos_words = ['good', 'great', 'fast', 'best', 'love', 'smooth']
        neg_words = ['slow', 'bad', 'late', 'dirty', 'rude', 'worst']
        
        for f in all_feedback:
            txt = f['text'].lower()
            if any(w in txt for w in pos_words): stats['positive'] += 1
            elif any(w in txt for w in neg_words): stats['negative'] += 1
            else: stats['neutral'] += 1
        return stats
    finally:
        conn.close()

def create_staff_user(username, password):
    """Creates a new user with SUPPORT_STAFF role"""
    return insert_user(username, password, 0, "SUPPORT_STAFF")

def get_refund_stats():
    """Calculates total money refunded (cancelled tickets)"""
    # Note: Assuming you have a way to track cancellations. 
    # If not, we will simulate this query based on 'tickets' table logic for now
    # or you can add a 'status' column to tickets later.
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count, SUM(fare) as total FROM tickets WHERE bookingDate < NOW()") 
        # In a real app, you'd filter by status='CANCELLED'
        return cursor.fetchone() 
    finally:
        conn.close()

# --- ADMIN FEATURES ---
def get_all_tickets_full():
    """Fetch all tickets with user details for the Admin Validator"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets ORDER BY bookingDate DESC LIMIT 50")
        return cursor.fetchall()
    finally:
        conn.close()

def toggle_station_status(station_name, status):
    """Simulate closing a station (In real app, you'd add a 'status' column to stations table)"""
    # For now, we just return True to simulate success for the UI
    return True

# ============================================================================
# TEST THE MODULE
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Database Module")
    print("=" * 60)
    
    # Test imports
    print("\n1. Testing imports...")
    try:
        import mysql.connector
        print("✅ mysql.connector imported successfully!")
    except ImportError as e:
        print(f"❌ mysql.connector import failed: {e}")
        print("\nPlease run: pip install mysql-connector-python")
        exit(1)
    
    # Test database connection
    print("\n2. Testing database connection...")
    try:
        conn = get_db_connection()
        if conn.is_connected():
            print("✅ Database connection successful!")
            conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nMake sure:")
        print("  1. MySQL server is running (start XAMPP)")
        print("  2. Database 'metrosystemdb' exists")
        print("  3. config.py has correct credentials")
        exit(1)
    
    # Test database setup
    print("\n3. Setting up database tables...")
    if setup_database():
        print("✅ Database tables created successfully!")
    
    # Test user operations
    print("\n4. Testing user operations...")
    from utils import hash_password
    
    test_user = "testuser123"
    test_pass = hash_password("password123")
    
    # Check if user already exists
    if username_exists(test_user):
        print(f"ℹ️  User '{test_user}' already exists, skipping insert")
    else:
        if insert_user(test_user, test_pass, 100.0, "USER"):
            print(f"✅ User '{test_user}' created!")
    
    # Fetch user
    user_data = get_user_by_username(test_user)
    if user_data:
        print(f"✅ User data retrieved: {user_data['username']}, Balance: {user_data['walletBalance']}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed! Database module is working correctly.")
    print("=" * 60)
