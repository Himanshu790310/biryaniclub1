# Import necessary libraries and modules
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import json
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re  # For input validation

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ag3su65fiyv6i86i8eruijterie8teuitfwtu7d')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///biryani_club.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)  # Session timeout

# Initialize database
db = SQLAlchemy(app)

# Models
class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    emoji = db.Column(db.String(10))
    in_stock = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    popularity = db.Column(db.Integer, default=0)  # Track item popularity

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    loyalty_points = db.Column(db.Integer, default=0)
    loyalty_tier = db.Column(db.String(20), default='bronze')  # bronze/silver/gold
    is_admin = db.Column(db.Boolean, default=False)
    is_delivery = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(20), unique=True, nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(15), nullable=False)
    customer_address = db.Column(db.Text, nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')
    coupon_code = db.Column(db.String(20))
    delivery_person_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    estimated_delivery = db.Column(db.DateTime)
    rating = db.Column(db.Integer)  # Order rating 1-5
    feedback = db.Column(db.Text)  # Customer feedback

    def get_items(self):
        return json.loads(self.items_json) if self.items_json else []

class Promotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    discount_type = db.Column(db.String(10), nullable=False)  # percent/fixed
    discount_value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_to = db.Column(db.DateTime)
    max_usage = db.Column(db.Integer, default=1)
    usage_count = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

# Store status (default to open)
store_status = {'open': True}

# Template context processor for current user
@app.context_processor
def inject_current_user():
    def get_current_user():
        if 'user_id' in session:
            return User.query.get(session['user_id'])
        return None
    return dict(get_current_user=get_current_user)

# Security enhancements
@app.after_request
def apply_security_headers(response):
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:;"
    return response

# Input validation helpers
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    pattern = r'^[0-9]{10,15}$'
    return re.match(pattern, phone) is not None

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def delivery_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_delivery:
            flash('Access denied. Delivery team privileges required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Base HTML template with enhanced styling and PWA support
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#ff6b35">
    <title>{{ title }}</title>
    <link rel="manifest" href="/manifest.json">
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Font Awesome -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">

    <style>
        :root {
            --primary: #ff6b35;
            --secondary: #f7931e;
            --success: #4ecdc4;
            --info: #667eea;
            --warning: #f093fb;
            --danger: #f5576c;
            --dark: #2c3e50;
            --bronze: #cd7f32;
            --silver: #c0c0c0;
            --gold: #ffd700;
            --gradient-1: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
            --gradient-2: linear-gradient(135deg, #4ecdc4 0%, #38ef7d 100%);
            --gradient-3: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --gradient-4: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            --gradient-5: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            --glass: rgba(255, 255, 255, 0.25);
            --glass-border: rgba(255, 255, 255, 0.18);
        }

        * { 
            font-family: 'Poppins', sans-serif; 
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 25%, #ff9a9e 75%, #fecfef 100%);
            background-attachment: fixed;
            min-height: 100vh;
            padding-bottom: 60px; /* Space for PWA install prompt */
        }

        .glass-effect {
            background: var(--glass);
            backdrop-filter: blur(15px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        }

        .navbar {
            background: var(--glass) !important;
            backdrop-filter: blur(20px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border-bottom: 1px solid var(--glass-border);
        }

        .navbar-brand {
            background: var(--gradient-1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 2rem;
        }

        .nav-link {
            font-weight: 600;
            transition: all 0.3s ease;
            border-radius: 10px;
            margin: 0 5px;
        }

        .nav-link:hover {
            background: var(--glass);
            transform: translateY(-2px);
        }

        .card {
            border: none;
            border-radius: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            transition: all 0.4s ease;
            background: var(--glass);
            backdrop-filter: blur(20px);
            overflow: hidden;
            border: 1px solid var(--glass-border);
        }

        .card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 30px 60px rgba(0,0,0,0.2);
        }

        .btn {
            border-radius: 50px;
            padding: 12px 30px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.3s ease;
            border: none;
            position: relative;
            overflow: hidden;
        }

        .btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s;
        }

        .btn:hover::before {
            left: 100%;
        }

        .btn-primary {
            background: var(--gradient-1);
            box-shadow: 0 8px 25px rgba(255, 107, 53, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 35px rgba(255, 107, 53, 0.4);
        }

        .btn-success {
            background: var(--gradient-2);
            box-shadow: 0 8px 25px rgba(78, 205, 196, 0.3);
        }

        .btn-info {
            background: var(--gradient-3);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
        }

        .btn-warning {
            background: var(--gradient-4);
            box-shadow: 0 8px 25px rgba(240, 147, 251, 0.3);
        }

        .btn-dark {
            background: var(--gradient-5);
            box-shadow: 0 8px 25px rgba(44, 62, 80, 0.3);
        }

        .hero-section {
            background: var(--gradient-1);
            color: white;
            border-radius: 30px;
            padding: 100px 50px;
            margin: 30px 0;
            position: relative;
            overflow: hidden;
        }

        .hero-section::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            animation: heroFloat 6s ease-in-out infinite;
        }

        @keyframes heroFloat {
            0%, 100% { transform: rotate(0deg); }
            50% { transform: rotate(180deg); }
        }

        .price-tag {
            background: var(--gradient-4);
            color: white;
            border-radius: 20px;
            padding: 10px 20px;
            font-weight: bold;
            font-size: 1.2rem;
            display: inline-block;
            transform: rotate(-10deg);
            box-shadow: 0 8px 25px rgba(245, 87, 108, 0.4);
            animation: wiggle 2s ease-in-out infinite;
        }

        @keyframes wiggle {
            0%, 100% { transform: rotate(-10deg); }
            50% { transform: rotate(-5deg) scale(1.05); }
        }

        .menu-item-card {
            border-radius: 25px;
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }

        .menu-item-card:hover {
            transform: scale(1.08) rotate(2deg);
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }

        .item-emoji {
            font-size: 4rem;
            display: inline-block;
            animation: itemBounce 3s ease-in-out infinite;
        }

        @keyframes itemBounce {
            0%, 100% { transform: scale(1) rotate(0deg); }
            50% { transform: scale(1.1) rotate(5deg); }
        }

        .cart-count {
            background: var(--gradient-4) !important;
            animation: pulse 1.5s infinite;
            border: 3px solid white;
        }

        @keyframes pulse {
            0% { transform: scale(1); }
            70% { transform: scale(1.1); }
            100% { transform: scale(1); }
        }

        .text-gradient {
            background: var(--gradient-1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1050;
            min-width: 300px;
            border-radius: 15px;
            backdrop-filter: blur(20px);
        }

        .auth-form {
            max-width: 450px;
            margin: 50px auto;
            padding: 40px;
            background: var(--glass);
            backdrop-filter: blur(20px);
            border-radius: 25px;
            border: 1px solid var(--glass-border);
            box-shadow: 0 25px 50px rgba(0,0,0,0.2);
        }

        .form-control {
            background: rgba(255,255,255,0.1);
            border: 1px solid var(--glass-border);
            border-radius: 15px;
            padding: 15px 20px;
            color: white;
            font-weight: 500;
            backdrop-filter: blur(10px);
        }

        .form-control::placeholder {
            color: rgba(255,255,255,0.7);
        }

        .form-control:focus {
            background: rgba(255,255,255,0.2);
            border-color: var(--primary);
            box-shadow: 0 0 0 0.2rem rgba(255, 107, 53, 0.25);
            color: white;
        }

        .admin-panel, .delivery-panel {
            background: var(--gradient-5);
            border-radius: 25px;
            padding: 30px;
            margin: 20px 0;
            color: white;
        }

        .status-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 1px;
        }

        .status-pending { background: var(--warning); }
        .status-preparing { background: var(--info); }
        .status-ready { background: var(--success); }
        .status-delivered { background: var(--dark); color: white; }

        .dashboard-card {
            background: var(--glass);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 30px;
            text-align: center;
            transition: all 0.3s ease;
        }

        .dashboard-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }

        .dashboard-icon {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            font-size: 2rem;
            color: white;
        }

        .store-status-banner {
            padding: 15px;
            border-radius: 15px;
            text-align: center;
            font-weight: bold;
            margin-bottom: 30px;
            color: white;
        }

        .store-open {
            background: var(--gradient-2);
            box-shadow: 0 0 20px rgba(78, 205, 196, 0.4);
        }

        .store-closed {
            background: var(--gradient-4);
            box-shadow: 0 0 20px rgba(240, 147, 251, 0.4);
        }
        
        .loyalty-badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-weight: 600;
            margin-left: 10px;
        }
        
        .loyalty-bronze {
            background: linear-gradient(135deg, #cd7f32, #a56b2d);
            color: white;
        }
        
        .loyalty-silver {
            background: linear-gradient(135deg, #c0c0c0, #a0a0a0);
            color: white;
        }
        
        .loyalty-gold {
            background: linear-gradient(135deg, #ffd700, #d4af37);
            color: #333;
        }
        
        .rating-stars {
            color: #ffc107;
            font-size: 1.5rem;
        }
        
        .pwa-install-prompt {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--glass);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 15px;
            padding: 15px 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 15px;
            max-width: 90%;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
            width: 100%;
        }
        
        .popular-item-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            background: var(--danger);
            color: white;
            border-radius: 20px;
            padding: 5px 10px;
            font-size: 0.8rem;
            font-weight: bold;
            animation: pulse 1.5s infinite;
        }

    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-light sticky-top">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/">
                <i class="fas fa-utensils me-2"></i>Biryani Club
            </a>

            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>

            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="/"><i class="fas fa-home me-1"></i>Home</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/menu"><i class="fas fa-book me-1"></i>Menu</a>
                    </li>
                    {% if session.user_id %}
                        <li class="nav-item">
                            <a class="nav-link" href="/my-orders"><i class="fas fa-shopping-bag me-1"></i>My Orders</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="/profile"><i class="fas fa-user me-1"></i>Profile</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="/rewards"><i class="fas fa-gift me-1"></i>Rewards</a>
                        </li>
                    {% endif %}
                </ul>

                <div class="d-flex align-items-center">
                    {% if session.user_id %}
                        {% if current_user and current_user.is_admin %}
                            <a href="/admin" class="btn btn-dark btn-sm me-2">
                                <i class="fas fa-shield-alt me-1"></i>Admin
                            </a>
                        {% endif %}
                        {% if current_user and current_user.is_delivery %}
                            <a href="/delivery" class="btn btn-info btn-sm me-2">
                                <i class="fas fa-truck me-1"></i>Delivery
                            </a>
                        {% endif %}
                        <button class="btn btn-outline-primary me-2" onclick="toggleCart()">
                            <i class="fas fa-shopping-cart me-1"></i>
                            Cart <span id="cart-count" class="badge cart-count">0</span>
                        </button>
                        <a href="/logout" class="btn btn-outline-danger">
                            <i class="fas fa-sign-out-alt me-1"></i>Logout
                        </a>
                    {% else %}
                        <button class="btn btn-outline-primary me-2" onclick="toggleCart()">
                            <i class="fas fa-shopping-cart me-1"></i>
                            Cart <span id="cart-count" class="badge cart-count">0</span>
                        </button>
                        <a href="/login" class="btn btn-primary me-2">
                            <i class="fas fa-sign-in-alt me-1"></i>Login
                        </a>
                        <a href="/signup" class="btn btn-outline-primary">
                            <i class="fas fa-user-plus me-1"></i>Sign Up
                        </a>
                    {% endif %}
                </div>
            </div>
        </div>
    </nav>

    <!-- Flash Messages -->
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show notification" role="alert">
                    <i class="fas fa-{{ 'exclamation-triangle' if category == 'error' or category == 'danger' else 'check-circle' }} me-2"></i>
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <!-- Main Content -->
    <main>
        {{ content|safe }}
    </main>

    <!-- Cart Modal -->
    <div class="modal fade" id="cartModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content glass-effect">
                <div class="modal-header text-white" style="background: var(--gradient-1); border: none;">
                    <h5 class="modal-title"><i class="fas fa-shopping-cart me-2"></i>Your Cart</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="cart-items"></div>
                    <hr style="border-color: var(--glass-border);">
                    <div class="d-flex justify-content-between h5">
                        <span>Total: </span>
                        <span id="cart-total">₹0</span>
                    </div>
                </div>
                <div class="modal-footer" style="border: none;">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Continue Shopping</button>
                    <a href="/checkout" class="btn btn-primary" id="checkout-button">Proceed to Checkout</a>
                </div>
            </div>
        </div>
    </div>

    <!-- PWA Install Prompt -->
    <div class="pwa-install-prompt" id="pwa-prompt" style="display: none;">
        <div>
            <strong>Install Biryani Club App</strong>
            <p>Get the best experience with our app</p>
        </div>
        <div>
            <button class="btn btn-sm btn-success" id="install-pwa">Install</button>
            <button class="btn btn-sm btn-outline-secondary" id="dismiss-pwa">Dismiss</button>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- PWA Service Worker -->
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js')
                .then(registration => {
                    console.log('ServiceWorker registration successful with scope: ', registration.scope);
                })
                .catch(err => {
                    console.log('ServiceWorker registration failed: ', err);
                });
            });
        }
        
        // PWA install prompt
        let deferredPrompt;
        const pwaPrompt = document.getElementById('pwa-prompt');
        
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            pwaPrompt.style.display = 'flex';
        });
        
        document.getElementById('install-pwa').addEventListener('click', () => {
            pwaPrompt.style.display = 'none';
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then((choiceResult) => {
                if (choiceResult.outcome === 'accepted') {
                    console.log('User accepted the install prompt');
                } else {
                    console.log('User dismissed the install prompt');
                }
                deferredPrompt = null;
            });
        });
        
        document.getElementById('dismiss-pwa').addEventListener('click', () => {
            pwaPrompt.style.display = 'none';
        });
    </script>

    <script>
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        const checkoutButton = document.getElementById('checkout-button');

        function updateCartCount() {
            const count = cart.reduce((sum, item) => sum + item.quantity, 0);
            document.getElementById('cart-count').textContent = count;
        }

        function addToCart(name, price, emoji) {
            const existingItem = cart.find(item => item.name === name);
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                cart.push({name, price, emoji, quantity: 1});
            }
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartCount();
            updateCartModal();
            showNotification(name + ' added to cart!', 'success');
            
            // Track item popularity (simulate)
            fetch('/api/track_popularity', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({item_name: name})
            });
        }

        function updateCartModal() {
            const cartItems = document.getElementById('cart-items');
            const cartTotal = document.getElementById('cart-total');

            if (cart.length === 0) {
                cartItems.innerHTML = '<p class="text-muted text-center">Your cart is empty</p>';
                cartTotal.textContent = '₹0';
                checkoutButton.classList.add('disabled');
                checkoutButton.removeAttribute('href');
                return;
            } else {
                checkoutButton.classList.remove('disabled');
                checkoutButton.setAttribute('href', '/checkout');
            }

            let html = '';
            let total = 0;

            cart.forEach((item, index) => {
                const itemTotal = item.price * item.quantity;
                total += itemTotal;
                html += `
                    <div class="d-flex justify-content-between align-items-center mb-3 p-3 rounded glass-effect">
                        <div>
                            <h6 class="mb-1">${item.emoji} ${item.name}</h6>
                            <small class="text-muted">₹${item.price} each</small>
                        </div>
                        <div class="d-flex align-items-center">
                            <button class="btn btn-sm btn-outline-secondary" onclick="updateQuantity(${index}, -1)">-</button>
                            <span class="mx-3">${item.quantity}</span>
                            <button class="btn btn-sm btn-outline-secondary" onclick="updateQuantity(${index}, 1)">+</button>
                            <div class="ms-3">
                                <strong>₹${itemTotal}</strong>
                                <button class="btn btn-sm btn-outline-danger ms-2" onclick="removeItem(${index})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });

            cartItems.innerHTML = html;
            cartTotal.textContent = '₹' + total;
        }

        function updateQuantity(index, change) {
            cart[index].quantity += change;
            if (cart[index].quantity <= 0) {
                cart.splice(index, 1);
            }
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartCount();
            updateCartModal();
        }

        function removeItem(index) {
            cart.splice(index, 1);
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartCount();
            updateCartModal();
        }

        function toggleCart() {
            updateCartModal();
            const cartModal = new bootstrap.Modal(document.getElementById('cartModal'));
            cartModal.show();
        }

        function showNotification(message, type) {
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} notification glass-effect`;
            notification.innerHTML = `
                <i class="fas fa-check-circle me-2"></i>${message}
                <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
            `;
            document.body.appendChild(notification);

            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, 3000);
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            updateCartCount();
            
            // Close notifications on click
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('btn-close')) {
                    e.target.closest('.notification').remove();
                }
            });
        });
    </script>

    {{ extra_scripts|safe }}
