import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, render_template, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix
import mongoengine

from config import Config
from telegram_bot import TelegramBot
from models import User, Conversation, FileMessage

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# MongoDB configuration
try:
    mongodb_settings = Config.get_mongodb_settings()
    if 'host' in mongodb_settings and mongodb_settings['host'].startswith('mongodb://'):
        # Full connection string
        mongoengine.connect(host=mongodb_settings['host'])
    else:
        # Individual parameters
        mongoengine.connect(**mongodb_settings)
    logger.info("Connected to MongoDB successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    # Use default local connection for development
    mongoengine.connect('telegram_bot')

# Initialize bot (will be done after config validation)
bot = None

def get_bot():
    """Get or initialize the bot"""
    global bot
    if bot is None:
        try:
            Config.validate()
            if not Config.TELEGRAM_BOT_TOKEN:
                raise ValueError("TELEGRAM_BOT_TOKEN is required")
            bot = TelegramBot(Config.TELEGRAM_BOT_TOKEN)
            logger.info("Bot initialized successfully")
            
            # Set webhook if URL is provided
            webhook_base_url = Config.TELEGRAM_WEBHOOK_URL or Config.RENDER_EXTERNAL_URL
            if webhook_base_url:
                full_webhook_url = f"{webhook_base_url.rstrip('/')}{Config.WEBHOOK_PATH}"
                bot.set_webhook(full_webhook_url)
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {str(e)}")
            raise
    return bot

@app.route("/")
def index():
    """Health check and bot status endpoint"""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram AI Bot</title>
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-body text-center">
                            <h1 class="card-title">🤖 Telegram AI Bot</h1>
                            <p class="card-text">
                                Intelligent Telegram bot powered by Google Gemini AI
                            </p>
                            
                            <div class="row mt-4">
                                <div class="col-md-6">
                                    <div class="card bg-success-subtle">
                                        <div class="card-body">
                                            <h5 class="card-title">Bot Status</h5>
                                            <p class="card-text">
                                                {% if bot_status %}
                                                    <span class="badge bg-success">✅ Active</span>
                                                {% else %}
                                                    <span class="badge bg-danger">❌ Not Configured</span>
                                                {% endif %}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card bg-info-subtle">
                                        <div class="card-body">
                                            <h5 class="card-title">Webhook</h5>
                                            <p class="card-text">
                                                {% if webhook_info %}
                                                    <span class="badge bg-info">🌐 {{ webhook_info }}</span>
                                                {% else %}
                                                    <span class="badge bg-secondary">⏳ Pending</span>
                                                {% endif %}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="mt-4">
                                <h5>Features:</h5>
                                <ul class="list-unstyled">
                                    <li>💬 Intelligent conversations with persistent memory</li>
                                    <li>🖼️ Image analysis using Gemini Vision</li>
                                    <li>📄 File processing and document analysis</li>
                                    <li>🧠 Powered by Google Gemini AI</li>
                                    <li>⚡ Real-time webhook processing</li>
                                    <li>🛠️ Built-in commands (/start, /help, /clear)</li>
                                    <li>🗄️ MongoDB database storage</li>
                                    <li>🔒 Secure API key handling</li>
                                </ul>
                            </div>
                            
                            <div class="mt-4">
                                <a href="{{ url_for('admin_login') }}" class="btn btn-outline-primary">🔧 Admin Panel</a>
                            </div>
                            
                            {% if not bot_status %}
                            <div class="alert alert-warning mt-3">
                                <strong>Setup Required:</strong> Please configure TELEGRAM_BOT_TOKEN and GEMINI_API_KEY environment variables.
                            </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        current_bot = get_bot()
        bot_status = current_bot is not None
        webhook_info = None
        
        if current_bot:
            try:
                webhook_data = current_bot.get_webhook_info()
                if webhook_data.get("ok") and webhook_data.get("result", {}).get("url"):
                    webhook_info = "Configured"
                else:
                    webhook_info = "Not Set"
            except:
                webhook_info = "Error"
    except:
        bot_status = False
        webhook_info = "Not Available"
    
    return render_template_string(template, bot_status=bot_status, webhook_info=webhook_info)

@app.route(Config.WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Handle incoming webhook updates from Telegram"""
    try:
        current_bot = get_bot()
        if not current_bot:
            logger.error("Bot not initialized")
            return jsonify({"error": "Bot not initialized"}), 500
        
        # Get the JSON data from the request
        update = request.get_json()
        
        if not update:
            logger.warning("Received empty webhook update")
            return jsonify({"error": "Empty update"}), 400
        
        # Process the update
        success = current_bot.handle_webhook_update(update)
        
        if success:
            return jsonify({"status": "ok"}), 200
        else:
            return jsonify({"error": "Failed to process update"}), 500
            
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/webhook_info")
def webhook_info():
    """Get webhook information endpoint"""
    try:
        current_bot = get_bot()
        if not current_bot:
            return jsonify({"error": "Bot not initialized"}), 500
        info = current_bot.get_webhook_info()
        return jsonify(info)
    except Exception as e:
        logger.error(f"Error getting webhook info: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    """Health check endpoint"""
    try:
        current_bot = get_bot()
        bot_initialized = current_bot is not None
    except:
        bot_initialized = False
        
    status = {
        "status": "healthy",
        "bot_initialized": bot_initialized,
        "telegram_token_configured": bool(Config.TELEGRAM_BOT_TOKEN),
        "gemini_key_configured": bool(Config.GEMINI_API_KEY),
    }
    
    return jsonify(status)

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

# Admin Panel Routes
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def require_admin_login(f):
    """Decorator to require admin authentication"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid password', 'error')
    
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Admin Login</title>
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-body">
                            <h3 class="card-title text-center mb-4">🔐 Admin Login</h3>
                            {% with messages = get_flashed_messages(with_categories=true) %}
                                {% if messages %}
                                    {% for category, message in messages %}
                                        <div class="alert alert-danger">{{ message }}</div>
                                    {% endfor %}
                                {% endif %}
                            {% endwith %}
                            <form method="POST">
                                <div class="mb-3">
                                    <label class="form-label">Admin Password</label>
                                    <input type="password" name="password" class="form-control" required>
                                </div>
                                <button type="submit" class="btn btn-primary w-100">Login</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(template)

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@require_admin_login
def admin_dashboard():
    """Admin dashboard"""
    try:
        # Get statistics
        total_users = User.objects.count()
        total_messages = Conversation.objects.count()
        total_files = FileMessage.objects.count()
        
        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_users = User.objects(created_at__gte=yesterday).count()
        recent_messages = Conversation.objects(timestamp__gte=yesterday).count()
        recent_files = FileMessage.objects(timestamp__gte=yesterday).count()
        
        # Most active users - simplified for MongoDB
        all_users = User.objects()
        active_users = []
        for user in all_users:
            message_count = Conversation.objects(user=str(user.telegram_id)).count()
            if message_count > 0:
                active_users.append({
                    'telegram_id': user.telegram_id,
                    'first_name': user.first_name,
                    'username': user.username,
                    'message_count': message_count
                })
        active_users = sorted(active_users, key=lambda x: x['message_count'], reverse=True)[:10]
        
        # Recent conversations
        recent_conversations = []
        recent_convs = Conversation.objects().order_by('-timestamp').limit(20)
        for conv in recent_convs:
            try:
                user = User.objects(telegram_id=int(conv.user)).first()
                if user:
                    recent_conversations.append((conv, user))
            except:
                pass
        
        stats = {
            'total_users': total_users,
            'total_messages': total_messages, 
            'total_files': total_files,
            'recent_users': recent_users,
            'recent_messages': recent_messages,
            'recent_files': recent_files
        }
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Bot Admin Dashboard</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg">
                <div class="container">
                    <span class="navbar-brand">🤖 Bot Admin Panel</span>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="{{ url_for('admin_users') }}">Users</a>
                        <a class="nav-link" href="{{ url_for('admin_files') }}">Files</a>
                        <a class="nav-link" href="{{ url_for('admin_config') }}">Config</a>
                        <a class="nav-link" href="{{ url_for('admin_logout') }}">Logout</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <h2>📊 Dashboard Overview</h2>
                
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card bg-primary-subtle">
                            <div class="card-body text-center">
                                <h3 class="card-title">{{ stats.total_users }}</h3>
                                <p class="card-text">Total Users</p>
                                <small class="text-muted">+{{ stats.recent_users }} today</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-success-subtle">
                            <div class="card-body text-center">
                                <h3 class="card-title">{{ stats.total_messages }}</h3>
                                <p class="card-text">Total Messages</p>
                                <small class="text-muted">+{{ stats.recent_messages }} today</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-info-subtle">
                            <div class="card-body text-center">
                                <h3 class="card-title">{{ stats.total_files }}</h3>
                                <p class="card-text">Files Processed</p>
                                <small class="text-muted">+{{ stats.recent_files }} today</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-warning-subtle">
                            <div class="card-body text-center">
                                <h3 class="card-title">{{ (stats.total_messages / stats.total_users)|round(1) if stats.total_users > 0 else 0 }}</h3>
                                <p class="card-text">Avg Messages/User</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5>🏆 Most Active Users</h5>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-sm">
                                        <thead>
                                            <tr>
                                                <th>User</th>
                                                <th>Messages</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for user in active_users %}
                                            <tr>
                                                <td>
                                                    <strong>{{ user.first_name or 'Unknown' }}</strong>
                                                    {% if user.username %}<br><small class="text-muted">@{{ user.username }}</small>{% endif %}
                                                </td>
                                                <td><span class="badge bg-primary">{{ user.message_count }}</span></td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5>💬 Recent Activity</h5>
                            </div>
                            <div class="card-body">
                                <div style="max-height: 400px; overflow-y: auto;">
                                    {% for conv, user in recent_conversations %}
                                    <div class="mb-2 p-2 border rounded">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div>
                                                <strong>{{ user.first_name or 'Unknown' }}</strong>
                                                <span class="badge bg-{{ 'primary' if conv.message_type == 'user' else 'success' }}">{{ conv.message_type }}</span>
                                            </div>
                                            <small class="text-muted">{{ conv.timestamp.strftime('%H:%M') }}</small>
                                        </div>
                                        <div class="mt-1">
                                            <small>{{ conv.content[:100] }}{% if conv.content|length > 100 %}...{% endif %}</small>
                                        </div>
                                    </div>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Auto-refresh every 30 seconds
                setTimeout(() => location.reload(), 30000);
            </script>
        </body>
        </html>
        """
        
        return render_template_string(template, stats=stats, active_users=active_users, recent_conversations=recent_conversations)
        
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        return f"Error loading dashboard: {str(e)}", 500

@app.route('/admin/users')
@require_admin_login
def admin_users():
    """User management page"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Get users with activity info for MongoDB
        skip = (page - 1) * per_page
        all_users = User.objects().order_by('-updated_at').skip(skip).limit(per_page)
        
        users_with_stats = []
        for user in all_users:
            message_count = Conversation.objects(user=str(user.telegram_id)).count()
            last_conv = Conversation.objects(user=str(user.telegram_id)).order_by('-timestamp').first()
            last_activity = last_conv.timestamp if last_conv else None
            users_with_stats.append((user, message_count, last_activity))
        
        # Create a simple pagination object
        class SimplePagination:
            def __init__(self, items, page, per_page, total):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.has_prev = page > 1
                self.has_next = skip + per_page < total
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        total_users = User.objects.count()
        users = SimplePagination(users_with_stats, page, per_page, total_users)
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Management - Bot Admin</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg">
                <div class="container">
                    <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">🤖 Bot Admin Panel</a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a>
                        <span class="nav-link active">Users</span>
                        <a class="nav-link" href="{{ url_for('admin_files') }}">Files</a>
                        <a class="nav-link" href="{{ url_for('admin_config') }}">Config</a>
                        <a class="nav-link" href="{{ url_for('admin_logout') }}">Logout</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <h2>👥 User Management</h2>
                
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>User Info</th>
                                <th>Telegram ID</th>
                                <th>Messages</th>
                                <th>Last Activity</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user, message_count, last_activity in users.items %}
                            <tr>
                                <td>
                                    <strong>{{ user.first_name or 'Unknown' }} {{ user.last_name or '' }}</strong>
                                    {% if user.username %}<br><small class="text-muted">@{{ user.username }}</small>{% endif %}
                                    <br><small class="text-muted">Joined: {{ user.created_at.strftime('%Y-%m-%d') }}</small>
                                </td>
                                <td><code>{{ user.telegram_id }}</code></td>
                                <td><span class="badge bg-primary">{{ message_count or 0 }}</span></td>
                                <td>
                                    {% if last_activity %}
                                        {{ last_activity.strftime('%Y-%m-%d %H:%M') }}
                                    {% else %}
                                        Never
                                    {% endif %}
                                </td>
                                <td>
                                    <a href="{{ url_for('admin_user_detail', user_id=user.id) }}" class="btn btn-sm btn-outline-primary">View</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <!-- Pagination -->
                <nav>
                    <ul class="pagination justify-content-center">
                        {% if users.has_prev %}
                            <li class="page-item">
                                <a class="page-link" href="{{ url_for('admin_users', page=users.prev_num) }}">Previous</a>
                            </li>
                        {% endif %}
                        
                        {% for page_num in users.iter_pages() %}
                            {% if page_num %}
                                {% if page_num != users.page %}
                                    <li class="page-item">
                                        <a class="page-link" href="{{ url_for('admin_users', page=page_num) }}">{{ page_num }}</a>
                                    </li>
                                {% else %}
                                    <li class="page-item active">
                                        <span class="page-link">{{ page_num }}</span>
                                    </li>
                                {% endif %}
                            {% else %}
                                <li class="page-item disabled">
                                    <span class="page-link">...</span>
                                </li>
                            {% endif %}
                        {% endfor %}
                        
                        {% if users.has_next %}
                            <li class="page-item">
                                <a class="page-link" href="{{ url_for('admin_users', page=users.next_num) }}">Next</a>
                            </li>
                        {% endif %}
                    </ul>
                </nav>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, users=users)
        
    except Exception as e:
        logger.error(f"Error in admin users: {str(e)}")
        return f"Error loading users: {str(e)}", 500

