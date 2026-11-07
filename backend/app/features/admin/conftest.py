"""Re-exports the chat fixtures (db, client, make_user) for the chat-cascade admin test."""

from app.features.chat import conftest as _chat

db = _chat.db
client = _chat.client
make_user = _chat.make_user