</body>
</html>
"""

# PWA Files
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Biryani Club",
        "short_name": "BiryaniClub",
        "description": "Delicious biryani delivered fast",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ff6b35",
        "theme_color": "#ff6b35",
        "icons": [
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    })

@app.route('/service-worker.js')
def service_worker():
    return app.send_static_file('service-worker.js')

# API Endpoints
@app.route('/api/track_popularity', methods=['POST'])
def track_popularity():
    try:
        data = request.json
        item = MenuItem.query.filter_by(name=data['item_name']).first()
        if item:
            item.popularity += 1
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False})
    except:
        return jsonify({'success': False})

# Authentication Routes
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        phone = data.get('phone')

        # Validate inputs
        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters')
        if not email or not validate_email(email):
            errors.append('Invalid email address')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters')
        if not full_name or len(full_name) < 2:
            errors.append('Full name is required')
        if not phone or not validate_phone(phone):
            errors.append('Invalid phone number')
            
        if errors:
            flash(', '.join(errors), 'danger')
            return jsonify({'success': False, 'errors': errors}) if request.is_json else redirect(url_for('signup'))

        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return jsonify({'success': False, 'error': 'Username already exists'}) if request.is_json else redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return jsonify({'success': False, 'error': 'Email already registered'}) if request.is_json else redirect(url_for('signup'))

        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            phone=phone
        )

        # Check for admin access
        if password == 'cupadmin':
            user.is_admin = True

        db.session.add(user)
        db.session.commit()

        session['user_id'] = user.id
        session['username'] = user.username

        flash('Account created successfully!', 'success')
        return jsonify({'success': True}) if request.is_json else redirect(url_for('home'))

    content = """
<div class="container">
    <div class="auth-form">
        <div class="text-center mb-4">
            <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-1);">
                <i class="fas fa-user-plus"></i>
            </div>
            <h2 class="fw-bold text-white">Join Biryani Club</h2>
            <p class="text-light">Create your account and start ordering!</p>
        </div>

        <form id="signup-form">
            <div class="mb-3">
                <input type="text" class="form-control" name="username" placeholder="Username" required minlength="3">
            </div>
            <div class="mb-3">
                <input type="email" class="form-control" name="email" placeholder="Email Address" required>
            </div>
            <div class="mb-3">
                <input type="text" class="form-control" name="full_name" placeholder="Full Name" required minlength="2">
            </div>
            <div class="mb-3">
                <input type="tel" class="form-control" name="phone" placeholder="Phone Number" required pattern="[0-9]{10,15}">
            </div>
            <div class="mb-4">
                <input type="password" class="form-control" name="password" placeholder="Password" required minlength="6">
                <small class="text-light">Enter 'cupadmin' for admin access</small>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-3">
                <i class="fas fa-user-plus me-2"></i>Create Account
            </button>
        </form>

        <div class="text-center">
            <p class="text-light">Already have an account? 
                <a href="/login" class="text-warning fw-bold">Login here</a>
            </p>
        </div>
    </div>
</div>

<script>
document.getElementById('signup-form').addEventListener('submit', function(e) {
    e.preventDefault();

    const formData = new FormData(this);
    const data = Object.fromEntries(formData.entries());

    fetch('/signup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/';
        } else {
            showNotification(data.error || data.errors.join(', '), 'danger');
        }
    })
    .catch(error => {
        showNotification('Error creating account', 'danger');
    });
});
</script>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Sign Up - Biryani Club", 
                                content=content, 
                                extra_scripts="")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        username = data.get('username')
        password = data.get('password')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome back!', 'success')
            return jsonify({'success': True}) if request.is_json else redirect(url_for('home'))
        else:
            flash('Invalid username or password!', 'danger')
            return jsonify({'success': False, 'error': 'Invalid credentials'}) if request.is_json else redirect(url_for('login'))

    content = """
<div class="container">
    <div class="auth-form">
        <div class="text-center mb-4">
            <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-3);">
                <i class="fas fa-sign-in-alt"></i>
            </div>
            <h2 class="fw-bold text-white">Welcome Back</h2>
            <p class="text-light">Login to your Biryani Club account</p>
        </div>

        <form id="login-form">
            <div class="mb-3">
                <input type="text" class="form-control" name="username" placeholder="Username" required>
            </div>
            <div class="mb-4">
                <input type="password" class="form-control" name="password" placeholder="Password" required>
            </div>
            <div class="mb-3">
                <a href="/forgot-password" class="text-warning">Forgot Password?</a>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-3">
                <i class="fas fa-sign-in-alt me-2"></i>Login
            </button>
        </form>

        <div class="text-center">
            <p class="text-light">Don't have an account? 
                <a href="/signup" class="text-warning fw-bold">Sign up here</a>
            </p>
        </div>
    </div>
</div>

<script>
document.getElementById('login-form').addEventListener('submit', function(e) {
    e.preventDefault();

    const formData = new FormData(this);
    const data = Object.fromEntries(formData.entries());

    fetch('/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/';
        } else {
            showNotification(data.error, 'danger');
        }
    })
    .catch(error => {
        showNotification('Login failed', 'danger');
    });
});
</script>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Login - Biryani Club", 
                                content=content, 
                                extra_scripts="")

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/forgot-password')
def forgot_password():
    # Placeholder for password reset functionality
    content = """
<div class="container">
    <div class="auth-form">
        <div class="text-center mb-4">
            <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-4);">
                <i class="fas fa-key"></i>
            </div>
            <h2 class="fw-bold text-white">Reset Password</h2>
            <p class="text-light">Enter your email to reset your password</p>
        </div>

        <form id="forgot-form">
            <div class="mb-3">
                <input type="email" class="form-control" name="email" placeholder="Email Address" required>
            </div>
            <button type="submit" class="btn btn-primary w-100 mb-3">
                <i class="fas fa-paper-plane me-2"></i>Send Reset Link
            </button>
        </form>

        <div class="text-center">
            <a href="/login" class="text-warning fw-bold">Back to Login</a>
        </div>
    </div>
