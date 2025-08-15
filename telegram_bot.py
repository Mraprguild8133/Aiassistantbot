import logging
import json
import os
import tempfile
from typing import Dict, Any
import requests
from config import Config
from gemini_service import GeminiService

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram Bot handler class"""
    
    def __init__(self, token: str):
        """Initialize the Telegram bot with token"""
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.gemini_service = GeminiService()
        
    def send_message(self, chat_id: int, text: str, parse_mode: str | None = None) -> bool:
        """
        Send a message to a Telegram chat
        
        Args:
            chat_id: The chat ID to send the message to
            text: The message text
            parse_mode: Optional parse mode (Markdown, HTML)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text
            }
            
            if parse_mode:
                payload["parse_mode"] = parse_mode
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully to chat {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message to chat {chat_id}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {str(e)}")
            return False
    
    def send_typing_action(self, chat_id: int):
        """Send typing action to show bot is processing"""
        try:
            url = f"{self.api_url}/sendChatAction"
            payload = {
                "chat_id": chat_id,
                "action": "typing"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"Failed to send typing action: {str(e)}")
    
    def handle_photo(self, message: Dict[str, Any]) -> str:
        """Handle photo messages"""
        try:
            user = message.get("from", {})
            telegram_id = user.get("id")
            photos = message.get("photo", [])
            caption = message.get("caption")
            
            if not photos:
                return "I didn't receive any photo. Please try sending it again."
            
            # Get the largest photo (best quality)
            largest_photo = max(photos, key=lambda p: p.get("file_size", 0))
            file_id = largest_photo["file_id"]
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # Download the photo
                if self.download_file(file_id, temp_path):
                    # Analyze with Gemini
                    result = self.gemini_service.analyze_image(
                        telegram_id=telegram_id,
                        file_id=file_id,
                        file_path=temp_path,
                        caption=caption
                    )
                    return result
                else:
                    return "Sorry, I couldn't download your image. Please try again."
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error handling photo: {str(e)}")
            return "Sorry, I encountered an error processing your image. Please try again."
    
    def handle_document(self, message: Dict[str, Any]) -> str:
        """Handle document messages"""
        try:
            user = message.get("from", {})
            telegram_id = user.get("id")
            document = message.get("document", {})
            
            file_id = document.get("file_id")
            file_name = document.get("file_name", "document")
            mime_type = document.get("mime_type")
            file_size = document.get("file_size", 0)
            
            # Check file size limit (20MB)
            if file_size > 20 * 1024 * 1024:
                return "Sorry, the file is too large. Please send files smaller than 20MB."
            
            # Create temporary file with appropriate extension
            file_extension = os.path.splitext(file_name)[1] if '.' in file_name else ''
            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # Download the document
                if self.download_file(file_id, temp_path):
                    # Analyze with Gemini
                    result = self.gemini_service.analyze_document(
                        telegram_id=telegram_id,
                        file_id=file_id,
                        file_path=temp_path,
                        file_name=file_name,
                        mime_type=mime_type
                    )
                    return result
                else:
                    return "Sorry, I couldn't download your file. Please try again."
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error handling document: {str(e)}")
            return "Sorry, I encountered an error processing your document. Please try again."

    def handle_command(self, message: Dict[str, Any]) -> str:
        """
        Handle bot commands
        
        Args:
            message: The message object from Telegram
        
        Returns:
            Response text
        """
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        username = user.get("first_name", "there")
        telegram_id = user.get("id")
        
        if text.startswith("/start"):
            return self.gemini_service.get_welcome_message(username)
        
        elif text.startswith("/help"):
            return (
                "🤖 *AI Assistant Bot Help*\n\n"
                "*Available Commands:*\n"
                "/start - Start a conversation with the bot\n"
                "/help - Show this help message\n"
                "/clear - Clear conversation history\n\n"
                "*Features:*\n"
                "• Ask me anything and I'll provide intelligent responses\n"
                "• I remember our conversation context across sessions\n"
                "• Send me images and I'll analyze them\n"
                "• Send me text files and I'll read and analyze them\n"
                "• Powered by Google Gemini AI\n\n"
                "*Examples:*\n"
                "• \"What's the weather like?\"\n"
                "• \"Explain quantum physics simply\"\n"
                "• Send a photo and ask \"What do you see?\"\n"
                "• Upload a text document for analysis"
            )
        
        elif text.startswith("/clear"):
            self.gemini_service.clear_context(telegram_id)
            return "✅ Conversation history cleared! We can start fresh."
        
        else:
            # Handle unknown commands
            return (
                "❓ Unknown command. Use /help to see available commands or just send me a message to chat!"
            )
    
    def download_file(self, file_id: str, file_path: str) -> bool:
        """Download a file from Telegram servers"""
        try:
            # Get file info
            url = f"{self.api_url}/getFile"
            response = requests.get(url, params={"file_id": file_id}, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Failed to get file info: {response.text}")
                return False
            
            file_info = response.json()
            if not file_info.get("ok"):
                logger.error(f"Failed to get file info: {file_info}")
                return False
            
            file_url_path = file_info["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_url_path}"
            
            # Download the file
            file_response = requests.get(download_url, timeout=30)
            if file_response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(file_response.content)
                logger.info(f"Downloaded file to {file_path}")
                return True
            else:
                logger.error(f"Failed to download file: {file_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            return False

    def process_message(self, message: Dict[str, Any]) -> str:
        """
        Process incoming messages and generate appropriate responses
        
        Args:
            message: The message object from Telegram
        
        Returns:
            Response text
        """
        try:
            user = message.get("from", {})
            username = user.get("username")
            first_name = user.get("first_name", "User")
            last_name = user.get("last_name")
            telegram_id = user.get("id")
            message_id = message.get("message_id")
            
            logger.info(f"Processing message from user {telegram_id} ({first_name}): {message.get('text', '[media/file]')}")
            
            # Handle photos
            if "photo" in message:
                return self.handle_photo(message)
            
            # Handle documents
            if "document" in message:
                return self.handle_document(message)
            
            # Handle text messages
            text = message.get("text", "")
            
            # Handle commands
            if text.startswith("/"):
                return self.handle_command(message)
            
            # Handle regular messages with AI
            if text.strip():
                return self.gemini_service.generate_response(
                    telegram_id=telegram_id,
                    message=text,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    message_id=message_id
                )
            else:
                return "Please send me a message and I'll be happy to help! 😊"
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return "Sorry, I encountered an error processing your message. Please try again."
    
    def handle_webhook_update(self, update: Dict[str, Any]) -> bool:
        """
        Handle incoming webhook updates from Telegram
        
        Args:
            update: The update object from Telegram
        
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            logger.info(f"Received update: {json.dumps(update, indent=2)}")
            
            # Handle regular messages
            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                
                # Send typing action to show bot is processing
                self.send_typing_action(chat_id)
                
                # Process the message and get response
                response_text = self.process_message(message)
                
                # Send the response
                success = self.send_message(
                    chat_id=chat_id,
                    text=response_text,
                    parse_mode="Markdown"
                )
                
                return success
            
            # Handle edited messages (treat as new messages)
            elif "edited_message" in update:
                message = update["edited_message"]
                chat_id = message["chat"]["id"]
                
                self.send_typing_action(chat_id)
                response_text = self.process_message(message)
                
                success = self.send_message(
                    chat_id=chat_id,
                    text=f"📝 *Updated response:*\n\n{response_text}",
                    parse_mode="Markdown"
                )
                
                return success
            
            else:
                logger.warning(f"Unhandled update type: {list(update.keys())}")
                return True  # Return True to acknowledge the update
                
        except Exception as e:
            logger.error(f"Error handling webhook update: {str(e)}")
            return False
    
    def set_webhook(self, webhook_url: str) -> bool:
        """
        Set the webhook URL for the bot
        
        Args:
            webhook_url: The full webhook URL
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.api_url}/setWebhook"
            payload = {
                "url": webhook_url,
                "drop_pending_updates": True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Webhook set successfully to: {webhook_url}")
                    return True
                else:
                    logger.error(f"Failed to set webhook: {result}")
                    return False
            else:
                logger.error(f"HTTP error setting webhook: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting webhook: {str(e)}")
            return False
    
    def get_webhook_info(self) -> Dict[str, Any]:
        """Get current webhook information"""
        try:
            url = f"{self.api_url}/getWebhookInfo"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get webhook info: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting webhook info: {str(e)}")
            return {}
