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
from xhtml2pdf import pisa
import json
import pdfkit, io
from pptx import Presentation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io
from supabase import create_client
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

        # Create a unique filename for Supabase (stored name)
        session_key = request.session.session_key or str(int(time.time()))
        timestamp = int(time.time())
        stored_name = f"{session_key}_{timestamp}_{file.name}"
        path_in_bucket = f"sessions/{stored_name}"

        # Keep original name for UI
        display_name = file.name  

        print(f"DEBUG: Uploading file: {stored_name}")

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

            # Store both in session
            TEMP_FILES[request.session.session_key] = path_in_bucket
            request.session["dataset_path"] = path_in_bucket
            request.session["dataset_display_name"] = display_name  

            messages.success(request, f"File uploaded successfully: {display_name}")

            # Redirect using stored name (backend ID), but keep display_name in session
            return redirect(reverse("dataset_preview", args=[stored_name]))

        except Exception as e:
            print(f"❌ Failed to upload to Supabase: {e}")
            messages.error(request, f"Failed to upload: {str(e)}")
            return redirect("index")

    return redirect("index")



def generate_data_profile(df):
    """Generate comprehensive data profile for health checks"""
    profile = {
        'shape': df.shape,
        'columns': [],
        'data_health': {
            'duplicate_rows': df.duplicated().sum(),
            'total_missing': df.isnull().sum().sum(),
            'missing_percentage': (df.isnull().sum().sum() / (df.shape[0] * df.shape[1])) * 100,
            'constant_columns': [],
            'high_cardinality_columns': []
        },
        'column_stats': {}
    }
    
    for col in df.columns:
        col_info = {
            'name': col,
            'dtype': str(df[col].dtype),
            'missing_count': df[col].isnull().sum(),
            'missing_percentage': (df[col].isnull().sum() / len(df)) * 100,
            'unique_count': df[col].nunique(),
            'cardinality_ratio': df[col].nunique() / len(df),
            'sample_values': df[col].dropna().head(3).tolist() if len(df[col].dropna()) > 0 else []
        }
        
        # Check if column is constant
        if col_info['unique_count'] <= 1:
            profile['data_health']['constant_columns'].append(col)
        
        # Check for high cardinality (might be ID columns)
        if col_info['cardinality_ratio'] > 0.9 and col_info['unique_count'] > 10:
            profile['data_health']['high_cardinality_columns'].append(col)
        
        # Type-specific stats
        if df[col].dtype in ['int64', 'float64']:
            col_info.update({
                'min': df[col].min() if not df[col].isnull().all() else None,
                'max': df[col].max() if not df[col].isnull().all() else None,
                'mean': df[col].mean() if not df[col].isnull().all() else None,
                'median': df[col].median() if not df[col].isnull().all() else None,
                'std': df[col].std() if not df[col].isnull().all() else None,
                'has_outliers': detect_outliers(df[col]) if not df[col].isnull().all() else False
            })
        elif df[col].dtype == 'object':
            if not df[col].isnull().all():
                value_counts = df[col].value_counts()
                col_info.update({
                    'top_values': value_counts.head(5).to_dict(),
                    'is_categorical': col_info['unique_count'] < len(df) * 0.5,
                    'avg_length': df[col].astype(str).str.len().mean()
                })
        
        profile['columns'].append(col_info)
        profile['column_stats'][col] = col_info
    
    return profile

