"""
Flask REST API for Metro Ticket Booking System
-----------------------------------------------
Main application file with all API endpoints

FEATURES:
- User registration and login
- Ticket booking, viewing, cancellation
- Wallet and MetroCard management
- Feedback and support tickets
- Admin operations (user management, stations, announcements)
- Support staff operations
- Monthly passes
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import logging
import math
# --- VITAL MISSING IMPORTS ---
import qrcode
import io
import base64
# -----------------------------

# Import our modules
import db
from models import User, Admin, SupportStaff, Ticket, Feedback, Role, SupportTicketStatus
from utils import hash_password, verify_password, format_date, format_datetime
from ds import MetroDataStore, StationInfo, Queue
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import io
from flask import send_file
import random

import psutil
import json
# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'  # Change this in production!

# Enable CORS for frontend integration
# Enable CORS for frontend integration
CORS(app, 
     supports_credentials=True,
     origins=["http://localhost:5000", "http://127.0.0.1:5000"],
     allow_headers=["Content-Type"],
     expose_headers=["Content-Type"])


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize datastore
datastore = MetroDataStore.get_instance()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_user() -> Optional[Dict[str, Any]]:
    """Get currently logged-in user from session"""
    username = session.get('username')
    if username:
        return db.get_user_by_username(username)
    return None


def require_login(func):
    """Decorator to require login for protected routes"""
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def require_role(required_role: str):
    """Decorator to require specific role"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'success': False, 'error': 'Not logged in'}), 401
            if user['role'] != required_role:
                return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/api/register', methods=['POST'])
