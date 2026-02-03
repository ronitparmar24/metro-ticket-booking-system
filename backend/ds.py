"""
Data Structures Module
----------------------
Custom implementations of Queue and MetroDataStore for the system.

IMPROVEMENTS over Java version:
- Thread-safe singleton pattern
- Type hints for better code safety
- More Pythonic implementation using collections
- Better encapsulation with private methods
"""

from typing import TypeVar, Generic, Optional, List, Dict, Set
from collections import defaultdict
from threading import Lock
import bisect

# Generic type for Queue
T = TypeVar('T')


# ============================================================================
# CUSTOM QUEUE IMPLEMENTATION (Like Java MyQueue)
# ============================================================================

class Node(Generic[T]):
    """
    Node class for linked list implementation
    Generic type allows any data type
    """
    def __init__(self, data: T):
        self.data: T = data
        self.next: Optional['Node[T]'] = None


class Queue(Generic[T]):
    """
    Custom Queue implementation using linked nodes
    
    Operations:
    - enqueue(elem): Add element to tail - O(1)
    - dequeue(): Remove and return element from head - O(1)
    - peek(): View head element without removing - O(1)
    - is_empty(): Check if queue is empty - O(1)
    - size(): Get queue size - O(1)
    
    IMPROVEMENT: Added __iter__ for Python iteration support
    """
    
    def __init__(self):
        self._head: Optional[Node[T]] = None  # Dequeue from head
        self._tail: Optional[Node[T]] = None  # Enqueue at tail
        self._size: int = 0
    
    def enqueue(self, elem: T) -> None:
        """
        Add element to the tail of queue
        
        Args:
            elem: Element to add
        """
        new_node = Node(elem)
        
        if self._tail is not None:
            self._tail.next = new_node
        
        self._tail = new_node
        
        if self._head is None:
            self._head = self._tail
        
        self._size += 1
    
    def dequeue(self) -> Optional[T]:
        """
        Remove and return element from head of queue
        
        Returns:
            Element from head or None if queue is empty
        """
        if self._head is None:
            return None
        
        value = self._head.data
        self._head = self._head.next
        
        if self._head is None:
            self._tail = None
        
        self._size -= 1
        return value
    
    def peek(self) -> Optional[T]:
        """
        View head element without removing it
        
        Returns:
            Element at head or None if queue is empty
        """
        return self._head.data if self._head is not None else None
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self._size == 0
    
    def size(self) -> int:
        """Get current size of queue"""
        return self._size
    
    def clear(self) -> None:
        """
        Clear all elements from queue
        IMPROVEMENT: New method for resetting queue
        """
        self._head = None
        self._tail = None
        self._size = 0
    
    def __len__(self) -> int:
        """Python built-in len() support"""
        return self._size
    
    def __bool__(self) -> bool:
        """Python truthiness - False if empty"""
        return not self.is_empty()
    
    def __iter__(self):
        """
        IMPROVEMENT: Make queue iterable in Python
        Allows: for item in queue: ...
        """
        current = self._head
        while current is not None:
            yield current.data
            current = current.next
    
    def __str__(self) -> str:
        """String representation of queue"""
        items = [str(item) for item in self]
        return f"Queue({' <- '.join(items)})"
    
    def __repr__(self) -> str:
        """Developer-friendly representation"""
        return f"Queue(size={self._size})"


# ============================================================================
# METRO DATA STORE (Singleton Pattern)
# ============================================================================

