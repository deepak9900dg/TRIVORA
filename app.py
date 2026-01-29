from flask import Flask, render_template, request, redirect, session, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import cloudinary
import cloudinary.uploader
import requests

def send_to_indexnow(new_post_url):
    url = "https://www.bing.com/indexnow"
    params = {
        "url": new_post_url,
        "key": "e35d5ba6bea14a9581ce9e6f6b6c5c87" # Aapki download ki hui key
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            print(f"Success: {new_post_url} indexing request sent!")
    except Exception as e:
        print(f"Error sending to IndexNow: {e}")

app = Flask(__name__)
from datetime import timedelta
import re  # <-- Ye import hona zaroori hai
from markupsafe import Markup
app.secret_key = os.environ.get('SECRET_KEY')
app.permanent_session_lifetime = timedelta(days=3650) # 30 din tak login rahega
# Vercel Settings se Secret Key uthayega, nahi toh default use karega
def make_clickable(text):
    # Link dhoondne ka pattern
    url_pattern = re.compile(r'(https?://[^\s]+)')
    
    # Link ko <a> tag mein badalna (target="_blank" ke saath)
    clickable_text = url_pattern.sub(
        r'<a href="\1" target="_blank" style="color: #e9967a; text-decoration: underline;">\1</a>', 
        text
    )
    return Markup(clickable_text)

# 2. Is function ko Flask/Jinja mein register karna
app.jinja_env.filters['make_clickable'] = make_clickable
app.secret_key = os.environ.get('SECRET_KEY') or "super-secret-trivora-key"

# File size limit 16MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- CLOUDINARY CONFIGURATION ---
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# --- DATABASE CONFIGURATION (Neon Postgres) ---
# Aapke variables 'POSTGRES_URL' aur 'DATABASE_URL' dono check honge
database_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')

if database_url:
    # Postgres format fix for SQLAlchemy
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
else:
    # Fail-safe: Local SQLite for testing
    database_url = 'sqlite:///' + os.path.join('/tmp', 'trivora.db')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Database object initialization (Sabse zaroori line)
db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(500), nullable=True)
    author = db.Column(db.String(50), nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

# Tables automatically ban jayenge Neon database mein
with app.app_context():
    db.create_all()

# --- ROUTES ---

@app.route('/')
def home():
    try:
        posts = Post.query.order_by(Post.date_posted.asc()).limit(6).all()
        return render_template('home.html', posts=posts)
    except Exception as e:
        return f"Database Error: {str(e)}"

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            return "Email already exists!"
        new_user = User(username=username, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        session['user'] = username
        return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            session.permanent = True
            session['user'] = user.username
            return redirect(url_for('home'))
        return "Invalid Credentials!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/category/<name>')
def category(name):
    posts = Post.query.filter_by(category=name).order_by(Post.date_posted.asc()).all()
    return render_template('category.html', category_name=name, posts=posts)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        content = request.form.get('content')
        file = request.files.get('image')

        image_url = None
        if file and file.filename != '' and allowed_file(file.filename):
            upload_result = cloudinary.uploader.upload(file, resource_type="auto")
            image_url = upload_result['secure_url']

        new_post = Post(title=title, category=category, content=content, image_file=image_url, author=session['user'])
        db.session.add(new_post)
        db.session.commit()
        post_url = f"https://trivora-blog.vercel.app/post/{new_post.id}" 
        
        # IndexNow function ko call karein
        try:
            send_to_indexnow(post_url)
        except:
            pass
        return redirect(url_for('category', name=category))
    return render_template('upload.html')

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = db.get_or_404(Post, post_id)
    return render_template('post_detail.html', post=post)

@app.route('/post/delete/<int:post_id>')
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if 'user' in session and session['user'] == post.author:
        db.session.delete(post)
        db.session.commit()
        return redirect(url_for('home'))
    return "Unauthorized!", 403

@app.route('/post/edit/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if 'user' not in session or session['user'] != post.author:
        return "Unauthorized!", 403

    if request.method == 'POST':
        post.title = request.form.get('title')
        post.category = request.form.get('category')
        post.content = request.form.get('content')

        file = request.files.get('image')
        if file and file.filename != '' and allowed_file(file.filename):
            upload_result = cloudinary.uploader.upload(file, resource_type="auto")
            post.image_file = upload_result['secure_url']

        db.session.commit()
        return redirect(url_for('post_detail', post_id=post.id))
    return render_template('edit_post.html', post=post)
@app.route('/sitemap.xml')
def sitemap():
    pages = []
    # Home page link
    pages.append(["https://trivora-blog.vercel.app/", datetime.now().strftime('%Y-%m-%d')])

    # 1. Contact Us page manual add karein
    pages.append([url_for('contact', _external=True), datetime.now().strftime('%Y-%m-%d')])

    # 2. Privacy Policy page manual add karein
    pages.append([url_for('privacy', _external=True), datetime.now().strftime('%Y-%m-%d')])

    # Har blog post ka link automatic jodein (jaisa pehle tha)
    posts = Post.query.all()
    for post in posts:
        url = url_for('post_detail', post_id=post.id, _external=True)
        pages.append([url, post.date_posted.strftime('%Y-%m-%d')])

    sitemap_xml = render_template('sitemap_template.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response
    
@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/privacy-policy')
def privacy():
    return render_template('privacy.html')

# Ye route batayega ki aapki key kya hai
@app.route('/e35d5ba6bea14a9581ce9e6f6b6c5c87.txt')  # Yahan apni file ka exact naam likhein
def index_now_key():
    # Return mein wahi key likhein jo file ke andar hai
    return "e35d5ba6bea14a9581ce9e6f6b6c5c87"
if __name__ == '__main__':
    app.run()