@app.route('/admin/user/<int:user_id>')
@require_admin_login
def admin_user_detail(user_id):
    """User detail page with conversation history"""
    try:
        user = User.objects(telegram_id=user_id).first()
        if not user:
            return "User not found", 404
        
        # Get conversation history
        conversations = Conversation.objects(user=str(user_id)).order_by('-timestamp').limit(100)
        
        # Get file history
        files = FileMessage.objects(user=str(user_id)).order_by('-timestamp').limit(50)
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Detail - {{ user.first_name }} - Bot Admin</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg">
                <div class="container">
                    <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">🤖 Bot Admin Panel</a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="{{ url_for('admin_users') }}">← Back to Users</a>
                        <a class="nav-link" href="{{ url_for('admin_logout') }}">Logout</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <div class="row">
                    <div class="col-md-4">
                        <div class="card">
                            <div class="card-header">
                                <h5>👤 User Information</h5>
                            </div>
                            <div class="card-body">
                                <p><strong>Name:</strong> {{ user.first_name }} {{ user.last_name or '' }}</p>
                                <p><strong>Username:</strong> {% if user.username %}@{{ user.username }}{% else %}None{% endif %}</p>
                                <p><strong>Telegram ID:</strong> <code>{{ user.telegram_id }}</code></p>
                                <p><strong>Joined:</strong> {{ user.created_at.strftime('%Y-%m-%d %H:%M') }}</p>
                                <p><strong>Last Updated:</strong> {{ user.updated_at.strftime('%Y-%m-%d %H:%M') }}</p>
                                <p><strong>Status:</strong> 
                                    <span class="badge bg-{{ 'success' if user.is_active else 'danger' }}">{{ 'Active' if user.is_active else 'Inactive' }}</span>
                                </p>
                                
                                <h6 class="mt-3">Statistics</h6>
                                <p><strong>Total Messages:</strong> {{ conversations|length }}</p>
                                <p><strong>Files Sent:</strong> {{ files|length }}</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-8">
                        <div class="card">
                            <div class="card-header">
                                <h5>💬 Conversation History</h5>
                            </div>
                            <div class="card-body">
                                <div style="max-height: 600px; overflow-y: auto;">
                                    {% for conv in conversations %}
                                    <div class="mb-3 p-3 border rounded {% if conv.message_type == 'user' %}bg-primary-subtle{% else %}bg-success-subtle{% endif %}">
                                        <div class="d-flex justify-content-between align-items-center mb-2">
                                            <span class="badge bg-{{ 'primary' if conv.message_type == 'user' else 'success' }}">{{ conv.message_type|title }}</span>
                                            <small class="text-muted">{{ conv.timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</small>
                                        </div>
                                        <div>{{ conv.content }}</div>
                                        {% if conv.message_id %}
                                            <small class="text-muted">Message ID: {{ conv.message_id }}</small>
                                        {% endif %}
                                    </div>
                                    {% endfor %}
                                    
                                    {% if not conversations %}
                                        <p class="text-muted text-center">No conversation history found.</p>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                        
                        {% if files %}
                        <div class="card mt-3">
                            <div class="card-header">
                                <h5>📁 File History</h5>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-sm">
                                        <thead>
                                            <tr>
                                                <th>File</th>
                                                <th>Type</th>
                                                <th>Status</th>
                                                <th>Date</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for file in files %}
                                            <tr>
                                                <td>
                                                    {{ file.file_name or 'Unknown' }}
                                                    {% if file.file_size %}<br><small class="text-muted">{{ (file.file_size / 1024)|round(1) }} KB</small>{% endif %}
                                                </td>
                                                <td><span class="badge bg-info">{{ file.file_type }}</span></td>
                                                <td><span class="badge bg-{{ 'success' if file.processed else 'warning' }}">{{ 'Processed' if file.processed else 'Pending' }}</span></td>
                                                <td>{{ file.timestamp.strftime('%m-%d %H:%M') }}</td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, user=user, conversations=conversations, files=files)
        
    except Exception as e:
        logger.error(f"Error in admin user detail: {str(e)}")
        return f"Error loading user detail: {str(e)}", 500