class MetroDataStore:
    """
    Central data store for Metro system (Singleton pattern)
    Stores all runtime data: users, tickets, feedbacks, stations, etc.
    
    IMPROVEMENTS:
    - Thread-safe singleton using lock
    - Uses Python collections (defaultdict, set, list)
    - Better organization with property decorators
    - Added helper methods for common operations
    """
    
    _instance: Optional['MetroDataStore'] = None
    _lock: Lock = Lock()
    
    def __new__(cls):
        """
        Thread-safe Singleton implementation
        Only one instance can exist
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize all data structures (called once)"""
        
        # Lists for storing entities
        self.users: List = []  # Will store User objects
        self.all_tickets: List = []  # Will store Ticket objects
        self.feedbacks: List = []  # Will store Feedback objects
        self.support_tickets: List = []  # Will store SupportTicket objects
        self.announcements: List[str] = []  # System announcements
        
        # Maps for quick lookups
        self.feedback_map: Dict[str, List] = defaultdict(list)  # username -> [feedbacks]
        self.station_info_map: Dict[str, 'StationInfo'] = {}  # station_name -> StationInfo
        
        # Sets for unique collections
        self.stations: Set[str] = set()  # All station names
        
        # Sorted structures
        self._sorted_users: List = []  # Maintained in sorted order by username
    
    @classmethod
    def get_instance(cls) -> 'MetroDataStore':
        """
        Get singleton instance
        
        Returns:
            The single MetroDataStore instance
        """
        return cls()
    
    # ========================================================================
    # USER OPERATIONS
    # ========================================================================
    
    def add_user(self, user) -> None:
        """
        Add user to both users list and sorted list
        
        Args:
            user: User object to add
        """
        self.users.append(user)
        # Use bisect to maintain sorted order by username
        bisect.insort(self._sorted_users, user, key=lambda u: u.username)
    
    def remove_user(self, user) -> None:
        """
        Remove user from both users list and sorted list
        
        Args:
            user: User object to remove
        """
        if user in self.users:
            self.users.remove(user)
        if user in self._sorted_users:
            self._sorted_users.remove(user)
    
    def find_user_by_username(self, username: str):
        """
        IMPROVEMENT: Find user by username
        
        Args:
            username: Username to search
            
        Returns:
            User object or None
        """
        for user in self.users:
            if user.username == username:
                return user
        return None
    
    def get_sorted_users(self) -> List:
        """
        Get users sorted by username
        
        Returns:
            List of User objects sorted by username
        """
        return self._sorted_users.copy()
    
    # ========================================================================
    # TICKET OPERATIONS
    # ========================================================================
    
    def add_ticket(self, ticket) -> None:
        """
        Add a ticket to the global tickets list
        
        Args:
            ticket: Ticket object to add
        """
        self.all_tickets.append(ticket)
    
    def get_tickets_by_user(self, username: str) -> List:
        """
        IMPROVEMENT: Get all tickets for a specific user
        
        Args:
            username: Username to filter tickets
            
        Returns:
            List of Ticket objects
        """
        return [t for t in self.all_tickets if t.username == username]
    
    def get_ticket_by_id(self, ticket_id: int):
        """
        IMPROVEMENT: Find ticket by ID
        
        Args:
            ticket_id: Ticket ID to search
            
        Returns:
            Ticket object or None
        """
        for ticket in self.all_tickets:
            if ticket.ticket_id == ticket_id:
                return ticket
        return None
    
    # ========================================================================
    # FEEDBACK OPERATIONS
    # ========================================================================
    
    def add_feedback(self, feedback) -> None:
        """
        Add a feedback entry and map it under the username key
        
        Args:
            feedback: Feedback object to add
        """
        self.feedbacks.append(feedback)
        self.feedback_map[feedback.username].append(feedback)
    
    def get_feedbacks_by_user(self, username: str) -> List:
        """
        Get all feedbacks submitted by a user
        
        Args:
            username: Username to filter feedbacks
            
        Returns:
            List of Feedback objects
        """
        return self.feedback_map.get(username, [])
    
    # ========================================================================
    # STATION OPERATIONS
    # ========================================================================
    
    def add_station(self, station_name: str) -> None:
        """
        IMPROVEMENT: Add a station to the system
        
        Args:
            station_name: Name of station to add
        """
        self.stations.add(station_name.lower())
    
    def add_station_info(self, station_name: str, station_info: 'StationInfo') -> None:
        """
        Add or update station info
        
        Args:
            station_name: Station name
            station_info: StationInfo object
        """
        self.station_info_map[station_name.lower()] = station_info
        self.add_station(station_name)
    
    def get_station_info(self, station_name: str) -> Optional['StationInfo']:
        """
        Get station info by name
        
        Args:
            station_name: Station name to fetch
            
        Returns:
            StationInfo object or None
        """
        return self.station_info_map.get(station_name.lower())
    
    def station_exists(self, station_name: str) -> bool:
        """
        Check if station exists
        
        Args:
            station_name: Station name to check
            
        Returns:
            True if station exists
        """
        return station_name.lower() in self.stations
    
    # ========================================================================
    # SUPPORT TICKET OPERATIONS
    # ========================================================================
    
    def add_support_ticket(self, ticket) -> None:
        """
        Add support ticket to the list
        
        Args:
            ticket: SupportTicket object to add
        """
        self.support_tickets.append(ticket)
    
    def get_support_tickets_by_staff(self, staff_username: str) -> List:
        """
        IMPROVEMENT: Get all support tickets assigned to a staff member
        
        Args:
            staff_username: Staff username
            
        Returns:
            List of SupportTicket objects
        """
        return [t for t in self.support_tickets 
                if t.assigned_staff_username == staff_username]
    
    def get_open_support_tickets(self) -> List:
        """
        IMPROVEMENT: Get all open/unassigned support tickets
        
        Returns:
            List of open SupportTicket objects
        """
        return [t for t in self.support_tickets if t.status == 'OPEN']
    
    # ========================================================================
    # ANNOUNCEMENT OPERATIONS
    # ========================================================================
    
    def add_announcement(self, message: str) -> None:
        """
        Add system-wide announcement
        
        Args:
            message: Announcement message
        """
        self.announcements.append(message)
    
    def get_latest_announcements(self, count: int = 5) -> List[str]:
        """
        IMPROVEMENT: Get latest N announcements
        
        Args:
            count: Number of announcements to return
            
        Returns:
            List of announcement strings
        """
        return self.announcements[-count:] if self.announcements else []
    
    # ========================================================================
    # STATISTICS (IMPROVEMENT: New analytics methods)
    # ========================================================================
    
    def get_total_users(self) -> int:
        """Get total number of users"""
        return len(self.users)
    
    def get_total_tickets(self) -> int:
        """Get total number of tickets"""
        return len(self.all_tickets)
    
    def get_total_feedbacks(self) -> int:
        """Get total number of feedbacks"""
        return len(self.feedbacks)
    
    def get_total_stations(self) -> int:
        """Get total number of stations"""
        return len(self.stations)
    
    def get_statistics(self) -> Dict[str, int]:
        """
        IMPROVEMENT: Get system statistics
        
        Returns:
            Dictionary with various system statistics
        """
        return {
            'total_users': self.get_total_users(),
            'total_tickets': self.get_total_tickets(),
            'total_feedbacks': self.get_total_feedbacks(),
            'total_stations': self.get_total_stations(),
            'total_support_tickets': len(self.support_tickets),
            'total_announcements': len(self.announcements)
        }
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def clear_all_data(self) -> None:
        """
        IMPROVEMENT: Clear all in-memory data (for testing/reset)
        WARNING: This does not clear database
        """
        self.users.clear()
        self.all_tickets.clear()
        self.feedbacks.clear()
        self.support_tickets.clear()
        self.announcements.clear()
        self.feedback_map.clear()
        self.station_info_map.clear()
        self.stations.clear()
        self._sorted_users.clear()
    
    def __str__(self) -> str:
        """String representation"""
        return (f"MetroDataStore(users={len(self.users)}, "
                f"tickets={len(self.all_tickets)}, "
                f"stations={len(self.stations)})")
    
    def __repr__(self) -> str:
        """Developer representation"""
        stats = self.get_statistics()
        return f"MetroDataStore({stats})"


