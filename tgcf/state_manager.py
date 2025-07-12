#!/usr/bin/env python3
"""State manager for tgcf.

This module provides persistent state management for tgcf sessions,
including message processing state, forward counts, and application state.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from pymongo import MongoClient


class StateManager:
    """Manages persistent state for tgcf using MongoDB."""
    
    def __init__(self, mongo_client: Optional[MongoClient] = None):
        self.mongo_client = mongo_client
        self.state_collection = None
        self.session_id = str(uuid.uuid4())
        self._session_active = True
        
        if mongo_client:
            self._initialize_collections()
    
    def _initialize_collections(self):
        """Initialize MongoDB collections for state management."""
        try:
            # Get database and collection
            db_name = os.getenv("MONGO_DB_NAME", "tgcf-config")
            col_name = os.getenv("MONGO_STATE_COL_NAME", "tgcf-state")
            
            db = self.mongo_client[db_name]
            self.state_collection = db[col_name]
            
            # Create indexes for better performance
            self.state_collection.create_index(["session_id", "state_type"])
            self.state_collection.create_index(["last_updated"])
            self.state_collection.create_index(["session_ended"])
            
            logging.info(f"State manager initialized with collection: {col_name}")
            
        except Exception as e:
            logging.error(f"Failed to initialize state collections: {e}")
            self.state_collection = None
    
    def save_state(self, state_type: str, state_data: Dict[str, Any], 
                  force_save: bool = False) -> bool:
        """Save state data to MongoDB with improved error handling."""
        if self.state_collection is None:
            logging.warning("State collection not initialized, skipping save")
            return False
        
        if not self._session_active and not force_save:
            logging.debug(f"Session inactive, skipping save for {state_type}")
            return False
        
        try:
            document = {
                "session_id": self.session_id,
                "state_type": state_type,
                "state_data": state_data,
                "last_updated": datetime.utcnow()
            }
            
            # Use upsert to create or update
            result = self.state_collection.replace_one(
                {"session_id": self.session_id, "state_type": state_type},
                document,
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                logging.debug(f"State saved: {state_type} for session {self.session_id}")
                return True
            else:
                logging.debug(f"State unchanged: {state_type}")
                return True  # Still successful, just no changes
                
        except Exception as e:
            logging.error(f"Failed to save state {state_type}: {e}")
            return False
    
    def load_state(self, state_type: str) -> Optional[Dict[str, Any]]:
        """Load state data from MongoDB with fallback to previous sessions."""
        if self.state_collection is None:
            logging.warning("State collection not initialized, cannot load state")
            return None
        
        try:
            # Try to load from current session first
            document = self.state_collection.find_one({
                "session_id": self.session_id,
                "state_type": state_type
            })
            
            if document:
                return document["state_data"]
            
            # If not found in current session, try to load from most recent session
            # that hasn't been explicitly ended
            document = self.state_collection.find_one(
                {
                    "state_type": state_type,
                    "session_ended": {"$exists": False}
                },
                sort=[("last_updated", -1)]
            )
            
            if document:
                logging.info(f"Loaded state {state_type} from previous active session")
                return document["state_data"]
            
            # Last resort: load from any session
            document = self.state_collection.find_one(
                {"state_type": state_type},
                sort=[("last_updated", -1)]
            )
            
            if document:
                logging.info(f"Loaded state {state_type} from previous session")
                return document["state_data"]
            
            return None
            
        except Exception as e:
            logging.error(f"Failed to load state {state_type}: {e}")
            return None
    
    def delete_state(self, state_type: str) -> bool:
        """Delete state data from MongoDB."""
        if self.state_collection is None:
            logging.warning("State collection not initialized, cannot delete state")
            return False
        
        try:
            result = self.state_collection.delete_many({
                "session_id": self.session_id,
                "state_type": state_type
            })
            
            if result.deleted_count > 0:
                logging.info(f"Deleted {result.deleted_count} state records for {state_type}")
                return True
            else:
                logging.warning(f"No state records found to delete for {state_type}")
                return False
                
        except Exception as e:
            logging.error(f"Failed to delete state {state_type}: {e}")
            return False
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions from MongoDB."""
        if self.state_collection is None:
            return []
        
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$session_id",
                        "session_id": {"$first": "$session_id"},
                        "last_activity": {"$max": "$last_updated"},
                        "state_types": {"$addToSet": "$state_type"},
                        "session_ended": {"$first": "$session_ended"},
                        "end_reason": {"$first": "$end_reason"}
                    }
                },
                {
                    "$sort": {"last_activity": -1}
                }
            ]
            
            return list(self.state_collection.aggregate(pipeline))
            
        except Exception as e:
            logging.error(f"Failed to get all sessions: {e}")
            return []
    
    def cleanup_old_sessions(self, keep_count: int = 5) -> bool:
        """Clean up old sessions, keeping only the most recent ones."""
        if self.state_collection is None:
            logging.warning("State collection not initialized, cannot cleanup")
            return False

        try:
            # Get all sessions ordered by last activity
            sessions = self.get_all_sessions()

            if len(sessions) <= keep_count:
                logging.info(f"Only {len(sessions)} sessions found, no cleanup needed")
                return True

            # Get sessions to delete (all except the most recent keep_count)
            sessions_to_delete = sessions[keep_count:]
            session_ids_to_delete = [session["session_id"] for session in sessions_to_delete]

            # Delete old sessions
            result = self.state_collection.delete_many({
                "session_id": {"$in": session_ids_to_delete}
            })

            logging.info(f"Cleaned up {result.deleted_count} old state records from {len(sessions_to_delete)} sessions")
            return True

        except Exception as e:
            logging.error(f"Failed to cleanup old sessions: {e}")
            return False

    def auto_cleanup_sessions(self):
        """Automatically clean up sessions to keep only the latest 5."""
        self.cleanup_old_sessions(keep_count=5)
    
    def save_message_processing_state(self, chat_id: int, last_message_id: int, 
                                    offset: int):
        """Save message processing state for a specific chat."""
        state_data = {
            "chat_id": chat_id,
            "last_message_id": last_message_id,
            "offset": offset,
            "last_processed": datetime.utcnow().isoformat()
        }
        
        self.save_state(f"message_processing_{chat_id}", state_data)
    
    def load_message_processing_state(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Load message processing state for a specific chat."""
        return self.load_state(f"message_processing_{chat_id}")
    
    def save_forward_counts(self, forward_counts: Dict[int, int], force_save: bool = False):
        """Save forward counts for all chats."""
        state_data = {
            "forward_counts": forward_counts,
            "last_reset": datetime.utcnow().isoformat()
        }
        
        self.save_state("forward_counts", state_data, force_save=force_save)
    
    def load_forward_counts(self) -> Dict[int, int]:
        """Load forward counts for all chats."""
        state = self.load_state("forward_counts")
        if state and "forward_counts" in state:
            return state["forward_counts"]
        return {}
    
    def save_application_state(self, mode: str, config_hash: str, 
                             running_since: datetime, active_forwards: List[int]):
        """Save general application state."""
        state_data = {
            "mode": mode,
            "config_hash": config_hash,
            "running_since": running_since.isoformat(),
            "active_forwards": active_forwards,
            "last_heartbeat": datetime.utcnow().isoformat()
        }
        
        self.save_state("application", state_data)
    
    def load_application_state(self) -> Optional[Dict[str, Any]]:
        """Load general application state."""
        return self.load_state("application")
    
    def save_random_message_state(self, chat_id: int, last_random_time: datetime, 
                                random_count: int, total_sent: int):
        """Save random message handler state."""
        state_data = {
            "chat_id": chat_id,
            "last_random_time": last_random_time.isoformat(),
            "random_count": random_count,
            "total_sent": total_sent
        }
        
        self.save_state(f"random_messages_{chat_id}", state_data)
    
    def load_random_message_state(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Load random message handler state."""
        return self.load_state(f"random_messages_{chat_id}")
    
    def mark_session_ended(self, reason: str = "normal_shutdown"):
        """Mark the current session as ended with proper state management."""
        if self.state_collection is None:
            logging.warning("State collection not initialized, cannot mark session as ended")
            return False
        
        try:
            # Mark session as inactive to prevent further saves
            self._session_active = False
            
            # Update all documents in this session with end marker
            result = self.state_collection.update_many(
                {"session_id": self.session_id},
                {"$set": {
                    "session_ended": datetime.utcnow(),
                    "end_reason": reason
                }}
            )
            
            if result.modified_count > 0:
                logging.info(f"Session {self.session_id} marked as ended: {reason} ({result.modified_count} documents updated)")
                return True
            else:
                logging.warning(f"No documents found for session {self.session_id} to mark as ended")
                return False
                
        except Exception as e:
            logging.error(f"Failed to mark session as ended: {e}")
            return False
    
    def is_session_active(self) -> bool:
        """Check if the current session is active."""
        return self._session_active
    
    def get_session_status(self) -> Dict[str, Any]:
        """Get current session status information."""
        status = {
            "session_id": self.session_id,
            "active": self._session_active,
            "mongo_connected": self.state_collection is not None
        }
        
        if self.state_collection is not None:
            try:
                # Check if session has been marked as ended
                ended_doc = self.state_collection.find_one({
                    "session_id": self.session_id,
                    "session_ended": {"$exists": True}
                })
                
                if ended_doc:
                    status.update({
                        "ended": True,
                        "end_reason": ended_doc.get("end_reason", "unknown"),
                        "end_time": ended_doc.get("session_ended")
                    })
                else:
                    status["ended"] = False
                    
                # Count documents in session
                status["document_count"] = self.state_collection.count_documents({
                    "session_id": self.session_id
                })
                
            except Exception as e:
                logging.error(f"Error getting session status: {e}")
                status["error"] = str(e)
        
        return status
    
    def force_end_session(self, reason: str = "force_ended"):
        """Force end the current session and create a new one."""
        # End current session
        self.mark_session_ended(reason)
        
        # Create new session
        self.session_id = str(uuid.uuid4())
        self._session_active = True
        
        logging.info(f"Force ended session and created new session: {self.session_id}")


# Global state manager instance
state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create the global state manager instance."""
    global state_manager
    
    if state_manager is None:
        state_manager = StateManager()
    
    return state_manager


def initialize_state_manager(mongo_client: Optional[MongoClient] = None):
    """Initialize the global state manager with optional MongoDB client."""
    global state_manager
    state_manager = StateManager(mongo_client)
    return state_manager
