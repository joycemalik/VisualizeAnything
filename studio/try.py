from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def test_grok_query(user_input):
    dataset_name = "test_table"
    columns_info = "id (int), name (text), age (int), city (text)"

    prompt = f"""
    You are an assistant that converts English into SQLite SQL.
    The table is named '{dataset_name}'.
    The table has the following columns with types: {columns_info}.
    Generate only a SELECT query (no explanation), using exact column names.
    Numeric values should not be quoted; strings should be quoted properly.

    English: {user_input}
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # <-- your Grok model
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        sql_query = response.choices[0].message.content.strip()
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        print(f"✅ English: {user_input}")
        print(f"➡️  Generated SQL: {sql_query}\n")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Test queries
    test_grok_query("show me all users older than 30")
    test_grok_query("list names of users who live in Delhi")
    test_grok_query("get all records where age is less than 25")