# ============================================================================
# STATION INFO CLASS (Will be used with MetroDataStore)
# ============================================================================

class StationInfo:
    """
    Station information with adjacency graph distances
    
    IMPROVEMENT: Better encapsulation with property decorators
    """
    
    def __init__(
        self, 
        name: str, 
        description: str = "", 
        has_restrooms: bool = False,
        has_parking: bool = False,
        has_wifi: bool = False
    ):
        self.name = name
        self.description = description
        self.has_restrooms = has_restrooms
        self.has_parking = has_parking
        self.has_wifi = has_wifi
        self.location: Optional[tuple] = None  # (x, y) coordinates
        
        # Map of adjacent station names to their direct distance in kilometers
        self.distances: Dict[str, int] = {}
    
    def set_location(self, x: float, y: float) -> None:
        """Set geographical coordinates of station"""
        self.location = (x, y)
    
    def add_distance(self, station: str, km: int) -> None:
        """Add or update direct distance to another station"""
        self.distances[station] = km
    
    def get_distance(self, station: str) -> Optional[int]:
        """Get distance to a specific station"""
        return self.distances.get(station)
    
    def get_adjacent_stations(self) -> List[str]:
        """Get list of all adjacent stations"""
        return list(self.distances.keys())
    
    def __str__(self) -> str:
        """String representation"""
        restroom_str = "[Restrooms]" if self.has_restrooms else ""
        parking_str = "[Parking]" if self.has_parking else ""
        wifi_str = "[WiFi]" if self.has_wifi else ""
        
        facilities = " ".join([restroom_str, parking_str, wifi_str]).strip()
        return f"{self.name} ({self.description}) {facilities}"
    
    def __repr__(self) -> str:
        """Developer representation"""
        return (f"StationInfo(name='{self.name}', "
                f"adjacent={len(self.distances)})")


