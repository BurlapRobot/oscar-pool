from app import app, db, User, Category, Nominee

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

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Available commands:")
        print("  python manage_db.py list_users")
        print("  python manage_db.py set_admin <discord_id> [true/false]")
        print("  python manage_db.py list_categories")
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
    else:
        print(f"Unknown command: {command}") 