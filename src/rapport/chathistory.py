import json
from pathlib import Path
from typing import List, Dict, Optional, Union, cast, Any
from datetime import datetime, timedelta
import logging

from rapport.chatmodel import (
    Chat,
)

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    def __init__(self, base_dir: Path):
        # Ensure the .assistant directory exists
        self.chats_dir = base_dir / "chats"
        self.chats_dir.mkdir(exist_ok=True)

        # Create an index file to track chat metadata
        self.index_path = base_dir / "chat_index.json"
        if not self.index_path.exists():
            self._save_index({})

        self.clear_old_chats()  # clear on startup

    def _save_index(self, index: Dict):
        """Save the chat index file"""
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)

    def _load_index(self) -> Dict:
        """Load the chat index file"""
        try:
            with open(self.index_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _generate_chat_id(self) -> str:
        """Generate a unique chat ID based on timestamp"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def save_chat(
        self,
        chat: Chat,
    ):
        """
        Save a chat session to a JSON file.
        If chat_id is already saved, update existing chat.
        If not already saved, create a new chat.
        """
        # Save chat to individual JSON file
        chat_path = self.chats_dir / f"{chat.id}.json"
        with open(chat_path, "w") as f:
            # Use Pydantic's model_dump with mode='json' for serialization
            chat_json = chat.model_dump(mode="json")
            json.dump(chat_json, f, indent=2)
        logger.info("Saved chat to %s", chat_path)

        # Update index
        index = self._load_index()
        index[chat.id] = {
            "title": chat.title,
            "created_at": chat.created_at.isoformat(),
            "model": chat.model,
        }
        self._save_index(index)

    def get_recent_chats(self, limit: int = 20) -> List[Dict]:
        """Retrieve the most recent chats from the index"""
        index = self._load_index()

        # Sort chats by creation date and limit the results
        sorted_chats = sorted(
            [{"id": k, **v} for k, v in index.items()],
            key=lambda x: x["created_at"],
            reverse=True,
        )[:limit]

        return sorted_chats

    def get_chat(self, chat_id: str) -> Optional[Chat]:
        """Retrieve a specific chat from its JSON file"""
        chat_path = self.chats_dir / f"{chat_id}.json"
        try:
            logger.info("Loading chat from %s", chat_path)
            with open(chat_path, "r") as f:
                d = json.load(f)
                if "updated_at" not in d:
                    d["updated_at"] = d["created_at"]
                return Chat(**d)
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

    def clear_old_chats(self, days: int = 90) -> int:
        """
        Delete chat files and entries from the index that are older than a specified number of days.

        Args:
            days (int): Number of days to consider as "old".

        Returns:
            int: The number of chats deleted.
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        index = self._load_index()
        chat_ids_to_delete = [
            chat_id
            for chat_id, data in index.items()
            if datetime.fromisoformat(data["created_at"]).date()
            < cutoff_date
        ]

        # Delete the files and update the index
        deleted_count = 0
        for chat_id in chat_ids_to_delete:
            try:
                chat_path = self.chats_dir / f"{chat_id}.json"
                chat_path.unlink()
            except FileNotFoundError:
                pass
            del index[chat_id]  # Update index
            deleted_count += 1

        if deleted_count > 0:
            self._save_index(index)  # Save updated index

        print(f"Cleared {deleted_count} old chats from before {cutoff_date}")

        return deleted_count