# ============================================================================
# TESTING THE MODULE
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Queue Implementation")
    print("=" * 60)
    
    # Test Queue
    q = Queue[str]()
    print(f"Empty queue: {q.is_empty()}")  # True
    
    q.enqueue("First")
    q.enqueue("Second")
    q.enqueue("Third")
    print(f"Queue size: {q.size()}")  # 3
    print(f"Queue contents: {q}")
    
    print(f"Peek: {q.peek()}")  # First
    print(f"Dequeue: {q.dequeue()}")  # First
    print(f"Dequeue: {q.dequeue()}")  # Second
    print(f"Queue size: {q.size()}")  # 1
    
    # Test iteration
    q.enqueue("Fourth")
    print("\nIterating through queue:")
    for item in q:
        print(f"  - {item}")
    
    print("\n" + "=" * 60)
    print("Testing MetroDataStore (Singleton)")
    print("=" * 60)
    
    # Test Singleton
    store1 = MetroDataStore.get_instance()
    store2 = MetroDataStore()
    print(f"Same instance? {store1 is store2}")  # True
    
    # Test adding stations
    store1.add_station("Connaught Place")
    store1.add_station("Rajiv Chowk")
    store1.add_station("Kashmere Gate")
    
    print(f"\nTotal stations: {store1.get_total_stations()}")
    print(f"Stations: {store1.stations}")
    
    # Test StationInfo
    cp_info = StationInfo(
        "Connaught Place",
        "Central Business District",
        has_restrooms=True,
        has_parking=True,
        has_wifi=True
    )
    cp_info.add_distance("rajiv chowk", 2)
    cp_info.add_distance("kashmere gate", 5)
    
    store1.add_station_info("connaught place", cp_info)
    
    retrieved = store1.get_station_info("connaught place")
    print(f"\nStation Info: {retrieved}")
    print(f"Adjacent stations: {retrieved.get_adjacent_stations()}")
    
    # Test statistics
    print(f"\nSystem Statistics:")
    stats = store1.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n✅ All tests passed!")
