import os
import sqlite3
import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
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
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO


# Load environment variables
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

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


def analyze_dataset_context(df):
    """Analyze dataset and provide context-aware suggestions"""
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        # Get dataset summary
        summary = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': df.dtypes.to_dict(),
            'numeric_cols': list(df.select_dtypes(include=[np.number]).columns),
            'categorical_cols': list(df.select_dtypes(include=['object']).columns),
            'sample_data': df.head(3).to_dict('records'),
            'missing_values': df.isnull().sum().to_dict()
        }
        
        prompt = f"""
        Analyze this dataset and provide insights:
        
        Dataset Summary:
        - Shape: {summary['shape']} (rows, columns)
        - Columns: {summary['columns']}
        - Data types: {summary['dtypes']}
        - Sample data: {summary['sample_data']}
        - Missing values: {summary['missing_values']}
        
        Please provide:
        1. What this dataset appears to be about (domain/context)
        2. 5 specific, actionable SQL queries that would provide valuable insights
        3. 3 most important visualizations that should be created first
        4. Key patterns or relationships to explore
        
        Format your response in JSON:
        {{
            "context": "Brief description of what this data represents",
            "domain": "business/finance/health/education/etc",
            "suggested_queries": [
                "SELECT COUNT(*) FROM data GROUP BY category_column",
                "SELECT AVG(numeric_column) FROM data WHERE condition",
                ...
            ],
            "priority_visualizations": [
                {{"type": "bar", "description": "Count by category", "reason": "Shows distribution"}},
                {{"type": "scatter", "description": "Correlation analysis", "reason": "Reveals relationships"}},
                {{"type": "heatmap", "description": "Missing data pattern", "reason": "Data quality check"}}
            ],
            "key_insights": ["insight1", "insight2", "insight3"]
        }}
        """
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=1000
        )
        
        import json
        analysis = json.loads(chat_completion.choices[0].message.content)
        return analysis
        
    except Exception as e:
        print(f"Analysis error: {e}")
        return {
            "context": "Dataset uploaded successfully",
            "domain": "general", 
            "suggested_queries": [
                "SELECT * FROM data LIMIT 10",
                "SELECT COUNT(*) FROM data",
                f"SELECT * FROM data WHERE {df.columns[0]} IS NOT NULL LIMIT 5"
            ],
            "priority_visualizations": [
                {"type": "bar", "description": "Basic distribution", "reason": "Overview of data"},
                {"type": "line", "description": "Trend analysis", "reason": "Pattern detection"},
                {"type": "scatter", "description": "Relationship analysis", "reason": "Correlation check"}
            ],
            "key_insights": ["Data contains " + str(df.shape[0]) + " records", "Multiple columns available for analysis"]
        }


def auto_visualize_dataset(request):
    """Generate automatic visualizations for the dataset"""
    if request.method == 'POST':
        path_in_bucket = request.session.get("dataset_path")
        
        if not path_in_bucket:
            return JsonResponse({'error': 'No dataset found'}, status=400)
        
        try:
            # Load dataset
            res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
            df = pd.read_csv(io.BytesIO(res))
            
            # Get analysis
            analysis = analyze_dataset_context(df)
            
            # Generate the 3 priority visualizations
            charts = []
            for viz in analysis['priority_visualizations']:
                try:
                    chart_data = generate_auto_chart(df, viz['type'], viz['description'])
                    if chart_data:
                        charts.append({
                            'type': viz['type'],
                            'description': viz['description'],
                            'reason': viz['reason'],
                            'image': chart_data['image'],
                            'explanation': chart_data['explanation']
                        })
                except Exception as e:
                    print(f"Failed to generate {viz['type']} chart: {e}")
                    continue
            
            return JsonResponse({
                'success': True,
                'analysis': analysis,
                'charts': charts
            })
            
        except Exception as e:
            return JsonResponse({'error': f'Auto-visualization failed: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Only POST method allowed'}, status=405)


