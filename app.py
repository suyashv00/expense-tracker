import os, json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import telebot
from mistralai import Mistral
from telebot import types
load_dotenv()

TELEGRAM_TOKEN = os.getenv("API_TOKEN")           # from BotFather
MODEL = "mistral-large-latest"

# ─── Clients ────────────────────────────────────────────────────────────────────
bot         = telebot.TeleBot(TELEGRAM_TOKEN)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
DB_FILE = os.getenv("SQLITE_FILE", "expenses.db")

# ─── DB Init ────────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur  = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_name TEXT,
        amount REAL,
        category TEXT,
        date TEXT,
        logged_at TEXT
    )
""")
conn.commit()

# ─── /start and /help commands ────────────────────────────────────────────────────
@bot.message_handler(commands=['start', 'help'])
def send_welcome(msg: types.Message):
    bot.reply_to(
        msg,
        "👋 Welcome to ExpenseBot!\n\n"
        "📝 Send expense messages like:\n"
        "`Spent 250 on groceries today`\n"
        "`80 on milk`\n"
        "`cab fare 500 yesterday`\n\n"
        "Commands:\n"
        "/start - Show this help message\n"
        "/help - Show this help message"
    )

# ─── Extract Expense Function ─────────────────────────────────────────────────────
def extract_expense_from_query(user_query: str) -> dict:
    """Extract expense details from user query using Mistral AI"""
    
    client = Mistral(api_key=MISTRAL_API_KEY)
    
    prompt = f"""
    Extract expense information from the user query and return a JSON object.
    
    User Query: "{user_query}"
    Today's date: {datetime.now().strftime("%d/%m/%Y")}
    
    Extract and return the following fields in JSON format:
    - expense_name (str): Name of the expense
    - amount (float): Amount spent
    - date (str): Date in DD/MM/YYYY format (use today's date if not mentioned)
    - category (str): Assign one category from: Food, Grocery, Travel, Entertainment, Utilities, Healthcare, Education, Other
    
    Return ONLY valid JSON, no additional text.
    Example output:
    {{"expense_name": "milk", "amount": 80.0, "date": "17/01/2026", "category": "Grocery"}}
    """
    
    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response = client.chat.complete(
        model=MODEL,
        messages=messages
    )
    
    # Parse the response
    response_text = response.choices[0].message.content.strip()
    # Remove markdown code block markers
    response_text = response_text.replace("```json", "").replace("```", "").strip()
    expense_data = json.loads(response_text)
    
    return expense_data

# ─── Insert Expense Function ──────────────────────────────────────────────────────
def insert_expense(expense_data: dict) -> bool:
    """Insert expense into database"""
    
    try:
        # Convert date format from DD/MM/YYYY to YYYY-MM-DD for storage
        date_obj = datetime.strptime(expense_data['date'], "%d/%m/%Y")
        formatted_date = date_obj.strftime("%Y-%m-%d")
        
        logged_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        cur.execute("""
            INSERT INTO expenses (expense_name, amount, category, date, logged_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            expense_data['expense_name'],
            expense_data['amount'],
            expense_data['category'],
            formatted_date,
            logged_at
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error inserting expense: {e}")
        return False

# ─── Process User Query Function ──────────────────────────────────────────────────
def process_user_query(user_query: str) -> dict:
    """Main function to process user query and insert expense"""
    
    print(f"Processing query: {user_query}")
    
    try:
        # Extract expense details using LLM
        expense_data = extract_expense_from_query(user_query)
        print(f"Extracted data: {expense_data}")
        
        # Insert into database
        if insert_expense(expense_data):
            print("Expense inserted successfully!")
            return {
                "success": True,
                "data": expense_data,
                "message": f"✅ Added expense: {expense_data['expense_name']} - ₹{expense_data['amount']} ({expense_data['category']})"
            }
        else:
            return {
                "success": False,
                "message": "❌ Failed to insert expense into database"
            }
    except Exception as e:
        print(f"Error processing query: {e}")
        return {
            "success": False,
            "message": f"❌ Error processing your request: {str(e)}"
        }

# ─── Main Message Handler ─────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_message(msg: types.Message):
    """Handle all text messages"""
    
    user_query = msg.text
    print(f"Received message from {msg.from_user.username}: {user_query}")
    
    # Process the user query
    result = process_user_query(user_query)
    
    # Send response back to user
    bot.reply_to(msg, result['message'])

if __name__ == "__main__":
    print("🤖 ExpenseBot is running...")
    bot.infinity_polling()