</div>
"""
    return render_template_string(BASE_TEMPLATE, 
                                title="Forgot Password - Biryani Club", 
                                content=content)

# User Profile Routes
@app.route('/my-orders')
@login_required
def my_orders():
    user = User.query.get(session['user_id'])
    if not user:
        flash('Please log in to view your orders.', 'warning')
        return redirect(url_for('login'))
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    
    # Thank you messages for delivered orders
    thank_you_messages = [
        "Thank you for choosing Biryani Club! 🙏 Order again soon!",
        "We hope you enjoyed your meal! 😋 Come back for more deliciousness!",
        "Your satisfaction is our priority! 💖 See you again soon!",
        "Thanks for being our valued customer! 🌟 Order again anytime!",
        "We're grateful for your order! 🎉 Can't wait to serve you again!",
        "Hope the biryani was perfect! 🍛 Looking forward to your next order!",
        "Thank you for trusting us with your hunger! 😊 Order again soon!"
    ]

    content = f"""
<div class="container py-5">
    <div class="text-center mb-5">
        <h2 class="display-4 fw-bold text-gradient">My Orders 📦</h2>
        <p class="lead text-muted">Track your order history and current orders</p>
    </div>

    <div class="row">
        <div class="col-lg-8 mx-auto">
    """

    if orders:
        for order in orders:
            status_class = f"status-{order.status}"
            status_icons = {
                'pending': 'fas fa-clock',
                'preparing': 'fas fa-fire',
                'ready': 'fas fa-check-circle',
                'delivered': 'fas fa-truck'
            }
            
            # Show random thank you message for delivered orders
            thank_you_msg = ""
            if order.status == 'delivered':
                import random
                thank_you_msg = f'<div class="alert alert-success mt-3"><i class="fas fa-heart me-2"></i>{random.choice(thank_you_messages)}</div>'

            items_summary = ", ".join([f"{item['name']} x{item['quantity']}" for item in order.get_items()][:3])
            if len(order.get_items()) > 3:
                items_summary += "..."

            # Add rating option for delivered orders
            rating_section = ""
            if order.status == 'delivered' and not order.rating:
                rating_section = f"""
                <div class="mt-3">
                    <h6>Rate Your Order:</h6>
                    <div class="rating-stars" id="rating-{order.id}">
                        <i class="far fa-star" data-value="1"></i>
                        <i class="far fa-star" data-value="2"></i>
                        <i class="far fa-star" data-value="3"></i>
                        <i class="far fa-star" data-value="4"></i>
                        <i class="far fa-star" data-value="5"></i>
                    </div>
                    <textarea class="form-control mt-2" id="feedback-{order.id}" placeholder="Your feedback (optional)" rows="2"></textarea>
                    <button class="btn btn-sm btn-primary mt-2" onclick="submitRating({order.id})">Submit Rating</button>
                </div>
                """
            elif order.rating:
                stars = ''.join(['<i class="fas fa-star"></i>' for _ in range(order.rating)])
                rating_section = f"""
                <div class="mt-3">
                    <h6>Your Rating:</h6>
                    <div class="rating-stars">
                        {stars}
                    </div>
                    {f'<p>{order.feedback}</p>' if order.feedback else ''}
                </div>
                """

            content += f"""
            <div class="card mb-4" id="order-{order.order_id}">
                <div class="card-header d-flex justify-content-between align-items-center" style="background: var(--gradient-1); color: white;">
                    <div>
                        <h5 class="mb-0">Order #{order.order_id}</h5>
                        <small class="opacity-75">{order.created_at.strftime('%B %d, %Y at %I:%M %p')}</small>
                    </div>
                    <div class="text-end">
                        <span class="status-badge {status_class}">
                            <i class="{status_icons.get(order.status, 'fas fa-info')} me-1"></i>{order.status.title()}
                        </span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-8">
                            <h6 class="fw-bold text-primary mb-2">Items Ordered:</h6>
                            <p class="text-muted mb-2">{items_summary}</p>
                            <p class="mb-0"><strong>Total: ₹{order.total}</strong></p>
                        </div>
                        <div class="col-md-4 text-md-end">
                            <p class="mb-1"><i class="fas fa-credit-card me-1"></i>{order.payment_method.upper()}</p>
                            <p class="mb-0"><i class="fas fa-map-marker-alt me-1"></i>{order.customer_address[:30]}...</p>
                        </div>
                    </div>
                    {thank_you_msg}
                    {rating_section}
                </div>
            </div>
            """
    else:
        content += """
            <div class="text-center py-5">
                <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-2);">
                    <i class="fas fa-shopping-bag"></i>
                </div>
                <h4 class="fw-bold text-muted mb-3">No Orders Yet</h4>
                <p class="text-muted mb-4">You haven't placed any orders yet. Start by exploring our delicious menu!</p>
                <a href="/menu" class="btn btn-primary">
                    <i class="fas fa-utensils me-2"></i>Browse Menu
                </a>
            </div>
        """

    content += """
        </div>
    </div>
</div>

<script>
// Auto-refresh orders every 30 seconds to show real-time updates
setInterval(function() {
    fetch('/api/my-orders-status')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            data.orders.forEach(order => {
                const orderCard = document.getElementById('order-' + order.order_id);
                if (orderCard) {
                    const statusBadge = orderCard.querySelector('.status-badge');
                    if (statusBadge) {
                        statusBadge.className = 'status-badge status-' + order.status;
                        statusBadge.innerHTML = '<i class="fas fa-' + getStatusIcon(order.status) + ' me-1"></i>' + order.status.charAt(0).toUpperCase() + order.status.slice(1);
                    }
                }
            });
        }
    })
    .catch(error => console.log('Status update failed:', error));
}, 30000);

function getStatusIcon(status) {
    const icons = {
        'pending': 'clock',
        'preparing': 'fire',
        'ready': 'check-circle',
        'delivered': 'truck'
    };
    return icons[status] || 'info';
}

// Rating functionality
function setupRatingStars() {
    document.querySelectorAll('.rating-stars i').forEach(star => {
        star.addEventListener('click', function() {
            const container = this.parentElement;
            const value = parseInt(this.getAttribute('data-value'));
            
            // Update stars
            container.querySelectorAll('i').forEach((s, index) => {
                if (index < value) {
                    s.classList.remove('far');
                    s.classList.add('fas');
                } else {
                    s.classList.remove('fas');
                    s.classList.add('far');
                }
            });
        });
    });
}

function submitRating(orderId) {
    const container = document.getElementById(`rating-${orderId}`);
    const stars = container.querySelectorAll('.fas').length;
    const feedback = document.getElementById(`feedback-${orderId}`).value;
    
    if (stars === 0) {
        showNotification('Please select a rating', 'warning');
        return;
    }
    
    fetch('/api/submit-rating', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId,
            rating: stars,
            feedback: feedback
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Rating submitted!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error submitting rating', 'danger');
        }
    });
}

// Initialize rating stars
document.addEventListener('DOMContentLoaded', setupRatingStars);
</script>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="My Orders - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/api/my-orders-status')
@login_required
def api_my_orders_status():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
    
    orders_data = []
    for order in orders:
        orders_data.append({
            'order_id': order.order_id,
            'status': order.status
        })
    
    return jsonify({'success': True, 'orders': orders_data})

@app.route('/api/submit-rating', methods=['POST'])
@login_required
def submit_rating():
    try:
        data = request.json
        order = Order.query.filter_by(id=data['order_id'], user_id=session['user_id']).first()
        if order:
            order.rating = data['rating']
            order.feedback = data.get('feedback', '')
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    if not user:
        flash('Please log in to view your profile.', 'warning')
        return redirect(url_for('login'))
    orders = Order.query.filter_by(customer_phone=user.phone).order_by(Order.created_at.desc()).all()

    # Determine loyalty tier
    tier_info = {
        'bronze': {'min': 0, 'max': 99, 'name': 'Bronze', 'color': 'bronze'},
        'silver': {'min': 100, 'max': 499, 'name': 'Silver', 'color': 'silver'},
        'gold': {'min': 500, 'name': 'Gold', 'color': 'gold'}
    }
    
    current_tier = tier_info[user.loyalty_tier]
    next_tier = None
    if user.loyalty_tier == 'bronze':
        next_tier = tier_info['silver']
    elif user.loyalty_tier == 'silver':
        next_tier = tier_info['gold']
    
    progress = 0
    if next_tier:
        progress = min(100, (user.loyalty_points - current_tier['min']) / (next_tier['min'] - current_tier['min']) * 100)

    content = f"""
<div class="container py-5">
    <div class="row">
        <div class="col-lg-4">
            <div class="card text-center">
                <div class="card-body p-4">
                    <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-1);">
                        <i class="fas fa-user"></i>
                    </div>
                    <h4 class="fw-bold">{user.full_name}</h4>
                    <p class="text-muted">@{user.username}</p>
                    <p><i class="fas fa-envelope me-2"></i>{user.email}</p>
                    <p><i class="fas fa-phone me-2"></i>{user.phone}</p>
                    <div class="mt-3">
                        <span class="badge" style="background: var(--gradient-2); font-size: 1rem; padding: 10px 20px;">
                            <i class="fas fa-star me-2"></i>{user.loyalty_points} Points
                            <span class="loyalty-badge loyalty-{current_tier['color']}">{current_tier['name']}</span>
                        </span>
                    </div>
                    {"<div class='mt-3'><span class='badge bg-danger'>Admin User</span></div>" if user.is_admin else ""}
                    {"<div class='mt-2'><span class='badge bg-info'>Delivery Team</span></div>" if user.is_delivery else ""}
                </div>
            </div>
            
            <div class="card mt-4">
                <div class="card-header" style="background: var(--gradient-1); color: white;">
                    <h5 class="mb-0"><i class="fas fa-crown me-2"></i>Loyalty Status</h5>
                </div>
                <div class="card-body">
                    <div class="text-center">
                        <div class="loyalty-badge loyalty-{current_tier['color']} mb-3" style="font-size: 1.5rem; padding: 10px 20px;">
                            {current_tier['name']} Member
                        </div>
    """
    
    if next_tier:
        content += f"""
                        <p class="mb-2">Progress to {next_tier['name']} Tier</p>
                        <div class="progress mb-3" style="height: 20px; border-radius: 10px;">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                 role="progressbar" 
                                 style="width: {progress}%; background: var(--{current_tier['color']});"
                                 aria-valuenow="{progress}" 
                                 aria-valuemin="0" 
                                 aria-valuemax="100">{int(progress)}%</div>
                        </div>
                        <p class="mb-0">Earn {next_tier['min'] - user.loyalty_points} more points to reach {next_tier['name']} tier</p>
        """
    else:
        content += """
                        <p class="mb-0">You've reached the highest loyalty tier!</p>
        """
    
    content += """
                    </div>
                </div>
            </div>
        </div>

        <div class="col-lg-8">
            <div class="card">
                <div class="card-header" style="background: var(--gradient-1); color: white;">
                    <h5 class="mb-0"><i class="fas fa-history me-2"></i>Order History</h5>
                </div>
                <div class="card-body">
    """

    if orders:
        for order in orders:
            status_class = f"status-{order.status}"
            content += f"""
                    <div class="d-flex justify-content-between align-items-center p-3 mb-3 rounded glass-effect">
                        <div>
                            <h6 class="mb-1">Order #{order.order_id}</h6>
                            <p class="mb-0 text-muted">{order.created_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                        </div>
                        <div class="text-end">
                            <div class="mb-1">
                                <span class="status-badge {status_class}">{order.status}</span>
                            </div>
                            <strong>₹{order.total}</strong>
                        </div>
                    </div>
            """
    else:
        content += """
                    <p class="text-muted text-center">No orders yet. <a href="/menu">Start ordering!</a></p>
        """

    content += """
                </div>
            </div>
        </div>
    </div>
</div>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Profile - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/rewards')
@login_required
def rewards():
    user = User.query.get(session['user_id'])
    if not user:
        flash('Please log in to view rewards.', 'warning')
        return redirect(url_for('login'))
    
    # Define rewards
    rewards = [
        {'name': '₹50 Discount', 'points': 100, 'description': 'Get ₹50 off your next order', 'icon': 'fa-tag'},
        {'name': 'Free Drink', 'points': 50, 'description': 'Free beverage with your order', 'icon': 'fa-coffee'},
        {'name': 'Free Dessert', 'points': 75, 'description': 'Complimentary dessert', 'icon': 'fa-ice-cream'},
        {'name': 'Priority Delivery', 'points': 200, 'description': 'Jump to front of the queue', 'icon': 'fa-bolt'},
        {'name': 'Birthday Surprise', 'points': 150, 'description': 'Special gift on your birthday', 'icon': 'fa-gift'},
    ]
    
    content = f"""