def generate_auto_chart(df, chart_type, description):
    """Generate automatic charts based on data analysis"""
    try:
        # Set up the plot style
        plt.style.use('default')
        sns.set_palette("husl")
        
        # Create figure
        fig, ax = plt.subplots(figsize=(10, 6))
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        categorical_cols = df.select_dtypes(include=['object']).columns
        
        if chart_type == 'bar' and len(categorical_cols) > 0 and len(numeric_cols) > 0:
            # Bar chart of categorical vs numeric
            cat_col = categorical_cols[0]
            num_col = numeric_cols[0]
            
            # Get top 10 categories to avoid overcrowding
            top_categories = df[cat_col].value_counts().head(10)
            filtered_df = df[df[cat_col].isin(top_categories.index)]
            
            grouped = filtered_df.groupby(cat_col)[num_col].mean().reset_index()
            sns.barplot(data=grouped, x=cat_col, y=num_col, ax=ax)
            ax.set_title(f'Average {num_col} by {cat_col}', fontsize=14, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            
        elif chart_type == 'scatter' and len(numeric_cols) >= 2:
            # Scatter plot of two numeric columns
            x_col, y_col = numeric_cols[0], numeric_cols[1]
            sns.scatterplot(data=df, x=x_col, y=y_col, ax=ax, alpha=0.6)
            ax.set_title(f'Relationship: {y_col} vs {x_col}', fontsize=14, fontweight='bold')
            
        elif chart_type == 'heatmap' and len(numeric_cols) >= 2:
            # Correlation heatmap
            correlation_matrix = df[numeric_cols].corr()
            sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', center=0, 
                      square=True, ax=ax, cbar_kws={'shrink': 0.8})
            ax.set_title('Correlation Matrix', fontsize=14, fontweight='bold')
            
        else:
            # Fallback: simple distribution plot
            if len(numeric_cols) > 0:
                df[numeric_cols[0]].hist(bins=20, ax=ax, alpha=0.7)
                ax.set_title(f'Distribution of {numeric_cols[0]}', fontsize=14, fontweight='bold')
            else:
                return None
        
        plt.tight_layout()
        
        # Convert to base64
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plot_data = buffer.getvalue()
        buffer.close()
        plt.close()
        
        plot_url = base64.b64encode(plot_data).decode()
        
        return {
            'image': f'data:image/png;base64,{plot_url}',
            'explanation': f'Auto-generated {chart_type} chart showing {description}'
        }
        
    except Exception as e:
        print(f"Auto chart generation error: {e}")
        return None


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
        
        # Analyze dataset context and provide suggestions
        analysis = analyze_dataset_context(df)
        
    except Exception as e:
        df = pd.DataFrame()
        analysis = None
        print(f"❌ Failed to load dataset from Supabase: {e}")  # DEBUG
        messages.error(request, f"Dataset not found. It may have been cleaned up or your session expired. Please upload the dataset again.")
        return redirect("index")

    context = {
        "dataset": {"name": dataset_name},
        "columns": df.columns.tolist() if not df.empty else [],
        "preview_rows": df.head(5).values.tolist() if not df.empty else [],
        "analysis": analysis,  # Add analysis to context
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

    # Handle both JSON and form data
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            user_input = data.get("query")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
    else:
        user_input = request.POST.get("query")
    
    path_in_bucket = request.session.get("dataset_path")
    print(f"DEBUG: run_query session dataset_path: {path_in_bucket}")

    if not path_in_bucket:
        return JsonResponse({
            "query": user_input or "", 
            "result": [], 
            "error": "No dataset found in session. Please upload a new dataset to continue."
        })

    # Load CSV
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
        df = pd.read_csv(io.BytesIO(res))
        print(f"✅ Dataset loaded for query: {dataset_name}")
    except Exception as e:
        print(f"❌ Failed to load dataset: {e}")
        error_msg = "Dataset file not found. This may happen if:"
        error_msg += "<br>• The file was automatically cleaned up"
        error_msg += "<br>• Your session has expired"
        error_msg += "<br>• There was a storage issue"
        error_msg += "<br><br>Please <a href='/' style='color: #4f46e5; text-decoration: underline;'>upload your dataset again</a> to continue."
        
        return JsonResponse({
            "query": user_input or "", 
            "result": [], 
            "error": error_msg
        })

    # Build in-memory SQLite table
    conn = sqlite3.connect(":memory:")
    try:
        # Let pandas create the table with proper quoting
        df.to_sql(dataset_name, conn, index=False, if_exists="replace")
    except Exception as e:
        conn.close()
        return JsonResponse({"query": user_input or "", "result": [], "error": f"Failed to stage table: {str(e)}"})

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
            return JsonResponse({"query": sql_query, "result": [], "error": "Only SELECT queries are allowed."})

        # Auto-fix semicolon if missing
        if not sql_query.endswith(";"):
            sql_query = sql_query + ";"

        # Check for multiple statements (semicolon in the middle)
        if re.search(r";\s*\S", sql_query):
            return JsonResponse({"query": sql_query, "result": [], "error": "Only single SELECT statements are allowed."})

        # Simple table name check - just ensure the dataset name appears somewhere in the query
        # This is more flexible than strict regex matching
        if dataset_name not in sql_query:
            return JsonResponse({"query": sql_query, "result": [], "error": f'Query must reference the dataset "{dataset_name}".'})

        print(f"DEBUG: Table name validation passed for: {dataset_name}")
        
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
                "result": [],
                "error": f"Query failed: {str(e)}. Available columns: {', '.join(cols)}"
            })

        if result_df.empty:
            return JsonResponse({"query": sql_query, "result": []})

        # Convert DataFrame to list of dictionaries for JSON response
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

        result_data = []
        for _, row in result_df.iterrows():
            row_dict = {}
            for col in result_df.columns:
                row_dict[col] = make_json_safe(row[col])
            result_data.append(row_dict)

        # Add visualization suggestions
        visualization_suggestion = suggest_visualization_type(result_df, sql_query)

        return JsonResponse({
            "query": sql_query, 
            "result": result_data,
            "visualization_suggestion": visualization_suggestion,
            "data_summary": {
                "rows": len(result_data),
                "columns": list(result_df.columns),
                "numeric_columns": list(result_df.select_dtypes(include=[np.number]).columns),
                "categorical_columns": list(result_df.select_dtypes(include=['object']).columns)
            }
        })

    except Exception as e:
        return JsonResponse({"query": user_input or "", "result": [], "error": f"Failed to generate/parse SQL: {str(e)}"})

    finally:
        conn.close()


