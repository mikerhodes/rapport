import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import glob

class ChatHistoryManager:
    def __init__(self):
        # Ensure the .assistant directory exists
        self.base_dir = Path.home() / ".assistant"
        self.chats_dir = self.base_dir / "chats"
        self.base_dir.mkdir(exist_ok=True)
        self.chats_dir.mkdir(exist_ok=True)
        
        # Create an index file to track chat metadata
        self.index_path = self.base_dir / "chat_index.json"
        if not self.index_path.exists():
            self._save_index({})
    
    def _save_index(self, index: Dict):
        """Save the chat index file"""
        with open(self.index_path, 'w') as f:
            json.dump(index, f, indent=2)
    
    def _load_index(self) -> Dict:
        """Load the chat index file"""
        try:
            with open(self.index_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _generate_chat_id(self) -> str:
        """Generate a unique chat ID based on timestamp"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def save_chat(self, messages: List[Dict], title: str, model: str, chat_id: Optional[str] = None) -> str:
        """
        Save a chat session to a JSON file. If chat_id is provided, update existing chat.
        If not provided, create a new chat.
        """
        # Generate new ID if this is a new chat
        if chat_id is None:
            chat_id = self._generate_chat_id()
        
        # Create chat data structure
        chat_data = {
            "id": chat_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "model": model,
            "messages": messages
        }
        
        # Save chat to individual JSON file
        chat_path = self.chats_dir / f"{chat_id}.json"
        with open(chat_path, 'w') as f:
            json.dump(chat_data, f, indent=2)
        
        # Update index
        index = self._load_index()
        index[chat_id] = {
            "title": title,
            "created_at": chat_data["created_at"],
            "model": model
        }
        self._save_index(index)
        
        return chat_id
    
    def get_recent_chats(self, limit: int = 20) -> List[Dict]:
        """Retrieve the most recent chats from the index"""
        index = self._load_index()
        
        # Sort chats by creation date and limit the results
        sorted_chats = sorted(
            [{"id": k, **v} for k, v in index.items()],
            key=lambda x: x["created_at"],
            reverse=True
        )[:limit]
        
        return sorted_chats
    
    def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Retrieve a specific chat from its JSON file"""
        chat_path = self.chats_dir / f"{chat_id}.json"
        try:
            with open(chat_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
    
    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat's JSON file and remove it from the index"""
        chat_path = self.chats_dir / f"{chat_id}.json"
        
        try:
            # Delete the chat file
            chat_path.unlink()
            
            # Remove from index
            index = self._load_index()
            if chat_id in index:
                del index[chat_id]
                self._save_index(index)
            
            return True
        except FileNotFoundError:
            return False
