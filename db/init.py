import os
import sqlite3
import sys

# Default DB path relative to project root
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "recovery_agent.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

def get_db_connection(db_path=None):
    if db_path is None:
        db_path = os.getenv("DB_PATH", DEFAULT_DB_PATH)
    
    # Ensure parent directory exists
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # Mandatory SQLite setting: Foreign key enforcement is OFF by default in SQLite.
    # Must explicitly run PRAGMA foreign_keys = ON immediately after opening connection.
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Verify foreign keys are enabled
    cursor = conn.cursor()
    fk_status = cursor.execute("PRAGMA foreign_keys;").fetchone()[0]
    if fk_status != 1:
        raise RuntimeError("Failed to enable SQLite foreign key enforcement!")
        
    return conn

def init_db(db_path=None):
    conn = get_db_connection(db_path)
    
    if not os.path.exists(SCHEMA_PATH):
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}")
        
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    cursor = conn.cursor()
    cursor.executescript(schema_sql)
    conn.commit()
    conn.close()
    
    print(f"Database successfully initialized at: {os.path.abspath(db_path)}")

if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else None
    init_db(target_path)
