"""ストレージ抽象化モジュール"""

import json
import os
from abc import ABC, abstractmethod
from typing import List


class Storage(ABC):
    """ストレージの抽象基底クラス"""

    @abstractmethod
    def load_history(self) -> List[str]:
        """処理済みURLの履歴を読み込む"""
        pass

    @abstractmethod
    def save_history(self, history: List[str], max_items: int):
        """処理済みURLの履歴を保存する"""
        pass


class JsonFileStorage(Storage):
    """JSONファイルベースのストレージ"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_history(self) -> List[str]:
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_history(self, history: List[str], max_items: int):
        new_history = history[-max_items:]
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(new_history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


class FirestoreStorage(Storage):
    """Firestoreベースのストレージ"""

    def __init__(
        self, collection_name: str, document_id: str, database: str = "choral-rss-bot"
    ):
        self.collection_name = collection_name
        self.document_id = document_id
        self.database = database
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from google.cloud import firestore

            self._db = firestore.Client(database=self.database)
        return self._db

    def load_history(self) -> List[str]:
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return data.get("processed_links", [])
            return []
        except Exception:
            return []

    def save_history(self, history: List[str], max_items: int):
        new_history = history[-max_items:]
        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_id)
            doc_ref.set({"processed_links": new_history}, merge=True)
        except Exception:
            pass
