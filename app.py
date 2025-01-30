from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from requests_oauthlib import OAuth2Session
import os
import configparser
from datetime import timedelta
from flask_migrate import Migrate

# Load config
config = configparser.ConfigParser()
config.read('settings.config')

app = Flask(__name__)
app.config['SECRET_KEY'] = config['Flask']['SECRET_KEY']
app.config['SQLALCHEMY_DATABASE_URI'] = config['Flask']['SQLALCHEMY_DATABASE_URI']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Load Discord settings from config
DISCORD_CLIENT_ID = config['Discord']['CLIENT_ID']
DISCORD_CLIENT_SECRET = config['Discord']['CLIENT_SECRET']
DISCORD_REDIRECT_URI = config['Discord']['REDIRECT_URI']
ALLOWED_GUILD_ID = config['Discord']['ALLOWED_GUILD_ID']

discord = OAuth2Session(DISCORD_CLIENT_ID, redirect_uri=DISCORD_REDIRECT_URI, scope=["identify", "guilds"])

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    show_movie = db.Column(db.Boolean, default=False)  # Moved from Nominee to Category

class Nominee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    movie = db.Column(db.String(100))  # Optional movie field
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('nominees', lazy=True))

# Helper function
def is_admin():
    discord_user = session.get('discord_user')
    if not discord_user:
        return False
    user = User.query.filter_by(discord_id=discord_user['id']).first()
    return user.is_admin if user else False

# Routes
@app.route('/', methods=['GET'])
def index():
    is_admin = False
    if 'discord_user' in session:
        user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
        is_admin = user.is_admin if user else False
    predictions = None
    if 'discord_user' in session:
        categories = Category.query.all()
        # Get user's predictions if they exist
        user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
        if user:
            predictions = [
                {
                    'category': p.category.name,
                    'nominee': p.nominee.name
                }
                for p in user.predictions
            ] if hasattr(user, 'predictions') else None
    return render_template('index.html', is_admin=is_admin, predictions=predictions)

@app.route('/login')
def login():
    authorization_url, state = discord.authorization_url('https://discord.com/api/oauth2/authorize')
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(days=7)