<div class="container py-5">
    <div class="text-center mb-5">
        <h2 class="display-4 fw-bold text-gradient">Rewards & Benefits</h2>
        <p class="lead text-muted">Redeem your loyalty points for exciting rewards</p>
        
        <div class="card glass-effect d-inline-block mt-4">
            <div class="card-body">
                <h4 class="fw-bold mb-0">
                    <i class="fas fa-star me-2 text-warning"></i>{user.loyalty_points} Points Available
                </h4>
            </div>
        </div>
    </div>

    <div class="row g-4">
        {''.join([f"""
        <div class="col-md-4">
            <div class="card h-100">
                <div class="card-body text-center p-4">
                    <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-{i % 5 + 1});">
                        <i class="fas {reward['icon']}"></i>
                    </div>
                    <h4 class="fw-bold">{reward['name']}</h4>
                    <p class="text-muted">{reward['description']}</p>
                    <div class="mt-3">
                        <span class="badge" style="background: var(--gradient-2); font-size: 1rem; padding: 8px 15px;">
                            {reward['points']} Points
                        </span>
                    </div>
                    <button class="btn btn-primary mt-3 {'disabled' if user.loyalty_points < reward['points'] else ''}" 
                            onclick="redeemReward({reward['points']}, '{reward['name']}')">
                        <i class="fas fa-gift me-2"></i>Redeem Now
                    </button>
                </div>
            </div>
        </div>
        """ for i, reward in enumerate(rewards)])}
    </div>
</div>