def detect_outliers(series):
    """Simple outlier detection using IQR method"""
    try:
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = series[(series < lower_bound) | (series > upper_bound)]
        return len(outliers) > 0
    except:
        return False


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
        Analyze this dataset and provide intelligent, specific insights:
        
        Dataset Summary:
        - Shape: {summary['shape']} (rows, columns)
        - Columns: {summary['columns']}
        - Data types: {summary['dtypes']}
        - Numeric columns: {summary['numeric_cols']}
        - Categorical columns: {summary['categorical_cols']}
        - Sample data: {summary['sample_data']}
        - Missing values: {summary['missing_values']}
        
        Based on the actual column names and data types, provide:
        1. What domain/business context this data represents (be specific, not generic)
        2. 5 SPECIFIC SQL queries using actual column names that would reveal valuable business insights
        3. 3 priority visualizations that make sense for this exact dataset
        4. Avoid generic responses like "dataset uploaded successfully"
        
        Format response as JSON:
        {{
            "context": "Specific description of what this data represents (e.g., 'Sales transaction data with customer demographics and purchase history')",
            "domain": "specific domain (e.g., 'e-commerce', 'healthcare', 'finance')",
            "suggested_queries": [
                "SELECT specific_column, COUNT(*) FROM data GROUP BY specific_column ORDER BY COUNT(*) DESC LIMIT 10",
                "SELECT AVG(specific_numeric_column) FROM data WHERE specific_condition",
                ...use actual column names from the data...
            ],
            "priority_visualizations": [
                {{"type": "bar", "description": "Distribution of [specific column]", "reason": "Shows business-relevant patterns"}},
                {{"type": "scatter", "description": "[specific columns] correlation", "reason": "Reveals relationships between key metrics"}},
                {{"type": "time_series", "description": "Trend over [time column]", "reason": "Shows temporal patterns"}}
            ]
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
        # Create smarter fallback based on actual data
        sample_numeric = [col for col in df.select_dtypes(include=[np.number]).columns[:2]]
        sample_categorical = [col for col in df.select_dtypes(include=['object']).columns[:2]]
        
        fallback_queries = []
        fallback_queries.append(f"SELECT COUNT(*) as total_rows FROM data")
        
        if sample_categorical:
            fallback_queries.append(f"SELECT \"{sample_categorical[0]}\", COUNT(*) as count FROM data GROUP BY \"{sample_categorical[0]}\" ORDER BY count DESC LIMIT 10")
        
        if sample_numeric:
            fallback_queries.append(f"SELECT AVG(\"{sample_numeric[0]}\") as average, MIN(\"{sample_numeric[0]}\") as minimum, MAX(\"{sample_numeric[0]}\") as maximum FROM data")
        
        if len(sample_numeric) >= 2:
            fallback_queries.append(f"SELECT \"{sample_numeric[0]}\", \"{sample_numeric[1]}\" FROM data WHERE \"{sample_numeric[0]}\" IS NOT NULL AND \"{sample_numeric[1]}\" IS NOT NULL LIMIT 100")
        
        fallback_queries.append("SELECT * FROM data LIMIT 20")
        
        return {
            "context": f"Dataset with {df.shape[0]} rows and {df.shape[1]} columns containing {len(sample_numeric)} numeric and {len(sample_categorical)} text columns",
            "domain": "data-analysis", 
            "suggested_queries": fallback_queries[:5],
            "priority_visualizations": [
                {"type": "bar", "description": f"Distribution of {sample_categorical[0] if sample_categorical else 'categories'}", "reason": "Shows data distribution patterns"},
                {"type": "scatter", "description": f"Relationship between {sample_numeric[0] if sample_numeric else 'variables'} and others", "reason": "Reveals correlations"},
                {"type": "histogram", "description": f"Frequency distribution of {sample_numeric[0] if sample_numeric else 'numeric values'}", "reason": "Shows data spread and outliers"}
            ]
        }


def auto_visualize_dataset(request):
    """Generate automatic visualizations for the dataset and save each to session"""
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
                        # Save the visualization to session for report builder
                        save_visualization(
                            request,
                            f"{viz['type'].title()} Chart",
                            chart_data['image'],
                            chart_data['explanation']
                        )
                        charts.append({
                            'type': viz['type'],
                            'description': viz['description'],
                            'reason': viz['reason'],
                            'image': chart_data['image'],
                            'explanation': chart_data['explanation'],
                            'chart_title': f"{viz['type'].title()} Chart"
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
    """Generate automatic Chart.js configuration based on data analysis"""
    try:
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
            
            return {
                'chart_config': {
                    'type': 'bar',
                    'data': {
                        'labels': grouped[cat_col].tolist(),
                        'datasets': [{
                            'label': f'Average {num_col}',
                            'data': grouped[num_col].tolist(),
                            'backgroundColor': '#7059f2ff',
                            'borderColor': '#533cd0ff',
                            'borderWidth': 1
                        }]
                    },
                    'options': {
                        'responsive': True,
                        'plugins': {
                            'title': {
                                'display': True,
                                'text': f'Average {num_col} by {cat_col}'
                            }
                        }
                    }
                },
                'explanation': f'Auto-generated bar chart showing average {num_col} by {cat_col}'
            }
            
        elif chart_type == 'scatter' and len(numeric_cols) >= 2:
            # Scatter plot of two numeric columns
            x_col, y_col = numeric_cols[0], numeric_cols[1]
            
            scatter_data = [{'x': x, 'y': y} for x, y in zip(df[x_col], df[y_col])]
            
            return {
                'chart_config': {
                    'type': 'scatter',
                    'data': {
                        'datasets': [{
                            'label': f'{y_col} vs {x_col}',
                            'data': scatter_data,
                            'backgroundColor': '#7059f2ff',
                            'borderColor': '#533cd0ff'
                        }]
                    },
                    'options': {
                        'responsive': True,
                        'plugins': {
                            'title': {
                                'display': True,
                                'text': f'Relationship: {y_col} vs {x_col}'
                            }
                        },
                        'scales': {
                            'x': {
                                'title': {
                                    'display': True,
                                    'text': x_col
                                }
                            },
                            'y': {
                                'title': {
                                    'display': True,
                                    'text': y_col
                                }
                            }
                        }
                    }
                },
                'explanation': f'Auto-generated scatter plot showing relationship between {x_col} and {y_col}'
            }
            
        else:
            # Fallback: simple histogram as bar chart
            if len(numeric_cols) > 0:
                col = numeric_cols[0]
                bins = pd.cut(df[col].dropna(), bins=10)
                hist_data = df.groupby(bins)[col].count()
                
                return {
                    'chart_config': {
                        'type': 'bar',
                        'data': {
                            'labels': [str(interval) for interval in hist_data.index],
                            'datasets': [{
                                'label': 'Frequency',
                                'data': hist_data.values.tolist(),
                                'backgroundColor': '#7059f2ff',
                                'borderColor': '#533cd0ff',
                                'borderWidth': 1
                            }]
                        },
                        'options': {
                            'responsive': True,
                            'plugins': {
                                'title': {
                                    'display': True,
                                    'text': f'Distribution of {col}'
                                }
                            }
                        }
                    },
                    'explanation': f'Auto-generated histogram showing distribution of {col}'
                }
            else:
                return None
        
    except Exception as e:
        print(f"Auto chart generation error: {e}")
        return None


def dataset_preview(request, dataset_name):
    path_in_bucket = request.session.get("dataset_path")
    display_name = request.session.get("dataset_display_name", dataset_name)  # fallback
    print(f"DEBUG: Preview session dataset_path: {path_in_bucket}")  # DEBUG

    if not path_in_bucket:
        messages.error(request, "No dataset in session.")
        return redirect("index")

    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path_in_bucket)
        df = pd.read_csv(io.BytesIO(res))
        print(f"✅ Loaded dataset from Supabase: {dataset_name}")  # DEBUG

        # Generate comprehensive data profile
        data_profile = generate_data_profile(df)

        # Analyze dataset context and provide suggestions
        analysis = analyze_dataset_context(df)

    except Exception as e:
        df = pd.DataFrame()
        analysis = None
        data_profile = None
        print(f"❌ Failed to load dataset from Supabase: {e}")  # DEBUG
        messages.error(
            request,
            "Dataset not found. It may have been cleaned up or your session expired. Please upload the dataset again."
        )
        return redirect("index")

    context = {
        "dataset": {
            "name": dataset_name,            # internal Supabase name
            "display_name": display_name     # clean original filename
        },
        "columns": df.columns.tolist() if not df.empty else [],
        "preview_rows": df.head(5).values.tolist() if not df.empty else [],
        "analysis": analysis,
        "data_profile": data_profile,
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

        # Get query parameters for pagination
        limit = int(request.GET.get('limit', 1000))
        offset = int(request.GET.get('offset', 0))
        
        # Apply pagination
        total_rows = len(df)
        df_page = df.iloc[offset:offset+limit]

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

        safe_rows = [{col: make_json_safe(row[col]) for col in df_page.columns} for _, row in df_page.iterrows()]

        return JsonResponse({
            "columns": df.columns.tolist(),
            "rows": safe_rows,
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total_rows
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
        auto_limit_added = False
        if not re.search(r'(?is)\blimit\s+\d+\b', sql_query):
            sql_query = sql_query[:-1] + " LIMIT 1000;"
            auto_limit_added = True

        print(f"DEBUG: Generated SQL: {sql_query}")

        # Execute
        try:
            result_df = pd.read_sql_query(sql_query, conn)
        except Exception as e:
            cols = df.columns.tolist()
            return JsonResponse({
                "query": sql_query,
                "result": [],
                "error": f"Query failed: {str(e)}. Available columns: {', '.join(cols)}",
                "auto_limit_added": auto_limit_added
            })

        if result_df.empty:
            return JsonResponse({"query": sql_query, "result": [], "auto_limit_added": auto_limit_added})

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

        # ---- Save to session for report builder ----
        save_query_result(
            request,
            user_input,
            sql_query,
            result_data,
            visualization_suggestion
        )
        # -------------------------------------------

        return JsonResponse({
            "query": sql_query, 
            "result": result_data,
            "visualization_suggestion": visualization_suggestion,
            "auto_limit_added": auto_limit_added,
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



def save_report(request, format):
    body = json.loads(request.body)
    html_content = body.get("html", "")

    if format == "pdf":
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)
        p.drawString(100, 750, html_content)  # Simple text export
        p.showPage()
        p.save()
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=report.pdf'
        return response
        
    elif format == "pptx":
        # Simple PPTX export (basic plain text slide)
        prs = Presentation()
        slide_layout = prs.slide_layouts[5]
        slide = prs.slides.add_slide(slide_layout)
        textbox = slide.shapes.add_textbox(100, 100, 500, 500)
        textbox.text = html_content
        buffer = io.BytesIO()
        prs.save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.presentation.presentation")
        response["Content-Disposition"] = "attachment; filename=report.pptx"
        return response

    elif format in ["jpg", "png"]:
        # Image export using html2image (optional, install html2image if needed)
        from html2image import Html2Image
        hti = Html2Image()
        ext = "png" if format == "png" else "jpg"
        output_path = f"report.{ext}"
        hti.screenshot(html_str=html_content, save_as=output_path)
        with open(output_path, "rb") as f:
            response = HttpResponse(f.read(), content_type=f"image/{ext}")
            response["Content-Disposition"] = f"attachment; filename=report.{ext}"
            return response

    return HttpResponse("Invalid format", status=400)


# ... all your imports ...

def save_chat_message(request, sender, content):
    """Save a chat message (user or assistant) to session."""
    chat_history = request.session.get('chat_history', [])
    chat_history.append({
        'type': 'chat_message',
        'sender': sender,
        'content': content,
        'timestamp': datetime.utcnow().isoformat()
    })
    request.session['chat_history'] = chat_history

def save_visualization(request, chart_title, image_url, explanation):
    """Save a visualization block to session."""
    visualizations = request.session.get('visualizations', [])
    visualizations.append({
        'type': 'visualization',
        'chart_title': chart_title,
        'image_url': image_url,
        'explanation': explanation,
        'timestamp': datetime.utcnow().isoformat()
    })
    request.session['visualizations'] = visualizations

def save_query_result(request, user_input, sql_query, result_data, visualization_suggestion):
    """Save a query history block to session."""
    chat_history = request.session.get('chat_history', [])
    chat_history.append({
        'type': 'query',
        'user_input': user_input,
        'sql_query': sql_query,
        'result_summary': {
            'rows': len(result_data),
            'columns': list(result_data[0].keys()) if result_data else [],
        },
        'visualization_suggestion': visualization_suggestion,
        'timestamp': datetime.utcnow().isoformat()
    })
    request.session['chat_history'] = chat_history



def report_builder(request):
    chat_history = request.session.get("chat_history", [])
    visualizations = request.session.get("visualizations", [])
    tables = request.session.get("tables", [])  # Add this

    # Compose all blocks in order (you may want to save the block order in session)
    blocks = []
    blocks.extend(chat_history)
    blocks.extend(visualizations)
    blocks.extend(tables)
    # Optionally, sort by timestamp or order field

    return render(request, "report_builder.html", {
        "blocks": blocks,
        # pass additional context as needed
    })


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


def chart_builder(request):
    """New Chart.js based chart builder with axis selection"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            print(f"Chart builder action: {action}")  # Debug log
            
            if action == 'get_columns':
                # Return available columns for axis selection
                query_results = data.get('query_results', [])
                columns = data.get('columns', [])
                
                print(f"Query results length: {len(query_results)}")  # Debug log
                print(f"Columns: {columns}")  # Debug log
                
                if not query_results or not columns:
                    return JsonResponse({'error': 'No data provided'}, status=400)
                
                df = pd.DataFrame(query_results, columns=columns)
                
                # Categorize columns
                numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
                categorical_columns = df.select_dtypes(include=['object']).columns.tolist()
                datetime_columns = []
                
                # Try to detect datetime columns
                for col in categorical_columns[:]:  # Use slice to avoid modifying list while iterating
                    try:
                        sample_data = df[col].dropna().iloc[:5]
                        if len(sample_data) > 0:
                            pd.to_datetime(sample_data)
                            datetime_columns.append(col)
                            categorical_columns.remove(col)
                    except:
                        pass
                
                column_info = {
                    'numeric': numeric_columns,
                    'categorical': categorical_columns,
                    'datetime': datetime_columns,
                    'all': columns
                }
                
                print(f"Column info: {column_info}")  # Debug log
                
                return JsonResponse({
                    'success': True,
                    'columns': column_info
                })
            
            elif action == 'generate_chart':
                # Generate Chart.js configuration
                chart_type = data.get('chart_type', 'bar')
                x_axis = data.get('x_axis', [])
                y_axis = data.get('y_axis', [])
                query_results = data.get('query_results', [])
                columns = data.get('columns', [])
                
                if not query_results or not columns:
                    return JsonResponse({'error': 'No data provided'}, status=400)
                
                if not x_axis or not y_axis:
                    return JsonResponse({'error': 'Please select both X and Y axis variables'}, status=400)
                
                df = pd.DataFrame(query_results, columns=columns)
                
                # Generate Chart.js configuration
                chart_config = generate_chartjs_config(df, chart_type, x_axis, y_axis)
                
                return JsonResponse({
                    'success': True,
                    'chart_config': chart_config
                })
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def generate_chartjs_config(df, chart_type, x_axis, y_axis):
    """Generate Chart.js configuration based on selected axes and chart type"""
    
    # Handle multiple X and Y axes
    x_col = x_axis[0] if isinstance(x_axis, list) else x_axis
    y_cols = y_axis if isinstance(y_axis, list) else [y_axis]
    
    # Prepare data based on chart type
    if chart_type in ['bar', 'line']:
        # Group data if needed
        if df[x_col].dtype == 'object':  # Categorical X-axis
            grouped = df.groupby(x_col)[y_cols].agg('mean').reset_index()
            labels = grouped[x_col].tolist()
            
            datasets = []
            colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF']
            
            for i, y_col in enumerate(y_cols):
                datasets.append({
                    'label': y_col,
                    'data': grouped[y_col].tolist(),
                    'backgroundColor': colors[i % len(colors)] if chart_type == 'bar' else 'transparent',
                    'borderColor': colors[i % len(colors)],
                    'borderWidth': 2,
                    'fill': False
                })
        else:  # Numeric X-axis
            labels = df[x_col].tolist()
            datasets = []
            colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
            
            for i, y_col in enumerate(y_cols):
                datasets.append({
                    'label': y_col,
                    'data': df[y_col].tolist(),
                    'backgroundColor': colors[i % len(colors)] if chart_type == 'bar' else 'transparent',
                    'borderColor': colors[i % len(colors)],
                    'borderWidth': 2,
                    'fill': False
                })
    
    elif chart_type == 'scatter':
        datasets = []
        colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
        
        for i, y_col in enumerate(y_cols):
            scatter_data = [{'x': x, 'y': y} for x, y in zip(df[x_col], df[y_col])]
            datasets.append({
                'label': f'{y_col} vs {x_col}',
                'data': scatter_data,
                'backgroundColor': colors[i % len(colors)],
                'borderColor': colors[i % len(colors)],
            })
        labels = []
    
    elif chart_type == 'pie':
        # For pie charts, use first Y column and group by X
        if df[x_col].dtype == 'object':
            grouped = df.groupby(x_col)[y_cols[0]].sum().reset_index()
            labels = grouped[x_col].tolist()
            data = grouped[y_cols[0]].tolist()
        else:
            # If X is numeric, create bins
            df[f'{x_col}_binned'] = pd.cut(df[x_col], bins=5, precision=0)
            grouped = df.groupby(f'{x_col}_binned')[y_cols[0]].sum().reset_index()
            labels = [str(interval) for interval in grouped[f'{x_col}_binned']]
            data = grouped[y_cols[0]].tolist()
        
        datasets = [{
            'data': data,
            'backgroundColor': ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF']
        }]
    
    # Chart.js configuration
    config = {
        'type': chart_type,
        'data': {
            'labels': labels,
            'datasets': datasets
        },
        'options': {
            'responsive': True,
            'maintainAspectRatio': False,
            'scales': {},
            'plugins': {
                'legend': {
                    'display': True,
                    'position': 'top'
                },
                'title': {
                    'display': True,
                    'text': f'{chart_type.title()} Chart: {", ".join(y_cols)} vs {x_col}'
                }
            }
        }
    }
    
    # Add scales for non-pie charts
    if chart_type != 'pie':
        config['options']['scales'] = {
            'x': {
                'display': True,
                'title': {
                    'display': True,
                    'text': x_col
                }
            },
            'y': {
                'display': True,
                'title': {
                    'display': True,
                    'text': ', '.join(y_cols)
                }
            }
        }
    
    return config


def generate_chart(request):
    """Legacy chart generation - redirects to new chart builder"""
    return JsonResponse({'error': 'Please use the new chart builder interface'}, status=400)