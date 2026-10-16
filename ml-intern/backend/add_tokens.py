import sqlite3
import time
import os

db_path = 'users.db'

def add_token(provider: str, key: str):
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found. Please start the server once to initialize it.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ensure api_tokens table exists (it should be created by auth_local.py, but just in case)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_tokens (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            key TEXT NOT NULL UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            cooldown_until REAL DEFAULT 0.0,
            error_count INTEGER DEFAULT 0,
            added_at REAL
        )
    ''')
    
    token_id = f"tok_{int(time.time()*1000)}"
    try:
        cursor.execute('''
            INSERT INTO api_tokens (id, provider, key, is_active, cooldown_until, error_count, added_at)
            VALUES (?, ?, ?, 1, 0.0, 0, ?)
        ''', (token_id, provider, key, time.time()))
        conn.commit()
        print(f"Successfully added {provider} token to the database.")
    except sqlite3.IntegrityError:
        print(f"This {provider} token is already in the database.")
    except Exception as e:
        print(f"Failed to add token: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Add API Tokens to Local Database ===")
    print("Leave blank to skip a provider.")
    
    mistral_key = input("Enter Mistral API Key: ").strip()
    if mistral_key:
        add_token("mistral", mistral_key)
        
    gemini_key = input("Enter Gemini (Google) API Key: ").strip()
    if gemini_key:
        add_token("gemini", gemini_key)
        
    openai_key = input("Enter OpenAI API Key: ").strip()
    if openai_key:
        add_token("openai", openai_key)
        
    print("\nDone! You can now restart your backend server.")
