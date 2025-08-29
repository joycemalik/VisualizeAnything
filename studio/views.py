import os
import sqlite3
import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse
import numpy as np
from django.urls import reverse
from groq import Groq
from dotenv import load_dotenv
from django.contrib import messages
import time
from datetime import datetime, timezone, timedelta
import json

import io
from supabase import create_client


# Load environment variables
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
print("DEBUG: SUPABASE_URL:", SUPABASE_URL)
print("DEBUG: SUPABASE_SERVICE_KEY loaded:", bool(SUPABASE_SERVICE_KEY))
print("DEBUG: SUPABASE_BUCKET:", SUPABASE_BUCKET)

TEMP_FILES = {}

def cleanup_old_files():
    try:
        files = supabase.storage.from_(SUPABASE_BUCKET).list("sessions/")
        for f in files:
            created_at = datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now - created_at > timedelta(hours=1):
                supabase.storage.from_(SUPABASE_BUCKET).remove([f["name"]])
                print(f"✅ Deleted old file from Supabase: {f['name']}")

    except Exception as e:
        print(f"⚠️ Cleanup failed: {e}")

def index(request):
    cleanup_old_files()
    return render(request, "index.html", {"datasets": []})


def dataset_list(request):
    return render(request, "datasets.html", {"datasets": []})


def upload_dataset(request):
    cleanup_old_files()  # delete old session files first

    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]

        # Create a unique filename for Supabase
        session_key = request.session.session_key or str(int(time.time()))
        timestamp = int(time.time())
        filename = f"{session_key}_{timestamp}_{file.name}"
        path_in_bucket = f"sessions/{filename}"

        print(f"DEBUG: Uploading file: {filename}")

        try:
            # Read file data as bytes
            data = file.read()

            # Delete if already exists in Supabase
            existing_files = supabase.storage.from_(SUPABASE_BUCKET).list("sessions/")
            existing_names = [f["name"] for f in existing_files]
            if path_in_bucket in existing_names:
                supabase.storage.from_(SUPABASE_BUCKET).remove([path_in_bucket])
                print(f"⚠️ Removed existing file before upload: {path_in_bucket}")

            # Upload to Supabase
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path_in_bucket,
                data,
                {"cacheControl": "3600"}
            )
            print(f"✅ Uploaded to Supabase: {path_in_bucket}")

            # Store Supabase path in session for later use
            TEMP_FILES[request.session.session_key] = path_in_bucket
            request.session["dataset_path"] = path_in_bucket

            messages.success(request, f"File uploaded successfully: {file.name}")
            return redirect(reverse("dataset_preview", args=[filename]))

        except Exception as e:
            print(f"❌ Failed to upload to Supabase: {e}")
            messages.error(request, f"Failed to upload: {str(e)}")
            return redirect("index")

    return redirect("index")


def dataset_preview(request, dataset_name):
    path_in_bucket = request.session.get("dataset_path")
    print(f"DEBUG: Preview session dataset_path: {path_in_bucket}")  # DEBUG

    if not path_in_bucket:
        messages.error(request, "No dataset in session.")
        return redirect("index")

    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
        df = pd.read_csv(io.BytesIO(res))
        print(f"✅ Loaded dataset from Supabase: {dataset_name}")  # DEBUG
    except Exception as e:
        df = pd.DataFrame()
        print(f"❌ Failed to load dataset from Supabase: {e}")  # DEBUG
        messages.error(request, f"Failed to load dataset: {str(e)}")

    context = {
        "dataset": {"name": dataset_name},
        "columns": df.columns.tolist() if not df.empty else [],
        "preview_rows": df.head(5).values.tolist() if not df.empty else [],
    }

    return render(request, "dataset_preview.html", context)


def full_dataset(request):
    path_in_bucket = request.session.get("dataset_path")
    print(f"DEBUG: full_dataset session path: {path_in_bucket}")  # DEBUG

    if not path_in_bucket:
        return JsonResponse({"error": "No dataset in session."}, status=400)

    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
        df = pd.read_csv(io.BytesIO(res))

        def make_json_safe(x):
            if isinstance(x, (np.integer, int)):
                return int(x)
            if isinstance(x, (np.floating, float)):
                if pd.isna(x) or np.isinf(x):
                    return None
                return float(x)
            if pd.isna(x):
                return None
            if isinstance(x, (np.bool_, bool)):
                return bool(x)
            return str(x)

        safe_rows = [{col: make_json_safe(row[col]) for col in df.columns} for _, row in df.iterrows()]

        return JsonResponse({
            "columns": df.columns.tolist(),
            "rows": safe_rows
        })

    except Exception as e:
        print(f"❌ full_dataset failed: {e}")  # DEBUG
        return JsonResponse({"error": f"Failed to read dataset: {str(e)}"}, status=500)


