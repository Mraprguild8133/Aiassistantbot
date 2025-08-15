# Telegram AI Bot

## Overview

This is a Flask-based Telegram bot that integrates with Google Gemini AI to provide intelligent conversational responses with advanced capabilities. The bot receives messages, images, and files through Telegram webhooks, processes them using Gemini AI, and maintains persistent conversation context across sessions using PostgreSQL database storage. The application supports text analysis, image recognition, and file processing capabilities.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Web Framework Architecture
- **Flask Application**: Serves as the main web server handling HTTP requests and webhook endpoints
- **ProxyFix Middleware**: Handles proxy headers for deployment behind reverse proxies
- **Health Check Endpoint**: Root endpoint provides bot status and configuration information

### Bot Architecture
- **TelegramBot Class**: Encapsulates all Telegram API interactions including message sending and webhook management
- **Webhook-based Processing**: Receives Telegram updates via HTTP webhooks rather than polling
- **Dynamic Initialization**: Bot initialization occurs on first request to handle environment variable validation

### AI Integration
- **GeminiService Class**: Manages Google Gemini AI API interactions for generating intelligent responses, image analysis, and file processing
- **Persistent Conversation Context**: Maintains per-user conversation history in PostgreSQL database across sessions
- **Vision Capabilities**: Analyzes images using Gemini Vision model with detailed descriptions and context awareness
- **File Processing**: Handles text documents, images, and other file types with intelligent analysis
- **Context Management**: Automatically manages conversation history with configurable limits to optimize performance

### Configuration Management
- **Environment-based Config**: All sensitive data (tokens, keys) loaded from environment variables
- **Configuration Validation**: Validates required environment variables on startup
- **Flexible Webhook URLs**: Supports both local development and production webhook configurations

### Message Processing Flow
1. Telegram sends webhook request to Flask endpoint (text, images, or files)
2. TelegramBot extracts message data, downloads media files if present
3. User information is stored/updated in PostgreSQL database
4. For text: GeminiService generates AI response using persistent conversation context
5. For images: Gemini Vision analyzes image content and provides detailed descriptions
6. For files: System processes text files, images as documents, with intelligent analysis
7. All interactions are saved to database for persistent context
8. Response sent back to user via Telegram API

## External Dependencies

### Third-party APIs
- **Telegram Bot API**: Core messaging platform integration for receiving and sending messages
- **Google Gemini AI API**: Provides natural language processing and response generation capabilities

### Python Libraries
- **Flask**: Web framework for handling HTTP requests and webhooks
- **Flask-SQLAlchemy**: Database ORM for PostgreSQL integration
- **Werkzeug**: WSGI utilities including ProxyFix middleware
- **Requests**: HTTP client library for making API calls to Telegram and file downloads
- **Google GenAI**: Official Google SDK for Gemini AI integration and vision capabilities
- **Psycopg2**: PostgreSQL database adapter for Python

### Infrastructure Requirements
- **Environment Variables**: TELEGRAM_BOT_TOKEN and GEMINI_API_KEY must be configured
- **Database**: PostgreSQL database for persistent conversation storage and file tracking
- **Webhook Endpoint**: Requires publicly accessible HTTPS URL for Telegram webhook delivery
- **Port Configuration**: Runs on port 5000 with configurable host binding
- **File Storage**: Temporary file storage for processing uploaded images and documents