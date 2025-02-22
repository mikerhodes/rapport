import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta


class ChatHistoryManager:
    def __init__(self):
        # Ensure the .assistant directory exists
        self.base_dir = Path.home() / ".interlocution"
        self.base_dir.mkdir(exist_ok=True)

        # Initialize SQLite database
        self.db_path = self.base_dir / "chats.db"
        self._init_database()

    def _init_database(self):
        """Initialize the SQLite database schema"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create chats metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    model TEXT NOT NULL
                )
            """)

            # Create messages table with foreign key to chats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE,
                    UNIQUE (chat_id, message_index)
                )
            """)

    def _generate_chat_id(self) -> str:
        """Generate a unique chat ID based on timestamp"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def save_chat(
        self,
        messages: List[Dict],
        title: str,
        model: str,
        chat_id: str,
        created_at: datetime,
    ):
        """
        Save a chat session to the database.
        If chat_id already exists, update the existing chat.
        If not already saved, create a new chat.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")

            # Save or update chat metadata
            cursor.execute(
                """
                REPLACE INTO chats (id, title, created_at, model)
                VALUES (?, ?, ?, ?)
            """,
                (chat_id, title, created_at.isoformat(), model),
            )

            # Delete existing messages for this chat
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))

            # Insert new messages
            message_data = [
                (chat_id, idx, msg["role"], msg["content"])
                for idx, msg in enumerate(messages)
            ]

            cursor.executemany(
                """
                INSERT INTO messages (chat_id, message_index, role, content)
                VALUES (?, ?, ?, ?)
            """,
                message_data,
            )

    def get_recent_chats(self, limit: int = 20) -> List[Dict]:
        """Retrieve the most recent chats from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, title, created_at, model
                FROM chats
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            rows = cursor.fetchall()

            return [
                {"id": row[0], "title": row[1], "created_at": row[2], "model": row[3]}
                for row in rows
            ]

    def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Retrieve a specific chat and its messages from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get chat metadata
            cursor.execute(
                """
                SELECT id, title, created_at, model
                FROM chats
                WHERE id = ?
            """,
                (chat_id,),
            )

            chat_row = cursor.fetchone()
            if chat_row is None:
                return None

            # Get chat messages
            cursor.execute(
                """
                SELECT role, content
                FROM messages
                WHERE chat_id = ?
                ORDER BY message_index
            """,
                (chat_id,),
            )

            messages = [
                {"role": row[0], "content": row[1]} for row in cursor.fetchall()
            ]

            return {
                "id": chat_row[0],
                "title": chat_row[1],
                "created_at": datetime.fromisoformat(chat_row[2]),
                "model": chat_row[3],
                "messages": messages,
            }

    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat and its messages from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")

            # Messages will be automatically deleted due to ON DELETE CASCADE
            cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

            deleted = cursor.rowcount > 0

        return deleted

    def clear_old_chats(self, days: int = 7) -> int:
        """
        Delete chats and their messages from the database that are older than a specified number of days.

        Args:
            days (int): Number of days to consider as "old".

        Returns:
            int: The number of chats deleted.
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_date = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")

            # Messages will be automatically deleted due to ON DELETE CASCADE
            cursor.execute(
                """
                DELETE FROM chats
                WHERE created_at < ?
            """,
                (cutoff_date.isoformat(),),
            )

            deleted_count = cursor.rowcount

            print(f"Cleared {deleted_count} old chats from before {cutoff_date}")

        return deleted_count
