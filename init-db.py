#!/usr/bin/env python
"""Initialize the database schema."""
import os
import sys
from pathlib import Path

# Add alertingSystem to path
sys.path.insert(0, str(Path(__file__).parent / "alertingSystem"))

from db import init_db

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL is required")
    sys.exit(1)

print(f"Initializing database at {database_url}...")
init_db(database_url)
print("Database initialized successfully!")