<script>
function redeemReward(points, name) {
    if (!confirm(`Redeem ${points} points for "${name}"?`)) return;
    
    fetch('/api/redeem-reward', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            points: points,
            reward_name: name
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(`Reward redeemed: ${name}`, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification(data.error, 'danger');
        }
    });
}
</script>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Rewards - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/api/redeem-reward', methods=['POST'])
@login_required
def redeem_reward():
    try:
        data = request.json
        user = User.query.get(session['user_id'])
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
            
        if user.loyalty_points < data['points']:
            return jsonify({'success': False, 'error': 'Not enough points'})
            
        user.loyalty_points -= data['points']
        
        # Update loyalty tier
        if user.loyalty_points < 100:
            user.loyalty_tier = 'bronze'
        elif user.loyalty_points < 500:
            user.loyalty_tier = 'silver'
        else:
            user.loyalty_tier = 'gold'
        
        db.session.commit()
        
        # In a real app, you would generate a coupon code here
        flash(f"Reward redeemed: {data['reward_name']}. Code: BIRYANI{user.id}{int(datetime.now().timestamp())}", 'success')
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Admin Panel
@app.route('/admin')
@admin_required
def admin():
    total_orders = Order.query.count()
    total_users = User.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    active_promotions = Promotion.query.filter_by(active=True).count()

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    # Popular items
    popular_items = MenuItem.query.order_by(MenuItem.popularity.desc()).limit(5).all()

    content = f"""
<div class="container py-5">
    <div class="text-center mb-5">
        <h2 class="display-4 fw-bold text-gradient">Admin Dashboard</h2>
        <p class="lead text-muted">Manage your Biryani Club operations</p>
    </div>

    <!-- Store Status Toggle -->
    <div class="text-center mb-5">
        <button class="btn btn-lg {'btn-success' if store_status['open'] else 'btn-danger'}" onclick="toggleStore()">
            <i class="fas fa-{ 'check-circle' if store_status['open'] else 'times-circle'} me-2"></i>
            Store is currently {'Open' if store_status['open'] else 'Closed'}
        </button>
    </div>

    <!-- Quick Actions -->
    <div class="row g-3 mb-5">
        <div class="col-md-3">
            <button class="btn btn-info w-100" onclick="showStockManagement()">
                <i class="fas fa-boxes me-2"></i>Manage Stock
            </button>
        </div>
        <div class="col-md-3">
            <button class="btn btn-warning w-100" onclick="showAssignDelivery()">
                <i class="fas fa-truck me-2"></i>Assign Delivery
            </button>
        </div>
        <div class="col-md-3">
            <button class="btn btn-secondary w-100" onclick="showPromotions()">
                <i class="fas fa-tags me-2"></i>Promotions
            </button>
        </div>
        <div class="col-md-3">
            <button class="btn btn-dark w-100" onclick="showAnalytics()">
                <i class="fas fa-chart-line me-2"></i>Analytics
            </button>
        </div>
    </div>

    <!-- Stats Cards -->
    <div class="row g-4 mb-5">
        <div class="col-lg-3 col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-1);">
                    <i class="fas fa-shopping-cart"></i>
                </div>
                <h3 class="fw-bold">{total_orders}</h3>
                <p class="text-muted">Total Orders</p>
            </div>
        </div>
        <div class="col-lg-3 col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-2);">
                    <i class="fas fa-users"></i>
                </div>
                <h3 class="fw-bold">{total_users}</h3>
                <p class="text-muted">Total Users</p>
            </div>
        </div>
        <div class="col-lg-3 col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-4);">
                    <i class="fas fa-clock"></i>
                </div>
                <h3 class="fw-bold">{pending_orders}</h3>
                <p class="text-muted">Pending Orders</p>
            </div>
        </div>
        <div class="col-lg-3 col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-3);">
                    <i class="fas fa-rupee-sign"></i>
                </div>
                <h3 class="fw-bold">₹{total_revenue:,.0f}</h3>
                <p class="text-muted">Total Revenue</p>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-md-6">
            <!-- Recent Orders -->
            <div class="card mb-4">
                <div class="card-header d-flex justify-content-between align-items-center" style="background: var(--gradient-5); color: white;">
                    <h5 class="mb-0"><i class="fas fa-list me-2"></i>Recent Orders</h5>
                    <button class="btn btn-light btn-sm" onclick="refreshOrders()">
                        <i class="fas fa-refresh me-1"></i>Refresh
                    </button>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Order ID</th>
                                    <th>Customer</th>
                                    <th>Total</th>
                                    <th>Status</th>
                                    <th>Date</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for order in recent_orders:
        status_class = f"status-{order.status}"

        content += f"""
                                <tr>
                                    <td><strong>#{order.order_id}</strong></td>
                                    <td>{order.customer_name}</td>
                                    <td><strong>₹{order.total}</strong></td>
                                    <td><span class="status-badge {status_class}">{order.status}</span></td>
                                    <td>{order.created_at.strftime('%m/%d/%Y')}</td>
                                    <td>
                                        <div class="btn-group" role="group">
                                            <button class="btn btn-info btn-sm" onclick="updateOrderStatus('{order.order_id}', 'preparing')">
                                                <i class="fas fa-fire"></i>
                                            </button>
                                            <button class="btn btn-success btn-sm" onclick="updateOrderStatus('{order.order_id}', 'ready')">
                                                <i class="fas fa-check"></i>
                                            </button>
                                            <button class="btn btn-primary btn-sm" onclick="updateOrderStatus('{order.order_id}', 'delivered')">
                                                <i class="fas fa-truck"></i>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
        """

    content += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-md-6">
            <!-- Popular Items -->
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center" style="background: var(--gradient-1); color: white;">
                    <h5 class="mb-0"><i class="fas fa-fire me-2"></i>Popular Items</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Item</th>
                                    <th>Category</th>
                                    <th>Popularity</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for item in popular_items:
        content += f"""
                                <tr>
                                    <td>{item.emoji} {item.name}</td>
                                    <td>{item.category}</td>
                                    <td>
                                        <div class="progress" style="height: 20px;">
                                            <div class="progress-bar bg-success" role="progressbar" 
                                                style="width: {min(100, item.popularity)}%;" 
                                                aria-valuenow="{item.popularity}" 
                                                aria-valuemin="0" 
                                                aria-valuemax="100">{item.popularity}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
        """

    content += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Stock Management Modal -->
    <div class="modal fade" id="stockModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content glass-effect">
                <div class="modal-header text-white" style="background: var(--gradient-2);">
                    <h5 class="modal-title"><i class="fas fa-boxes me-2"></i>Stock Management</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="stock-items"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Assign Delivery Modal -->
    <div class="modal fade" id="deliveryModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content glass-effect">
                <div class="modal-header text-white" style="background: var(--gradient-3);">
                    <h5 class="modal-title"><i class="fas fa-truck me-2"></i>Assign Delivery Person</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="delivery-assignments"></div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Promotions Modal -->
    <div class="modal fade" id="promotionsModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content glass-effect">
                <div class="modal-header text-white" style="background: var(--gradient-4);">
                    <h5 class="modal-title"><i class="fas fa-tags me-2"></i>Manage Promotions</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="promotions-content"></div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Analytics Modal -->
    <div class="modal fade" id="analyticsModal" tabindex="-1">
        <div class="modal-dialog modal-xl">
            <div class="modal-content glass-effect">
                <div class="modal-header text-white" style="background: var(--gradient-5);">
                    <h5 class="modal-title"><i class="fas fa-chart-line me-2"></i>Sales Analytics</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="chart-container">
                        <canvas id="salesChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function updateOrderStatus(orderId, status) {
    fetch('/admin/update_order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Order status updated!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error updating status', 'danger');
        }
    });
}

function refreshOrders() {
    location.reload();
}

function toggleStore() {
    fetch('/admin/toggle_store', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Store status updated!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error updating store status', 'danger');
        }
    });
}

function showStockManagement() {
    fetch('/admin/stock_items')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let html = '';
            data.items.forEach(item => {
                const stockStatus = item.in_stock ? 'In Stock' : 'Out of Stock';
                const btnClass = item.in_stock ? 'btn-danger' : 'btn-success';
                const btnText = item.in_stock ? 'Mark Out of Stock' : 'Mark In Stock';
                const btnIcon = item.in_stock ? 'times' : 'check';
                
                html += `
                    <div class="d-flex justify-content-between align-items-center p-3 mb-3 rounded glass-effect">
                        <div>
                            <h6 class="mb-1">${item.emoji} ${item.name}</h6>
                            <small class="text-muted">₹${item.price} - ${item.category}</small><br>
                            <span class="badge ${item.in_stock ? 'bg-success' : 'bg-danger'}">${stockStatus}</span>
                        </div>
                        <button class="btn ${btnClass} btn-sm" onclick="toggleStock('${item.name}', ${!item.in_stock})">
                            <i class="fas fa-${btnIcon} me-1"></i>${btnText}
                        </button>
                    </div>
                `;
            });
            document.getElementById('stock-items').innerHTML = html;
            const stockModal = new bootstrap.Modal(document.getElementById('stockModal'));
            stockModal.show();
        }
    });
}

function toggleStock(itemName, inStock) {
    fetch('/admin/toggle_stock', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            item_name: itemName,
            in_stock: inStock
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Stock status updated!', 'success');
            showStockManagement(); // Refresh the modal
        } else {
            showNotification('Error updating stock', 'danger');
        }
    });
}

function showAssignDelivery() {
    fetch('/admin/delivery_assignments')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let html = '';
            data.ready_orders.forEach(order => {
                html += `
                    <div class="card mb-3">
                        <div class="card-body">
                            <h6>Order #${order.order_id}</h6>
                            <p class="mb-2">${order.customer_name} - ₹${order.total}</p>
                            <select class="form-select mb-2" id="delivery-${order.order_id}">
                                <option value="">Select Delivery Person</option>
                `;
                
                data.delivery_persons.forEach(person => {
                    html += `<option value="${person.id}">${person.full_name}</option>`;
                });
                
                html += `
                            </select>
                            <button class="btn btn-primary btn-sm" onclick="assignDelivery('${order.order_id}')">
                                <i class="fas fa-truck me-1"></i>Assign
                            </button>
                        </div>
                    </div>
                `;
            });
            
            if (data.ready_orders.length === 0) {
                html = '<p class="text-muted text-center">No orders ready for delivery assignment.</p>';
            }
            
            document.getElementById('delivery-assignments').innerHTML = html;
            const deliveryModal = new bootstrap.Modal(document.getElementById('deliveryModal'));
            deliveryModal.show();
        }
    });
}

function assignDelivery(orderId) {
    const selectElement = document.getElementById('delivery-' + orderId);
    const deliveryPersonId = selectElement.value;
    
    if (!deliveryPersonId) {
        showNotification('Please select a delivery person', 'warning');
        return;
    }
    
    fetch('/admin/assign_delivery', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId,
            delivery_person_id: deliveryPersonId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Delivery person assigned!', 'success');
            showAssignDelivery(); // Refresh the modal
        } else {
            showNotification('Error assigning delivery person', 'danger');
        }
    });
}

function showPromotions() {
    fetch('/admin/promotions')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let html = `
                <button class="btn btn-success mb-3" onclick="showAddPromotion()">
                    <i class="fas fa-plus me-2"></i>Add New Promotion
                </button>
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Code</th>
                                <th>Description</th>
                                <th>Discount</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            data.promotions.forEach(promo => {
                const discount = promo.discount_type === 'percent' ? 
                    `${promo.discount_value}%` : `₹${promo.discount_value}`;
                    
                const status = promo.active ? 
                    '<span class="badge bg-success">Active</span>' : 
                    '<span class="badge bg-secondary">Inactive</span>';
                
                html += `
                    <tr>
                        <td><strong>${promo.code}</strong></td>
                        <td>${promo.description}</td>
                        <td>${discount}</td>
                        <td>${status}</td>
                        <td>
                            <button class="btn btn-sm btn-info" onclick="editPromotion(${promo.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deletePromotion(${promo.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            html += `
                        </tbody>
                    </table>
                </div>
            `;
            
            document.getElementById('promotions-content').innerHTML = html;
            const promotionsModal = new bootstrap.Modal(document.getElementById('promotionsModal'));
            promotionsModal.show();
        }
    });
}

function showAddPromotion() {
    const html = `
        <div class="card">
            <div class="card-body">
                <h5 class="mb-4">Add New Promotion</h5>
                <form id="add-promotion-form">
                    <div class="mb-3">
                        <label class="form-label">Code</label>
                        <input type="text" class="form-control" name="code" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Description</label>
                        <textarea class="form-control" name="description" required></textarea>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Discount Type</label>
                            <select class="form-select" name="discount_type" required>
                                <option value="percent">Percentage</option>
                                <option value="fixed">Fixed Amount</option>
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Discount Value</label>
                            <input type="number" class="form-control" name="discount_value" step="0.01" min="0" required>
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Minimum Order (₹)</label>
                            <input type="number" class="form-control" name="min_order" step="0.01" min="0">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Max Usage</label>
                            <input type="number" class="form-control" name="max_usage" min="1">
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Valid From</label>
                            <input type="date" class="form-control" name="valid_from">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Valid To</label>
                            <input type="date" class="form-control" name="valid_to">
                        </div>
                    </div>
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" name="active" id="promo-active" checked>
                        <label class="form-check-label" for="promo-active">Active</label>
                    </div>
                    <button type="submit" class="btn btn-primary">Save Promotion</button>
                </form>
            </div>
        </div>
    `;
    
    document.getElementById('promotions-content').innerHTML = html;
    
    // Add form submission handler
    document.getElementById('add-promotion-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const data = Object.fromEntries(formData.entries());
        
        fetch('/admin/add_promotion', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('Promotion added!', 'success');
                showPromotions(); // Refresh promotions list
            } else {
                showNotification('Error adding promotion', 'danger');
            }
        });
    });
}

function showAnalytics() {
    fetch('/admin/sales_data')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const ctx = document.getElementById('salesChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Daily Revenue',
                        data: data.revenue,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        borderWidth: 3,
                        tension: 0.3,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                callback: function(value) {
                                    return '₹' + value;
                                }
                            }
                        },
                        x: {
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#fff'
                            }
                        }
                    }
                }
            });
            
            const analyticsModal = new bootstrap.Modal(document.getElementById('analyticsModal'));
            analyticsModal.show();
        }
    });
}
</script>
"""

    user = User.query.get(session['user_id'])
    return render_template_string(BASE_TEMPLATE, 
                                title="Admin Panel - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

# Admin API Endpoints
@app.route('/admin/update_order', methods=['POST'])
@admin_required
def update_order_status():
    try:
        data = request.json
        order_id = data.get('order_id')
        status = data.get('status')

        order = Order.query.filter_by(order_id=order_id).first()
        if order:
            order.status = status
            if status == 'ready':
                order.estimated_delivery = datetime.now() + timedelta(minutes=30)
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/toggle_store', methods=['POST'])
@admin_required
def toggle_store_status():
    global store_status
    store_status['open'] = not store_status['open']
    return jsonify({'success': True, 'open': store_status['open']})

@app.route('/admin/stock_items')
@admin_required
def get_stock_items():
    try:
        # Get items from database, or create them if they don't exist
        db_items = MenuItem.query.all()
        
        if not db_items:
            # Initialize database with menu items
            for category, items in MENU.items():
                for item in items:
                    menu_item = MenuItem(
                        name=item['name'],
                        category=category,
                        price=item['price'],
                        description=item['description'],
                        emoji=item['emoji'],
                        in_stock=True
                    )
                    db.session.add(menu_item)
            db.session.commit()
            db_items = MenuItem.query.all()
        
        items_data = []
        for item in db_items:
            items_data.append({
                'name': item.name,
                'category': item.category,
                'price': item.price,
                'description': item.description,
                'emoji': item.emoji,
                'in_stock': item.in_stock
            })
        
        return jsonify({'success': True, 'items': items_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/toggle_stock', methods=['POST'])
@admin_required
def toggle_stock():
    try:
        data = request.json
        item_name = data.get('item_name')
        in_stock = data.get('in_stock')
        
        item = MenuItem.query.filter_by(name=item_name).first()
        if item:
            item.in_stock = in_stock
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Item not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delivery_assignments')
@admin_required
def get_delivery_assignments():
    try:
        ready_orders = Order.query.filter_by(status='ready', delivery_person_id=None).all()
        delivery_persons = User.query.filter_by(is_delivery=True).all()
        
        orders_data = []
        for order in ready_orders:
            orders_data.append({
                'order_id': order.order_id,
                'customer_name': order.customer_name,
                'total': order.total
            })
        
        persons_data = []
        for person in delivery_persons:
            persons_data.append({
                'id': person.id,
                'full_name': person.full_name
            })
        
        return jsonify({
            'success': True,
            'ready_orders': orders_data,
            'delivery_persons': persons_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/assign_delivery', methods=['POST'])
@admin_required
def assign_delivery_person():
    try:
        data = request.json
        order_id = data.get('order_id')
        delivery_person_id = data.get('delivery_person_id')
        
        order = Order.query.filter_by(order_id=order_id).first()
        if order:
            order.delivery_person_id = delivery_person_id
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/promotions')
@admin_required
def get_promotions():
    try:
        promotions = Promotion.query.all()
        promotions_data = []
        for promo in promotions:
            promotions_data.append({
                'id': promo.id,
                'code': promo.code,
                'description': promo.description,
                'discount_type': promo.discount_type,
                'discount_value': promo.discount_value,
                'min_order': promo.min_order,
                'valid_from': promo.valid_from.strftime('%Y-%m-%d') if promo.valid_from else None,
                'valid_to': promo.valid_to.strftime('%Y-%m-%d') if promo.valid_to else None,
                'max_usage': promo.max_usage,
                'usage_count': promo.usage_count,
                'active': promo.active
            })
        return jsonify({'success': True, 'promotions': promotions_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/add_promotion', methods=['POST'])
@admin_required
def add_promotion():
    try:
        data = request.json
        promo = Promotion(
            code=data['code'],
            description=data['description'],
            discount_type=data['discount_type'],
            discount_value=data['discount_value'],
            min_order=data.get('min_order', 0),
            valid_from=datetime.strptime(data['valid_from'], '%Y-%m-%d') if data.get('valid_from') else None,
            valid_to=datetime.strptime(data['valid_to'], '%Y-%m-%d') if data.get('valid_to') else None,
            max_usage=data.get('max_usage', 1),
            active=data.get('active', 'off') == 'on'
        )
        db.session.add(promo)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/sales_data')
@admin_required
def sales_data():
    # Generate sample sales data (in a real app, this would come from the database)
    labels = [f"Day {i}" for i in range(1, 31)]
    revenue = [1000 + i*150 + random.randint(-200, 200) for i in range(30)]
    return jsonify({
        'success': True,
        'labels': labels,
        'revenue': revenue
    })

# Delivery Panel
@app.route('/delivery')
@delivery_required
def delivery_panel():
    delivery_person = User.query.get(session['user_id'])
    assigned_orders = Order.query.filter_by(delivery_person_id=delivery_person.id, status='ready').all()
    available_orders = Order.query.filter_by(status='ready', delivery_person_id=None).all()

    content = f"""
<div class="container py-5">
    <div class="text-center mb-5">
        <h2 class="display-4 fw-bold text-gradient">Delivery Dashboard</h2>
        <p class="lead text-muted">Welcome back, {delivery_person.full_name}!</p>
    </div>

    <!-- Stats -->
    <div class="row g-4 mb-5">
        <div class="col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-1);">
                    <i class="fas fa-truck"></i>
                </div>
                <h3 class="fw-bold">{len(assigned_orders)}</h3>
                <p class="text-muted">My Deliveries</p>
            </div>
        </div>
        <div class="col-md-6">
            <div class="dashboard-card">
                <div class="dashboard-icon mx-auto" style="background: var(--gradient-2);">
                    <i class="fas fa-clock"></i>
                </div>
                <h3 class="fw-bold">{len(available_orders)}</h3>
                <p class="text-muted">Available Orders</p>
            </div>
        </div>
    </div>

    <!-- My Deliveries -->
    <div class="card mb-4">
        <div class="card-header" style="background: var(--gradient-1); color: white;">
            <h5 class="mb-0"><i class="fas fa-truck me-2"></i>My Deliveries</h5>
        </div>
        <div class="card-body">
    """

    if assigned_orders:
        for order in assigned_orders:
            content += f"""
            <div class="d-flex justify-content-between align-items-center p-3 mb-3 rounded glass-effect">
                <div>
                    <h6 class="mb-1">Order #{order.order_id}</h6>
                    <p class="mb-1"><i class="fas fa-user me-1"></i>{order.customer_name} - {order.customer_phone}</p>
                    <p class="mb-0"><i class="fas fa-map-marker-alt me-1"></i>{order.customer_address}</p>
                </div>
                <div class="text-end">
                    <div class="mb-2">
                        <strong>₹{order.total}</strong>
                    </div>
                    <button class="btn btn-success btn-sm" onclick="completeDelivery('{order.order_id}')">
                        <i class="fas fa-check me-1"></i>Delivered
                    </button>
                </div>
            </div>
            """
    else:
        content += """
            <p class="text-muted text-center">No current deliveries assigned.</p>
        """

    content += """
        </div>
    </div>

    <!-- Available Orders -->
    <div class="card">
        <div class="card-header" style="background: var(--gradient-2); color: white;">
            <h5 class="mb-0"><i class="fas fa-list me-2"></i>Available Orders</h5>
        </div>
        <div class="card-body">
    """

    if available_orders:
        for order in available_orders:
            content += f"""
            <div class="d-flex justify-content-between align-items-center p-3 mb-3 rounded glass-effect">
                <div>
                    <h6 class="mb-1">Order #{order.order_id}</h6>
                    <p class="mb-1"><i class="fas fa-user me-1"></i>{order.customer_name} - {order.customer_phone}</p>
                    <p class="mb-0"><i class="fas fa-map-marker-alt me-1"></i>{order.customer_address}</p>
                </div>
                <div class="text-end">
                    <div class="mb-2">
                        <strong>₹{order.total}</strong>
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="acceptDelivery('{order.order_id}')">
                        <i class="fas fa-truck me-1"></i>Accept
                    </button>
                </div>
            </div>
            """
    else:
        content += """
            <p class="text-muted text-center">No orders available for delivery.</p>
        """

    content += """
        </div>
    </div>
</div>

<script>
function acceptDelivery(orderId) {
    fetch('/delivery/accept', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Delivery accepted!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error accepting delivery', 'danger');
        }
    });
}

function completeDelivery(orderId) {
    fetch('/delivery/complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Delivery completed!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error completing delivery', 'danger');
        }
    });
}
</script>
"""

    user = User.query.get(session['user_id'])
    return render_template_string(BASE_TEMPLATE, 
                                title="Delivery Panel - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/delivery/accept', methods=['POST'])
@delivery_required
def accept_delivery():
    try:
        data = request.json
        order_id = data.get('order_id')

        order = Order.query.filter_by(order_id=order_id).first()
        if order:
            order.delivery_person_id = session['user_id']
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delivery/complete', methods=['POST'])
@delivery_required
def complete_delivery():
    try:
        data = request.json
        order_id = data.get('order_id')

        order = Order.query.filter_by(order_id=order_id).first()
        if order:
            order.status = 'delivered'
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Main Routes
@app.route('/')
def home():
    user = User.query.get(session.get('user_id')) if 'user_id' in session else None

    store_status_banner = ""
    if not store_status['open']:
        store_status_banner = """
        <div class="container">
            <div class="store-status-banner store-closed">
                <i class="fas fa-times-circle me-2"></i>The store is currently closed. Orders are not being accepted.
            </div>
        </div>
        """
    else:
        store_status_banner = """
        <div class="container">
            <div class="store-status-banner store-open">
                <i class="fas fa-check-circle me-2"></i>Welcome! The store is open and accepting orders.
            </div>
        </div>
        """

    # Get popular items
    popular_items = MenuItem.query.order_by(MenuItem.popularity.desc()).limit(3).all()

    popular_section = ""
    if popular_items:
        popular_section = """
        <section class="py-5">
            <div class="container">
                <div class="text-center mb-5">
                    <h2 class="display-5 fw-bold text-gradient">Customer Favorites</h2>
                    <p class="lead text-muted">Most popular dishes this week</p>
                </div>
                
                <div class="row g-4">
        """ + ''.join([f"""
                    <div class="col-md-4">
                        <div class="card menu-item-card h-100">
                            <div class="card-body text-center p-4 position-relative">
                                <span class="popular-item-badge">Popular</span>
                                <div class="item-emoji">{item.emoji}</div>
                                <h4 class="fw-bold">{item.name}</h4>
                                <p class="text-muted">{item.description}</p>
                                <div class="d-flex justify-content-between align-items-center mt-3">
                                    <div class="price-tag">₹{item.price}</div>
                                    <button class="btn btn-primary" onclick="addToCart('{item.name}', {item.price}, '{item.emoji}')">
                                        <i class="fas fa-plus me-2"></i>Add
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
        """ for item in popular_items]) + """
                </div>
            </div>
        </section>
        """

    content = f"""
<!-- Store Status Banner -->
{store_status_banner}

<!-- Hero Section -->
<section class="hero-section position-relative text-white text-center overflow-hidden">
    <div class="container position-relative">
        <div class="row align-items-center">
            <div class="col-lg-8 mx-auto">
                <h1 class="display-2 fw-bold mb-4">
                    <span class="item-emoji">🍛</span> Welcome to <br>
                    <span style="background: linear-gradient(45deg, #ffd700, #ffec8c); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Biryani Club</span>
                    <span class="item-emoji">✨</span>
                </h1>
                <p class="lead mb-5 fs-3">Authentic, mouth-watering biryani and delicious treats, delivered fresh to your doorstep in <strong>30 minutes</strong>!</p>

                <div class="d-grid gap-3 d-md-flex justify-content-md-center">
                    <a href="/menu" class="btn btn-light btn-lg px-5 py-3" style="background: linear-gradient(45deg, #ff6b35, #f7931e); color: white; font-weight: bold;">
                        <i class="fas fa-fire me-2"></i>Order Now
                    </a>
                    <a href="tel:+919876543210" class="btn btn-outline-light btn-lg px-4 py-3">
                        <i class="fas fa-phone me-2"></i>Call Us
                    </a>
                </div>
            </div>
        </div>
    </div>
</section>

<!-- Features Section -->
<section class="py-5">
    <div class="container">
        <div class="text-center mb-5">
            <h2 class="display-5 fw-bold text-gradient">Why Choose Biryani Club?</h2>
            <p class="lead text-muted">Experience the magic of authentic flavors</p>
        </div>

        <div class="row g-4">
            <div class="col-lg-4">
                <div class="card text-center h-100">
                    <div class="card-body p-4">
                        <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-2);">
                            <i class="fas fa-rocket"></i>
                        </div>
                        <h4 class="fw-bold mb-3">Lightning Fast ⚡</h4>
                        <p class="text-muted">Fresh, hot biryani delivered within 30-45 minutes guaranteed!</p>
                    </div>
                </div>
            </div>

            <div class="col-lg-4">
                <div class="card text-center h-100">
                    <div class="card-body p-4">
                        <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-2);">
                            <i class="fas fa-seedling"></i>
                        </div>
                        <h4 class="fw-bold mb-3">Fresh Ingredients 🌿</h4>
                        <p class="text-muted">Only the freshest ingredients and authentic spices for perfect taste.</p>
                    </div>
                </div>
            </div>

            <div class="col-lg-4">
                <div class="card text-center h-100">
                    <div class="card-body p-4">
                        <div class="dashboard-icon mx-auto mb-3" style="background: var(--gradient-2);">
                            <i class="fas fa-heart"></i>
                        </div>
                        <h4 class="fw-bold mb-3">Made with Love ❤️</h4>
                        <p class="text-muted">Every dish prepared with love and traditional recipes.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</section>

{popular_section}

<!-- Footer Section -->
<footer class="py-4 mt-5">
    <div class="container">
        <div class="text-center">
            <div class="glass-effect p-4 rounded">
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <h5 class="fw-bold text-gradient mb-2">Biryani Club</h5>
                        <p class="text-muted mb-0">Authentic flavors delivered fresh</p>
                    </div>
                    <div class="col-md-6">
                        <p class="text-muted mb-0">
                            <i class="fas fa-copyright me-1"></i>2024 Biryani Club. All rights reserved.
                        </p>
                        <small class="text-muted">Made with ❤️ for food lovers</small>
                    </div>
                </div>
            </div>
        </div>
    </div>
</footer>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Biryani Club - Delicious Food Delivered", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/menu')
def menu():
    user = User.query.get(session.get('user_id')) if 'user_id' in session else None

    if not store_status['open']:
        return render_template_string(BASE_TEMPLATE,
                                    title="Store Closed",
                                    content="""
                                    <div class="container text-center py-5">
                                        <h1 class="display-1 text-danger"><i class="fas fa-times-circle"></i></h1>
                                        <h2 class="fw-bold text-gradient mb-3">Store is Closed</h2>
                                        <p class="lead text-muted">We are sorry, but the store is currently closed. Please check back later or contact us for updates.</p>
                                        <a href="/" class="btn btn-primary mt-4"><i class="fas fa-home me-2"></i>Go to Home</a>
                                    </div>
                                    """,
                                    current_user=user)

    # Get menu items from database, fallback to static menu
    db_items = MenuItem.query.all()
    menu_dict = {}
    
    if db_items:
        for item in db_items:
            if item.category not in menu_dict:
                menu_dict[item.category] = []
            menu_dict[item.category].append({
                'name': item.name,
                'price': item.price,
                'description': item.description,
                'emoji': item.emoji,
                'in_stock': item.in_stock
            })
    else:
        # Use static menu if no items in database
        for category, items in MENU.items():
            menu_dict[category] = []
            for item in items:
                menu_dict[category].append({
                    'name': item['name'],
                    'price': item['price'],
                    'description': item['description'],
                    'emoji': item['emoji'],
                    'in_stock': True
                })

    content = """
<div class="container py-5">
    <div class="text-center mb-5">
        <h2 class="display-4 fw-bold text-gradient">Our Delicious Menu 🍽️</h2>
        <p class="lead text-muted">Authentic flavors that will make you crave for more</p>
    </div>

    """

    for category, items in menu_dict.items():
        content += f"""
    <div class="mb-5">
        <h3 class="fw-bold mb-4 text-center" style="color: var(--primary);">
            <i class="fas fa-utensils me-2"></i>{category}
        </h3>
        <div class="row g-4">
        """

        for item in items:
            stock_class = "" if item['in_stock'] else "opacity-50"
            stock_badge = "" if item['in_stock'] else '<span class="badge bg-danger mb-2">Out of Stock</span><br>'
            button_html = f"""
                <button class="btn btn-primary btn-sm" onclick="addToCart('{item['name']}', {item['price']}, '{item['emoji']}')">
                    <i class="fas fa-plus me-2"></i>Add
                </button>
            """ if item['in_stock'] else '<button class="btn btn-secondary btn-sm" disabled><i class="fas fa-times me-2"></i>Unavailable</button>'

            content += f"""
            <div class="col-lg-4 col-md-6">
                <div class="menu-item-card card {stock_class}">
                    <div class="card-body p-4">
                        <div class="text-center mb-3">
                            <span class="item-emoji">{item['emoji']}</span>
                        </div>
                        <div class="text-center mb-2">
                            {stock_badge}
                        </div>
                        <h5 class="fw-bold text-center mb-2">{item['name']}</h5>
                        <p class="text-muted text-center small mb-3">{item['description']}</p>

                        <div class="d-flex justify-content-between align-items-center">
                            <div class="price-tag">₹{item['price']}</div>
                            {button_html}
                        </div>
                    </div>
                </div>
            </div>
            """

        content += """
        </div>
    </div>
        """

    content += """
</div>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Menu - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

@app.route('/checkout')
def checkout():
    user = User.query.get(session.get('user_id')) if 'user_id' in session else None

    if not store_status['open']:
        return render_template_string(BASE_TEMPLATE,
                                    title="Store Closed",
                                    content="""
                                    <div class="container text-center py-5">
                                        <h1 class="display-1 text-danger"><i class="fas fa-times-circle"></i></h1>
                                        <h2 class="fw-bold text-gradient mb-3">Store is Closed</h2>
                                        <p class="lead text-muted">We are sorry, but the store is currently closed. Please check back later or contact us for updates.</p>
                                        <a href="/" class="btn btn-primary mt-4"><i class="fas fa-home me-2"></i>Go to Home</a>
                                    </div>
                                    """,
                                    current_user=user)

    # Get active promotions
    promotions = Promotion.query.filter_by(active=True).all()

    content = """
<div class="container py-5">
    <div class="row justify-content-center">
        <div class="col-lg-8">
            <div class="text-center mb-5">
                <h2 class="display-5 fw-bold text-gradient">Checkout 🛒</h2>
                <p class="lead text-muted">Complete your order in just a few steps</p>
            </div>

            <form id="checkout-form">
                <div class="card mb-4">
                    <div class="card-header text-white" style="background: var(--gradient-1);">
                        <h5 class="mb-0"><i class="fas fa-user me-2"></i>Customer Details</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label for="customer_name" class="form-label">Full Name *</label>
                                <input type="text" class="form-control form-control-lg" id="customer_name" required style="background: rgba(255,255,255,0.9); color: var(--dark);">
                            </div>
                            <div class="col-md-6 mb-3">
                                <label for="customer_phone" class="form-label">Phone Number *</label>
                                <input type="tel" class="form-control form-control-lg" id="customer_phone" required pattern="[0-9]{10,15}" style="background: rgba(255,255,255,0.9); color: var(--dark);">
                            </div>
                            <div class="col-12 mb-3">
                                <label for="customer_address" class="form-label">Delivery Address *</label>
                                <textarea class="form-control form-control-lg" id="customer_address" rows="3" required style="background: rgba(255,255,255,0.9); color: var(--dark);"></textarea>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header text-white" style="background: var(--gradient-2);">
                        <h5 class="mb-0"><i class="fas fa-credit-card me-2"></i>Payment Method</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="payment_method" id="payment_cash" value="cash" checked>
                                    <label class="form-check-label w-100" for="payment_cash">
                                        <div class="card text-center glass-effect">
                                            <div class="card-body py-3">
                                                <i class="fas fa-money-bill-wave fa-2x text-success mb-2"></i>
                                                <h6>Cash on Delivery</h6>
                                            </div>
                                        </div>
                                    </label>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="payment_method" id="payment_upi" value="upi">
                                    <label class="form-check-label w-100" for="payment_upi">
                                        <div class="card text-center glass-effect">
                                            <div class="card-body py-3">
                                                <i class="fab fa-google-pay fa-2x text-primary mb-2"></i>
                                                <h6>UPI Payment</h6>
                                            </div>
                                        </div>
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header text-white" style="background: var(--gradient-3);">
                        <h5 class="mb-0"><i class="fas fa-shopping-bag me-2"></i>Order Summary</h5>
                    </div>
                    <div class="card-body">
                        <div id="order-summary"></div>
                        <hr style="border-color: var(--glass-border);">
                        
                        <!-- Promotions Section -->
                        <div class="mb-3">
                            <h6 class="fw-bold text-primary mb-3">
                                <i class="fas fa-tags me-2"></i>Apply Promotion Code
                            </h6>
                            <div class="input-group">
                                <input type="text" class="form-control" id="promo-code" placeholder="Enter promo code">
                                <button class="btn btn-primary" type="button" onclick="applyPromo()">Apply</button>
                            </div>
                            <div id="promo-message" class="mt-2 small"></div>
                        </div>
                        
                        <!-- Loyalty Points Section -->
                        {% if session.user_id %}
                            {% set current_user = get_current_user() %}
                            {% if current_user and current_user.loyalty_points >= 2 %}
                                <div class="mb-3 p-3 rounded glass-effect">
                                    <h6 class="fw-bold text-success mb-2">
                                        <i class="fas fa-star me-2"></i>Loyalty Points Available: {{ current_user.loyalty_points }}
                                    </h6>
                                    <p class="small text-muted mb-2">2 points = ₹1 discount</p>
                                    <div class="d-flex align-items-center">
                                        <label for="loyalty-points" class="form-label me-2 mb-0">Use points:</label>
                                        <input type="number" id="loyalty-points" class="form-control form-control-sm me-2" 
                                               min="0" max="{{ current_user.loyalty_points }}" value="0" 
                                               style="width: 100px; background: rgba(255,255,255,0.9); color: var(--dark);"
                                               onchange="updateLoyaltyDiscount()">
                                        <button type="button" class="btn btn-success btn-sm" onclick="useMaxPoints()">
                                            <i class="fas fa-coins me-1"></i>Use Max
                                        </button>
                                    </div>
                                </div>
                            {% endif %}
                        {% endif %}
                        
                        <div class="d-flex justify-content-between mb-2">
                            <span>Subtotal:</span>
                            <span id="subtotal">₹0</span>
                        </div>
                        <div class="d-flex justify-content-between mb-2" id="promo-discount-row" style="display: none !important;">
                            <span class="text-success">Promotion Discount:</span>
                            <span class="text-success" id="promo-discount">-₹0</span>
                        </div>
                        <div class="d-flex justify-content-between mb-2" id="loyalty-discount-row" style="display: none !important;">
                            <span class="text-success">Loyalty Discount:</span>
                            <span class="text-success" id="loyalty-discount">-₹0</span>
                        </div>
                        <hr style="border-color: var(--glass-border);">
                        <div class="d-flex justify-content-between h5 text-primary">
                            <span>Total:</span>
                            <span id="final-total">₹0</span>
                        </div>
                    </div>
                </div>

                <div class="text-center">
                    <button type="submit" class="btn btn-primary btn-lg px-5 py-3">
                        <i class="fas fa-shopping-cart me-2"></i>Place Order
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
"""

    scripts = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    updateOrderSummary();

    document.getElementById('checkout-form').addEventListener('submit', function(e) {
        e.preventDefault();
        placeOrder();
    });
});

function updateOrderSummary() {
    const cart = JSON.parse(localStorage.getItem('cart') || '[]');
    const summaryDiv = document.getElementById('order-summary');
    const subtotalDiv = document.getElementById('subtotal');
    const totalDiv = document.getElementById('final-total');

    if (cart.length === 0) {
        summaryDiv.innerHTML = '<p class="text-muted">No items in cart</p>';
        if (subtotalDiv) subtotalDiv.textContent = '₹0';
        totalDiv.textContent = '₹0';
        return;
    }

    let html = '';
    let subtotal = 0;

    cart.forEach(item => {
        const itemTotal = item.price * item.quantity;
        subtotal += itemTotal;
        html += `
            <div class="d-flex justify-content-between mb-2">
                <span>${item.emoji} ${item.name} x ${item.quantity}</span>
                <span>₹${itemTotal}</span>
            </div>
        `;
    });

    summaryDiv.innerHTML = html;
    if (subtotalDiv) subtotalDiv.textContent = '₹' + subtotal;
    
    // Calculate final total with discounts
    updateDiscounts();
}

function updateDiscounts() {
    updateLoyaltyDiscount();
    updatePromoDiscount();
}

function updateLoyaltyDiscount() {
    const cart = JSON.parse(localStorage.getItem('cart') || '[]');
    let subtotal = 0;
    cart.forEach(item => {
        subtotal += item.price * item.quantity;
    });

    const loyaltyPointsInput = document.getElementById('loyalty-points');
    const loyaltyDiscountRow = document.getElementById('loyalty-discount-row');
    const loyaltyDiscountSpan = document.getElementById('loyalty-discount');
    const finalTotalSpan = document.getElementById('final-total');
    
    let loyaltyDiscount = 0;
    if (loyaltyPointsInput) {
        const pointsUsed = parseInt(loyaltyPointsInput.value) || 0;
        loyaltyDiscount = Math.floor(pointsUsed / 2); // 2 points = ₹1
        
        if (loyaltyDiscount > 0) {
            loyaltyDiscountRow.style.display = 'flex';
            loyaltyDiscountSpan.textContent = '-₹' + loyaltyDiscount;
        } else {
            loyaltyDiscountRow.style.display = 'none';
        }
    }
    
    // Apply promo discount if any
    const promoDiscount = parseFloat(document.getElementById('promo-discount').textContent.replace('-₹', '')) || 0;
    
    const finalTotal = Math.max(0, subtotal - loyaltyDiscount - promoDiscount);
    finalTotalSpan.textContent = '₹' + finalTotal;
}

function updatePromoDiscount() {
    // This would be updated after applying a promo
    // Currently handled in applyPromo()
}

function applyPromo() {
    const promoCode = document.getElementById('promo-code').value;
    if (!promoCode) {
        document.getElementById('promo-message').innerHTML = '<span class="text-danger">Please enter a promo code</span>';
        return;
    }
    
    fetch('/api/apply-promo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            promo_code: promoCode
        })
    })
    .then(response => response.json())
    .then(data => {
        const promoMessage = document.getElementById('promo-message');
        const promoDiscountRow = document.getElementById('promo-discount-row');
        const promoDiscountSpan = document.getElementById('promo-discount');
        
        if (data.success) {
            promoMessage.innerHTML = `<span class="text-success">${data.message}</span>`;
            promoDiscountRow.style.display = 'flex';
            promoDiscountSpan.textContent = '-₹' + data.discount;
            updateDiscounts();
        } else {
            promoMessage.innerHTML = `<span class="text-danger">${data.error}</span>`;
            promoDiscountRow.style.display = 'none';
            updateDiscounts();
        }
    });
}

function useMaxPoints() {
    const cart = JSON.parse(localStorage.getItem('cart') || '[]');
    let subtotal = 0;
    cart.forEach(item => {
        subtotal += item.price * item.quantity;
    });

    const loyaltyPointsInput = document.getElementById('loyalty-points');
    if (loyaltyPointsInput) {
        const maxPoints = parseInt(loyaltyPointsInput.getAttribute('max'));
        const maxUsablePoints = Math.min(maxPoints, subtotal * 2); // Can't use more points than order value
        loyaltyPointsInput.value = maxUsablePoints;
        updateDiscounts();
    }
}

function placeOrder() {
    const cart = JSON.parse(localStorage.getItem('cart') || '[]');

    if (cart.length === 0) {
        alert('Your cart is empty!');
        return;
    }

    const loyaltyPointsInput = document.getElementById('loyalty-points');
    const loyaltyPointsUsed = loyaltyPointsInput ? parseInt(loyaltyPointsInput.value) || 0 : 0;
    const promoCode = document.getElementById('promo-code').value || '';

    const formData = {
        customer_name: document.getElementById('customer_name').value,
        customer_phone: document.getElementById('customer_phone').value,
        customer_address: document.getElementById('customer_address').value,
        payment_method: document.querySelector('input[name="payment_method"]:checked').value,
        items: cart,
        loyalty_points_used: loyaltyPointsUsed,
        promo_code: promoCode
    };

    fetch('/place_order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            localStorage.removeItem('cart');
            window.location.href = '/order_confirmation/' + data.order_id;
        } else {
            alert('Error placing order: ' + data.error);
        }
    })
    .catch(error => {
        alert('Error: ' + error.message);
    });
}
</script>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Checkout - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts=scripts)

