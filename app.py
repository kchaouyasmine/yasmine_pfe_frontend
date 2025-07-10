from backend import create_app
from backend.routes.auth import auth_bp
from flask_cors import CORS

app = create_app()
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:5173"}})
app.config.update({
    'SESSION_COOKIE_SAMESITE': 'none',
    'SESSION_COOKIE_SECURE': True,  
    'SESSION_COOKIE_HTTPONLY': True
})
app.config['WTF_CSRF_ENABLED'] = False
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    