@app.route('/admin/files')
@require_admin_login
def admin_files():
    """File management page"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Get files with user info for MongoDB
        skip = (page - 1) * per_page
        all_files = FileMessage.objects().order_by('-timestamp').skip(skip).limit(per_page)
        
        files_with_users = []
        for file_msg in all_files:
            try:
                user = User.objects(telegram_id=int(file_msg.user)).first()
                if user:
                    files_with_users.append((file_msg, user))
            except:
                pass
        
        # Create pagination object
        total_files = FileMessage.objects.count()
        files = SimplePagination(files_with_users, page, per_page, total_files)
        
        # Statistics
        processed_files = FileMessage.objects(processed=True).count()
        pending_files = total_files - processed_files
        
        # File types statistics
        file_types = []
        for file_type in ['photo', 'document', 'audio', 'video']:
            count = FileMessage.objects(file_type=file_type).count()
            if count > 0:
                file_types.append({'file_type': file_type, 'count': count})
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>File Management - Bot Admin</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg">
                <div class="container">
                    <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">🤖 Bot Admin Panel</a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a>
                        <a class="nav-link" href="{{ url_for('admin_users') }}">Users</a>
                        <span class="nav-link active">Files</span>
                        <a class="nav-link" href="{{ url_for('admin_config') }}">Config</a>
                        <a class="nav-link" href="{{ url_for('admin_logout') }}">Logout</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <h2>📁 File Management</h2>
                
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card bg-info-subtle">
                            <div class="card-body text-center">
                                <h4>{{ total_files }}</h4>
                                <p class="mb-0">Total Files</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-success-subtle">
                            <div class="card-body text-center">
                                <h4>{{ processed_files }}</h4>
                                <p class="mb-0">Processed</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-warning-subtle">
                            <div class="card-body text-center">
                                <h4>{{ pending_files }}</h4>
                                <p class="mb-0">Pending</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card">
                            <div class="card-body">
                                <h6>File Types</h6>
                                {% for file_type, count in file_types %}
                                    <div class="d-flex justify-content-between">
                                        <span>{{ file_type }}</span>
                                        <span class="badge bg-secondary">{{ count }}</span>
                                    </div>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>File Info</th>
                                <th>User</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Date</th>
                                <th>Analysis</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for file, user in files.items %}
                            <tr>
                                <td>
                                    <strong>{{ file.file_name or 'Unknown File' }}</strong>
                                    {% if file.file_size %}<br><small class="text-muted">{{ (file.file_size / 1024)|round(1) }} KB</small>{% endif %}
                                    {% if file.mime_type %}<br><small class="text-muted">{{ file.mime_type }}</small>{% endif %}
                                </td>
                                <td>
                                    <a href="{{ url_for('admin_user_detail', user_id=user.id) }}">{{ user.first_name }}</a>
                                    {% if user.username %}<br><small class="text-muted">@{{ user.username }}</small>{% endif %}
                                </td>
                                <td><span class="badge bg-info">{{ file.file_type }}</span></td>
                                <td><span class="badge bg-{{ 'success' if file.processed else 'warning' }}">{{ 'Processed' if file.processed else 'Pending' }}</span></td>
                                <td>{{ file.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
                                <td>
                                    {% if file.analysis_result %}
                                        <small>{{ file.analysis_result[:100] }}{% if file.analysis_result|length > 100 %}...{% endif %}</small>
                                    {% else %}
                                        <em class="text-muted">No analysis</em>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <!-- Pagination -->
                <nav>
                    <ul class="pagination justify-content-center">
                        {% if files.has_prev %}
                            <li class="page-item">
                                <a class="page-link" href="{{ url_for('admin_files', page=files.prev_num) }}">Previous</a>
                            </li>
                        {% endif %}
                        
                        {% for page_num in files.iter_pages() %}
                            {% if page_num %}
                                {% if page_num != files.page %}
                                    <li class="page-item">
                                        <a class="page-link" href="{{ url_for('admin_files', page=page_num) }}">{{ page_num }}</a>
                                    </li>
                                {% else %}
                                    <li class="page-item active">
                                        <span class="page-link">{{ page_num }}</span>
                                    </li>
                                {% endif %}
                            {% else %}
                                <li class="page-item disabled">
                                    <span class="page-link">...</span>
                                </li>
                            {% endif %}
                        {% endfor %}
                        
                        {% if files.has_next %}
                            <li class="page-item">
                                <a class="page-link" href="{{ url_for('admin_files', page=files.next_num) }}">Next</a>
                            </li>
                        {% endif %}
                    </ul>
                </nav>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, files=files, total_files=total_files, processed_files=processed_files, pending_files=pending_files, file_types=file_types)
        
    except Exception as e:
        logger.error(f"Error in admin files: {str(e)}")
        return f"Error loading files: {str(e)}", 500

@app.route('/admin/config', methods=['GET', 'POST'])
@require_admin_login
def admin_config():
    """Bot configuration management"""
    try:
        if request.method == 'POST':
            # Handle configuration updates
            action = request.form.get('action')
            
            if action == 'clear_all_conversations':
                count = Conversation.query.count()
                Conversation.query.delete()
                db.session.commit()
                flash(f'Cleared {count} conversations', 'success')
                
            elif action == 'clear_all_files':
                count = FileMessage.query.count()
                FileMessage.query.delete()
                db.session.commit()
                flash(f'Cleared {count} file records', 'success')
                
            elif action == 'webhook_info':
                current_bot = get_bot()
                if current_bot:
                    info = current_bot.get_webhook_info()
                    flash(f'Webhook info retrieved: {info}', 'info')
            
            return redirect(url_for('admin_config'))
        
        # Get current configuration status
        config_status = {
            'telegram_token': bool(Config.TELEGRAM_BOT_TOKEN),
            'gemini_key': bool(Config.GEMINI_API_KEY),
            'webhook_url': Config.TELEGRAM_WEBHOOK_URL,
            'webhook_path': Config.WEBHOOK_PATH,
        }
        
        # Get database statistics
        db_stats = {
            'total_users': User.query.count(),
            'total_conversations': Conversation.query.count(),
            'total_files': FileMessage.query.count(),
            'active_users': User.query.filter_by(is_active=True).count()
        }
        
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Configuration - Bot Admin</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <nav class="navbar navbar-expand-lg">
                <div class="container">
                    <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">🤖 Bot Admin Panel</a>
                    <div class="navbar-nav ms-auto">
                        <a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a>
                        <a class="nav-link" href="{{ url_for('admin_users') }}">Users</a>
                        <a class="nav-link" href="{{ url_for('admin_files') }}">Files</a>
                        <span class="nav-link active">Config</span>
                        <a class="nav-link" href="{{ url_for('admin_logout') }}">Logout</a>
                    </div>
                </div>
            </nav>
            
            <div class="container mt-4">
                <h2>⚙️ Bot Configuration</h2>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'success' if category == 'success' else 'info' if category == 'info' else 'danger' }} alert-dismissible fade show">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5>🔧 System Status</h5>
                            </div>
                            <div class="card-body">
                                <table class="table table-sm">
                                    <tr>
                                        <td>Telegram Bot Token</td>
                                        <td><span class="badge bg-{{ 'success' if config_status.telegram_token else 'danger' }}">{{ 'Configured' if config_status.telegram_token else 'Missing' }}</span></td>
                                    </tr>
                                    <tr>
                                        <td>Gemini API Key</td>
                                        <td><span class="badge bg-{{ 'success' if config_status.gemini_key else 'danger' }}">{{ 'Configured' if config_status.gemini_key else 'Missing' }}</span></td>
                                    </tr>
                                    <tr>
                                        <td>Webhook URL</td>
                                        <td><span class="badge bg-{{ 'success' if config_status.webhook_url else 'warning' }}">{{ 'Set' if config_status.webhook_url else 'Not Set' }}</span></td>
                                    </tr>
                                    <tr>
                                        <td>Webhook Path</td>
                                        <td><code>{{ config_status.webhook_path }}</code></td>
                                    </tr>
                                </table>
                                
                                <form method="POST" class="mt-3">
                                    <input type="hidden" name="action" value="webhook_info">
                                    <button type="submit" class="btn btn-sm btn-outline-info">Check Webhook Status</button>
                                </form>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5>📊 Database Statistics</h5>
                            </div>
                            <div class="card-body">
                                <table class="table table-sm">
                                    <tr><td>Total Users</td><td><span class="badge bg-primary">{{ db_stats.total_users }}</span></td></tr>
                                    <tr><td>Active Users</td><td><span class="badge bg-success">{{ db_stats.active_users }}</span></td></tr>
                                    <tr><td>Total Conversations</td><td><span class="badge bg-info">{{ db_stats.total_conversations }}</span></td></tr>
                                    <tr><td>Total Files</td><td><span class="badge bg-warning">{{ db_stats.total_files }}</span></td></tr>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-4">
                    <div class="col-12">
                        <div class="card border-warning">
                            <div class="card-header bg-warning-subtle">
                                <h5 class="text-warning">⚠️ Danger Zone</h5>
                            </div>
                            <div class="card-body">
                                <p class="text-muted">These actions cannot be undone. Use with caution.</p>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <form method="POST" onsubmit="return confirm('Are you sure you want to clear ALL conversations? This cannot be undone!')">
                                            <input type="hidden" name="action" value="clear_all_conversations">
                                            <button type="submit" class="btn btn-outline-danger">Clear All Conversations</button>
                                        </form>
                                        <small class="text-muted">Removes all conversation history from the database</small>
                                    </div>
                                    
                                    <div class="col-md-6">
                                        <form method="POST" onsubmit="return confirm('Are you sure you want to clear ALL file records? This cannot be undone!')">
                                            <input type="hidden" name="action" value="clear_all_files">
                                            <button type="submit" class="btn btn-outline-danger">Clear All File Records</button>
                                        </form>
                                        <small class="text-muted">Removes all file processing records from the database</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        return render_template_string(template, config_status=config_status, db_stats=db_stats)
        
    except Exception as e:
        logger.error(f"Error in admin config: {str(e)}")
        return f"Error loading config: {str(e)}", 500

if __name__ == "__main__":
    try:
        Config.validate()
        app.run(
            host=Config.WEBHOOK_HOST,
            port=Config.WEBHOOK_PORT,
            debug=True
        )
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        print(f"Configuration error: {str(e)}")
        print("Please set the required environment variables:")
        print("- TELEGRAM_BOT_TOKEN: Your Telegram bot token")
        print("- GEMINI_API_KEY: Your Google Gemini API key")
        print("- TELEGRAM_WEBHOOK_URL (optional): Your webhook URL")
