#!/usr/bin/env python3
"""State monitor and management utility for tgcf.

This script provides utilities to monitor and manage the state of tgcf sessions
stored in MongoDB.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from pymongo import MongoClient
from tgcf.state_manager import StateManager, get_state_manager
from tgcf.config import MONGO_CON_STR


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def get_mongodb_client() -> Optional[MongoClient]:
    """Get MongoDB client connection."""
    if not MONGO_CON_STR:
        logging.error("MongoDB connection string not found in environment variables")
        return None
    
    try:
        client = MongoClient(MONGO_CON_STR)
        # Test connection
        client.admin.command('ping')
        return client
    except Exception as e:
        logging.error(f"Failed to connect to MongoDB: {e}")
        return None


def display_sessions(state_manager: StateManager):
    """Display all available sessions."""
    sessions = state_manager.get_all_sessions()
    
    if not sessions:
        print("No sessions found.")
        return
    
    print(f"\n{'='*80}")
    print("TGCF SESSIONS")
    print(f"{'='*80}")
    
    for i, session in enumerate(sessions, 1):
        print(f"\n{i}. Session ID: {session['session_id']}")
        print(f"   Last Activity: {session['last_activity']}")
        print(f"   State Types: {', '.join(session['state_types'])}")
        
        # Check if session ended
        session_data = state_manager.state_collection.find_one({
            "session_id": session['session_id'],
            "session_ended": {"$exists": True}
        })
        
        if session_data:
            print(f"   Status: ENDED ({session_data.get('end_reason', 'unknown')})")
            print(f"   End Time: {session_data.get('session_ended', 'unknown')}")
        else:
            print(f"   Status: ACTIVE")


def display_session_details(state_manager: StateManager, session_id: str):
    """Display detailed information about a specific session."""
    states = state_manager.state_collection.find({"session_id": session_id})
    
    print(f"\n{'='*80}")
    print(f"SESSION DETAILS: {session_id}")
    print(f"{'='*80}")
    
    for state in states:
        print(f"\nState Type: {state['state_type']}")
        print(f"Last Updated: {state['last_updated']}")
        print(f"Data: {state['state_data']}")


def cleanup_old_sessions(state_manager: StateManager, keep_count: int = 5):
    """Clean up old sessions."""
    sessions_before = len(state_manager.get_all_sessions())
    state_manager.cleanup_old_sessions(keep_count)
    sessions_after = len(state_manager.get_all_sessions())
    
    cleaned = sessions_before - sessions_after
    print(f"Cleaned up {cleaned} old sessions. Kept {sessions_after} recent sessions.")


def export_session_data(state_manager: StateManager, session_id: str, output_file: str):
    """Export session data to a file."""
    states = list(state_manager.state_collection.find({"session_id": session_id}))
    
    if not states:
        print(f"No data found for session: {session_id}")
        return
    
    try:
        import json
        with open(output_file, 'w') as f:
            # Convert datetime objects to strings for JSON serialization
            for state in states:
                if 'last_updated' in state:
                    state['last_updated'] = state['last_updated'].isoformat()
                if 'session_ended' in state:
                    state['session_ended'] = state['session_ended'].isoformat()
            
            json.dump(states, f, indent=2, default=str)
        
        print(f"Session data exported to: {output_file}")
    except Exception as e:
        print(f"Failed to export session data: {e}")


def main():
    """Main function for state monitor CLI."""
    setup_logging()
    
    # Get MongoDB client
    client = get_mongodb_client()
    if not client:
        sys.exit(1)
    
    # Initialize state manager
    state_manager = StateManager(client)
    
    if len(sys.argv) < 2:
        print("Usage: python state_monitor.py <command> [options]")
        print("\nCommands:")
        print("  list                     - List all sessions")
        print("  show <session_id>        - Show details of a specific session")
        print("  cleanup [keep_count]     - Clean up old sessions (default: keep 5)")
        print("  export <session_id> <file> - Export session data to file")
        print("  stats                    - Show database statistics")
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        display_sessions(state_manager)
    
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: python state_monitor.py show <session_id>")
            return
        session_id = sys.argv[2]
        display_session_details(state_manager, session_id)
    
    elif command == "cleanup":
        keep_count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        cleanup_old_sessions(state_manager, keep_count)
    
    elif command == "export":
        if len(sys.argv) < 4:
            print("Usage: python state_monitor.py export <session_id> <output_file>")
            return
        session_id = sys.argv[2]
        output_file = sys.argv[3]
        export_session_data(state_manager, session_id, output_file)
    
    elif command == "stats":
        total_sessions = len(state_manager.get_all_sessions())
        total_documents = state_manager.state_collection.count_documents({})
        
        print(f"\n{'='*50}")
        print("DATABASE STATISTICS")
        print(f"{'='*50}")
        print(f"Total Sessions: {total_sessions}")
        print(f"Total Documents: {total_documents}")
        print(f"Collection Name: {state_manager.state_collection.name}")
        print(f"Database Name: {state_manager.state_collection.database.name}")
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'python state_monitor.py' without arguments to see usage help.")


if __name__ == "__main__":
    main()
