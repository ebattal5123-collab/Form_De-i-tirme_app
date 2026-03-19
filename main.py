import os
import sqlite3
import tempfile
import hashlib
import secrets
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, render_template_string, send_file, flash
from functools import wraps
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ========== VERİTABANI (SQLite) ==========
# Render'da kalıcı depolama için /tmp klasörünü kullan
DB_PATH = '/tmp/users.db' if os.path.exists('/tmp') else 'users.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            conversion_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Veritabanı tabloları hazır.")

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, email, password):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, hash_password(password))
        )
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        return None

def login_user(username, password):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, email FROM users WHERE (username = ? OR email = ?) AND password = ?",
        (username, username, hash_password(password))
    )
    user = c.fetchone()
    conn.close()
    return user

def save_conversion(user_id, filename, conversion_type):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversions (user_id, filename, conversion_type) VALUES (?, ?, ?)",
        (user_id, filename, conversion_type)
    )
    conn.commit()
    conn.close()

def get_user_conversions(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT filename, conversion_type, created_at FROM conversions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    conversions = c.fetchall()
    conn.close()
    return [(row[0], row[1], row[2]) for row in conversions]

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash("Lütfen önce giriş yapın.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ========== CSS STYLES ==========
STYLES = '''
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #0a0f1e 0%, #0b1a2a 100%);
        min-height: 100vh;
        color: #e0e0e0;
    }
    .navbar {
        background: rgba(10, 20, 30, 0.8);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid #1e3a5f;
        padding: 1rem 0;
        position: fixed;
        width: 100%;
        top: 0;
        z-index: 1000;
    }
    .navbar-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 0 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .navbar-brand {
        font-size: 1.5rem;
        font-weight: bold;
        background: linear-gradient(45deg, #4a9eff, #7ac7ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-decoration: none;
    }
    .navbar-menu {
        display: flex;
        gap: 2rem;
        align-items: center;
    }
    .navbar-link {
        color: #e0e0e0;
        text-decoration: none;
        transition: color 0.3s;
        font-weight: 500;
    }
    .navbar-link:hover { color: #4a9eff; }
    .navbar-user {
        color: #4a9eff;
        font-weight: 500;
        padding: 0.5rem 1rem;
        background: rgba(74, 158, 255, 0.1);
        border-radius: 8px;
    }
    .logout-btn {
        background: transparent;
        border: 1px solid #dc3545;
        color: #dc3545;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        text-decoration: none;
        transition: all 0.3s;
    }
    .logout-btn:hover { background: #dc3545; color: white; }
    .container {
        max-width: 1200px;
        margin: 100px auto 50px;
        padding: 0 2rem;
    }
    .hero {
        text-align: center;
        margin-bottom: 3rem;
        animation: fadeIn 1s ease;
    }
    .hero h1 {
        font-size: 3rem;
        background: linear-gradient(45deg, #4a9eff, #7ac7ff, #4a9eff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .hero p {
        font-size: 1.2rem;
        color: #a0b0c0;
    }
    .card {
        background: rgba(20, 30, 45, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid #1e3a5f;
        border-radius: 20px;
        padding: 2.5rem;
        box-shadow: 0 20px 40px rgba(0, 20, 40, 0.4);
        animation: slideUp 0.5s ease;
        max-width: 600px;
        margin: 0 auto;
    }
    .card h2 {
        color: #4a9eff;
        margin-bottom: 1.5rem;
        font-size: 1.8rem;
        text-align: center;
    }
    .form-group {
        margin-bottom: 1.5rem;
    }
    .form-group label {
        display: block;
        margin-bottom: 0.5rem;
        color: #a0b0c0;
    }
    .form-control {
        width: 100%;
        padding: 0.8rem;
        background: rgba(10, 20, 30, 0.8);
        border: 1px solid #1e3a5f;
        border-radius: 8px;
        color: #e0e0e0;
        font-size: 1rem;
    }
    .form-control:focus {
        outline: none;
        border-color: #4a9eff;
    }
    .btn-primary {
        background: linear-gradient(45deg, #4a9eff, #2a7aff);
        color: white;
        border: none;
        padding: 1rem 2rem;
        border-radius: 12px;
        font-size: 1.1rem;
        font-weight: 600;
        cursor: pointer;
        width: 100%;
        transition: all 0.3s;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .btn-primary:hover {
        background: linear-gradient(45deg, #2a7aff, #4a9eff);
        transform: translateY(-2px);
        box-shadow: 0 10px 20px rgba(74, 158, 255, 0.3);
    }
    .btn-secondary {
        background: transparent;
        border: 2px solid #4a9eff;
        color: #4a9eff;
        padding: 1rem 2rem;
        border-radius: 12px;
        font-size: 1.1rem;
        font-weight: 600;
        cursor: pointer;
        width: 100%;
        transition: all 0.3s;
        text-decoration: none;
        display: inline-block;
        text-align: center;
        margin-top: 1rem;
    }
    .btn-secondary:hover {
        background: rgba(74, 158, 255, 0.1);
        transform: translateY(-2px);
    }
    .flash-message {
        background: rgba(220, 53, 69, 0.2);
        border: 1px solid #dc3545;
        color: #ff8b8b;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .text-center {
        text-align: center;
    }
    .mt-3 {
        margin-top: 1rem;
    }
    .auth-link {
        color: #4a9eff;
        text-decoration: none;
        font-weight: 500;
    }
    .auth-link:hover {
        text-decoration: underline;
    }
    .file-input {
        width: 100%;
        padding: 1rem;
        background: rgba(10, 20, 30, 0.8);
        border: 2px dashed #1e3a5f;
        border-radius: 12px;
        color: #e0e0e0;
        margin: 1rem 0;
        cursor: pointer;
        transition: all 0.3s;
    }
    .file-input:hover {
        border-color: #4a9eff;
        background: rgba(74, 158, 255, 0.05);
    }
    .conversion-type {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
        justify-content: center;
        flex-wrap: wrap;
    }
    .conversion-type button {
        background: transparent;
        border: 1px solid #1e3a5f;
        color: #a0b0c0;
        padding: 0.8rem 1.5rem;
        border-radius: 30px;
        cursor: pointer;
        font-weight: 500;
        transition: all 0.3s;
    }
    .conversion-type button.active {
        background: #4a9eff;
        color: white;
        border-color: #4a9eff;
    }
    .conversion-type button:hover {
        border-color: #4a9eff;
        color: #4a9eff;
    }
    .hidden-form { display: none; }
    .active-form { display: block; }
    .features {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 2rem;
        margin-top: 3rem;
    }
    .feature-card {
        background: rgba(20, 30, 45, 0.4);
        border: 1px solid #1e3a5f;
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        transition: all 0.3s;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        border-color: #4a9eff;
        box-shadow: 0 10px 30px rgba(74, 158, 255, 0.2);
    }
    .feature-icon { font-size: 2.5rem; margin-bottom: 1rem; }
    .feature-title { color: #4a9eff; font-size: 1.2rem; margin-bottom: 0.5rem; }
    .feature-text { color: #a0b0c0; font-size: 0.9rem; }
    .history-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1.5rem;
    }
    .history-table th {
        text-align: left;
        padding: 0.8rem;
        background: rgba(74, 158, 255, 0.1);
        color: #4a9eff;
        font-weight: 600;
    }
    .history-table td {
        padding: 0.8rem;
        border-bottom: 1px solid #1e3a5f;
    }
    .history-table tr:hover {
        background: rgba(74, 158, 255, 0.05);
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .loading {
        display: none;
        text-align: center;
        padding: 2rem;
    }
    .loading.active {
        display: block;
    }
    .loading .spinner {
        width: 50px;
        height: 50px;
        border: 5px solid rgba(74, 158, 255, 0.2);
        border-top-color: #4a9eff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 1rem;
    }
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
</style>
'''

NAVBAR = '''
<nav class="navbar">
    <div class="navbar-container">
        <a href="/" class="navbar-brand">📄 Doc2PDF</a>
        <div class="navbar-menu">
            <a href="/" class="navbar-link">Ana Sayfa</a>
            <a href="/#features" class="navbar-link">Özellikler</a>
            {% if session.user_id %}
                <a href="/profile" class="navbar-link">Profilim</a>
                <span class="navbar-user">👤 {{ session.username }}</span>
                <a href="/logout" class="logout-btn">Çıkış</a>
            {% else %}
                <a href="/login" class="navbar-link">Giriş</a>
                <a href="/register" class="navbar-link">Kayıt</a>
            {% endif %}
        </div>
    </div>
</nav>
'''

# ========== ANA SAYFA ==========
INDEX_HTML = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Belge Dönüştürücü - Ana Sayfa</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {STYLES}
</head>
<body>
    {NAVBAR}
    
    <div class="container">
        {{% with messages = get_flashed_messages() %}}
            {{% if messages %}}
                {{% for message in messages %}}
                    <div class="flash-message">{{{{ message }}}}</div>
                {{% endfor %}}
            {{% endif %}}
        {{% endwith %}}
        
        <div class="hero">
            <h1>📄 Belge ve Görsel Dönüştürücü</h1>
            <p>DOCX, JPEG, PNG dosyalarınızı tek tıkla dönüştürün. Ücretsiz, hızlı ve güvenli.</p>
        </div>
        
        {{% if session.user_id %}}
        <div class="card">
            <h2>🚀 Dönüştürme Türünü Seç</h2>
            
            <div class="conversion-type">
                <button type="button" id="btn-docx" class="active" onclick="showForm('docx')">📄 DOCX → PDF</button>
                <button type="button" id="btn-jpeg" onclick="showForm('jpeg')">🖼️ JPEG → PNG</button>
                <button type="button" id="btn-png" onclick="showForm('png')">🖼️ PNG → JPEG</button>
            </div>
            
            <div id="form-docx" class="active-form">
                <form method="post" action="/convert/docx-to-pdf" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".docx" class="file-input" required>
                    <button type="submit" class="btn-primary">PDF'e Çevir</button>
                </form>
            </div>
            
            <div id="form-jpeg" class="hidden-form">
                <form method="post" action="/convert/jpeg-to-png" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".jpg,.jpeg" class="file-input" required>
                    <button type="submit" class="btn-primary">PNG'e Çevir</button>
                </form>
            </div>
            
            <div id="form-png" class="hidden-form">
                <form method="post" action="/convert/png-to-jpeg" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".png" class="file-input" required>
                    <button type="submit" class="btn-primary">JPEG'e Çevir</button>
                </form>
            </div>
        </div>
        {{% else %}}
        <div class="card">
            <h2>🔐 Devam Etmek İçin Giriş Yap</h2>
            <p style="color: #a0b0c0; margin-bottom: 2rem; text-align: center;">Dönüştürme yapabilmek için önce hesabınıza giriş yapmalısınız.</p>
            <a href="/login" class="btn-secondary">Giriş Yap</a>
            <a href="/register" class="btn-primary" style="margin-top: 1rem;">Kayıt Ol</a>
        </div>
        {{% endif %}}
        
        <div id="features" class="features">
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <div class="feature-title">Hızlı Dönüşüm</div>
                <div class="feature-text">Saniyeler içinde PDF veya PNG/JPEG elde edin</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🔒</div>
                <div class="feature-title">Güvenli</div>
                <div class="feature-text">Dosyalarınız dönüştürüldükten hemen sonra silinir</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📱</div>
                <div class="feature-title">Mobil Uyumlu</div>
                <div class="feature-text">Her cihazda rahatça kullanın</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🎨</div>
                <div class="feature-title">Çoklu Format</div>
                <div class="feature-text">DOCX, JPEG, PNG dönüşümleri</div>
            </div>
        </div>
    </div>
    
    <script>
        function showForm(type) {{
            document.getElementById('btn-docx').classList.remove('active');
            document.getElementById('btn-jpeg').classList.remove('active');
            document.getElementById('btn-png').classList.remove('active');
            document.getElementById('btn-' + type).classList.add('active');
            
            document.getElementById('form-docx').classList.remove('active-form');
            document.getElementById('form-docx').classList.add('hidden-form');
            document.getElementById('form-jpeg').classList.remove('active-form');
            document.getElementById('form-jpeg').classList.add('hidden-form');
            document.getElementById('form-png').classList.remove('active-form');
            document.getElementById('form-png').classList.add('hidden-form');
            
            document.getElementById('form-' + type).classList.remove('hidden-form');
            document.getElementById('form-' + type).classList.add('active-form');
        }}
    </script>
</body>
</html>
'''

# ========== GİRİŞ SAYFASI ==========
LOGIN_HTML = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Belge Dönüştürücü - Giriş Yap</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {STYLES}
</head>
<body>
    {NAVBAR}
    
    <div class="container">
        {{% with messages = get_flashed_messages() %}}
            {{% if messages %}}
                {{% for message in messages %}}
                    <div class="flash-message">{{{{ message }}}}</div>
                {{% endfor %}}
            {{% endif %}}
        {{% endwith %}}
        
        <div class="hero">
            <h1>🔐 Giriş Yap</h1>
            <p>Hesabınıza giriş yaparak dönüştürme işlemlerine başlayın.</p>
        </div>
        
        <div class="card" style="max-width: 400px;">
            <form method="post" action="/login" onsubmit="showLoading()">
                <div class="form-group">
                    <label>Kullanıcı Adı / E-posta</label>
                    <input type="text" name="username" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label>Şifre</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                
                <button type="submit" class="btn-primary">Giriş Yap</button>
            </form>
            
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <p>Giriş yapılıyor, lütfen bekleyin...</p>
            </div>
            
            <p class="text-center mt-3">
                Hesabınız yok mu? <a href="/register" class="auth-link">Kayıt Ol</a>
            </p>
        </div>
    </div>
    
    <script>
        function showLoading() {{
            document.querySelector('form').style.display = 'none';
            document.getElementById('loading').classList.add('active');
        }}
    </script>
</body>
</html>
'''

# ========== KAYIT SAYFASI ==========
REGISTER_HTML = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Belge Dönüştürücü - Kayıt Ol</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {STYLES}
</head>
<body>
    {NAVBAR}
    
    <div class="container">
        {{% with messages = get_flashed_messages() %}}
            {{% if messages %}}
                {{% for message in messages %}}
                    <div class="flash-message">{{{{ message }}}}</div>
                {{% endfor %}}
            {{% endif %}}
        {{% endwith %}}
        
        <div class="hero">
            <h1>📝 Kayıt Ol</h1>
            <p>Yeni bir hesap oluşturarak dönüştürme işlemlerine başlayın.</p>
        </div>
        
        <div class="card" style="max-width: 400px;">
            <form method="post" action="/register" onsubmit="showLoading()">
                <div class="form-group">
                    <label>Kullanıcı Adı</label>
                    <input type="text" name="username" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label>E-posta</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label>Şifre</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label>Şifre Tekrar</label>
                    <input type="password" name="confirm_password" class="form-control" required>
                </div>
                
                <button type="submit" class="btn-primary">Kayıt Ol</button>
            </form>
            
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <p>Kayıt yapılıyor, lütfen bekleyin...</p>
            </div>
            
            <p class="text-center mt-3">
                Zaten hesabınız var mı? <a href="/login" class="auth-link">Giriş Yap</a>
            </p>
        </div>
    </div>
    
    <script>
        function showLoading() {{
            document.querySelector('form').style.display = 'none';
            document.getElementById('loading').classList.add('active');
        }}
    </script>
</body>
</html>
'''

# ========== PROFİL SAYFASI ==========
def get_profile_html(conversions):
    if conversions:
        rows = ''
        for filename, conv_type, created_at in conversions:
            rows += f'''
            <tr>
                <td>{filename}</td>
                <td>{conv_type}</td>
                <td>{created_at}</td>
            </tr>
            '''
        table = f'''
        <table class="history-table">
            <thead>
                <tr>
                    <th>Dosya</th>
                    <th>Dönüşüm Tipi</th>
                    <th>Tarih</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        '''
    else:
        table = '<p style="color: #a0b0c0; text-align: center;">Henüz hiç dönüşüm yapmamışsınız.</p>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Belge Dönüştürücü - Profilim</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        {STYLES}
    </head>
    <body>
        {NAVBAR}
        
        <div class="container">
            <div class="hero">
                <h1>👤 Profilim</h1>
                <p>Hoş geldin, {session["username"]}!</p>
            </div>
            
            <div class="card">
                <h2>📊 Dönüşüm Geçmişim</h2>
                {table}
            </div>
        </div>
    </body>
    </html>
    '''

# ========== ROUTES ==========
@app.route('/')
def index():
    return render_template_string(INDEX_HTML, session=session)

@app.route('/register')
def register():
    return render_template_string(REGISTER_HTML, session=session)

@app.route('/login')
def login():
    return render_template_string(LOGIN_HTML, session=session)

@app.route('/register', methods=['POST'])
def register_post():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    
    if not username or not email or not password:
        flash("Tüm alanları doldurun.")
        return redirect(url_for('register'))
    
    if password != confirm_password:
        flash("Şifreler eşleşmiyor.")
        return redirect(url_for('register'))
    
    if len(password) < 6:
        flash("Şifre en az 6 karakter olmalı.")
        return redirect(url_for('register'))
    
    user_id = register_user(username, email, password)
    if user_id:
        flash("Kayıt başarılı! Şimdi giriş yapabilirsiniz.")
        return redirect(url_for('login'))
    else:
        flash("Bu kullanıcı adı veya e-posta zaten kullanılıyor.")
        return redirect(url_for('register'))

@app.route('/login', methods=['POST'])
def login_post():
    username = request.form['username']
    password = request.form['password']
    
    user = login_user(username, password)
    if user:
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['email'] = user[2]
        flash("Giriş başarılı!")
        return redirect(url_for('index'))
    else:
        flash("Kullanıcı adı/E-posta veya şifre hatalı.")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Çıkış yapıldı.")
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    conversions = get_user_conversions(session['user_id'])
    return get_profile_html(conversions)

# ---------- DÖNÜŞTÜRME ROUTELARI ----------
@app.route('/convert/docx-to-pdf', methods=['POST'])
@login_required
def convert_docx_to_pdf():
    if 'file' not in request.files:
        flash("Dosya seçilmedi")
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash("Dosya adı boş")
        return redirect(url_for('index'))
    
    if not file.filename.lower().endswith('.docx'):
        flash("Lütfen geçerli bir .docx dosyası seçin.")
        return redirect(url_for('index'))

    filename = file.filename
    save_conversion(session['user_id'], filename, 'DOCX→PDF')

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_docx:
            file.save(tmp_docx.name)
            docx_path = tmp_docx.name

        pdf_path = docx_path.replace('.docx', '.pdf')
        
        doc = Document(docx_path)
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        y = height - 50
        margin = 50
        line_height = 14
        
        c.setFont("Helvetica", 11)
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                words = text.split()
                line = ""
                for word in words:
                    test_line = line + " " + word if line else word
                    if c.stringWidth(test_line, "Helvetica", 11) < (width - 2 * margin):
                        line = test_line
                    else:
                        if y < margin + line_height:
                            c.showPage()
                            c.setFont("Helvetica", 11)
                            y = height - margin
                        c.drawString(margin, y, line)
                        y -= line_height
                        line = word
                if line:
                    if y < margin + line_height:
                        c.showPage()
                        c.setFont("Helvetica", 11)
                        y = height - margin
                    c.drawString(margin, y, line)
                    y -= line_height
            y -= 5
        
        c.save()
        
        response = send_file(
            pdf_path,
            as_attachment=True,
            download_name=filename.replace('.docx', '.pdf'),
            mimetype='application/pdf'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(docx_path)
            except:
                pass
            try:
                os.unlink(pdf_path)
            except:
                pass
        
        return response
        
    except Exception as e:
        flash(f"Dönüştürme hatası: {str(e)}")
        return redirect(url_for('index'))

@app.route('/convert/jpeg-to-png', methods=['POST'])
@login_required
def convert_jpeg_to_png():
    if 'file' not in request.files:
        flash("Dosya seçilmedi")
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash("Dosya adı boş")
        return redirect(url_for('index'))
    
    if not (file.filename.lower().endswith('.jpg') or file.filename.lower().endswith('.jpeg')):
        flash("Lütfen geçerli bir .jpg veya .jpeg dosyası seçin.")
        return redirect(url_for('index'))

    filename = file.filename
    save_conversion(session['user_id'], filename, 'JPEG→PNG')

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_jpg:
            file.save(tmp_jpg.name)
            jpg_path = tmp_jpg.name

        png_path = jpg_path.replace('.jpg', '.png')
        if not png_path.endswith('.png'):
            png_path = jpg_path + '.png'
        
        img = Image.open(jpg_path)
        img.save(png_path, 'PNG')

        response = send_file(
            png_path,
            as_attachment=True,
            download_name=filename.rsplit('.', 1)[0] + '.png',
            mimetype='image/png'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(jpg_path)
            except:
                pass
            try:
                os.unlink(png_path)
            except:
                pass
        
        return response
        
    except Exception as e:
        flash(f"Dönüştürme hatası: {str(e)}")
        return redirect(url_for('index'))

@app.route('/convert/png-to-jpeg', methods=['POST'])
@login_required
def convert_png_to_jpeg():
    if 'file' not in request.files:
        flash("Dosya seçilmedi")
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash("Dosya adı boş")
        return redirect(url_for('index'))
    
    if not file.filename.lower().endswith('.png'):
        flash("Lütfen geçerli bir .png dosyası seçin.")
        return redirect(url_for('index'))

    filename = file.filename
    save_conversion(session['user_id'], filename, 'PNG→JPEG')

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_png:
            file.save(tmp_png.name)
            png_path = tmp_png.name

        jpeg_path = png_path.replace('.png', '.jpg')
        
        img = Image.open(png_path)
        rgb_img = img.convert('RGB')
        rgb_img.save(jpeg_path, 'JPEG')

        response = send_file(
            jpeg_path,
            as_attachment=True,
            download_name=filename.rsplit('.', 1)[0] + '.jpg',
            mimetype='image/jpeg'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(png_path)
            except:
                pass
            try:
                os.unlink(jpeg_path)
            except:
                pass
        
        return response
        
    except Exception as e:
        flash(f"Dönüştürme hatası: {str(e)}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🚀 BELGE DÖNÜŞTÜRÜCÜ BAŞLATILDI                         ║
    ║                                                           ║
    ║   📱 Ana Sayfa: http://localhost:{port}                    ║
    ║   🔐 Giriş Sayfası: http://localhost:{port}/login          ║
    ║   📝 Kayıt Sayfası: http://localhost:{port}/register       ║
    ║   👤 Profil Sayfası: http://localhost:{port}/profile       ║
    ║                                                           ║
    ║   🎨 Modern mavi-siyah tema                               ║
    ║   ⏳ Loading ekranı aktif                                 ║
    ║   🖼️ 3 dönüşüm tipi destekleniyor                        ║
    ║   🗄️  SQLite veritabanı (/tmp/users.db)                  ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port)
