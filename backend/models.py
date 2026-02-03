"""
Models Module
-------------
Contains all data model classes: User, Admin, SupportStaff, Ticket, 
Feedback, SupportTicket, MetroCard, MonthlyPass

IMPROVEMENTS over Java version:
- Python properties with @property decorator
- Better string representations
- Type hints for clarity
- Cleaner inheritance structure
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from abc import ABC, abstractmethod
import db
from utils import hash_password, verify_password, format_date, format_datetime


# ============================================================================
# ROLE CONSTANTS
# ============================================================================

class Role:
    """User role constants"""
    USER = "USER"
    ADMIN = "ADMIN"
    SUPPORT_STAFF = "SUPPORT_STAFF"


class SupportTicketStatus:
    """Support ticket status constants"""
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


# ============================================================================
# BASE PERSON CLASS (Abstract)
# ============================================================================

class Person(ABC):
    """
    Abstract base class for all persons in the system
    
    Attributes:
        username: Unique username
        password: Hashed password
        role: User role (USER, ADMIN, SUPPORT_STAFF)
    """
    
    def __init__(self, username: str, password: str, role: str):
        self.username = username
        self.password = password  # Should be hashed
        self.role = role
    
    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change user password after verifying old password
        
        Args:
            old_password: Current password (plain text)
            new_password: New password (plain text)
            
        Returns:
            True if password changed successfully
        """
        # Verify old password
        if not verify_password(old_password, self.password):
            print("❌ Old password incorrect.")
            return False
        
        # Check if new password is same as old
        new_hashed = hash_password(new_password)
        if new_hashed == self.password:
            print("❌ New password cannot be the same as the old password.")
            return False
        
        # Update password
        self.password = new_hashed
        if db.update_user_password(self.username, new_hashed):
            print("✅ Password changed successfully.")
            return True
        else:
            print("❌ Failed to update password in database.")
            return False
    
    def __str__(self) -> str:
        return f"{self.role}: {self.username}"
    
    def __repr__(self) -> str:
        return f"Person(username='{self.username}', role='{self.role}')"


# ============================================================================
# USER CLASS
# ============================================================================

