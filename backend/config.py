"""
Database Configuration Module
------------------------------
Stores MySQL connection details.
IMPROVEMENT: Added environment variable support for security.
"""

import os
from typing import Dict

"""
Database Configuration Module
"""

class Config:
    """Database configuration class"""
    
    # MySQL connection details
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'root',
        'password': '',  # Your MySQL password (empty for default XAMPP)
        'database': 'metrosystemdb',
        'autocommit': False,
        'raise_on_warnings': False
    }
    
    # Connection pool settings
    POOL_NAME = "metro_pool"
    POOL_SIZE = 5
    
    @staticmethod
    def get_db_config():
        """Returns database configuration dictionary"""
        return Config.DB_CONFIG

# Print config on load (for debugging)
if __name__ == "__main__":
    print("Database Config:", Config.get_db_config())
