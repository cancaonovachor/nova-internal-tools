from abc import ABC, abstractmethod
import json
import os
from typing import List, Set
from rich.console import Console

console = Console()

class Storage(ABC):
    @abstractmethod
    def load_history(self) -> List[str]:
        """Load processing history (list of unique IDs/URLs)"""
        pass

    @abstractmethod
    def save_history(self, history: List[str], max_items: int):
        """Save processing history"""
        pass

class JsonFileStorage(Storage):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_history(self) -> List[str]:
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[red]Error loading history from {self.file_path}: {e}[/red]")
            return []

    def save_history(self, history: List[str], max_items: int):
        new_history = history[-max_items:]
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(new_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[red]Error saving history to {self.file_path}: {e}[/red]")

class FirestoreStorage(Storage):
    def __init__(self, collection_name: str, document_id: str):
        self.collection_name = collection_name
        self.document_id = document_id
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from google.cloud import firestore
            self._db = firestore.Client()
        return self._db

    def load_history(self) -> List[str]:
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return data.get("processed_links", [])
            return []
        except Exception as e:
            console.print(f"[red]Error loading history from Firestore: {e}[/red]")
            return []

    def save_history(self, history: List[str], max_items: int):
        new_history = history[-max_items:]
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc_ref.set({"processed_links": new_history}, merge=True)
        except Exception as e:
            console.print(f"[red]Error saving history to Firestore: {e}[/red]")