@app.route('/api/apply-promo', methods=['POST'])
def apply_promo():
    try:
        data = request.json
        promo = Promotion.query.filter_by(code=data['promo_code'], active=True).first()
        
        if not promo:
            return jsonify({'success': False, 'error': 'Invalid promo code'})
            
        # Check validity dates
        now = datetime.utcnow()
        if promo.valid_from and promo.valid_from > now:
            return jsonify({'success': False, 'error': 'Promo not yet valid'})
        if promo.valid_to and promo.valid_to < now:
            return jsonify({'success': False, 'error': 'Promo expired'})
            
        # Check max usage
        if promo.max_usage and promo.usage_count >= promo.max_usage:
            return jsonify({'success': False, 'error': 'Promo limit reached'})
            
        return jsonify({
            'success': True,
            'discount': promo.discount_value,
            'message': f'Promo applied: {promo.description}'
        })
    except:
        return jsonify({'success': False, 'error': 'Error applying promo'})

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        data = request.json

        # Generate order ID
        order_id = 'ORD' + str(int(datetime.now().timestamp()))[-8:]

        # Calculate totals
        cart = data['items']
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        
        # Apply promo discount
        promo_discount = 0
        promo = Promotion.query.filter_by(code=data.get('promo_code', '')).first()
        if promo:
            if promo.discount_type == 'percent':
                promo_discount = subtotal * (promo.discount_value / 100)
            else:
                promo_discount = promo.discount_value
            promo_discount = min(promo_discount, subtotal)
            
            # Update promo usage
            promo.usage_count += 1
            if promo.max_usage and promo.usage_count >= promo.max_usage:
                promo.active = False
        
        # Handle loyalty points redemption
        loyalty_points_used = data.get('loyalty_points_used', 0)
        loyalty_discount = 0
        
        if loyalty_points_used > 0 and 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user and user.loyalty_points >= loyalty_points_used:
                loyalty_discount = loyalty_points_used // 2  # 2 points = ₹1
                # Ensure discount doesn't exceed order value
                loyalty_discount = min(loyalty_discount, subtotal - promo_discount)
        
        total = subtotal - promo_discount - loyalty_discount

        # Create order
        order = Order(
            order_id=order_id,
            customer_name=data['customer_name'],
            customer_phone=data['customer_phone'],
            customer_address=data['customer_address'],
            items_json=json.dumps(cart),
            subtotal=subtotal,
            discount=promo_discount + loyalty_discount,
            total=total,
            payment_method=data['payment_method'],
            coupon_code=data.get('promo_code', ''),
            user_id=session.get('user_id')  # Associate order with logged-in user
        )

        db.session.add(order)

        # Update user's loyalty points
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user:
                # Deduct used points
                user.loyalty_points -= loyalty_points_used
                # Add new points based on final amount (1 point per ₹10)
                user.loyalty_points += int(total / 10)
                
                # Update loyalty tier
                if user.loyalty_points < 100:
                    user.loyalty_tier = 'bronze'
                elif user.loyalty_points < 500:
                    user.loyalty_tier = 'silver'
                else:
                    user.loyalty_tier = 'gold'

        db.session.commit()

        return jsonify({'success': True, 'order_id': order_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/order_confirmation/<order_id>')
def order_confirmation(order_id):
    user = User.query.get(session.get('user_id')) if 'user_id' in session else None
    order = Order.query.filter_by(order_id=order_id).first()

    if not order:
        return "Order not found", 404

    content = f"""
<div class="container py-5">
    <div class="row justify-content-center">
        <div class="col-lg-8">
            <div class="text-center mb-5">
                <div style="width: 100px; height: 100px; border-radius: 50%; background: var(--gradient-2); display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; animation: scaleIn 0.5s ease;">
                    <i class="fas fa-check fa-3x text-white"></i>
                </div>
                <h1 class="display-4 fw-bold text-success mb-3">Order Confirmed! 🎉</h1>
                <p class="lead text-muted">Thank you for choosing Biryani Club. Your delicious meal is being prepared!</p>
            </div>

            <div class="card mb-4">
                <div class="card-header text-center py-4 text-white" style="background: var(--gradient-1);">
                    <h3 class="mb-0"><i class="fas fa-receipt me-2"></i>Order #{order.order_id}</h3>
                    <p class="mb-0 opacity-75">{order.created_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>

                <div class="card-body p-4">
                    <div class="row mb-4">
                        <div class="col-md-6">
                            <h6 class="fw-bold text-primary mb-3"><i class="fas fa-user me-2"></i>Customer Details</h6>
                            <p class="mb-1"><strong>Name:</strong> {order.customer_name}</p>
                            <p class="mb-1"><strong>Phone:</strong> {order.customer_phone}</p>
                            <p class="mb-0"><strong>Payment:</strong> 
                                <span class="badge" style="background: var(--gradient-2);">{order.payment_method.upper()}</span>
                            </p>
                        </div>
                        <div class="col-md-6">
                            <h6 class="fw-bold text-primary mb-3"><i class="fas fa-map-marker-alt me-2"></i>Delivery Address</h6>
                            <p class="mb-0">{order.customer_address}</p>
                        </div>
                    </div>

                    <h6 class="fw-bold text-primary mb-3"><i class="fas fa-shopping-bag me-2"></i>Your Order</h6>
    """

    for item in order.get_items():
        content += f"""
                    <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
                        <div>
                            <h6 class="mb-1">{item['emoji']} {item['name']}</h6>
                            <small class="text-muted">Quantity: {item['quantity']}</small>
                        </div>
                        <div class="text-end">
                            <strong>₹{item['price'] * item['quantity']}</strong>
                        </div>
                    </div>
        """

    content += f"""
                    <div class="mt-4 p-3 rounded glass-effect">
                        <div class="d-flex justify-content-between mb-2"><span>Subtotal:</span><span>₹{order.subtotal}</span></div>
                        {"<div class='d-flex justify-content-between mb-2 text-success'><span>Discount:</span><span>-₹" + str(order.discount) + "</span></div>" if order.discount > 0 else ""}
                        <hr style='border-color: var(--glass-border);'>
                        <div class="d-flex justify-content-between h5 text-primary mb-0">
                            <span>Total:</span>
                            <span>₹{order.total}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card mb-4">
                <div class="card-body text-center py-4">
                    <h5 class="fw-bold text-primary mb-3"><i class="fas fa-clock me-2"></i>Estimated Delivery Time</h5>
                    <div style="font-size: 2rem; font-weight: bold; background: var(--gradient-1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px;">30-45 Minutes</div>
                    <p class="text-muted mb-0">Our chef is already working on your order!</p>
                </div>
            </div>

            <div class="text-center">
                <h4 class="fw-bold text-gradient mb-3">Thank You for Choosing Biryani Club! 🙏</h4>
                <p class="text-muted mb-4">We're preparing your order with love and care.</p>
                <div class="d-flex justify-content-center gap-3">
                    <a href="/menu" class="btn btn-primary"><i class="fas fa-utensils me-2"></i>Order More</a>
                    <a href="/" class="btn btn-outline-primary"><i class="fas fa-home me-2"></i>Home</a>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
@keyframes scaleIn {{
    0% {{ transform: scale(0); }}
    100% {{ transform: scale(1); }}
}}
</style>
"""

    return render_template_string(BASE_TEMPLATE, 
                                title="Order Confirmation - Biryani Club", 
                                content=content, 
                                current_user=user,
                                extra_scripts="")

# Create admin user on startup
def create_admin_user():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@biryaniclub.com',
            password_hash=generate_password_hash('cupadmin'),
            full_name='Admin User',
            phone='1234567890',
            is_admin=True
        )
        db.session.add(admin)

    # Create delivery user
    delivery = User.query.filter_by(username='delivery').first()
    if not delivery:
        delivery = User(
            username='delivery',
            email='delivery@biryaniclub.com',
            password_hash=generate_password_hash('delivery123'),
            full_name='Delivery Person',
            phone='9876543210',
            is_delivery=True
        )
        db.session.add(delivery)

    # Initialize menu items in database
    if MenuItem.query.count() == 0:
        for category, items in MENU.items():
            for item in items:
                menu_item = MenuItem(
                    name=item['name'],
                    category=category,
                    price=item['price'],
                    description=item['description'],
                    emoji=item['emoji'],
                    in_stock=True
                )
                db.session.add(menu_item)

    # Create sample promotion
    if Promotion.query.count() == 0:
        promo = Promotion(
            code='WELCOME20',
            description='20% off on first order',
            discount_type='percent',
            discount_value=20,
            min_order=500,
            max_usage=100,
            valid_to=datetime.utcnow() + timedelta(days=30)
        db.session.add(promo)

    db.session.commit()

# Initialize database and create tables
with app.app_context():
    db.create_all()
    create_admin_user()

if __name__ == '__main__':
    print("🍛 Biryani Club Professional App is starting...")
    print("📱 Features: User Auth, Admin Panel, Delivery Management")
    print("🎨 Professional UI with Glass Effects and Animations")
    print("🔒 Enhanced Security with Input Validation")
    print("📊 Analytics Dashboard and Loyalty Program")
    print("👨‍💼 Admin: username='admin', password='cupadmin'")
    print("🚚 Delivery: username='delivery', password='delivery123'")

    app.run(debug=True, host='0.0.0.0', port=5000)