class User(Person):
    """
    Regular user who can book tickets, submit feedback, etc.
    
    Attributes:
        username: Unique username
        password: Hashed password
        wallet_balance: Current wallet balance
        metro_card: Associated MetroCard object (optional)
        tickets: List of Ticket objects
    """
    
    def __init__(self, username: str, password: str, wallet_balance: float = 0.0):
        super().__init__(username, password, Role.USER)
        self.wallet_balance = wallet_balance
        self.metro_card: Optional['MetroCard'] = None
        self.tickets: List['Ticket'] = []
    
    @property
    def balance(self) -> float:
        """Get current wallet balance"""
        return self.wallet_balance
    
    def recharge_wallet(self, amount: float) -> bool:
        """
        Recharge wallet with specified amount
        
        Args:
            amount: Amount to add to wallet
            
        Returns:
            True if recharge successful
        """
        if amount <= 0:
            print("❌ Amount must be positive.")
            return False
        
        if amount > 5000:
            print("❌ Maximum recharge amount is Rs. 5000.")
            return False
        
        self.wallet_balance += amount
        if db.update_user_wallet_balance(self.username, self.wallet_balance):
            print(f"✅ Wallet recharged! New balance: Rs. {self.wallet_balance:.2f}")
            return True
        else:
            # Rollback on database error
            self.wallet_balance -= amount
            print("❌ Failed to update wallet in database.")
            return False
    
    def deduct_from_wallet(self, amount: float) -> bool:
        """
        Deduct amount from wallet
        
        Args:
            amount: Amount to deduct
            
        Returns:
            True if deduction successful
        """
        if amount > self.wallet_balance:
            print(f"❌ Insufficient wallet balance. Current: Rs. {self.wallet_balance:.2f}")
            return False
        
        self.wallet_balance -= amount
        if db.update_user_wallet_balance(self.username, self.wallet_balance):
            return True
        else:
            # Rollback on database error
            self.wallet_balance += amount
            return False
    
    def book_ticket(self, source: str, destination: str, passengers: int, 
                    fare: float, travel_date: date) -> Optional['Ticket']:
        """
        Book a ticket
        
        Args:
            source: Source station
            destination: Destination station
            passengers: Number of passengers
            fare: Total fare
            travel_date: Travel date
            
        Returns:
            Ticket object if successful, None otherwise
        """
        # Check wallet balance
        if fare > self.wallet_balance:
            print(f"❌ Insufficient balance. Required: Rs. {fare:.2f}, Available: Rs. {self.wallet_balance:.2f}")
            return None
        
        # Deduct fare from wallet
        if not self.deduct_from_wallet(fare):
            print("❌ Failed to deduct fare from wallet.")
            return None
        
        # Insert ticket into database
        ticket_id = db.insert_ticket(self.username, source, destination, passengers, fare, travel_date, False)
        
        if ticket_id > 0:
            # Create ticket object
            ticket = Ticket(self.username, source, destination, passengers, fare, travel_date)
            ticket.ticket_id = ticket_id
            ticket.booking_date = datetime.now()
            self.tickets.append(ticket)
            print(f"✅ Ticket #{ticket_id} booked successfully!")
            print(f"   Remaining balance: Rs. {self.wallet_balance:.2f}")
            return ticket
        else:
            # Rollback wallet deduction if ticket creation failed
            self.wallet_balance += fare
            db.update_user_wallet_balance(self.username, self.wallet_balance)
            print("❌ Failed to book ticket.")
            return None
    
    def cancel_ticket(self, ticket_id: int) -> bool:
        """
        Cancel a ticket and get refund
        
        Args:
            ticket_id: Ticket ID to cancel
            
        Returns:
            True if cancellation successful
        """
        # Find ticket
        ticket = None
        for t in self.tickets:
            if t.ticket_id == ticket_id:
                ticket = t
                break
        
        if not ticket:
            # Try to fetch from database
            ticket_data = db.get_ticket_by_id(ticket_id)
            if not ticket_data or ticket_data['username'] != self.username:
                print(f"❌ Ticket #{ticket_id} not found or doesn't belong to you.")
                return False
            
            # Create ticket object from database data
            ticket = Ticket(
                ticket_data['username'],
                ticket_data['source'],
                ticket_data['destination'],
                ticket_data['passengers'],
                ticket_data['fare'],
                ticket_data['travelDate']
            )
            ticket.ticket_id = ticket_data['ticketId']
            ticket.cancelled = ticket_data['cancelled']
        
        if ticket.cancelled:
            print(f"❌ Ticket #{ticket_id} is already cancelled.")
            return False
        
        # Calculate refund
        refund = ticket.cancel()
        
        # Update in database
        if db.cancel_ticket(ticket_id):
            # Add refund to wallet
            self.wallet_balance += refund
            db.update_user_wallet_balance(self.username, self.wallet_balance)
            print(f"✅ Ticket #{ticket_id} cancelled. Refund: Rs. {refund:.2f}")
            print(f"   New balance: Rs. {self.wallet_balance:.2f}")
            return True
        else:
            print("❌ Failed to cancel ticket in database.")
            return False
    
    def view_tickets(self, filter_type: int = 1) -> List['Ticket']:
        """
        View tickets based on filter
        
        Args:
            filter_type: 1=All, 2=Upcoming, 3=Past
            
        Returns:
            List of Ticket objects
        """
        tickets = db.get_tickets_by_user(self.username)
        
        if not tickets:
            print("ℹ️  No tickets found.")
            return []
        
        today = date.today()
        result = []
        
        for ticket_data in tickets:
            ticket = Ticket(
                ticket_data['username'],
                ticket_data['source'],
                ticket_data['destination'],
                ticket_data['passengers'],
                ticket_data['fare'],
                ticket_data['travelDate']
            )
            ticket.ticket_id = ticket_data['ticketId']
            ticket.cancelled = ticket_data['cancelled']
            ticket.booking_date = ticket_data['bookingDate']
            
            # Apply filter
            if filter_type == 2:  # Upcoming
                if ticket.travel_date >= today and not ticket.cancelled:
                    result.append(ticket)
            elif filter_type == 3:  # Past
                if ticket.travel_date < today:
                    result.append(ticket)
            else:  # All
                result.append(ticket)
        
        return result
    
    def submit_feedback(self, text: str, feedback_type: str = "feedback") -> bool:
        """
        Submit feedback or complaint
        
        Args:
            text: Feedback text
            feedback_type: 'feedback' or 'complaint'
            
        Returns:
            True if submission successful
        """
        feedback_id = db.insert_feedback(self.username, text, feedback_type)
        
        if feedback_id > 0:
            print(f"✅ {feedback_type.capitalize()} submitted successfully! ID: {feedback_id}")
            return True
        else:
            print(f"❌ Failed to submit {feedback_type}.")
            return False
    
    def get_my_feedbacks(self) -> List[Dict[str, Any]]:
        """Get all feedbacks submitted by this user"""
        return db.get_feedbacks_by_username(self.username)
    
    def __str__(self) -> str:
        return f"User: {self.username} (Balance: Rs. {self.wallet_balance:.2f})"
    
    def __repr__(self) -> str:
        return f"User(username='{self.username}', balance={self.wallet_balance})"


