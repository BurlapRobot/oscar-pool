Oscar Voting App Setup Guide
===========================

Prerequisites
------------
- Python 3.8 or higher
- pip (Python package installer)
- Git

Initial Setup
------------
1. Clone the repository:
   git clone [repository-url]
   cd [repository-name]

2. Create and activate a virtual environment:
   Windows:
     python -m venv venv
     venv\Scripts\activate
   
   Mac/Linux:
     python3 -m venv venv
     source venv/bin/activate

3. Install required packages:
   pip install -r requirements.txt

Configuration
------------
1. Create a settings.config file with the following structure:
   [Flask]
   SECRET_KEY = your_secret_key_here
   SQLALCHEMY_DATABASE_URI = sqlite:///oscars.db

   [Discord]
   CLIENT_ID = your_discord_client_id
   CLIENT_SECRET = your_discord_client_secret
   REDIRECT_URI = http://localhost:5001/callback
   ALLOWED_GUILD_ID = your_discord_server_id

2. Generate SSL certificates for local HTTPS:
   openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

Database Setup
-------------
1. Set the Flask application environment:
   Windows:
     set FLASK_APP=app.py
   
   Mac/Linux:
     export FLASK_APP=app.py

2. Initialize the database:
   python -m flask db init
   python -m flask db migrate -m "Initial migration"
   python -m flask db upgrade

Discord Setup
------------
1. Create a Discord application at https://discord.com/developers/applications
2. Set up OAuth2 with the following settings:
   - Redirect URI: http://localhost:5001/callback
   - Scopes: identify, guilds
3. Copy the Client ID and Client Secret to your settings.config file

Running the Application
----------------------
1. Ensure your virtual environment is activated
2. Start the server:
   python app.py

3. Access the application at:
   https://localhost:5001

Database Management
------------------
- Export categories and nominees:
  python manage_db.py export

- Import categories and nominees:
  python manage_db.py import filename.csv

- List all categories:
  python manage_db.py list_categories

- Manage admin users:
  python manage_db.py set_admin <discord_id> true/false

File Structure
-------------
app.py              - Main application file
manage_db.py        - Database management utilities
requirements.txt    - Python package dependencies
settings.config     - Configuration file (create this)
cert.pem           - SSL certificate (generate this)
key.pem            - SSL private key (generate this)
/templates         - HTML templates
/static            - Static files (CSS, JS, images)

Requirements
-----------
Flask==2.0.1
Flask-SQLAlchemy==2.5.1
Flask-Migrate==3.1.0
requests-oauthlib==1.3.0
python-dotenv==0.19.0
[See requirements.txt for full list]

Troubleshooting
--------------
1. Database errors:
   - Delete the migrations folder and database file
   - Re-run the database setup steps

2. SSL Certificate errors:
   - Regenerate the SSL certificates
   - Ensure cert.pem and key.pem are in the root directory

3. Discord authentication issues:
   - Verify Discord application settings
   - Check REDIRECT_URI matches exactly
   - Ensure all required scopes are enabled

Support
-------
For issues or questions, please create an issue in the repository. 