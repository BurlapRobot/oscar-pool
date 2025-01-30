from app import app, db, User, Category, Nominee
import configparser
import csv
import os

def load_config():
    """Load configuration from settings.config"""
    config = configparser.ConfigParser()
    if os.path.exists('settings.config'):
        config.read('settings.config')
    else:
        config.read('settings.config.example')
    return config

def list_users():
    """List all users and their admin status"""
    print("\nUsers in database:")
    print("-" * 50)
    print(f"{'Discord ID':<20} {'Username':<20} {'Admin'}")
    print("-" * 50)
    
    with app.app_context():
        users = User.query.all()
        for user in users:
            print(f"{user.discord_id:<20} {user.username:<20} {user.is_admin}")

def set_admin(discord_id, admin_status=True):
    """Set admin status for a user by Discord ID"""
    with app.app_context():
        user = User.query.filter_by(discord_id=discord_id).first()
        if user:
            user.is_admin = admin_status
            db.session.commit()
            print(f"Updated {user.username}'s admin status to {admin_status}")
        else:
            print(f"No user found with Discord ID: {discord_id}")

def list_categories():
    """List all categories and their nominees"""
    print("\nCategories and Nominees:")
    print("-" * 50)
    
    with app.app_context():
        categories = Category.query.all()
        for category in categories:
            print(f"\nCategory: {category.name}")
            print("Nominees:")
            for nominee in category.nominees:
                print(f"  - {nominee.name}")

def list_2024_nominees():
    """Read and display categories and nominees from the 2024 CSV file"""
    config = load_config()
    csv_path = config.get('Data', 'DATA_FILE', fallback='oscars.csv')
    
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return
        
    print("\n2024 Categories and Nominees:")
    print("-" * 50)
    
    #try:
    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')
        current_category = None
        print(reader.fieldnames)
        for row in reader:
            category = (row.get('Category') or '').strip()
            nominee = (row.get('Nominees') or '').strip()
            year = (row.get('Year') or '').strip()
            if year != None and year == '2024':
                if category and category != current_category:
                    current_category = category
                    print(f"\nCategory: {category}")
                    print("Nominees:")
            
                if nominee:
                    print(f"  - {nominee}")
                    
#    except Exception as e:
#        print(f"Error reading CSV file: {e}")

def export_categories():
    """Export categories and nominees to a CSV file"""
    import csv
    from datetime import datetime
    from app import db, Category, Nominee
    
    categories = Category.query.all()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'oscars_export_{timestamp}.csv'
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Category', 'Nominee', 'Movie', 'ShowMovie'])
        
        for category in categories:
            for nominee in category.nominees:
                writer.writerow([
                    category.name,
                    nominee.name,
                    nominee.movie or '',  # Use empty string if movie is None
                    '1' if nominee.show_movie else '0'
                ])
    
    print(f"Exported categories and nominees to {filename}")

def import_categories(filename):
    """Import categories and nominees from a CSV file"""
    import csv
    from app import db, Category, Nominee
    
    if not os.path.exists(filename):
        print(f"Error: File {filename} not found")
        return
    
    try:
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                category_name = row['Category'].strip()
                nominee_name = row['Nominee'].strip() if row['Nominee'] else None
                movie = row.get('Movie', '').strip() or None  # Convert empty string to None
                show_movie = row.get('ShowMovie', '0').strip() in ['1', 'true', 'True']
                
                if not category_name:
                    continue
                
                # Find or create category
                category = Category.query.filter_by(name=category_name).first()
                if not category:
                    category = Category(name=category_name)
                    db.session.add(category)
                    db.session.flush()
                
                # Add or update nominee
                if nominee_name:
                    nominee = Nominee.query.filter_by(
                        category_id=category.id,
                        name=nominee_name
                    ).first()
                    
                    if nominee:
                        # Update existing nominee
                        nominee.movie = movie
                        nominee.show_movie = show_movie
                    else:
                        # Create new nominee
                        nominee = Nominee(
                            name=nominee_name,
                            category_id=category.id,
                            movie=movie,
                            show_movie=show_movie
                        )
                        db.session.add(nominee)
        
        db.session.commit()
        print("Import completed successfully")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error during import: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Available commands:")
        print("  python manage_db.py list_users")
        print("  python manage_db.py set_admin <discord_id> [true/false]")
        print("  python manage_db.py list_categories")
        print("  python manage_db.py list_2024")
        print("  python manage_db.py export")
        print("  python manage_db.py import <filename>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list_users":
        list_users()
    elif command == "set_admin":
        if len(sys.argv) < 3:
            print("Please provide a Discord ID")
            sys.exit(1)
        discord_id = sys.argv[2]
        admin_status = True if len(sys.argv) < 4 else sys.argv[3].lower() == 'true'
        set_admin(discord_id, admin_status)
    elif command == "list_categories":
        list_categories()
    elif command == "list_2024":
        list_2024_nominees()
    elif command == "export":
        export_categories()
    elif command == "import":
        if len(sys.argv) < 3:
            print("Error: Please provide filename")
            print("Usage: python manage_db.py import <filename>")
            sys.exit(1)
        import_categories(sys.argv[2])
    else:
        print(f"Unknown command: {command}") 