import logging
import os
import tempfile
import requests
from typing import Optional
from datetime import datetime, timedelta

from google import genai
from google.genai import types
from models import User, Conversation, FileMessage
import mongoengine

logger = logging.getLogger(__name__)

class GeminiService:
    """Service class for Google Gemini AI integration with persistent storage"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Gemini service with API key"""
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-2.5-flash"
        self.vision_model = "gemini-2.5-pro"
        self.max_context_messages = 20
    
    def get_or_create_user(self, telegram_id: int, username: str | None = None, first_name: str | None = None, last_name: str | None = None) -> User:
        """Get or create a user in the database"""
        user = User.objects(telegram_id=telegram_id).first()
            
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            user.save()
            logger.info(f"Created new user: {telegram_id}")
        else:
            # Update user info if changed
            if user.username != username or user.first_name != first_name:
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.updated_at = datetime.utcnow()
                user.save()
        return user
    
    def save_message(self, user: User, message_type: str, content: str, message_id: int | None = None):
        """Save a message to the database"""
        message = Conversation(
            user=str(user.telegram_id),
            message_type=message_type,
            content=content,
            message_id=message_id
        )
        message.save()
    
    def get_conversation_context(self, user: User, limit: int | None = None) -> list[Conversation]:
        """Get recent conversation context for a user"""
        query = Conversation.objects(user=str(user.telegram_id)).order_by('-timestamp')
        if limit:
            query = query.limit(limit)
        return list(query)[::-1]  # Reverse to get chronological order

    def generate_response(self, telegram_id: int, message: str, username: str | None = None, first_name: str | None = None, last_name: str | None = None, message_id: int | None = None) -> str:
        """
        Generate an AI response to the user's message with persistent context awareness
        
        Args:
            telegram_id: Telegram user ID
            message: The user's message
            username: Optional username for personalization
            first_name: User's first name
            last_name: User's last name
            message_id: Telegram message ID
        
        Returns:
            Generated response from Gemini AI
        """
        try:
            # Get or create user
            user = self.get_or_create_user(telegram_id, username, first_name, last_name)
            
            # Save user message
            self.save_message(user, "user", message, message_id)
            
            # Get conversation context
            recent_messages = self.get_conversation_context(user, self.max_context_messages)
            
            # Build context-aware prompt
            context_messages = []
            for msg in recent_messages[-10:]:  # Use last 10 messages for context
                context_messages.append(f"{msg.message_type.capitalize()}: {msg.content}")
            
            context = "\n".join(context_messages)
            
            system_prompt = (
                "You are a helpful AI assistant integrated into a Telegram bot. "
                "Provide helpful, accurate, and concise responses. "
                "Be friendly and conversational. "
                "If asked about your capabilities, mention that you're powered by Google Gemini AI and can process text, images, and files. "
                f"The user's name is {first_name or username or 'there'}. "
                "Keep responses relatively short for chat format unless detailed information is requested."
            )
            
            if context:
                full_prompt = f"{system_prompt}\n\nConversation history:\n{context}\n\nPlease respond to the latest user message."
            else:
                full_prompt = f"{system_prompt}\n\nUser message: {message}"
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            
            ai_response = response.text or "I'm sorry, I couldn't generate a response right now."
            
            # Save AI response
            self.save_message(user, "assistant", ai_response)
            
            logger.info(f"Generated response for user {telegram_id}: {ai_response[:100]}...")
            return ai_response
            
        except Exception as e:
            logger.error(f"Error generating response for user {telegram_id}: {str(e)}")
            return "I'm experiencing some technical difficulties right now. Please try again later."
    
    def clear_context(self, telegram_id: int):
        """Clear conversation context for a user"""
        try:
            Conversation.objects(user=str(telegram_id)).delete()
            logger.info(f"Cleared conversation context for user {telegram_id}")
        except Exception as e:
            logger.error(f"Error clearing context for user {telegram_id}: {str(e)}")
    
    def get_welcome_message(self, username: str | None = None) -> str:
        """Generate a personalized welcome message"""
        try:
            prompt = (
                f"Generate a friendly welcome message for a new user "
                f"{'named ' + username if username else ''} who just started using "
                f"an AI assistant Telegram bot. Keep it concise and welcoming. "
                f"Mention that you're powered by Google Gemini AI and can help with text, images, and files. Ask how you can help."
            )
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            return response.text or f"Welcome{' ' + username if username else ''}! I'm an AI assistant powered by Google Gemini. I can help with text, images, and files. How can I help you today?"
            
        except Exception as e:
            logger.error(f"Error generating welcome message: {str(e)}")
            return f"Welcome{' ' + username if username else ''}! I'm an AI assistant powered by Google Gemini. I can help with text, images, and files. How can I help you today?"
            
    def analyze_image(self, telegram_id: int, file_id: str, file_path: str, caption: str | None = None) -> str:
        """Analyze an image using Gemini Vision"""
        try:
            user = self.get_or_create_user(telegram_id)
            
            # Save file message record
            file_msg = FileMessage(
                user=str(user.telegram_id),
                file_id=file_id,
                file_type="photo",
                processed=False
            )
            file_msg.save()
            
            # Read the image file
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            
            # Analyze with Gemini Vision
            prompt = (
                "Analyze this image in detail and describe what you see. "
                "Include objects, people, setting, colors, mood, and any text if present. "
                "Be conversational and engaging in your description."
            )
            
            if caption:
                prompt += f" The user also sent this caption: '{caption}'"
            
            response = self.client.models.generate_content(
                model=self.vision_model,
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                    prompt,
                ],
            )
            
            analysis_result = response.text or "I could not analyze this image."
            
            # Update file message with analysis
            file_msg.analysis_result = analysis_result
            file_msg.processed = True
            file_msg.save()
            
            # Save the analysis as a conversation message
            self.save_message(user, "user", f"[Sent an image{': ' + caption if caption else ''}]")
            self.save_message(user, "assistant", analysis_result)
            
            logger.info(f"Analyzed image for user {telegram_id}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing image for user {telegram_id}: {str(e)}")
            return "I'm sorry, I couldn't analyze this image. Please try again later."
    
    def analyze_document(self, telegram_id: int, file_id: str, file_path: str, file_name: str, mime_type: str | None = None) -> str:
        """Analyze a document file"""
        try:
            user = self.get_or_create_user(telegram_id)
            
            # Save file message record
            file_msg = FileMessage(
                user=str(user.telegram_id),
                file_id=file_id,
                file_type="document",
                file_name=file_name,
                mime_type=mime_type,
                processed=False
            )
            file_msg.save()
            
            # Read file content (for text-based files)
            analysis_result = ""
            
            if mime_type and 'text' in mime_type:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    prompt = (
                        f"Analyze this {mime_type} document and provide a helpful summary or analysis. "
                        f"The filename is '{file_name}'. Here's the content:\n\n{content[:4000]}"  # Limit content length
                    )
                    
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                    
                    analysis_result = response.text or "I could not analyze this document."
                    
                except Exception as e:
                    logger.error(f"Error reading text file: {str(e)}")
                    analysis_result = f"I received your document '{file_name}' but couldn't read its content. It might be in a format I can't process yet."
            
            elif mime_type and 'image' in mime_type:
                # Handle images sent as documents
                return self.analyze_image(telegram_id, file_id, file_path)
            
            else:
                analysis_result = f"I received your file '{file_name}' ({mime_type or 'unknown type'}). I can currently analyze text files and images. For other file types, please let me know what you'd like to know about it!"
            
            # Update file message with analysis
            file_msg.analysis_result = analysis_result
            file_msg.processed = True
            file_msg.save()
            
            # Save the file interaction as conversation messages
            self.save_message(user, "user", f"[Sent a file: {file_name}]")
            self.save_message(user, "assistant", analysis_result)
            
            logger.info(f"Analyzed document for user {telegram_id}: {file_name}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing document for user {telegram_id}: {str(e)}")
            return "I'm sorry, I couldn't analyze this document. Please try again later."