def suggest_visualization_type(df, query):
    """Suggest the best visualization type based on data characteristics"""
    query_lower = query.lower()
    
    # Check for aggregation functions
    if any(func in query_lower for func in ['count', 'sum', 'avg', 'average', 'max', 'min']):
        if 'group by' in query_lower:
            return "bar_chart"
        elif len(df) == 1:
            return "metric_card"
        else:
            return "bar_chart"
    
    # Check for time series
    date_columns = [col for col in df.columns if any(word in col.lower() for word in ['date', 'time', 'year', 'month'])]
    if date_columns and len(df) > 1:
        return "line_chart"


def generate_chart(request):
    """Generate chart using Seaborn based on query results"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            chart_type = data.get('chart_type', 'bar')
            query_results = data.get('query_results', [])
            columns = data.get('columns', [])
            
            if not query_results or not columns:
                return JsonResponse({'error': 'No data provided'}, status=400)
            
            # Convert to DataFrame
            df = pd.DataFrame(query_results, columns=columns)
            
            # Set up the plot style
            plt.style.use('default')
            sns.set_palette("husl")
            
            # Create figure
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Generate chart based on type
            chart_explanation = ""
            
            if chart_type == 'scatter':
                if len(df.select_dtypes(include=[np.number]).columns) >= 2:
                    numeric_cols = df.select_dtypes(include=[np.number]).columns[:2]
                    x_col, y_col = numeric_cols[0], numeric_cols[1]
                    sns.scatterplot(data=df, x=x_col, y=y_col, ax=ax, s=100, alpha=0.7)
                    ax.set_title(f'Scatter Plot: {y_col} vs {x_col}', fontsize=16, fontweight='bold')
                    chart_explanation = f"This scatter plot shows the relationship between {x_col} and {y_col}. Each point represents one data record."
                else:
                    return JsonResponse({'error': 'Need at least 2 numeric columns for scatter plot'}, status=400)
                    
            elif chart_type == 'box':
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    # If there are categorical columns, use them for grouping
                    cat_cols = df.select_dtypes(include=['object']).columns
                    if len(cat_cols) > 0 and len(numeric_cols) > 0:
                        sns.boxplot(data=df, x=cat_cols[0], y=numeric_cols[0], ax=ax)
                        ax.set_title(f'Box Plot: {numeric_cols[0]} by {cat_cols[0]}', fontsize=16, fontweight='bold')
                        chart_explanation = f"This box plot shows the distribution of {numeric_cols[0]} across different categories of {cat_cols[0]}. The box shows the quartiles, and whiskers show the range."
                    else:
                        sns.boxplot(data=df[numeric_cols], ax=ax)
                        ax.set_title('Box Plot of Numeric Variables', fontsize=16, fontweight='bold')
                        chart_explanation = "This box plot shows the distribution of numeric variables. The box shows the quartiles, and whiskers show the range."
                else:
                    return JsonResponse({'error': 'Need at least 1 numeric column for box plot'}, status=400)
                    
            elif chart_type == 'heatmap':
                numeric_df = df.select_dtypes(include=[np.number])
                if len(numeric_df.columns) >= 2:
                    correlation_matrix = numeric_df.corr()
                    sns.heatmap(correlation_matrix, annot=True, cmap='coolwarm', center=0, 
                              square=True, ax=ax, cbar_kws={'shrink': 0.8})
                    ax.set_title('Correlation Heatmap', fontsize=16, fontweight='bold')
                    chart_explanation = "This heatmap shows the correlation between numeric variables. Values close to 1 indicate strong positive correlation, close to -1 indicate strong negative correlation, and close to 0 indicate no correlation."
                else:
                    return JsonResponse({'error': 'Need at least 2 numeric columns for heatmap'}, status=400)
                    
            elif chart_type == 'bar':
                if len(df.columns) >= 2:
                    # Try to find categorical and numeric columns
                    cat_cols = df.select_dtypes(include=['object']).columns
                    num_cols = df.select_dtypes(include=[np.number]).columns
                    
                    if len(cat_cols) > 0 and len(num_cols) > 0:
                        # Group by categorical column and sum numeric values
                        grouped = df.groupby(cat_cols[0])[num_cols[0]].sum().reset_index()
                        sns.barplot(data=grouped, x=cat_cols[0], y=num_cols[0], ax=ax)
                        ax.set_title(f'Bar Chart: {num_cols[0]} by {cat_cols[0]}', fontsize=16, fontweight='bold')
                        chart_explanation = f"This bar chart shows the total {num_cols[0]} for each category of {cat_cols[0]}."
                    else:
                        # Simple bar chart of first two columns
                        sns.barplot(data=df, x=df.columns[0], y=df.columns[1], ax=ax)
                        ax.set_title(f'Bar Chart: {df.columns[1]} by {df.columns[0]}', fontsize=16, fontweight='bold')
                        chart_explanation = f"This bar chart shows {df.columns[1]} values for each {df.columns[0]}."
                else:
                    return JsonResponse({'error': 'Need at least 2 columns for bar chart'}, status=400)
                    
            elif chart_type == 'line':
                if len(df.columns) >= 2:
                    sns.lineplot(data=df, x=df.columns[0], y=df.columns[1], ax=ax, marker='o')
                    ax.set_title(f'Line Chart: {df.columns[1]} vs {df.columns[0]}', fontsize=16, fontweight='bold')
                    chart_explanation = f"This line chart shows the trend of {df.columns[1]} over {df.columns[0]}."
                else:
                    return JsonResponse({'error': 'Need at least 2 columns for line chart'}, status=400)
            
            # Rotate x-axis labels if they're long
            ax.tick_params(axis='x', rotation=45)
            plt.tight_layout()
            
            # Convert plot to base64 string
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            buffer.seek(0)
            plot_data = buffer.getvalue()
            buffer.close()
            plt.close()
            
            # Encode to base64
            plot_url = base64.b64encode(plot_data).decode()
            
            # Generate AI explanation using Groq
            try:
                client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
                
                # Prepare data summary for AI
                data_summary = {
                    'shape': df.shape,
                    'columns': list(df.columns),
                    'numeric_cols': list(df.select_dtypes(include=[np.number]).columns),
                    'categorical_cols': list(df.select_dtypes(include=['object']).columns),
                    'sample_data': df.head(3).to_dict('records')
                }
                
                prompt = f"""
                Analyze this {chart_type} chart and provide insights:
                
                Data Summary:
                - Shape: {data_summary['shape']} (rows, columns)
                - Columns: {data_summary['columns']}
                - Sample data: {data_summary['sample_data']}
                
                Chart Type: {chart_type}
                Basic Description: {chart_explanation}
                
                Please provide:
                1. Key insights from the visualization
                2. Notable patterns or trends
                3. Potential business implications
                4. Any anomalies or interesting observations
                
                Keep the analysis concise but insightful (2-3 paragraphs max).
                """
                
                chat_completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.1-8b-instant",
                    temperature=0.3,
                    max_tokens=500
                )
                
                ai_explanation = chat_completion.choices[0].message.content
                
            except Exception as e:
                ai_explanation = f"Chart generated successfully. {chart_explanation}"
            
            return JsonResponse({
                'success': True,
                'chart_image': f'data:image/png;base64,{plot_url}',
                'explanation': ai_explanation,
                'chart_type': chart_type
            })
            
        except Exception as e:
            return JsonResponse({'error': f'Chart generation failed: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    # Categorical data
    if len(df) <= 10 and len(df.columns) == 2:
        return "pie_chart"
    
    return "bar_chart"