@app.route('/callback')
def callback():
    try:
        token = discord.fetch_token(
            "https://discord.com/api/oauth2/token",
            client_secret=DISCORD_CLIENT_SECRET,
            authorization_response=request.url
        )
        
        user_response = discord.get('https://discord.com/api/users/@me')
        if user_response.status_code != 200:
            print(f"Discord API error: {user_response.status_code}")
            flash('Failed to get user information.', 'error')
            return redirect(url_for('index'))
            
        user_data = user_response.json()
        
        # Generate avatar URL
        avatar_hash = user_data.get('avatar')
        if avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{user_data['id']}/{avatar_hash}.png"
        else:
            # Default avatar if user has none
            default_avatar_id = int(user_data['discriminator']) % 5
            avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_id}.png"
        
        # Store or update user in database
        user = User.query.filter_by(discord_id=user_data['id']).first()
        if not user:
            user = User(
                discord_id=user_data['id'],
                username=user_data['username']
            )
            db.session.add(user)
        else:
            user.username = user_data['username']
        
        db.session.commit()

        # Store user info in session
        session.permanent = True
        session['discord_user'] = {
            'id': user_data['id'],
            'username': user_data['username'],
            'avatar_url': avatar_url
        }
        session['oauth2_token'] = token
        
        flash('Logged in successfully!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Login error: {str(e)}")
        flash('Authentication failed. Please try again.', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('discord_user', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


@app.route('/add_nominee', methods=['GET', 'POST'])
def add_nominee():
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    categories = Category.query.all()
    
    # Get the specific category if category_id is provided
    category_id = request.args.get('category_id')
    category = Category.query.get(category_id) if category_id else None
    
    if request.method == 'POST':
        nominee_name = request.form['nominee_name']
        category_id = request.form['category_id']
        movie = request.form.get('movie', '')
        
        if nominee_name and category_id:
            new_nominee = Nominee(
                name=nominee_name, 
                category_id=category_id,
                movie=movie
            )
            db.session.add(new_nominee)
            db.session.commit()
            flash('Nominee added successfully!', 'success')
        else:
            flash('Nominee name and category must be selected.', 'error')
        return redirect(url_for('add_nominee'))
    
    return render_template('add_nominee.html', categories=categories, category=category)

@app.route('/admin/dashboard')
def admin_dashboard():
    # Check if user is logged in and is an admin
    if 'discord_user' not in session:
        flash('You must be logged in to access this page.', 'danger')
        return redirect(url_for('index'))
    
    user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
    if not user or not user.is_admin:
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('index'))
    
    # Get all categories with their nominees
    categories = Category.query.all()
    return render_template('admin_dashboard.html', categories=categories)

@app.route('/admin/category/add', methods=['GET', 'POST'])
def add_category():
    # Check if user is logged in and is an admin
    if 'discord_user' not in session:
        flash('You must be logged in to access this page.', 'danger')
        return redirect(url_for('index'))
    
    user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
    if not user or not user.is_admin:
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        category_name = request.form.get('category_name')
        nominees = request.form.getlist('nominees[]')
        
        if not category_name:
            flash('Please provide a category name.', 'danger')
            return redirect(url_for('add_category'))
        
        try:
            # Create new category
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()  # Get the category ID
            
            # Add nominees if provided
            for nominee_name in nominees:
                if nominee_name.strip():  # Only add non-empty nominees
                    nominee = Nominee(name=nominee_name.strip(), category_id=category.id)
                    db.session.add(nominee)
            
            db.session.commit()
            flash('Category added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error adding category. Please try again.', 'danger')
            return redirect(url_for('add_category'))
    
    return render_template('add_category.html')

@app.route('/admin/category/edit/<int:category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))

    category = Category.query.get_or_404(category_id)
    
    if request.method == 'POST':
        category_name = request.form.get('category_name')
        show_movie = request.form.get('show_movie') == 'on'
        
        if category_name:
            category.name = category_name
            category.show_movie = show_movie
            db.session.commit()
            flash('Category updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Category name is required.', 'error')
    
    return render_template('edit_category.html', category=category)

@app.route('/admin/nominee/edit/<int:nominee_id>', methods=['GET', 'POST'])
def edit_nominee(nominee_id):
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    nominee = Nominee.query.get_or_404(nominee_id)
    
    if request.method == 'POST':
        name = request.form.get('nominee_name')
        movie = request.form.get('movie', '')
        
        if name:
            nominee.name = name
            nominee.movie = movie
            db.session.commit()
            flash('Nominee updated successfully!', 'success')
            return redirect(url_for('edit_category', category_id=nominee.category_id))
        else:
            flash('Nominee name is required.', 'error')
    
    return render_template('edit_nominee.html', nominee=nominee)

@app.route('/admin/nominee/delete/<int:nominee_id>', methods=['POST'])
def delete_nominee(nominee_id):
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    nominee = Nominee.query.get_or_404(nominee_id)
    category_id = nominee.category_id
    
    try:
        db.session.delete(nominee)
        db.session.commit()
        flash('Nominee deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting nominee.', 'error')
    
    return redirect(url_for('edit_category', category_id=category_id))

# Database initialization
def init_db(app):
    with app.app_context():
        db.create_all()

@app.context_processor
def utility_processor():
    def is_admin():
        if not session.get('discord_user'):
            return False
        user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
        return user.is_admin if user else False
    return dict(is_admin=is_admin())

if __name__ == "__main__":
    init_db(app)
    app.run(
        debug=True, 
        host='localhost', 
        port=5001,
        ssl_context=('cert.pem', 'key.pem')
    )
