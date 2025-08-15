from datetime import datetime
from mongoengine import Document, StringField, IntField, BooleanField, DateTimeField, ListField, EmbeddedDocument, EmbeddedDocumentField


class User(Document):
    """User model for storing Telegram user information"""
    telegram_id = IntField(required=True, unique=True)
    username = StringField(max_length=255)
    first_name = StringField(max_length=255)
    last_name = StringField(max_length=255)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    is_active = BooleanField(default=True)
    
    meta = {
        'collection': 'users',
        'indexes': ['telegram_id']
    }
    
    def __str__(self):
        return f'User {self.telegram_id}: {self.first_name}'


class Conversation(Document):
    """Conversation model for storing message history"""
    user = StringField(required=True)  # Reference to User's telegram_id
    message_type = StringField(required=True, choices=['user', 'assistant'])
    content = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    message_id = IntField()
    
    meta = {
        'collection': 'conversations',
        'indexes': ['user', '-timestamp'],
        'ordering': ['-timestamp']
    }
    
    def __str__(self):
        return f'Message {self.id}: {self.message_type}'


class FileMessage(Document):
    """File message model for storing file/image information"""
    user = StringField(required=True)  # Reference to User's telegram_id
    file_id = StringField(required=True, max_length=255)
    file_type = StringField(required=True, max_length=50)  # 'photo', 'document', 'audio', etc.
    file_name = StringField(max_length=255)
    file_size = IntField()
    mime_type = StringField(max_length=100)
    processed = BooleanField(default=False)
    analysis_result = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'file_messages',
        'indexes': ['user', '-timestamp', 'processed'],
        'ordering': ['-timestamp']
    }
    
    def __str__(self):
        return f'FileMessage {self.id}: {self.file_type}'