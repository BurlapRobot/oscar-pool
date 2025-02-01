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
ALLOWED_GUILD_IDS = set(config['Discord']['ALLOWED_GUILD_IDS'].split(','))  # Changed to list of IDs

discord = OAuth2Session(DISCORD_CLIENT_ID, redirect_uri=DISCORD_REDIRECT_URI, scope=["identify", "guilds"])

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    predictions = db.relationship('Prediction', backref='user', lazy=True)
    __table_args__ = (
        db.UniqueConstraint('discord_id', name='unique_discord_id'),
    )

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    show_movie = db.Column(db.Boolean, default=False)

class Nominee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    movie = db.Column(db.String(100))
    winner = db.Column(db.Boolean, default=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', name='fk_nominee_category'), nullable=False)
    category = db.relationship('Category', backref=db.backref('nominees', lazy=True))

class Pool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.UniqueConstraint('name', name='unique_pool_name'),
    )

class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_prediction_user'), nullable=False)
    nominee_id = db.Column(db.Integer, db.ForeignKey('nominee.id', name='fk_prediction_nominee'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', name='fk_prediction_category'), nullable=False)
    pool_id = db.Column(db.Integer, db.ForeignKey('pool.id', name='fk_prediction_pool'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships
    nominee = db.relationship('Nominee', backref=db.backref('predictions', lazy=True))
    category = db.relationship('Category', backref=db.backref('predictions', lazy=True))
    pool = db.relationship('Pool', backref=db.backref('predictions', lazy=True))
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_id', 'pool_id', name='unique_user_category_pool_prediction'),
    )

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
    is_admin_user = False
    predictions_by_pool = {}
    
    if 'discord_user' in session:
        user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
        is_admin_user = user.is_admin if user else False
        
        if user:
            # Get all predictions for the user across all pools
            predictions = (Prediction.query
                         .join(Pool)
                         .join(Category)
                         .join(Nominee)
                         .filter(Prediction.user_id == user.id)
                         .order_by(Pool.name, Category.name)
                         .all())
            
            # Group predictions by pool
            for prediction in predictions:
                if prediction.pool.id not in predictions_by_pool:
                    predictions_by_pool[prediction.pool.id] = {
                        'name': prediction.pool.name,
                        'predictions': []
                    }
                predictions_by_pool[prediction.pool.id]['predictions'].append(prediction)
    
    return render_template('index.html',
                         is_admin=is_admin_user,
                         predictions_by_pool=predictions_by_pool)

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
        
        # Check user's guilds
        guilds_response = discord.get('https://discord.com/api/users/@me/guilds')
        if guilds_response.status_code != 200:
            print(f"Discord API error: {guilds_response.status_code}")
            flash('Failed to get guild information.', 'error')
            return redirect(url_for('index'))
            
        guilds = guilds_response.json()
        user_guild_ids = {str(guild['id']) for guild in guilds}
        
        # Check if user is in any of the allowed guilds
        if not (user_guild_ids & ALLOWED_GUILD_IDS):
            flash('You must be a member of the required Discord server to use this application.', 'error')
            return redirect(url_for('index'))
        
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
    category_id = request.args.get('category_id')
    category = Category.query.get(category_id) if category_id else None
    
    if request.method == 'POST':
        nominee_name = request.form['nominee_name']
        category_id = request.form['category_id']
        movie = request.form.get('movie', '')
        winner = request.form.get('winner') == 'on'
        
        if nominee_name and category_id:
            new_nominee = Nominee(
                name=nominee_name, 
                category_id=category_id,
                movie=movie,
                winner=winner
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
    
    categories = Category.query.all()
    pools = Pool.query.order_by(Pool.created_at.desc()).all()
    
    # Get selected pool and its predictions
    selected_pool_id = request.args.get('pool_id', type=int)
    selected_pool = None
    user_predictions = None
    
    if selected_pool_id:
        selected_pool = Pool.query.get(selected_pool_id)
        if selected_pool:
            user_predictions = (Prediction.query
                              .join(User)
                              .join(Category)
                              .join(Nominee)
                              .filter(Prediction.pool_id == selected_pool_id)
                              .order_by(User.username, Category.name)
                              .all())
    
    return render_template('admin_dashboard.html',
                         categories=categories,
                         pools=pools,
                         selected_pool=selected_pool,
                         user_predictions=user_predictions)

@app.route('/admin/prediction/<int:prediction_id>/delete', methods=['POST'])
def delete_prediction(prediction_id):
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    prediction = Prediction.query.get_or_404(prediction_id)
    pool_id = prediction.pool_id
    
    try:
        db.session.delete(prediction)
        db.session.commit()
        flash('Prediction deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting prediction.', 'error')
    
    return redirect(url_for('admin_dashboard', pool_id=pool_id))

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
        winner = request.form.get('winner') == 'on'
        
        if name:
            nominee.name = name
            nominee.movie = movie
            nominee.winner = winner
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

# Add some helper functions for pool management
def get_active_pools():
    return Pool.query.filter_by(is_active=True).all()

def get_user_predictions(user_id, pool_id):
    return (Prediction.query
            .join(Category, Prediction.category_id == Category.id)
            .join(Nominee, Prediction.nominee_id == Nominee.id)
            .filter(Prediction.user_id == user_id, Prediction.pool_id == pool_id)
            .all())

# Add a route for pool management
@app.route('/admin/pools', methods=['GET', 'POST'])
def manage_pools():
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        pool_name = request.form.get('pool_name')
        if pool_name:
            new_pool = Pool(name=pool_name)
            db.session.add(new_pool)
            try:
                db.session.commit()
                flash('Pool created successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error creating pool. Name might be duplicate.', 'error')
    
    pools = Pool.query.all()
    return render_template('manage_pools.html', pools=pools)

@app.route('/admin/pool/<int:pool_id>/toggle', methods=['POST'])
def toggle_pool(pool_id):
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    pool = Pool.query.get_or_404(pool_id)
    pool.is_active = not pool.is_active
    db.session.commit()
    flash(f'Pool "{pool.name}" {"activated" if pool.is_active else "deactivated"} successfully!', 'success')
    return redirect(url_for('manage_pools'))

@app.route('/make_prediction', methods=['GET', 'POST'])
def select_pool():
    if 'discord_user' not in session:
        flash('You must be logged in to make predictions.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        pool_name = request.form.get('pool_name')
        pool = Pool.query.filter_by(name=pool_name, is_active=True).first()
        
        if pool:
            return redirect(url_for('make_prediction', pool_id=pool.id))
        else:
            flash('Invalid or inactive pool name. Please try again.', 'error')
    
    return render_template('select_pool.html')

@app.route('/make_prediction/<int:pool_id>', methods=['GET', 'POST'])
def make_prediction(pool_id):
    if 'discord_user' not in session:
        flash('You must be logged in to make predictions.', 'error')
        return redirect(url_for('index'))
    
    pool = Pool.query.get_or_404(pool_id)
    if not pool.is_active:
        flash('This prediction pool is not currently active.', 'error')
        return redirect(url_for('select_pool'))
    
    user = User.query.filter_by(discord_id=session['discord_user']['id']).first()
    
    if request.method == 'POST':
        try:
            # Get all categories and process predictions
            categories = Category.query.order_by(Category.name).all()
            for category in categories:
                nominee_id = request.form.get(f'category_{category.id}')
                if nominee_id:
                    # Check if prediction already exists
                    prediction = Prediction.query.filter_by(
                        user_id=user.id,
                        category_id=category.id,
                        pool_id=pool_id).first()
                    
                    if prediction:
                        # Update existing prediction
                        prediction.nominee_id = nominee_id
                    else:
                        # Create new prediction
                        prediction = Prediction(
                            user_id=user.id,
                            nominee_id=nominee_id,
                            category_id=category.id,
                            pool_id=pool_id
                        )
                        db.session.add(prediction)
            
            db.session.commit()
            flash('Your predictions have been saved!', 'success')
            return redirect(url_for('index', pool_id=pool_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error saving predictions: {str(e)}")
            flash('There was an error saving your predictions. Please try again.', 'error')
    
    # Get existing predictions for this user and pool
    existing_predictions = {
        pred.category_id: pred.nominee_id 
        for pred in Prediction.query.filter_by(user_id=user.id, pool_id=pool_id).all()
    }
    
    # Get all categories and their nominees
    categories = Category.query.order_by(Category.name).all()
    
    return render_template(
        'make_prediction.html',
        pool=pool,
        categories=categories,
        existing_predictions=existing_predictions
    )

@app.route('/admin/prediction/delete_user_pool', methods=['POST'])
def delete_user_pool_predictions():
    if 'discord_user' not in session or not is_admin():
        flash('Access denied. Admins only.', 'error')
        return redirect(url_for('index'))
    
    user_id = request.form.get('user_id')
    pool_id = request.form.get('pool_id')
    
    if not user_id or not pool_id:
        flash('Missing required information.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Delete all predictions for the user in the specified pool
        Prediction.query.filter_by(
            user_id=user_id,
            pool_id=pool_id
        ).delete()
        db.session.commit()
        flash('All predictions deleted successfully for this user in the pool.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting predictions.', 'error')
    
    return redirect(url_for('admin_dashboard', pool_id=pool_id))

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

def export():
    """Export categories, nominees, and predictions to a CSV file"""
    import csv
    from datetime import datetime
    
    with app.app_context():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'oscars_export_{timestamp}.csv'
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Updated headers to include prediction data
            writer.writerow(['Pool', 'User', 'Category', 'ShowMovie', 'Nominee', 'Movie', 'Prediction', 'Last Updated'])
            
            # Get all pools
            pools = Pool.query.all()
            for pool in pools:
                # Get all predictions for this pool
                predictions = (Prediction.query
                             .join(User)
                             .join(Category)
                             .join(Nominee)
                             .filter(Prediction.pool_id == pool.id)
                             .order_by(User.username, Category.name)
                             .all())
                
                # Write predictions
                for pred in predictions:
                    writer.writerow([
                        pool.name,
                        pred.user.username,
                        pred.category.name,
                        '1' if pred.category.show_movie else '0',
                        pred.nominee.name,
                        pred.nominee.movie or '',
                        '1',  # This nominee was predicted
                        pred.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    ])
                    
                    # Write other nominees in this category (not predicted)
                    other_nominees = (Nominee.query
                                    .filter(Nominee.category_id == pred.category_id)
                                    .filter(Nominee.id != pred.nominee_id)
                                    .all())
                    
                    for nominee in other_nominees:
                        writer.writerow([
                            pool.name,
                            pred.user.username,
                            pred.category.name,
                            '1' if pred.category.show_movie else '0',
                            nominee.name,
                            nominee.movie or '',
                            '0',  # This nominee was not predicted
                            ''  # No update timestamp for non-predictions
                        ])
        
        print(f"Exported categories, nominees, and predictions to {filename}")

if __name__ == "__main__":
    init_db(app)
    app.run(
        debug=True, 
        host='localhost', 
        port=5001,
        ssl_context=('cert.pem', 'key.pem')
    )
