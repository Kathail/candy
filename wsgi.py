import os

from app import create_app
from app.init_db import init_db

app = create_app()
init_db(app)

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_ENV") == "development"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", 5000))

    app.run(debug=debug_mode, host=host, port=port)