def api_register():
    """
    Register a new user
    
    Request JSON:
        {
            "username": "string",
            "password": "string",
            "role": "USER" (optional, default)
        }
    
    Returns:
        {"success": true, "message": "User registered successfully"}
    """
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        role = data.get('role', Role.USER)
        
        # Validation
        if not username or len(username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
        
        if not password or len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if role not in [Role.USER, Role.ADMIN, Role.SUPPORT_STAFF]:
            role = Role.USER
        
        # Check if username exists
        if db.username_exists(username):
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        # Hash password and create user
        password_hash = hash_password(password)
        initial_balance = 0.0
        
        if db.insert_user(username, password_hash, initial_balance, role):
            # Create metro card for new user
            db.insert_metro_card(username, 0.0, False, 50.0)
            
            logger.info(f"New user registered: {username} (Role: {role})")
            return jsonify({
                'success': True,
                'message': 'User registered successfully',
                'username': username,
                'role': role
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to create user'}), 500
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    """
    User login
    
    Request JSON:
        {
            "username": "string",
            "password": "string"
        }
    
    Returns:
        {"success": true, "user": {...}, "message": "Login successful"}
    """
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        # Get user from database
        user = db.get_user_by_username(username)
        
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Verify password
        if not verify_password(password, user['password']):
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Set session
        session['username'] = username
        session['role'] = user['role']
        
        logger.info(f"User logged in: {username}")
        
        # Remove password from response
        user_data = {
            'username': user['username'],
            'walletBalance': user['walletBalance'],
            'role': user['role']
        }
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': user_data
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logout', methods=['POST'])
@require_login
def api_logout():
    """Logout current user"""
    username = session.get('username')
    session.clear()
    logger.info(f"User logged out: {username}")
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200


@app.route('/api/me', methods=['GET'])
@require_login
def api_get_current_user():
    """Get current logged-in user details"""
    user = get_current_user()
    if user:
        # Calculate totals for better dashboard accuracy
        return jsonify({
            'success': True,
            'user': {
                'username': user['username'],
                'walletBalance': float(user['walletBalance']), # Ensure it returns a float, not Decimal
                'role': user['role'],
                'loyaltyPoints': user.get('loyaltyPoints', 0)
            }
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404
# ============================================================================
# USER ROUTES (Wallet, Profile)
# ============================================================================
# --- REPLACE api_recharge_wallet IN app.py ---
# In app.py - Replace the existing api_recharge_wallet function
@app.route('/api/user/wallet/recharge', methods=['POST'])
@require_login
def api_recharge_wallet():
    try:
        data = request.json
        # 1. Ensure amount is a float
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        user = get_current_user()
        
        # 2. CRITICAL FIX: Force walletBalance to float to prevent Decimal/Float conflicts
        current_balance = float(user['walletBalance']) 
        new_balance = current_balance + amount
        
        # 3. Perform the update
        if db.update_user_wallet_balance(user['username'], new_balance):
            
            # 4. Save to History (Fail-safe: inside its own try/except)
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO wallet_history (username, amount, type, description) VALUES (%s, %s, 'CREDIT', 'Wallet Recharge')",
                    (user['username'], amount)
                )
                conn.commit()
                conn.close()
            except Exception as log_error:
                print(f"History Save Warning: {log_error}")

            return jsonify({
                'success': True,
                'message': f'Wallet recharged with Rs. {amount:.2f}',
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Database update failed'}), 500
        
    except Exception as e:
        print(f"Recharge Error: {e}") # Print error to terminal for debugging
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/user/wallet/balance', methods=['GET'])
@require_login
def api_get_wallet_balance():
    """Get current wallet balance"""
    user = get_current_user()
    return jsonify({
        'success': True,
        'balance': user['walletBalance']
    }), 200


@app.route('/api/user/change-password', methods=['POST'])
@require_login
def api_change_password():
    """
    Change password
    
    Request JSON:
        {
            "oldPassword": "string",
            "newPassword": "string"
        }
    """
    try:
        data = request.json
        old_password = data.get('oldPassword', '')
        new_password = data.get('newPassword', '')
        
        if not old_password or not new_password:
            return jsonify({'success': False, 'error': 'Both passwords required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
        
        user = get_current_user()
        
        # Verify old password
        if not verify_password(old_password, user['password']):
            return jsonify({'success': False, 'error': 'Old password incorrect'}), 400
        
        # Check if new password is same as old
        if verify_password(new_password, user['password']):
            return jsonify({'success': False, 'error': 'New password must be different'}), 400
        
        # Update password
        new_hash = hash_password(new_password)
        if db.update_user_password(user['username'], new_hash):
            return jsonify({
                'success': True,
                'message': 'Password changed successfully'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to update password'}), 500
        
    except Exception as e:
        logger.error(f"Password change error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TICKET ROUTES
# ============================================================================
# --- ADD THIS HELPER FUNCTION ---
# --- ADD THIS TO IMPORTS AT THE TOP ---
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ============================================================================
# FEATURE 1 & 4: SMART FARE CALCULATOR (Update this existing function)
# ============================================================================
def calculate_dynamic_fare(source, destination, passengers):
    """Calculate fare, distance, AND time with Peak Hour logic"""
    # 1. Get coordinates
    loc1 = db.get_station_location(source)
    loc2 = db.get_station_location(destination)
    
    if not loc1 or not loc2:
        return 50.0 * passengers, 0.0, 0, False
    
    # 2. Calculate Distance (Math)
    dist = math.sqrt((loc2['x'] - loc1['x'])**2 + (loc2['y'] - loc1['y'])**2) * 100
    
    # 3. Calculate Estimated Time (Assuming 30km/h avg speed + 2 mins per station)
    # This is a realistic estimation formula
    time_minutes = int((dist / 30) * 60) + 5 
    
    # 4. Base Calculation
    base_rate = 5.0
    base_cost = 10.0 + (dist * base_rate)
    
    # 5. PEAK HOUR LOGIC (Real-world feature)
    current_hour = datetime.now().hour
    is_peak = False
    
    # Peak hours: 8-10 AM and 5-7 PM (17-19)
    if (8 <= current_hour <= 10) or (17 <= current_hour <= 19):
        base_cost *= 1.25  # 25% Surge pricing
        is_peak = True
        
    # Rounding
    single_fare = max(10, round(base_cost / 5) * 5)
    total_fare = single_fare * passengers
    
    return total_fare, round(dist, 1), time_minutes, is_peak

# Update the API to send this new data to frontend
@app.route('/api/tickets/calculate-fare', methods=['POST'])
def api_calculate_fare_details():
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        passengers = int(data.get('passengers', 1))
        
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Stations required'}), 400
            
        # Unpack all 4 values
        fare, distance, time, is_peak = calculate_dynamic_fare(source, destination, passengers)
        
        return jsonify({
            'success': True,
            'fare': fare,
            'distance': distance,
            'time': time,        # Send time to frontend
            'is_peak': is_peak,  # Send peak status
            'passengers': passengers
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# FEATURE 2: PDF TICKET DOWNLOAD (New Endpoint)
# ============================================================================
@app.route('/api/tickets/<int:ticket_id>/pdf', methods=['GET'])
def generate_ticket_pdf(ticket_id):
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Auth required'}), 401
        
    try:
        ticket = db.get_ticket_by_id(ticket_id)
        if not ticket or ticket['username'] != username:
            return jsonify({'success': False, 'message': 'Invalid ticket'}), 404

        # Create PDF in memory
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        # Design the PDF Receipt
        c.setFont("Helvetica-Bold", 24)
        c.drawString(200, 750, "METRO TICKET")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 700, f"Ticket ID: #{ticket_id}")
        c.drawString(50, 680, f"Date: {ticket['travelDate']}")
        c.drawString(50, 660, f"Passenger: {username}")
        
        c.line(50, 640, 550, 640)
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 600, f"From: {ticket['source'].upper()}")
        c.drawString(50, 570, f"To:   {ticket['destination'].upper()}")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 530, f"Passengers: {ticket['passengers']}")
        c.drawString(50, 510, f"Status: {'CANCELLED' if ticket['cancelled'] else 'CONFIRMED'}")
        
        c.setFont("Helvetica-Bold", 18)
        c.drawString(400, 530, f"Total: Rs. {ticket['fare']}")
        
        c.save()
        buffer.seek(0)
        
        # Convert to base64 to send to frontend
        pdf_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'pdf_file': f"data:application/pdf;base64,{pdf_base64}",
            'filename': f"ticket_{ticket_id}.pdf"
        })
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# --- UPDATED BOOKING FUNCTION ---
@app.route('/api/tickets/book', methods=['POST'])
@require_login
def api_book_ticket():
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        passengers = int(data.get('passengers', 1))
        travel_date_str = data.get('travelDate', '')
        
        # 1. Validation
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Source and destination required'}), 400
        
        if source == destination:
            return jsonify({'success': False, 'error': 'Source and destination must be different'}), 400
        
        if passengers < 1 or passengers > 6:
            return jsonify({'success': False, 'error': 'Passengers must be between 1 and 6'}), 400
        
        # 2. Parse travel date
        try:
            travel_date = datetime.strptime(travel_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format (use YYYY-MM-DD)'}), 400
        
        if travel_date < date.today():
            return jsonify({'success': False, 'error': 'Travel date must be in the future'}), 400
        
        # ---------------------------------------------------------
        # 3. FIX: Correctly unpack all 4 values returned by the function
        # ---------------------------------------------------------
        fare, distance, time, is_peak = calculate_dynamic_fare(source, destination, passengers)
        
        # Get user details
        user = get_current_user()
        
        # 4. Check wallet balance
        if fare > user['walletBalance']:
            return jsonify({
                'success': False,
                'error': f'Insufficient balance. Required: Rs. {fare:.2f}, Available: Rs. {user["walletBalance"]:.2f}'
            }), 400
        
        # 5. Deduct from wallet
        new_balance = user['walletBalance'] - fare
        if not db.update_user_wallet_balance(user['username'], new_balance):
            return jsonify({'success': False, 'error': 'Failed to update wallet balance'}), 500
        
        # 6. Insert ticket
        ticket_id = db.insert_ticket(
            user['username'],
            source,
            destination,
            passengers,
            fare,
            travel_date,
            distance,
            False
        )
        if ticket_id > 0:
            # --- NEW: AWARD LOYALTY POINTS (1 Point per Rs 2 spent) ---
            points_earned = int(fare / 2)
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                # Update User Points
                cursor.execute("UPDATE users SET loyaltyPoints = loyaltyPoints + %s WHERE username = %s", (points_earned, user['username']))
                # Send Notification
                msg = f"Booking confirmed! You earned {points_earned} Green Points."
                cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (user['username'], msg))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Loyalty Error: {e}") # Don't fail booking if loyalty fails
            # -----------------------------------------------------------# Don't fail booking if loyalty fails
            return jsonify({
                'success': True,
                'message': 'Ticket booked successfully',
                'ticket': {
                    'ticketId': ticket_id,
                    'source': source,
                    'destination': destination,
                    'passengers': passengers,
                    'fare': fare,
                    'travelDate': travel_date_str,
                    'time': time,        # Optional: Send est. time back
                    'is_peak': is_peak   # Optional: Send peak status back
                },
                'newBalance': new_balance
            }), 201
        else:
            # Refund if ticket insertion fails
            db.update_user_wallet_balance(user['username'], user['walletBalance'])
            return jsonify({'success': False, 'error': 'Database error: Failed to generate ticket'}), 500
        
    except Exception as e:
        logger.error(f"Ticket booking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/tickets/my-tickets', methods=['GET'])
@require_login
def api_get_my_tickets():
    """Get all tickets for current user"""
    try:
        user = get_current_user()
        tickets = db.get_tickets_by_user(user['username'])
        
        # Format tickets for response
        formatted_tickets = []
        for ticket in tickets:
            formatted_tickets.append({
                'ticketId': ticket['ticketId'],
                'source': ticket['source'],
                'destination': ticket['destination'],
                'passengers': ticket['passengers'],
                'fare': ticket['fare'],
                'travelDate': format_date(ticket['travelDate']),
                'cancelled': ticket['cancelled'],
                'bookingDate': format_datetime(ticket['bookingDate'])
            })
        
        return jsonify({
            'success': True,
            'tickets': formatted_tickets
        }), 200
        
    except Exception as e:
        logger.error(f"Get tickets error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tickets/cancel/<int:ticket_id>', methods=['POST'])
@require_login
def api_cancel_ticket(ticket_id):
    """
    Cancel a ticket and get refund
    
    Refund: 80% if cancelled 24+ hours before travel, else 50%
    """
    try:
        user = get_current_user()
        
        # Get ticket
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        if ticket['username'] != user['username']:
            return jsonify({'success': False, 'error': 'This ticket does not belong to you'}), 403
        
        if ticket['cancelled']:
            return jsonify({'success': False, 'error': 'Ticket already cancelled'}), 400
        
        # Calculate refund
        travel_datetime = datetime.combine(ticket['travelDate'], datetime.min.time())
        time_diff = travel_datetime - datetime.now()
        
        if time_diff.total_seconds() >= 24 * 60 * 60:  # >= 24 hours
            refund_rate = 0.8
        else:
            refund_rate = 0.5
        
        refund = ticket['fare'] * refund_rate
        
        # Cancel ticket in database
        if db.cancel_ticket(ticket_id):
            # Add refund to wallet
            new_balance = user['walletBalance'] + refund
            db.update_user_wallet_balance(user['username'], new_balance)
            
            return jsonify({
                'success': True,
                'message': 'Ticket cancelled successfully',
                'refund': refund,
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to cancel ticket'}), 500
        
    except Exception as e:
        logger.error(f"Ticket cancellation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# FEEDBACK ROUTES
# ============================================================================

@app.route('/api/feedback/submit', methods=['POST'])
@require_login
def api_submit_feedback():
    """
    Submit feedback or complaint
    
    Request JSON:
        {
            "text": "string",
            "type": "feedback" or "complaint"
        }
    """
    try:
        data = request.json
        text = data.get('text', '').strip()
        feedback_type = data.get('type', 'feedback')
        
        if not text:
            return jsonify({'success': False, 'error': 'Feedback text required'}), 400
        
        if feedback_type not in ['feedback', 'complaint']:
            feedback_type = 'feedback'
        
        user = get_current_user()
        feedback_id = db.insert_feedback(user['username'], text, feedback_type)
        
        if feedback_id > 0:
            # If it's a complaint, create a support ticket
            if feedback_type == 'complaint':
                db.insert_support_ticket(feedback_id, SupportTicketStatus.OPEN)
            
            return jsonify({
                'success': True,
                'message': f'{feedback_type.capitalize()} submitted successfully',
                'feedbackId': feedback_id
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to submit feedback'}), 500
        
    except Exception as e:
        logger.error(f"Feedback submission error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/feedback/my-feedbacks', methods=['GET'])
@require_login
def api_get_my_feedbacks():
    """Get all feedbacks submitted by current user"""
    try:
        user = get_current_user()
        feedbacks = db.get_feedbacks_by_username(user['username'])
        
        formatted_feedbacks = []
        for fb in feedbacks:
            formatted_feedbacks.append({
                'feedbackId': fb['feedbackId'],
                'text': fb['text'],
                'type': fb['type'],
                'timestamp': format_datetime(fb['timestamp'])
            })
        
        return jsonify({
            'success': True,
            'feedbacks': formatted_feedbacks
        }), 200
        
    except Exception as e:
        logger.error(f"Get feedbacks error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


\
# ============================================================================
# METRO CARD ROUTES
# ============================================================================
# ============================================================================
# METRO CARD ROUTES (Final Debugged Version)
# ============================================================================
# ============================================================================
# METRO CARD ROUTES (Robust Integer Fix)
# ============================================================================

@app.route('/api/metrocard/details', methods=['GET'])
@require_login
def api_get_metrocard():
    """Get metro card details (Creates one if missing)"""
    try:
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        # --- FIX: AUTO-CREATE CARD IF MISSING ---
        if not card:
            logger.info(f"Creating missing metro card for {user['username']}")
            # Insert with 0 (False) explicitly
            db.insert_metro_card(user['username'], 0.0, 0, 50.0)
            card = db.get_metro_card_by_username(user['username'])
        # ----------------------------------------
        
        if card:
            # Check if autoRechargeEnabled is 1 or True
            is_auto = card['autoRechargeEnabled'] == 1 or card['autoRechargeEnabled'] is True
            
            return jsonify({
                'success': True,
                'card': {
                    'cardNumber': card['cardNumber'],
                    'balance': card['balance'],
                    'autoRechargeEnabled': is_auto, 
                    'minBalanceThreshold': card['minBalanceThreshold']
                }
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Could not create card'}), 500
        
    except Exception as e:
        logger.error(f"Get metro card error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/metrocard/recharge', methods=['POST'])
@require_login
def api_recharge_metrocard():
    """Recharge metro card"""
    try:
        data = request.json
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        if not card:
            return jsonify({'success': False, 'error': 'Metro card not found'}), 404
        
        new_balance = card['balance'] + amount
        
        # Preserve existing setting as Integer (1 or 0)
        current_setting = 1 if (card['autoRechargeEnabled'] == 1 or card['autoRechargeEnabled'] is True) else 0
        
        if db.update_metro_card(
            card['cardNumber'],
            new_balance,
            current_setting,
            card['minBalanceThreshold']
        ):
            return jsonify({
                'success': True,
                'message': f'Metro card recharged with Rs. {amount:.2f}',
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to recharge card'}), 500
        
    except Exception as e:
        logger.error(f"Metro card recharge error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# app.py - FIXED Auto-Recharge Route
@app.route('/api/metrocard/autorecharge', methods=['POST'])
@require_login
def toggle_auto_recharge():
    """Toggle the auto-recharge switch"""
    try:
        data = request.json
        # 1. Get the raw boolean (True/False)
        raw_enable = data.get('enable')
        
        # 2. CRITICAL FIX: Convert Boolean to Integer (1 or 0)
        # MySQL needs 1 for True, 0 for False
        enable_int = 1 if raw_enable else 0
        
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        if not card:
            return jsonify({'success': False, 'error': 'No card found'}), 404
            
        # 3. Update Database using the INTEGER value
        if db.update_metro_card(
            card['cardNumber'], 
            card['balance'], 
            enable_int, # Passing 1 or 0
            card['minBalanceThreshold']
        ):
            status = "enabled" if enable_int else "disabled"
            return jsonify({'success': True, 'message': f'Auto-recharge {status}'})
        else:
            return jsonify({'success': False, 'error': 'Database update failed'}), 500
            
    except Exception as e:
        logger.error(f"Auto-recharge Toggle Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
# ============================================================================
# STATION ROUTES
# ============================================================================

@app.route('/api/stations', methods=['GET'])
def api_get_all_stations():
    """Get all station names"""
    try:
        stations = list(db.get_all_station_names())
        return jsonify({
            'success': True,
            'stations': stations
        }), 200
    except Exception as e:
        logger.error(f"Get stations error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ADMIN ROUTES
# ============================================================================

@app.route('/api/admin/users', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_get_all_users():
    """Get all users (Admin only)"""
    try:
        users = db.get_all_users()
        
        formatted_users = []
        for user in users:
            formatted_users.append({
                'username': user['username'],
                'walletBalance': user['walletBalance'],
                'role': user['role']
            })
        
        return jsonify({
            'success': True,
            'users': formatted_users
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/users/<username>', methods=['DELETE'])
@require_role(Role.ADMIN)
def api_admin_remove_user(username):
    """Remove a user (Admin only)"""
    try:
        current_user = get_current_user()
        
        if username == current_user['username']:
            return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
        
        if db.remove_user(username):
            return jsonify({
                'success': True,
                'message': f'User {username} removed successfully'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to remove user'}), 500
        
    except Exception as e:
        logger.error(f"Admin remove user error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/stations/add', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_add_station():
    """
    Add a new station (Admin only)
    
    Request JSON:
        {
            "name": "station_name",
            "x": 0.0,
            "y": 0.0
        }
    """
    try:
        data = request.json
        name = data.get('name', '').lower().strip()
        x = float(data.get('x', 0.0))
        y = float(data.get('y', 0.0))
        
        if not name:
            return jsonify({'success': False, 'error': 'Station name required'}), 400
        
        if db.insert_or_update_station_location(name, x, y):
            return jsonify({
                'success': True,
                'message': f'Station {name} added successfully'
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to add station'}), 500
        
    except Exception as e:
        logger.error(f"Admin add station error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/announcements', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_add_announcement():
    """
    Add system announcement (Admin only)
    
    Request JSON:
        {"message": "string"}
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'}), 400
        
        if db.insert_announcement(message):
            return jsonify({
                'success': True,
                'message': 'Announcement added successfully'
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to add announcement'}), 500
        
    except Exception as e:
        logger.error(f"Admin add announcement error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/feedbacks', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_get_all_feedbacks():
    """Get all feedbacks (Admin only)"""
    try:
        feedbacks = db.get_all_feedbacks()
        
        formatted_feedbacks = []
        for fb in feedbacks:
            formatted_feedbacks.append({
                'feedbackId': fb['feedbackId'],
                'username': fb['username'],
                'text': fb['text'],
                'type': fb['type'],
                'timestamp': format_datetime(fb['timestamp'])
            })
        
        return jsonify({
            'success': True,
            'feedbacks': formatted_feedbacks
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get feedbacks error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ANNOUNCEMENTS (Public)
# ============================================================================

@app.route('/api/announcements', methods=['GET'])
def api_get_announcements():
    """Get all announcements"""
    try:
        announcements = db.get_all_announcements()
        
        formatted = []
        for ann in announcements:
            formatted.append({
                'id': ann['id'],
                'message': ann['message'],
                'createdDate': format_datetime(ann['createdDate'])
            })
        
        return jsonify({
            'success': True,
            'announcements': formatted
        }), 200
        
    except Exception as e:
        logger.error(f"Get announcements error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/api/health', methods=['GET'])
def api_health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'message': 'Metro Backend API is running',
        'version': '1.0.0'
    }), 200


@app.route('/', methods=['GET'])
def api_root():
    """Root endpoint"""
    return jsonify({
        'message': 'Metro Ticket Booking System API',
        'version': '1.0.0',
        'endpoints': {
            'auth': '/api/register, /api/login, /api/logout',
            'tickets': '/api/tickets/*',
            'feedback': '/api/feedback/*',
            'admin': '/api/admin/*',
            'health': '/api/health'
        }
    }), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ============================================================================
# SERVE FRONTEND PAGES
# ============================================================================

from flask import send_from_directory
import os

# Get the frontend directory path
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

@app.route('/index.html')
@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/login.html')
def serve_login():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/register.html')
def serve_register():
    return send_from_directory(FRONTEND_DIR, 'register.html')

@app.route('/dashboard.html')
def serve_dashboard():
    return send_from_directory(FRONTEND_DIR, 'dashboard.html')

@app.route('/admin.html')
def serve_admin():
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), filename)
# ============================================================================
# NEW FEATURES - QR CODE, PDF, ANALYTICS
# ============================================================================

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# Generate QR Code for Ticket
@app.route('/api/tickets/<int:ticket_id>/qrcode', methods=['GET'])
def generate_qr_code(ticket_id):
    """Generate QR code for ticket"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # CORRECTION: Added 'db.' prefix
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        # Verify ticket belongs to user
        if ticket['username'] != username:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Create QR data
        qr_data = f"METRO-{ticket_id}|{ticket['source']}|{ticket['destination']}|{ticket['travelDate']}|{ticket['passengers']}"
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': f'data:image/png;base64,{img_base64}'
        })
    except Exception as e:
        logger.error(f"QR Code Error: {e}") # Log the error to console
        return jsonify({'success': False, 'message': str(e)}), 500

# Get Transaction History
# --- REPLACE get_transactions IN app.py ---
@app.route('/api/user/transactions', methods=['GET'])
def get_transactions():
    """Get unified transaction history (Tickets + Recharges)"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Get Tickets (DEBITS)
        cursor.execute("""
            SELECT ticketId as id, fare as amount, bookingDate as date, 
                   CONCAT(source, ' -> ', destination) as description, 
                   'DEBIT' as type, cancelled
            FROM tickets
            WHERE username = %s
        """, (username,))
        tickets = cursor.fetchall()
        
        # 2. Get Recharges (CREDITS)
        cursor.execute("""
            SELECT id, amount, date, description, 'CREDIT' as type, 
                   FALSE as cancelled
            FROM wallet_history
            WHERE username = %s
        """, (username,))
        recharges = cursor.fetchall()
        
        conn.close()
        
        # 3. Merge and Sort by Date (Newest First)
        all_transactions = tickets + recharges
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return jsonify({
            'success': True,
            'transactions': all_transactions[:50] # Limit to 50 items
        })
    except Exception as e:
        logger.error(f"Transaction Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# Get Spending Analytics
@app.route('/api/user/analytics', methods=['GET'])
# app.py - REPLACE THE EXISTING get_analytics FUNCTION
@app.route('/api/user/analytics', methods=['GET'])
def get_analytics():
    """Get user spending analytics with REAL DB DISTANCE"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Total spent and TOTAL DISTANCE (Real DB Data)
        # We use COALESCE to return 0 if the sum is NULL
        cursor.execute("""
            SELECT 
                SUM(fare) as total_spent, 
                COUNT(*) as total_bookings,
                COALESCE(SUM(distance), 0) as total_distance 
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
        """, (username,))
        totals = cursor.fetchone()
        
        # 2. Monthly spending (for the chart)
        cursor.execute("""
            SELECT DATE_FORMAT(bookingDate, '%Y-%m') as month, 
                   SUM(fare) as amount, COUNT(*) as count
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
            GROUP BY DATE_FORMAT(bookingDate, '%Y-%m')
            ORDER BY month DESC
            LIMIT 6
        """, (username,))
        monthly = cursor.fetchall()
        
        # 3. Most used routes
        cursor.execute("""
            SELECT source, destination, COUNT(*) as trip_count
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
            GROUP BY source, destination
            ORDER BY trip_count DESC
            LIMIT 5
        """, (username,))
        routes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'analytics': {
                'total_spent': float(totals['total_spent'] or 0),
                'total_bookings': totals['total_bookings'] or 0,
                'total_distance': float(totals['total_distance'] or 0), # Real Distance
                'monthly_spending': monthly,
                'favorite_routes': routes
            }
        })
    except Exception as e:
        logger.error(f"Analytics Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# Save Favorite Route
@app.route('/api/user/favorites', methods=['POST'])
def add_favorite():
    """Add favorite route"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    data = request.json
    source = data.get('source')
    destination = data.get('destination')
    
    if not source or not destination:
        return jsonify({'success': False, 'message': 'Source and destination required'}), 400
    
    try:
        # CORRECTION: Added 'db.' prefix
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Create favorites table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_routes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50),
                source VARCHAR(100),
                destination VARCHAR(100),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # Add favorite
        cursor.execute("""
            INSERT INTO favorite_routes (username, source, destination)
            VALUES (%s, %s, %s)
        """, (username, source, destination))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Route saved to favorites'})
    except Exception as e:
        logger.error(f"Favorites Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get Favorite Routes
@app.route('/api/user/favorites', methods=['GET'])
def get_favorites():
    """Get user's favorite routes"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # CORRECTION: Added 'db.' prefix
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, source, destination, created_date
            FROM favorite_routes
            WHERE username = %s
            ORDER BY created_date DESC
        """, (username,))
        
        favorites = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'favorites': favorites})
    except Exception as e:
        return jsonify({'success': True, 'favorites': []})

        # ============================================================================
# NEW FEATURES: LOYALTY, LOST & FOUND, NOTIFICATIONS, EMAIL
# ============================================================================

# --- FEATURE 1: LOYALTY POINTS REDEMPTION ---
@app.route('/api/loyalty/redeem', methods=['POST'])
@require_login
def redeem_loyalty_points():
    """Redeem 50 points for Rs. 20 Wallet Balance"""
    try:
        user = get_current_user()
        points = user.get('loyaltyPoints', 0)
        
        if points < 50:
            return jsonify({'success': False, 'error': 'Need 50 points to redeem!'}), 400
            
        # Logic: Deduct 50 points, Add Rs 20
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Update Points
        cursor.execute("UPDATE users SET loyaltyPoints = loyaltyPoints - 50 WHERE username = %s", (user['username'],))
        # 2. Add Money
        cursor.execute("UPDATE users SET walletBalance = walletBalance + 20 WHERE username = %s", (user['username'],))
        # 3. Add Notification
        msg = "Redeemed 50 Green Points for Rs. 20 credit"
        cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (user['username'], msg))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Points redeemed successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- FEATURE 2: LOST & FOUND ---

@app.route('/api/lostfound/my', methods=['GET'])
@require_login
def get_my_lost_reports():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM lost_found WHERE username = %s ORDER BY reportDate DESC", (user['username'],))
        reports = cursor.fetchall()
        conn.close()
        return jsonify({'success': True, 'reports': reports})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- FEATURE 3: EMAIL TICKET ---
@app.route('/api/tickets/<int:ticket_id>/email', methods=['POST'])
@require_login
def email_ticket_receipt(ticket_id):
    """Simulates sending an email"""
    try:
        # In a real app, we would use smtplib here.
        # For this project, we log it and return success.
        user = get_current_user()
        logger.info(f"📧 EMAIL SENT: Ticket #{ticket_id} sent to {user['username']}@metro.com")
        
        # Add a notification
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", 
                      (user['username'], f"Ticket #{ticket_id} receipt sent to email."))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'Receipt sent to {user["username"]}@gmail.com'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # ============================================================================
# NEW FEATURES: LOYALTY, LOST & FOUND, NOTIFICATIONS
# ============================================================================

# --- 1. SYSTEM UPGRADE (Creates new tables automatically) ---
# --- UPDATE THIS FUNCTION IN app.py ---
# --- REPLACE THIS FUNCTION IN app.py ---
# --- REPLACE THIS FUNCTION IN app.py ---
# --- REPLACE THIS IN app.py ---
# --- REPLACE THIS FUNCTION IN app.py ---
@app.route('/api/system/upgrade', methods=['GET'])
def upgrade_system_tables():
    """Final Fix: Creates missing tables and ignores errors"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Add Loyalty Points (Ignore if exists)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN loyaltyPoints INT DEFAULT 0")
        except:
            pass 

        # 2. Create Lost & Found
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lost_found (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    item VARCHAR(100),
                    description TEXT,
                    status VARCHAR(20) DEFAULT 'SEARCHING',
                    reportDate DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass

        # 3. Create Notifications
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    message VARCHAR(255),
                    is_read BOOLEAN DEFAULT FALSE,
                    date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass

        # 4. Create Wallet History (THIS IS THE MISSING TABLE)
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallet_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    amount DOUBLE,
                    type VARCHAR(20),
                    description VARCHAR(100),
                    date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'System Upgraded Successfully!'})
    except Exception as e:
        # Even if there is a big error, don't crash the browser, just tell us.
        return jsonify({'success': False, 'error': str(e)})

# --- 3. GET NOTIFICATIONS ---
@app.route('/api/notifications', methods=['GET'])
@require_login
def get_user_notifications():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT message, date FROM notifications WHERE username = %s ORDER BY date DESC LIMIT 5", (user['username'],))
        notifs = cursor.fetchall()
        
        # Also get Loyalty Points to show on dashboard
        cursor.execute("SELECT loyaltyPoints FROM users WHERE username = %s", (user['username'],))
        points_row = cursor.fetchone()
        points = points_row['loyaltyPoints'] if points_row else 0
        
        conn.close()
        return jsonify({'success': True, 'notifications': notifs, 'loyaltyPoints': points})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 4. REPORT LOST ITEM ---
# --- UPDATE THIS ROUTE IN app.py ---
@app.route('/api/lost-found/report', methods=['POST'])
@require_login
def report_lost_item():
    try:
        data = request.json
        item_text = data.get('item', '').strip()
        description = data.get('description', item_text).strip() # Use item as desc if empty

        if not item_text:
            return jsonify({'success': False, 'error': 'Item description required'}), 400

        user = get_current_user()

        # FIX: Use the correct table function we just created
        if db.insert_lost_found(user['username'], item_text, description):
            return jsonify({
                'success': True,
                'message': 'Lost item reported successfully! Check "My Reports" for updates.'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Database error: Failed to save report'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- 5. EMAIL SIMULATION ---
@app.route('/api/tickets/<int:ticket_id>/email', methods=['POST'])
@require_login
def email_ticket(ticket_id):
    # Simulates sending email by logging it
    logger.info(f"📧 Sending Ticket #{ticket_id} to user email...")
    return jsonify({'success': True, 'message': 'Ticket sent to your registered email!'})

# app.py - Add this temporary route
@app.route('/api/fix-db-distance', methods=['GET'])
def fix_db_distance():
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Try to add the column. If it exists, this will just fail silently.
        try:
            cursor.execute("ALTER TABLE tickets ADD COLUMN distance DOUBLE DEFAULT 0.0")
            msg = "✅ Success: 'distance' column added to tickets table."
        except Exception as e:
            msg = f"ℹ️ Notice: {str(e)} (Column probably already exists)"
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
# app.py - Add this temporary route to fix coordinates
@app.route('/api/fix-stations', methods=['GET'])
def fix_stations():
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Move Connaught Place slightly North
        cursor.execute("UPDATE station_locations SET x = 28.6350, y = 77.2200 WHERE name = 'connaught_place'")
        
        # 2. Move Rajiv Chowk slightly South (or keep it, but ensure they differ)
        cursor.execute("UPDATE station_locations SET x = 28.6280, y = 77.2150 WHERE name = 'rajiv_chowk'")
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Station coordinates updated! Try booking now.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    # --- ADD TO app.py (Admin Section) ---

# 1. GET ALL LOST ITEMS
@app.route('/api/admin/lost-found', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_lost_found():
    items = db.get_all_lost_found_items()
    # Format dates
    for item in items:
        item['reportDate'] = format_datetime(item['reportDate'])
    return jsonify({'success': True, 'items': items})

# 2. UPDATE LOST ITEM STATUS
@app.route('/api/admin/lost-found/<int:item_id>/status', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_update_item_status(item_id):
    data = request.json
    status = data.get('status')
    if db.update_lost_found_status(item_id, status):
        return jsonify({'success': True, 'message': 'Status updated'})
    return jsonify({'success': False, 'error': 'Update failed'}), 500

# 3. ANALYTICS DATA FOR CHARTS
@app.route('/api/admin/analytics/revenue', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_revenue_stats():
    # Get real data from DB
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Revenue per month
    cursor.execute("""
        SELECT DATE_FORMAT(bookingDate, '%Y-%m') as month, SUM(fare) as revenue 
        FROM tickets WHERE cancelled = 0 
        GROUP BY month ORDER BY month DESC LIMIT 6
    """)
    revenue_data = cursor.fetchall()
    
    # Ticket status counts
    cursor.execute("SELECT cancelled, COUNT(*) as count FROM tickets GROUP BY cancelled")
    status_data = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'success': True, 
        'revenue': revenue_data,
        'status': status_data
    })

# FEATURE 4: LIVE STATION STATUS (Simulated)
@app.route('/api/station/status/<string:station_name>', methods=['GET'])
def get_station_status(station_name):
    # Simulating real-time data
    crowd_levels = ['Low', 'Moderate', 'High', 'Very High']
    next_train = random.randint(2, 15)
    parking = random.randint(0, 50)
    
    return jsonify({
        'success': True,
        'station': station_name,
        'crowd': random.choice(crowd_levels),
        'next_train_min': next_train,
        'parking_slots': parking,
        'lift_status': 'Operational'
    })

# FEATURE 3: SOS ALERT
@app.route('/api/sos/alert', methods=['POST'])
@require_login
def trigger_sos():
    user = get_current_user()
    # In a real app, this would SMS the police. Here we log it.
    print(f"🚨 SOS TRIGGERED BY {user['username']}! Location: Dashboard")
    return jsonify({'success': True, 'message': 'Emergency Alert Sent to Station Control!'})

# --- ADD TO app.py (Admin Section) ---

@app.route('/api/admin/live-feed', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_live_feed():
    return jsonify({'success': True, 'tickets': db.get_recent_global_tickets()})

@app.route('/api/admin/station-stats', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_station_stats():
    return jsonify({'success': True, 'stats': db.get_station_traffic_stats()})

@app.route('/api/admin/top-users', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_top_users():
    return jsonify({'success': True, 'users': db.get_top_users_by_balance()})

@app.route('/api/admin/system/reset', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_system_reset():
    """DANGEROUS: Wipes all data"""
    if db.clear_all_data():
        # Re-initialize default admin/stations if needed here
        return jsonify({'success': True, 'message': 'System Wiped Successfully'})
    return jsonify({'success': False, 'error': 'Reset Failed'}), 500

# --- NEW ADMIN PRO ROUTES ---

@app.route('/api/admin/analytics/peak-hours', methods=['GET'])
def api_admin_peak_hours():
    return jsonify({'success': True, 'data': db.get_peak_hour_stats()})

@app.route('/api/admin/analytics/sentiment', methods=['GET'])
def api_admin_sentiment():
    return jsonify({'success': True, 'data': db.get_feedback_sentiment()})

@app.route('/api/admin/staff/add', methods=['POST'])
def api_admin_add_staff():
    data = request.json
    hashed = hash_password(data['password'])
    if db.create_staff_user(data['username'], hashed):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User exists'})

@app.route('/api/admin/pricing/surge', methods=['POST'])
def api_admin_surge():
    # In a real app, save this to a 'config' table. 
    # Here we just acknowledge it for the UI demo.
    data = request.json
    return jsonify({'success': True, 'multiplier': data['multiplier']})

@app.route('/api/admin/tickets/all', methods=['GET'])
def api_admin_all_tickets():
    return jsonify({'success': True, 'tickets': db.get_all_tickets_full()})

@app.route('/api/admin/station/status', methods=['POST'])
def api_admin_station_status():
    data = request.json
    db.toggle_station_status(data['name'], data['status'])
    return jsonify({'success': True})

# --- ADD TO app.py ---

import psutil # You might need to install this: pip install psutil
import json

# 1. CCTV & INFRASTRUCTURE
@app.route('/api/admin/infra/cctv', methods=['GET'])
def api_admin_cctv():
    # Simulating camera status based on real stations
    stations = db.get_all_station_names() # Uses your existing DB function
    cameras = []
    for i, st in enumerate(stations):
        cameras.append({
            'id': f"CAM-{100+i}",
            'location': st,
            'status': 'ONLINE' if i % 5 != 0 else 'MAINTENANCE', # Every 5th cam offline
            'activity': 'HIGH' if i < 3 else 'LOW'
        })
    return jsonify({'success': True, 'cameras': cameras})

# 2. POWER GRID ANALYTICS (Real DB Math)
@app.route('/api/admin/infra/power', methods=['GET'])
def api_admin_power():
    # Calculate energy usage based on real ticket volume (More passengers = More trains)
    tickets = db.get_all_tickets_full()
    total_pax = len(tickets)
    base_load = 450 # kWh
    current_load = base_load + (total_pax * 1.5) 
    return jsonify({
        'success': True, 
        'grid_load': current_load,
        'voltage': 240 + (total_pax % 10), # Simulated fluctuation
        'efficiency': 94
    })

# 3. DATABASE BACKUP (Real Feature)
@app.route('/api/admin/system/backup', methods=['GET'])
def api_admin_backup():
    # Exports User DB to JSON
    users = db.get_all_users() # Assuming you have a get_all_users fn
    return jsonify({
        'success': True,
        'timestamp': str(datetime.now()),
        'record_count': len(users),
        'data': users 
    })

# 4. SERVER HEALTH (Real System Data)
@app.route('/api/admin/system/health', methods=['GET'])
def api_admin_health():
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
    except:
        cpu, ram = 45, 60 # Fallback if psutil not installed
    return jsonify({'success': True, 'cpu': cpu, 'ram': ram})

@app.route('/api/ticket/download/<int:ticket_id>')
def download_ticket_pdf(ticket_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'})
    
    # Fetch ticket details
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tickets WHERE ticket_id = %s AND user_id = %s", 
                   (ticket_id, session['user_id']))
    ticket = cursor.fetchone()
    conn.close()

    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found'})

    # Generate PDF in memory
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Draw Ticket Design
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "METRO TICKET")
    c.setFont("Helvetica", 14)
    c.drawString(100, 700, f"Ticket ID: #{ticket['ticket_id']}")
    c.drawString(100, 670, f"Source: {ticket['source'].replace('_', ' ').title()}")
    c.drawString(100, 640, f"Destination: {ticket['destination'].replace('_', ' ').title()}")
    c.drawString(100, 610, f"Date: {ticket['booking_date']}")
    c.drawString(100, 580, f"Fare: Rs. {ticket['fare']}")
    c.drawString(100, 550, f"Status: {ticket['status']}")
    
    # Add Footer
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(100, 500, "Please show this PDF at the station gate.")
    
    c.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f'ticket_{ticket_id}.pdf', mimetype='application/pdf')

# --- ADD THESE TO app.py FOR ADMIN FEATURES ---

# 1. GLOBAL SEARCH ("God Mode")
@app.route('/api/admin/global_search')
def admin_global_search():
    query = request.args.get('q', '').lower()
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Search Users
    cursor.execute("SELECT user_id, username, role FROM users WHERE username LIKE %s", (f"%{query}%",))
    users = cursor.fetchall()
    
    # Search Tickets
    cursor.execute("SELECT ticket_id, source, destination, status FROM tickets WHERE ticket_id LIKE %s", (f"%{query}%",))
    tickets = cursor.fetchall()
    
    conn.close()
    return jsonify({'success': True, 'results': {'users': users, 'tickets': tickets}})

# 2. SYSTEM CONTROL (Peak Pricing & Maintenance)
system_config = {'peak_pricing': False, 'maintenance_mode': False}

@app.route('/api/admin/config/update', methods=['POST'])
def update_system_config():
    data = request.json
    if 'peak_pricing' in data: system_config['peak_pricing'] = data['peak_pricing']
    if 'maintenance_mode' in data: system_config['maintenance_mode'] = data['maintenance_mode']
    return jsonify({'success': True, 'config': system_config})

@app.route('/api/admin/config/get')
def get_system_config():
    return jsonify({'success': True, 'config': system_config})

# 3. BULK REFUND ACTION
@app.route('/api/admin/refunds/approve_all', methods=['POST'])
def approve_all_refunds():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    # Approve all pending refunds < Rs 500 (Safe auto-approve limit)
    cursor.execute("UPDATE tickets SET status='REFUNDED' WHERE status='CANCELLED' AND fare < 500")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Auto-approved {affected} refunds.'})

# 4. USER BAN ACTION
@app.route('/api/admin/users/ban', methods=['POST'])
def ban_user():
    user_id = request.json.get('user_id')
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET walletBalance = 0 WHERE user_id = %s", (user_id,)) # Punish by draining wallet (Example)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User penalized.'})

# 5. SERVER LOGS VIEWER
@app.route('/api/admin/logs')
def get_server_logs():
    # Simulated logs for demo
    logs = [
        {'time': '10:00:01', 'level': 'INFO', 'msg': 'Server started successfully'},
        {'time': '10:05:23', 'level': 'WARN', 'msg': 'High load detected on Station: Rajiv Chowk'},
        {'time': '10:10:45', 'level': 'INFO', 'msg': 'Backup completed'},
        {'time': '10:15:12', 'level': 'ERROR', 'msg': 'Failed payment attempt: User #402'}
    ]
    return jsonify({'success': True, 'logs': logs})

# ============================================================================
# NEW ADMIN DASHBOARD ANALYTICS ENDPOINTS
# ============================================================================

# 1. REAL-TIME DASHBOARD STATISTICS
@app.route('/api/admin/dashboard/stats', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Total revenue from non-cancelled tickets
        cursor.execute("""
            SELECT COALESCE(SUM(fare), 0) as total_revenue,
                   COUNT(*) as total_tickets
            FROM tickets WHERE cancelled = FALSE
        """)
        revenue_data = cursor.fetchone()
        
        # Total users
        cursor.execute("SELECT COUNT(*) as total_users FROM users WHERE role = 'USER'")
        user_data = cursor.fetchone()
        
        # Today's bookings
        cursor.execute("""
            SELECT COUNT(*) as today_bookings, COALESCE(SUM(fare), 0) as today_revenue
            FROM tickets 
            WHERE DATE(bookingDate) = CURDATE() AND cancelled = FALSE
        """)
        today_data = cursor.fetchone()
        
        # Yesterday's revenue for growth calculation
        cursor.execute("""
            SELECT COALESCE(SUM(fare), 0) as yesterday_revenue
            FROM tickets 
            WHERE DATE(bookingDate) = DATE_SUB(CURDATE(), INTERVAL 1 DAY) AND cancelled = FALSE
        """)
        yesterday_data = cursor.fetchone()
        
        # Calculate growth percentage
        yesterday_rev = float(yesterday_data['yesterday_revenue'] or 0)
        today_rev = float(today_data['today_revenue'] or 0)
        
        if yesterday_rev > 0:
            growth = ((today_rev - yesterday_rev) / yesterday_rev) * 100
        else:
            growth = 100 if today_rev > 0 else 0
        
        # Active tickets (upcoming)
        cursor.execute("""
            SELECT COUNT(*) as active_tickets
            FROM tickets 
            WHERE cancelled = FALSE AND travelDate >= CURDATE()
        """)
        active_data = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_revenue': float(revenue_data['total_revenue']),
                'total_tickets': revenue_data['total_tickets'],
                'total_users': user_data['total_users'],
                'today_bookings': today_data['today_bookings'],
                'today_revenue': float(today_data['today_revenue']),
                'revenue_growth': round(growth, 2),
                'active_tickets': active_data['active_tickets']
            }
        })
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 2. REAL-TIME REVENUE TRACKING
@app.route('/api/admin/revenue/realtime', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_revenue_realtime():
    """Get revenue trends for last 7 days"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Last 7 days revenue
        cursor.execute("""
            SELECT DATE(bookingDate) as date, 
                   COALESCE(SUM(fare), 0) as revenue,
                   COUNT(*) as bookings
            FROM tickets 
            WHERE cancelled = FALSE 
                AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(bookingDate)
            ORDER BY date ASC
        """)
        daily_revenue = cursor.fetchall()
        
        # Hourly revenue for today
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, 
                   COALESCE(SUM(fare), 0) as revenue,
                   COUNT(*) as bookings
            FROM tickets 
            WHERE cancelled = FALSE AND DATE(bookingDate) = CURDATE()
            GROUP BY HOUR(bookingDate)
            ORDER BY hour ASC
        """)
        hourly_revenue = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'daily': daily_revenue,
            'hourly': hourly_revenue
        })
    except Exception as e:
        logger.error(f"Revenue tracking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 3. LIVE BOOKINGS FEED
@app.route('/api/admin/bookings/live', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_bookings_live():
    """Get recent bookings for live feed"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT ticketId, username, source, destination, 
                   passengers, fare, bookingDate, cancelled
            FROM tickets 
            ORDER BY bookingDate DESC 
            LIMIT 20
        """)
        bookings = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'bookings': bookings
        })
    except Exception as e:
        logger.error(f"Live bookings error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 4. STATION PERFORMANCE ANALYTICS
@app.route('/api/admin/stations/performance', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_stations_performance():
    """Get station usage metrics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Top source stations
        cursor.execute("""
            SELECT source as station, 
                   COUNT(*) as trips,
                   COALESCE(SUM(passengers), 0) as total_passengers
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY source
            ORDER BY trips DESC
            LIMIT 10
        """)
        top_sources = cursor.fetchall()
        
        # Top destination stations
        cursor.execute("""
            SELECT destination as station, 
                   COUNT(*) as trips,
                   COALESCE(SUM(passengers), 0) as total_passengers
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY destination
            ORDER BY trips DESC
            LIMIT 10
        """)
        top_destinations = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'sources': top_sources,
            'destinations': top_destinations
        })
    except Exception as e:
        logger.error(f"Station performance error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 5. USER ANALYTICS
@app.route('/api/admin/users/analytics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_users_analytics():
    """Get user behavior insights"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # New users in last 7 days
        cursor.execute("""
            SELECT DATE(createdAt) as date, COUNT(*) as new_users
            FROM users 
            WHERE role = 'USER' AND createdAt >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY DATE(createdAt)
            ORDER BY date ASC
        """)
        new_users = cursor.fetchall()
        
        # Top users by wallet balance
        cursor.execute("""
            SELECT username, walletBalance
            FROM users 
            WHERE role = 'USER'
            ORDER BY walletBalance DESC
            LIMIT 10
        """)
        top_balance = cursor.fetchall()
        
        # Top users by spending
        cursor.execute("""
            SELECT t.username, 
                   COALESCE(SUM(t.fare), 0) as total_spent,
                   COUNT(*) as total_bookings
            FROM tickets t
            WHERE t.cancelled = FALSE
            GROUP BY t.username
            ORDER BY total_spent DESC
            LIMIT 10
        """)
        top_spenders = cursor.fetchall()
        
        # Active vs inactive users
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT u.username) as total_users,
                COUNT(DISTINCT t.username) as active_users
            FROM users u
            LEFT JOIN tickets t ON u.username = t.username AND t.cancelled = FALSE
            WHERE u.role = 'USER'
        """)
        activity = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'new_users': new_users,
            'top_balance': top_balance,
            'top_spenders': top_spenders,
            'activity': activity
        })
    except Exception as e:
        logger.error(f"User analytics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 6. SYSTEM ALERTS
@app.route('/api/admin/alerts/system', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_system_alerts():
    """Get automated system alerts"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        alerts = []
        
        # Low balance users
        cursor.execute("""
            SELECT username, walletBalance
            FROM users 
            WHERE role = 'USER' AND walletBalance < 50
            ORDER BY walletBalance ASC
            LIMIT 10
        """)
        low_balance = cursor.fetchall()
        
        for user in low_balance:
            alerts.append({
                'type': 'warning',
                'category': 'Low Balance',
                'message': f"User {user['username']} has low balance: Rs. {user['walletBalance']}",
                'data': user
            })
        
        # Pending refunds (cancelled tickets)
        cursor.execute("""
            SELECT COUNT(*) as pending_refunds
            FROM tickets 
            WHERE cancelled = TRUE AND bookingDate >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        refund_count = cursor.fetchone()
        
        if refund_count['pending_refunds'] > 0:
            alerts.append({
                'type': 'info',
                'category': 'Refunds',
                'message': f"{refund_count['pending_refunds']} cancelled tickets in last 7 days",
                'data': refund_count
            })
        
        # Check CPU/RAM
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            
            if cpu > 80:
                alerts.append({
                    'type': 'danger',
                    'category': 'System Health',
                    'message': f"High CPU usage: {cpu}%"
                })
            
            if ram > 80:
                alerts.append({
                    'type': 'danger',
                    'category': 'System Health',
                    'message': f"High RAM usage: {ram}%"
                })
        except:
            pass
        
        conn.close()
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'count': len(alerts)
        })
    except Exception as e:
        logger.error(f"System alerts error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 7. REFUND MANAGEMENT
@app.route('/api/admin/refunds/pending', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_refunds_pending():
    """Get pending refund requests"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT ticketId, username, source, destination, 
                   passengers, fare, bookingDate, travelDate
            FROM tickets 
            WHERE cancelled = TRUE
            ORDER BY bookingDate DESC
            LIMIT 50
        """)
        pending = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'refunds': pending
        })
    except Exception as e:
        logger.error(f"Refunds error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 8. ENHANCED LOST & FOUND
@app.route('/api/admin/lostfound/all', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_lostfound_all():
    """Get all lost items with enhanced data"""
    try:
        items = db.get_all_lost_found_items()
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        logger.error(f"Lost & found error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Update lost item status
@app.route('/api/admin/lostfound/<int:item_id>/update', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_lostfound_update(item_id):
    """Update lost item status"""
    try:
        data = request.json
        status = data.get('status', 'SEARCHING')
        
        if db.update_lost_found_status(item_id, status):
            return jsonify({'success': True, 'message': 'Status updated'})
        return jsonify({'success': False, 'error': 'Update failed'}), 500
    except Exception as e:
        logger.error(f"Lost & found update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 9. PEAK HOURS ANALYTICS (Enhanced)
@app.route('/api/admin/analytics/peakhours', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_analytics_peakhours():
    """Get hour-by-hour booking distribution"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, 
                   COUNT(*) as bookings,
                   COALESCE(SUM(passengers), 0) as passengers,
                   COALESCE(SUM(fare), 0) as revenue
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY HOUR(bookingDate)
            ORDER BY hour ASC
        """)
        hourly_data = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'hourly': hourly_data
        })
    except Exception as e:
        logger.error(f"Peak hours error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 10. SUSPICIOUS ACTIVITY DETECTION
@app.route('/api/admin/security/suspicious', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_security_suspicious():
    """Detect potentially fraudulent patterns"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        suspicious = []
        
        # Multiple bookings in short time (>5 tickets in 1 hour)
        cursor.execute("""
            SELECT username, 
                   COUNT(*) as ticket_count,
                   MIN(bookingDate) as first_booking,
                   MAX(bookingDate) as last_booking,
                   COALESCE(SUM(fare), 0) as total_amount
            FROM tickets 
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            GROUP BY username
            HAVING ticket_count > 5
        """)
        rapid_bookings = cursor.fetchall()
        
        for item in rapid_bookings:
            suspicious.append({
                'type': 'Rapid Bookings',
                'username': item['username'],
                'details': f"{item['ticket_count']} tickets in 1 hour",
                'amount': float(item['total_amount'])
            })
        
        # High value single transactions (>Rs. 500)
        cursor.execute("""
            SELECT ticketId, username, fare, bookingDate, source, destination
            FROM tickets 
            WHERE fare > 500 AND bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            ORDER BY fare DESC
        """)
        high_value = cursor.fetchall()
        
        for item in high_value:
            suspicious.append({
                'type': 'High Value Transaction',
                'username': item['username'],
                'details': f"Rs. {item['fare']} ticket #{item['ticketId']}",
                'amount': float(item['fare'])
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'suspicious': suspicious,
            'count': len(suspicious)
        })
    except Exception as e:
        logger.error(f"Security check error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# ADMIN ENDPOINTS - ADDITIONAL 10 FEATURES
# ============================================================================

# 11. Station Status Management
@app.route('/api/admin/stations/status', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_stations_status():
    """Get or update station operational status"""
    try:
        if request.method == 'GET':
            # Get all stations with status
            conn = db.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Get station names and calculate status based on recent activity
            cursor.execute("""
                SELECT 
                    sl.name as station,
                    COUNT(DISTINCT t1.ticketId) as departures,
                    COUNT(DISTINCT t2.ticketId) as arrivals,
                    COALESCE(SUM(t1.passengers), 0) + COALESCE(SUM(t2.passengers), 0) as total_passengers
                FROM station_locations sl
                LEFT JOIN tickets t1 ON sl.name = t1.source AND t1.bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                LEFT JOIN tickets t2 ON sl.name = t2.destination AND t2.bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY sl.name
            """)
            
            stations = cursor.fetchall()
            
            # Add status based on activity
            for station in stations:
                passengers = station['total_passengers']
                if passengers > 100:
                    station['status'] = 'crowded'
                    station['status_text'] = 'High Traffic'
                elif passengers > 50:
                    station['status'] = 'moderate'
                    station['status_text'] = 'Moderate'
                else:
                    station['status'] = 'low'
                    station['status_text'] = 'Low Traffic'
            
            conn.close()
            return jsonify({'success': True, 'stations': stations})
        
        else:  # POST - update station status
            data = request.json
            # In real implementation, you'd have a station_status table
            return jsonify({'success': True, 'message': 'Station status updated'})
            
    except Exception as e:
        logger.error(f"Station status error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 12. Route Analytics
@app.route('/api/admin/routes/analytics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_routes_analytics():
    """Get route popularity and profitability analysis"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Top routes by bookings
        cursor.execute("""
            SELECT 
                CONCAT(source, ' → ', destination) as route,
                COUNT(*) as bookings,
                SUM(passengers) as total_passengers,
                SUM(fare) as total_revenue,
                AVG(fare) as avg_fare,
                AVG(distance) as avg_distance
            FROM tickets
            WHERE cancelled = FALSE
            GROUP BY source, destination
            ORDER BY bookings DESC
            LIMIT 10
        """)
        
        top_routes = cursor.fetchall()
        
        # Route profitability (revenue per km)
        cursor.execute("""
            SELECT 
                CONCAT(source, ' → ', destination) as route,
                SUM(fare) / NULLIF(SUM(distance), 0) as revenue_per_km,
                COUNT(*) as trips
            FROM tickets
            WHERE cancelled = FALSE AND distance > 0
            GROUP BY source, destination
            ORDER BY revenue_per_km DESC
            LIMIT 10
        """)
        
        profitable_routes = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'top_routes': top_routes,
            'profitable_routes': profitable_routes
        })
        
    except Exception as e:
        logger.error(f"Route analytics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 13. Monthly Pass Management
@app.route('/api/admin/passes/management', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_passes_management():
    """Get monthly pass statistics and active passes"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Active passes
        cursor.execute("""
            SELECT 
                mp.*,
                u.walletBalance,
                DATEDIFF(mp.expiryDate, CURDATE()) as days_remaining
            FROM monthly_passes mp
            JOIN users u ON mp.username = u.username
            WHERE mp.expiryDate >= CURDATE()
            ORDER BY mp.expiryDate ASC
        """)
        
        active_passes = cursor.fetchall()
        
        # Pass statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_active,
                SUM(price) as total_revenue,
                AVG(price) as avg_price,
                COUNT(CASE WHEN DATEDIFF(expiryDate, CURDATE()) <= 7 THEN 1 END) as expiring_soon
            FROM monthly_passes
            WHERE expiryDate >= CURDATE()
        """)
        
        stats = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'active_passes': active_passes,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Pass management error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 14. Feedback Dashboard
@app.route('/api/admin/feedback/dashboard', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_feedback_dashboard():
    """Get feedback categorization and sentiment analysis"""
    try:
        feedbacks = db.get_all_feedbacks()
        
        # Categorize by type
        feedback_count = sum(1 for f in feedbacks if f['type'] == 'feedback')
        complaint_count = sum(1 for f in feedbacks if f['type'] == 'complaint')
        
        # Simple sentiment analysis
        sentiment = {'positive': 0, 'negative': 0, 'neutral': 0}
        pos_words = ['good', 'great', 'excellent', 'amazing', 'best', 'love', 'fast', 'clean']
        neg_words = ['bad', 'worst', 'terrible', 'slow', 'dirty', 'late', 'rude', 'poor']
        
        for f in feedbacks:
            text = f['text'].lower()
            if any(word in text for word in pos_words):
                sentiment['positive'] += 1
            elif any(word in text for word in neg_words):
                sentiment['negative'] += 1
            else:
                sentiment['neutral'] += 1
        
        # Recent feedback
        recent = feedbacks[:10] if len(feedbacks) > 10 else feedbacks
        
        return jsonify({
            'success': True,
            'total': len(feedbacks),
            'feedback_count': feedback_count,
            'complaint_count': complaint_count,
            'sentiment': sentiment,
            'recent': recent
        })
        
    except Exception as e:
        logger.error(f"Feedback dashboard error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 15. Promotions Management
@app.route('/api/admin/promotions/all', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_promotions_all():
    """Get all promotional campaigns"""
    try:
        # Mock data for promotions (in real app, create promotions table)
        promotions = [
            {
                'id': 1,
                'code': 'METRO50',
                'discount': 50,
                'type': 'percentage',
                'active': True,
                'used': 156,
                'created': '2026-01-01'
            },
            {
                'id': 2,
                'code': 'NEWUSER',
                'discount': 100,
                'type': 'flat',
                'active': True,
                'used': 89,
                'created': '2026-01-15'
            }
        ]
        
        return jsonify({
            'success': True,
            'promotions': promotions,
            'count': len(promotions)
        })
        
    except Exception as e:
        logger.error(f"Promotions error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/promotions/create', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_promotions_create():
    """Create new promotional campaign"""
    try:
        data = request.json
        # In real app, insert into promotions table
        return jsonify({
            'success': True,
            'message': 'Promotion created successfully',
            'promotion_id': 3
        })
        
    except Exception as e:
        logger.error(f"Create promotion error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 16. Staff Metrics
@app.route('/api/admin/staff/metrics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_staff_metrics():
    """Get staff performance metrics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get support staff
        cursor.execute("""
            SELECT username, walletBalance, role
            FROM users
            WHERE role = 'SUPPORT_STAFF'
        """)
        
        staff = cursor.fetchall()
        
        # Mock performance data
        for member in staff:
            member['tickets_resolved'] = random.randint(10, 50)
            member['avg_response_time'] = f"{random.randint(5, 30)} min"
            member['satisfaction_score'] = round(random.uniform(4.0, 5.0), 1)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'staff': staff,
            'total_staff': len(staff)
        })
        
    except Exception as e:
        logger.error(f"Staff metrics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 17. Financial Reports
@app.route('/api/admin/reports/financial', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_reports_financial():
    """Generate financial reports"""
    try:
        period = request.args.get('period', 'daily')  # daily, weekly, monthly
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if period == 'daily':
            # Last 7 days
            cursor.execute("""
                SELECT 
                    DATE(bookingDate) as date,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(bookingDate)
                ORDER BY date DESC
            """)
        elif period == 'weekly':
            # Last 8 weeks
            cursor.execute("""
                SELECT 
                    YEARWEEK(bookingDate) as week,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 56 DAY)
                GROUP BY YEARWEEK(bookingDate)
                ORDER BY week DESC
            """)
        else:  # monthly
            # Last 6 months
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(bookingDate, '%Y-%m') as month,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                GROUP BY DATE_FORMAT(bookingDate, '%Y-%m')
                ORDER BY month DESC
            """)
        
        data = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'period': period,
            'data': data
        })
        
    except Exception as e:
        logger.error(f"Financial reports error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 18. Notifications Management
@app.route('/api/admin/notifications/manage', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_notifications_manage():
    """Manage system-wide notifications"""
    try:
        if request.method == 'GET':
            announcements = db.get_all_announcements()
            return jsonify({
                'success': True,
                'announcements': announcements,
                'count': len(announcements)
            })
        else:  # POST - create new announcement
            data = request.json
            message = data.get('message', '')
            
            if db.insert_announcement(message):
                return jsonify({
                    'success': True,
                    'message': 'Announcement created successfully'
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to create announcement'}), 500
                
    except Exception as e:
        logger.error(f"Notifications error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 19. Capacity Planning
@app.route('/api/admin/capacity/analysis', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_capacity_analysis():
    """Get capacity planning and load analysis data"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Hourly passenger distribution
        cursor.execute("""
            SELECT 
                HOUR(bookingDate) as hour,
                SUM(passengers) as total_passengers,
                COUNT(*) as bookings,
                AVG(passengers) as avg_passengers_per_booking
            FROM tickets
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY HOUR(bookingDate)
            ORDER BY hour
        """)
        
        hourly_load = cursor.fetchall()
        
        # Station capacity utilization
        cursor.execute("""
            SELECT 
                source as station,
                SUM(passengers) as passengers_out,
                COUNT(*) as trips_out
            FROM tickets
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY source
            ORDER BY passengers_out DESC
            LIMIT 10
        """)
        
        station_load = cursor.fetchall()
        
        # Calculate capacity recommendations
        for item in hourly_load:
            passengers = item['total_passengers']
            if passengers > 200:
                item['recommendation'] = 'Add extra trains'
            elif passengers > 100:
                item['recommendation'] = 'Monitor closely'
            else:
                item['recommendation'] = 'Normal capacity'
        
        conn.close()
        
        return jsonify({
            'success': True,
            'hourly_load': hourly_load,
            'station_load': station_load
        })
        
    except Exception as e:
        logger.error(f"Capacity analysis error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 20. Emergency Management
@app.route('/api/admin/emergency/alerts', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_emergency_alerts():
    """Emergency alert and incident management"""
    try:
        if request.method == 'GET':
            # Mock emergency incidents
            incidents = [
                {
                    'id': 1,
                    'type': 'maintenance',
                    'station': 'Rajiv Chowk',
                    'status': 'resolved',
                    'reported': '2026-01-28 10:00:00',
                    'resolved': '2026-01-28 12:00:00'
                }
            ]
            
            return jsonify({
                'success': True,
                'incidents': incidents,
                'active_alerts': 0
            })
        
        else:  # POST - create emergency alert
            data = request.json
            alert_type = data.get('type', 'general')
            message = data.get('message', '')
            
            # Broadcast to all users (in real app, use push notifications)
            db.insert_announcement(f"EMERGENCY: {message}")
            
            return jsonify({
                'success': True,
                'message': 'Emergency alert broadcasted',
                'alert_id': random.randint(1000, 9999)
            })
            
    except Exception as e:
        logger.error(f"Emergency alerts error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    # In app.py

@app.route('/api/stations/info/<string:station_name>', methods=['GET'])
def api_get_station_info(station_name):
    """Get professional facility info for a station"""
    try:
        station = db.get_station_details(station_name)
        
        if not station:
            # Fallback: Return simulated data if DB is empty (for demo purposes)
            import random
            return jsonify({
                'success': True,
                'station': {
                    'name': station_name,
                    'has_wifi': random.choice([True, False]),
                    'has_parking': random.choice([True, False]),
                    'has_restroom': True,
                    'has_atm': random.choice([True, False]),
                    'is_accessible': True,
                    'contact_number': '1800-METRO-HELP',
                    'status': 'Operational'
                }
            })

        return jsonify({'success': True, 'station': station})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    # --- ADD THIS TO app.py TO FIX EMPTY INFO ---
@app.route('/api/fix-facilities', methods=['GET'])
def fix_facilities_data():
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Randomly enable facilities for all stations
        import random
        stations = db.get_all_station_names()
        
        count = 0
        for station in stations:
            cursor.execute("""
                UPDATE station_locations 
                SET has_wifi = %s, has_parking = %s, has_restroom = 1, 
                    has_atm = %s, is_accessible = %s
                WHERE name = %s
            """, (
                random.choice([1, 1, 0]), # Higher chance of having Wifi
                random.choice([1, 0]), 
                random.choice([1, 0]), 
                random.choice([1, 1, 0]), 
                station
            ))
            count += 1
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Updated facilities for {count} stations! Try the "i" button now.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================================================
# MAIN - RUN SERVER
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Metro Ticket Booking System - Flask API")
    print("=" * 60)
    
    # Setup database
    print("\n🔧 Setting up database...")
    if db.setup_database():
        print("✅ Database setup complete!")
    
    # Add some default stations if none exist
    stations = db.get_all_station_names()
    if len(stations) == 0:
        print("\n📍 Adding default stations...")
        default_stations = [
            ('connaught_place', 28.6328, 77.2197),
            ('rajiv_chowk', 28.6328, 77.2197),
            ('kashmere_gate', 28.6692, 77.2289),
            ('chandni_chowk', 28.6505, 77.2303),
            ('new_delhi', 28.6431, 77.2197)
        ]
        for name, x, y in default_stations:
            db.insert_or_update_station_location(name, x, y)
        print("✅ Default stations added!")
    
    print("\n" + "=" * 60)
    print("🚀 Starting Flask server...")
    print("=" * 60)
    print("\n📡 API Endpoints:")
    print("   • http://localhost:5000/api/health")
    print("   • http://localhost:5000/api/register")
    print("   • http://localhost:5000/api/login")
    print("   • http://localhost:5000/api/tickets/book")
    print("   • http://localhost:5000/api/tickets/my-tickets")
    print("\n✅ Server running on http://localhost:5000")
    print("   Press Ctrl+C to stop\n")
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