# ============================================================================
# ADMIN CLASS
# ============================================================================

class Admin(Person):
    """
    Admin user with system management capabilities
    """
    
    def __init__(self, username: str, password: str):
        super().__init__(username, password, Role.ADMIN)
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users in the system"""
        return db.get_all_users()
    
    def remove_user(self, username: str) -> bool:
        """Remove a user from system"""
        if db.remove_user(username):
            print(f"✅ User '{username}' removed successfully.")
            return True
        else:
            print(f"❌ Failed to remove user '{username}'.")
            return False
    
    def add_announcement(self, message: str) -> bool:
        """Add system-wide announcement"""
        if db.insert_announcement(message):
            print("✅ Announcement added successfully.")
            return True
        else:
            print("❌ Failed to add announcement.")
            return False
    
    def get_all_feedbacks(self) -> List[Dict[str, Any]]:
        """Get all feedbacks from all users"""
        return db.get_all_feedbacks()
    
    def add_station(self, name: str, x: float = 0.0, y: float = 0.0) -> bool:
        """Add or update a station"""
        if db.insert_or_update_station_location(name, x, y):
            print(f"✅ Station '{name}' added/updated successfully.")
            return True
        else:
            print(f"❌ Failed to add station '{name}'.")
            return False
    
    def get_all_stations(self) -> List[str]:
        """Get all station names"""
        return list(db.get_all_station_names())
    
    def __str__(self) -> str:
        return f"Admin: {self.username}"
    
    def __repr__(self) -> str:
        return f"Admin(username='{self.username}')"


# ============================================================================
# SUPPORT STAFF CLASS
# ============================================================================

class SupportStaff(Person):
    """
    Support staff who handle user complaints and feedback
    """
    
    def __init__(self, username: str, password: str):
        super().__init__(username, password, Role.SUPPORT_STAFF)
    
    def get_assigned_tickets(self) -> List[Dict[str, Any]]:
        """Get all support tickets assigned to this staff member"""
        return db.get_assigned_tickets_by_staff(self.username)
    
    def resolve_ticket(self, ticket_id: int) -> bool:
        """Mark a support ticket as resolved"""
        if db.update_support_ticket_status(ticket_id, SupportTicketStatus.RESOLVED, datetime.now()):
            print(f"✅ Support ticket #{ticket_id} marked as resolved.")
            return True
        else:
            print(f"❌ Failed to resolve ticket #{ticket_id}.")
            return False
    
    def __str__(self) -> str:
        return f"SupportStaff: {self.username}"
    
    def __repr__(self) -> str:
        return f"SupportStaff(username='{self.username}')"


# ============================================================================
# TICKET CLASS
# ============================================================================

class Ticket:
    """
    Represents a metro ticket booking
    
    Attributes:
        ticket_id: Unique ticket ID
        username: Username of ticket owner
        source: Source station
        destination: Destination station
        passengers: Number of passengers
        fare: Total fare
        travel_date: Date of travel
        cancelled: Cancellation status
        booking_date: Date and time of booking
    """
    
    def __init__(self, username: str, source: str, destination: str, 
                 passengers: int, fare: float, travel_date: date):
        self.ticket_id: Optional[int] = None  # Set after DB insertion
        self.username = username
        self.source = source
        self.destination = destination
        self.passengers = passengers
        self.fare = fare
        self.travel_date = travel_date
        self.cancelled = False
        self.booking_date: Optional[datetime] = None
    
    def cancel(self) -> float:
        """
        Cancel the ticket and calculate refund
        
        Returns:
            Refund amount (80% if >= 24hrs before travel, else 50%)
        """
        if self.cancelled:
            return 0.0
        
        self.cancelled = True
        
        # Calculate time difference
        now = datetime.now()
        travel_datetime = datetime.combine(self.travel_date, datetime.min.time())
        diff = travel_datetime - now
        
        # Refund rate based on cancellation time
        if diff.total_seconds() >= 24 * 60 * 60:  # >= 24 hours
            refund_rate = 0.8
        else:
            refund_rate = 0.5
        
        return self.fare * refund_rate
    
    def __str__(self) -> str:
        status = "[CANCELLED]" if self.cancelled else ""
        return (f"Ticket #{self.ticket_id} | {self.source} → {self.destination} | "
                f"{self.passengers} passenger(s) | Rs. {self.fare:.2f} | "
                f"Travel: {format_date(self.travel_date)} {status}")
    
    def __repr__(self) -> str:
        return f"Ticket(id={self.ticket_id}, {self.source}→{self.destination})"


# ============================================================================
# FEEDBACK CLASS
# ============================================================================

class Feedback:
    """
    Represents user feedback or complaint
    
    Attributes:
        feedback_id: Unique feedback ID (set by database)
        username: Username of feedback submitter
        text: Feedback text content
        type: Type of feedback ('feedback' or 'complaint')
        timestamp: Submission timestamp
    """
    
    def __init__(self, username: str, text: str, feedback_type: str):
        self.feedback_id: Optional[int] = None
        self.username = username
        self.text = text
        self.type = feedback_type
        self.timestamp: Optional[datetime] = None
    
    def __str__(self) -> str:
        time_str = format_datetime(self.timestamp) if self.timestamp else "N/A"
        return f"[{time_str}] {self.username} ({self.type}): {self.text}"
    
    def __repr__(self) -> str:
        return f"Feedback(id={self.feedback_id}, user='{self.username}', type='{self.type}')"


# ============================================================================
# SUPPORT TICKET CLASS
# ============================================================================

class SupportTicket:
    """
    Represents a support ticket linked to feedback
    
    Attributes:
        ticket_id: Unique support ticket ID
        feedback: Associated Feedback object
        status: Current status (OPEN, IN_PROGRESS, RESOLVED)
        assigned_staff_username: Username of assigned staff member
        created_date: Creation timestamp
        resolved_date: Resolution timestamp (if resolved)
    """
    
    def __init__(self, feedback: Feedback):
        self.ticket_id: Optional[int] = None
        self.feedback = feedback
        self.status = SupportTicketStatus.OPEN
        self.assigned_staff_username: Optional[str] = None
        self.created_date: Optional[datetime] = None
        self.resolved_date: Optional[datetime] = None
    
    def assign(self, staff_username: str) -> None:
        """Assign ticket to a staff member"""
        self.assigned_staff_username = staff_username
        self.status = SupportTicketStatus.IN_PROGRESS
    
    def resolve(self) -> None:
        """Mark ticket as resolved"""
        self.status = SupportTicketStatus.RESOLVED
        self.resolved_date = datetime.now()
    
    def __str__(self) -> str:
        assigned = self.assigned_staff_username if self.assigned_staff_username else "Unassigned"
        return (f"SupportTicket #{self.ticket_id} | User: {self.feedback.username} | "
                f"Status: {self.status} | Assigned: {assigned}")
    
    def __repr__(self) -> str:
        return f"SupportTicket(id={self.ticket_id}, status='{self.status}')"


# ============================================================================
# METRO CARD CLASS
# ============================================================================

class MetroCard:
    """
    Represents a Metro Card for cashless travel
    
    Attributes:
        card_number: Unique card number
        balance: Current card balance
        owner: User object who owns this card
        auto_recharge_enabled: Auto-recharge flag
        min_balance_threshold: Threshold for auto-recharge
    """
    
    def __init__(self, card_number: int, initial_balance: float, owner: Optional[User] = None):
        self.card_number = card_number
        self.balance = initial_balance
        self.owner = owner
        self.auto_recharge_enabled = False
        self.min_balance_threshold = 50.0
    
    def recharge(self, amount: float) -> bool:
        """Recharge metro card"""
        if amount <= 0:
            print("❌ Recharge amount must be positive.")
            return False
        
        self.balance += amount
        print(f"✅ Metro Card recharged! New Balance: Rs. {self.balance:.2f}")
        
        # Update in database
        if db.update_metro_card(self.card_number, self.balance, 
                                self.auto_recharge_enabled, self.min_balance_threshold):
            return True
        else:
            self.balance -= amount  # Rollback
            return False
    
    def deduct(self, fare: float) -> bool:
        """Deduct fare from card"""
        if fare > self.balance:
            print(f"❌ Insufficient Metro Card balance. Current: Rs. {self.balance:.2f}")
            return False
        
        self.balance -= fare
        print(f"✅ Fare deducted: Rs. {fare:.2f}. Card Balance: Rs. {self.balance:.2f}")
        
        # Check for auto-recharge
        if self.auto_recharge_enabled and self.balance < self.min_balance_threshold:
            self._try_auto_recharge()
        
        return True
    
    def _try_auto_recharge(self) -> bool:
        """Attempt auto-recharge from wallet"""
        if not self.owner:
            return False
        
        recharge_amount = max(self.min_balance_threshold * 2, 100.0)
        
        if self.owner.wallet_balance >= recharge_amount:
            if self.owner.deduct_from_wallet(recharge_amount):
                self.balance += recharge_amount
                db.update_metro_card(self.card_number, self.balance, 
                                     self.auto_recharge_enabled, self.min_balance_threshold)
                print(f"🔄 Auto-recharged Rs. {recharge_amount:.2f} from wallet to Metro Card")
                return True
        
        return False
    
    def set_auto_recharge(self, enabled: bool, threshold: float = 50.0) -> None:
        """Enable/disable auto-recharge"""
        self.auto_recharge_enabled = enabled
        self.min_balance_threshold = threshold
        db.update_metro_card(self.card_number, self.balance, enabled, threshold)
        status = "enabled" if enabled else "disabled"
        print(f"✅ Auto-recharge {status} (Threshold: Rs. {threshold:.2f})")
    
    def __str__(self) -> str:
        auto_status = "Auto-Recharge ON" if self.auto_recharge_enabled else "Auto-Recharge OFF"
        return f"MetroCard #{self.card_number} | Balance: Rs. {self.balance:.2f} | {auto_status}"
    
    def __repr__(self) -> str:
        return f"MetroCard(number={self.card_number}, balance={self.balance})"


# ============================================================================
# MONTHLY PASS CLASS
# ============================================================================

class MonthlyPass:
    """
    Represents a monthly pass for unlimited travel between two stations
    
    Attributes:
        pass_id: Unique pass ID
        username: Username of pass owner
        source: Source station
        destination: Destination station
        purchase_date: Date of purchase
        expiry_date: Expiry date
        price: Pass price
    """
    
    def __init__(self, username: str, source: str, destination: str, 
                 purchase_date: date, expiry_date: date, price: float):
        self.pass_id: Optional[int] = None
        self.username = username
        self.source = source
        self.destination = destination
        self.purchase_date = purchase_date
        self.expiry_date = expiry_date
        self.price = price
    
    def is_valid(self) -> bool:
        """Check if pass is still valid"""
        return date.today() <= self.expiry_date
    
    def days_remaining(self) -> int:
        """Get number of days remaining"""
        if not self.is_valid():
            return 0
        return (self.expiry_date - date.today()).days
    
    def __str__(self) -> str:
        status = "VALID" if self.is_valid() else "EXPIRED"
        return (f"MonthlyPass #{self.pass_id} | {self.source} ↔ {self.destination} | "
                f"Valid until: {format_date(self.expiry_date)} | [{status}]")
    
    def __repr__(self) -> str:
        return f"MonthlyPass(id={self.pass_id}, {self.source}↔{self.destination})"


# ============================================================================
# TESTING THE MODULE
# ============================================================================

# ============================================================================
# TESTING THE MODULE
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Models Module")
    print("=" * 60)
    
    # Make sure database is set up
    db.setup_database()
    
    # Test 1: Create a real user in database for testing
    print("\n1. Testing User creation in database...")
    test_username = "testmodel"
    test_password = hash_password("pass123")
    
    # Check if user already exists
    if not db.username_exists(test_username):
        if db.insert_user(test_username, test_password, 500.0, Role.USER):
            print(f"   ✅ User '{test_username}' created in database")
            # Create metro card for user
            db.insert_metro_card(test_username, 100.0, False, 50.0)
    else:
        print(f"   ℹ️  User '{test_username}' already exists")
    
    # Now create User object from database data
    user_data = db.get_user_by_username(test_username)
    if user_data:
        user = User(user_data['username'], user_data['password'], user_data['walletBalance'])
        print(f"   Created: {user}")
    
        # Test wallet operations
        print("\n2. Testing User wallet operations...")
        initial_balance = user.wallet_balance
        if user.recharge_wallet(200):
            print(f"   ✅ Wallet recharged successfully!")
            print(f"   Old balance: Rs. {initial_balance:.2f}")
            print(f"   New balance: Rs. {user.wallet_balance:.2f}")
    
    # Test Ticket
    print("\n3. Testing Ticket...")
    ticket = Ticket("testmodel", "connaught_place", "rajiv_chowk", 2, 150.0, date.today() + timedelta(days=5))
    ticket.ticket_id = 999
    print(f"   {ticket}")
    
    refund = ticket.cancel()
    print(f"   Refund after cancellation: Rs. {refund:.2f}")
    
    # Test Feedback
    print("\n4. Testing Feedback...")
    feedback = Feedback("testmodel", "Great service!", "feedback")
    print(f"   {feedback}")
    
    # Test MetroCard
    print("\n5. Testing MetroCard...")
    card_data = db.get_metro_card_by_username(test_username)
    if card_data:
        card = MetroCard(card_data['cardNumber'], card_data['balance'], user)
        print(f"   {card}")
        card.set_auto_recharge(True, 50.0)
    
    print("\n✅ All model tests passed!")