def run_query(request, dataset_name):
    import re

    def make_sql_prompt(dataset_name: str, columns: list[dict], user_input: str) -> str:
        # Build a SAFE JSON instruction object
        obj = {
            "role": "system",
            "task": "Translate English to exactly one SQLite SELECT query.",
            "dialect": "sqlite",
            "table": {
                "name": dataset_name,
                "columns": columns  # [{"name":"col","type":"int64"}, ...]
            },
            "rules": [
                "Respond with JSON ONLY. No prose, no code fences.",
                "Return exactly one key: sql.",
                "The value must be exactly one SELECT statement ending with a semicolon.",
                "Use ONLY the provided table.",
                f'Always double-quote the table name in FROM: FROM "{dataset_name}".',
                "Use only columns that exist.",
                "Do not use JOINs, other tables, PRAGMA, or DDL.",
                "Numeric literals unquoted; strings single-quoted and escaped.",
                "No comments, no multiple statements."
            ],
            "input": {"english": user_input},
            "output_schema": {
                "type": "object",
                "required": ["sql"],
                "additionalProperties": False,
                "properties": {"sql": {"type": "string"}}
            },
            "respond_with": "json_only"
        }
        return json.dumps(obj, ensure_ascii=False)

    def extract_top_level_json(text: str) -> dict:
        # First try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Fallback: extract first balanced {...} block
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    block = text[start:i+1]
                    try:
                        return json.loads(block)
                    except Exception:
                        # keep scanning in case there is another block later
                        start = -1
        raise ValueError("Model did not return valid JSON.")

    if request.method != "POST":
        return JsonResponse({"error": "POST request required"}, status=400)

    user_input = request.POST.get("query")
    path_in_bucket = request.session.get("dataset_path")
    print(f"DEBUG: run_query session dataset_path: {path_in_bucket}")

    if not path_in_bucket:
        return JsonResponse({"query": user_input, "result": "⚠ No dataset found in session."})

    # Load CSV
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
        df = pd.read_csv(io.BytesIO(res))
        print(f"✅ Dataset loaded for query: {dataset_name}")
    except Exception as e:
        print(f"❌ Failed to load dataset: {e}")
        return JsonResponse({"query": user_input, "result": f"⚠ Failed to load dataset: {str(e)}"})

    # Build in-memory SQLite table
    conn = sqlite3.connect(":memory:")
    try:
        # Let pandas create the table with proper quoting
        df.to_sql(dataset_name, conn, index=False, if_exists="replace")
    except Exception as e:
        conn.close()
        return JsonResponse({"query": user_input, "result": f"⚠ Failed to stage table: {str(e)}"})

    # Column metadata for the prompt
    columns = [{"name": c, "type": str(t)} for c, t in zip(df.columns, df.dtypes)]

    # JSON prompt (safe)
    prompt_json = make_sql_prompt(dataset_name, columns, user_input)

    try:
        # Call model — keep temp 0; send the JSON as the sole message content
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt_json}],
            temperature=0,
            # If your client supports it, uncomment to force JSON:
            # response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        obj = extract_top_level_json(raw)

        if list(obj.keys()) != ["sql"]:
            raise ValueError("Bad shape: expected exactly one key 'sql'.")

        sql_query = obj["sql"].strip()

        # Guards
        if not re.match(r'(?is)^\s*select\b', sql_query):
            return JsonResponse({"query": sql_query, "result": "⚠ Only SELECT queries are allowed."})

        # Must end with a single semicolon and be a single statement
        if not sql_query.endswith(";") or re.search(r";\s*\S", sql_query):
            return JsonResponse({"query": sql_query, "result": "⚠ Return exactly one SELECT statement ending with a semicolon."})

        # Ensure it selects from the quoted table name
        quoted_from = re.search(rf'(?is)\bfrom\s+"{re.escape(dataset_name)}"\b', sql_query)
        if not quoted_from:
            # If it referenced the same name unquoted, auto-fix once
            unquoted_from = re.search(rf'(?is)\bfrom\s+{re.escape(dataset_name)}\b', sql_query)
            if unquoted_from:
                sql_query = re.sub(rf'(?is)\bfrom\s+{re.escape(dataset_name)}\b',
                                   f'FROM "{dataset_name}"', sql_query, count=1)
            else:
                return JsonResponse({"query": sql_query, "result": f'⚠ Query must read FROM "{dataset_name}".'})

        # Optional: add LIMIT 1000 if none present (prevents giant tables)
        if not re.search(r'(?is)\blimit\s+\d+\b', sql_query):
            sql_query = sql_query[:-1] + " LIMIT 1000;"

        print(f"DEBUG: Generated SQL: {sql_query}")

        # Execute
        try:
            result_df = pd.read_sql_query(sql_query, conn)
        except Exception as e:
            cols = df.columns.tolist()
            return JsonResponse({
                "query": sql_query,
                "result": f"⚠ Query failed: {str(e)}. Available columns: {', '.join(cols)}"
            })

        if result_df.empty:
            return JsonResponse({"query": sql_query, "result": "⚠ No results found."})

        result_html = f'<div class="table-responsive">{result_df.to_html(classes="table table-bordered", index=False)}</div>'
        return JsonResponse({"query": sql_query, "result": result_html})

    except Exception as e:
        return JsonResponse({"query": user_input, "result": f"⚠ Failed to generate/parse SQL: {str(e)}"})

    finally:
        conn.close()

