import os
import sqlite3
import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
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


def clear_session_data(request):
    """Clear all previous session data when uploading new dataset"""
    keys_to_clear = [
        'chat_history',
        'visualizations', 
        'tables',
        'report_blocks',
        'query_results'
    ]
    
    for key in keys_to_clear:
        if key in request.session:
            del request.session[key]
    
    print("✅ Cleared previous session data for fresh start")

def index(request):
    cleanup_old_files()
    return render(request, "index.html", {"datasets": []})


def dataset_list(request):
    return render(request, "datasets.html", {"datasets": []})


def upload_dataset(request):
    cleanup_old_files()  # delete old session files first

    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]

        # Clear previous session data for clean slate
        clear_session_data(request)

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
        3. 3 SELECTIVE priority visualizations that make sense for this exact dataset (avoid overwhelming charts)
        4. Focus on the most important and insightful visualizations, not everything
        
        For visualizations, prefer:
        - Bar charts for top N categories (not all categories)
        - Scatter plots with meaningful relationships
        - Histograms for key numeric distributions
        - Avoid time series if no clear time column exists
        
        Format response as JSON:
        {{
            "context": "Specific description of what this data represents",
            "domain": "specific domain (e.g., 'e-commerce', 'healthcare', 'finance')",
            "suggested_queries": [
                "SELECT specific_column, COUNT(*) FROM data GROUP BY specific_column ORDER BY COUNT(*) DESC LIMIT 10",
                "SELECT AVG(specific_numeric_column) FROM data WHERE specific_condition"
            ],
            "priority_visualizations": [
                {{"type": "bar", "description": "Top 10 [specific column] distribution", "reason": "Shows most significant patterns"}},
                {{"type": "scatter", "description": "[specific columns] correlation analysis", "reason": "Reveals key relationships"}},
                {{"type": "histogram", "description": "[specific numeric column] distribution", "reason": "Shows data spread for key metric"}}
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
                {"type": "bar", "description": f"Top 10 {sample_categorical[0] if sample_categorical else 'categories'} distribution", "reason": "Shows most significant data patterns"},
                {"type": "scatter", "description": f"Relationship between {sample_numeric[0] if len(sample_numeric) > 0 else 'first'} and {sample_numeric[1] if len(sample_numeric) > 1 else 'second'} variables", "reason": "Reveals correlations between key metrics"} if len(sample_numeric) >= 2 else {"type": "histogram", "description": f"Distribution of {sample_numeric[0] if sample_numeric else 'numeric values'}", "reason": "Shows data spread"},
                {"type": "histogram", "description": f"Frequency distribution of {sample_numeric[0] if sample_numeric else 'values'}", "reason": "Shows data distribution and outliers"}
            ][:3]  # Ensure only 3 visualizations
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
            
            # Validate dataset size for visualization
            if len(df) > 10000:
                # Sample large datasets for analysis
                df_sample = df.sample(n=5000, random_state=42)
                print(f"Large dataset detected ({len(df)} rows). Using sample of 5000 rows for analysis.")
            else:
                df_sample = df
            
            # Get analysis
            analysis = analyze_dataset_context(df_sample)
            
            # Limit to maximum 3 visualizations to avoid overwhelming
            priority_visualizations = analysis.get('priority_visualizations', [])[:3]
            
            # Generate the priority visualizations
            charts = []
            successful_charts = 0
            max_charts = 3
            
            for viz in priority_visualizations:
                if successful_charts >= max_charts:
                    break
                    
                try:
                    chart_data = generate_auto_chart(df_sample, viz['type'], viz['description'])
                    if chart_data:
                        # Save the visualization to session for report builder
                        save_visualization(
                            request,
                            f"{viz['type'].title()} Chart: {viz['description'][:50]}",
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
                        successful_charts += 1
                        print(f"Successfully generated {viz['type']} chart")
                    else:
                        print(f"Failed to generate {viz['type']} chart - no data returned")
                except Exception as e:
                    print(f"Failed to generate {viz['type']} chart: {e}")
                    continue
            
            if not charts:
                return JsonResponse({
                    'error': 'Could not generate any visualizations for this dataset. Please try manual chart creation.',
                    'analysis': analysis
                })
            
            return JsonResponse({
                'success': True,
                'analysis': analysis,
                'charts': charts,
                'message': f'Generated {len(charts)} selective visualizations focusing on key insights.'
            })
            
        except Exception as e:
            return JsonResponse({'error': f'Auto-visualization failed: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Only POST method allowed'}, status=405)

def generate_auto_chart(df, chart_type, description):
    """Generate automatic Chart.js configuration based on data analysis"""
    try:
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        categorical_cols = df.select_dtypes(include=['object']).columns
        
        # Limit data size for better performance and readability
        max_categories = 10
        max_data_points = 100
        
        if chart_type == 'bar' and len(categorical_cols) > 0 and len(numeric_cols) > 0:
            # Bar chart of categorical vs numeric
            cat_col = categorical_cols[0]
            num_col = numeric_cols[0]
            
            # Get top N categories to avoid overcrowding
            top_categories = df[cat_col].value_counts().head(max_categories)
            filtered_df = df[df[cat_col].isin(top_categories.index)]
            
            # Group and aggregate data
            grouped = filtered_df.groupby(cat_col)[num_col].mean().round(2).reset_index()
            
            # Further limit if still too many data points
            if len(grouped) > max_categories:
                grouped = grouped.head(max_categories)
            
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
                                'text': f'Top {len(grouped)} {cat_col} by Average {num_col}'
                            },
                            'legend': {
                                'display': False
                            }
                        },
                        'scales': {
                            'y': {
                                'beginAtZero': True
                            }
                        }
                    }
                },
                'image': generate_chart_image('bar', grouped[cat_col].tolist(), grouped[num_col].tolist(), f'Top {len(grouped)} {cat_col}'),
                'explanation': f'Bar chart showing top {len(grouped)} categories of {cat_col} by average {num_col}. Limited to most significant categories for clarity.'
            }
            
        elif chart_type == 'scatter' and len(numeric_cols) >= 2:
            # Scatter plot of two numeric columns
            x_col, y_col = numeric_cols[0], numeric_cols[1]
            
            # Sample data if too large
            sample_df = df.sample(n=min(max_data_points, len(df))).copy()
            
            # Remove outliers for better visualization
            for col in [x_col, y_col]:
                Q1 = sample_df[col].quantile(0.25)
                Q3 = sample_df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                sample_df = sample_df[(sample_df[col] >= lower_bound) & (sample_df[col] <= upper_bound)]
            
            scatter_data = [{'x': round(x, 2), 'y': round(y, 2)} 
                          for x, y in zip(sample_df[x_col], sample_df[y_col]) 
                          if pd.notna(x) and pd.notna(y)]
            
            return {
                'chart_config': {
                    'type': 'scatter',
                    'data': {
                        'datasets': [{
                            'label': f'{y_col} vs {x_col}',
                            'data': scatter_data,
                            'backgroundColor': '#7059f2ff',
                            'borderColor': '#533cd0ff',
                            'pointRadius': 4
                        }]
                    },
                    'options': {
                        'responsive': True,
                        'plugins': {
                            'title': {
                                'display': True,
                                'text': f'{y_col} vs {x_col} Relationship'
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
                'image': generate_chart_image('scatter', [d['x'] for d in scatter_data], [d['y'] for d in scatter_data], f'{y_col} vs {x_col}'),
                'explanation': f'Scatter plot showing relationship between {x_col} and {y_col}. Sample of {len(scatter_data)} data points, outliers removed for clarity.'
            }
            
        elif chart_type in ['histogram', 'line'] and len(numeric_cols) > 0:
            # Histogram for numeric distribution
            num_col = numeric_cols[0]
            
            # Remove outliers and create bins
            data_series = df[num_col].dropna()
            Q1 = data_series.quantile(0.25)
            Q3 = data_series.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            filtered_data = data_series[(data_series >= lower_bound) & (data_series <= upper_bound)]
            
            # Create histogram bins
            bins = 15  # Reasonable number of bins
            hist, bin_edges = np.histogram(filtered_data, bins=bins)
            bin_centers = [(bin_edges[i] + bin_edges[i+1]) / 2 for i in range(len(bin_edges)-1)]
            
            return {
                'chart_config': {
                    'type': 'bar',
                    'data': {
                        'labels': [f'{round(bc, 2)}' for bc in bin_centers],
                        'datasets': [{
                            'label': f'Frequency',
                            'data': hist.tolist(),
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
                                'text': f'Distribution of {num_col}'
                            },
                            'legend': {
                                'display': False
                            }
                        },
                        'scales': {
                            'x': {
                                'title': {
                                    'display': True,
                                    'text': num_col
                                }
                            },
                            'y': {
                                'title': {
                                    'display': True,
                                    'text': 'Frequency'
                                },
                                'beginAtZero': True
                            }
                        }
                    }
                },
                'image': generate_chart_image('histogram', bin_centers, hist.tolist(), f'Distribution of {num_col}'),
                'explanation': f'Histogram showing the distribution of {num_col}. Outliers removed and data grouped into {bins} bins for better readability.'
            }
            
        elif chart_type == 'pie' and len(categorical_cols) > 0:
            # Pie chart for categorical distribution
            cat_col = categorical_cols[0]
            
            # Get top categories only
            value_counts = df[cat_col].value_counts().head(8)  # Max 8 slices for readability
            
            # Group small categories as "Others"
            if len(value_counts) < df[cat_col].nunique():
                others_count = df[cat_col].value_counts().iloc[8:].sum()
                if others_count > 0:
                    value_counts['Others'] = others_count
            
            return {
                'chart_config': {
                    'type': 'pie',
                    'data': {
                        'labels': value_counts.index.tolist(),
                        'datasets': [{
                            'data': value_counts.values.tolist(),
                            'backgroundColor': [
                                '#7059f2ff', '#533cd0ff', '#3b82f6', '#10b981', 
                                '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'
                            ]
                        }]
                    },
                    'options': {
                        'responsive': True,
                        'plugins': {
                            'title': {
                                'display': True,
                                'text': f'Distribution of {cat_col}'
                            },
                            'legend': {
                                'position': 'right'
                            }
                        }
                    }
                },
                'image': generate_chart_image('pie', value_counts.index.tolist(), value_counts.values.tolist(), f'Distribution of {cat_col}'),
                'explanation': f'Pie chart showing distribution of {cat_col}. Limited to top {len(value_counts)} categories for clarity.'
            }
        
        return None
        
    except Exception as e:
        print(f"Error generating auto chart: {e}")
        return None


def generate_chart_image(chart_type, x_data, y_data, title):
    """Generate a simple base64 encoded chart image using matplotlib"""
    try:
        import matplotlib.pyplot as plt
        import base64
        from io import BytesIO
        
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(8, 6))
        
        if chart_type == 'bar':
            ax.bar(range(len(x_data)), y_data, color='#7059f2')
            ax.set_xticks(range(len(x_data)))
            ax.set_xticklabels(x_data, rotation=45, ha='right')
        elif chart_type == 'scatter':
            ax.scatter(x_data, y_data, color='#7059f2', alpha=0.6)
        elif chart_type == 'histogram':
            ax.bar(range(len(x_data)), y_data, color='#7059f2')
            ax.set_xticks(range(len(x_data)))
            ax.set_xticklabels([f'{x:.1f}' for x in x_data], rotation=45, ha='right')
        elif chart_type == 'pie':
            ax.pie(y_data, labels=x_data, autopct='%1.1f%%', startangle=90)
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        # Convert to base64
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
        
    except Exception as e:
        print(f"Error generating chart image: {e}")
        return ""


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
        # Save the user query as a chat message
        save_chat_message(request, "User", user_input)
        
        # Save the AI response (SQL + results summary)
        ai_response = f"Generated SQL Query:\n```sql\n{sql_query}\n```\n\nFound {len(result_data)} results."
        save_chat_message(request, "AI Assistant", ai_response)
        
        # Save the detailed query result
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



def save_report_blocks(request):
    """Save edited report blocks back to session"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            blocks = data.get('blocks', [])
            request.session['report_blocks'] = blocks
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'})


def save_report(request, format):
    """Enhanced report generation with complete chat history and figures"""
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            blocks = data.get("blocks", [])
            
            # If no blocks provided, get from session
            if not blocks:
                blocks = request.session.get('report_blocks', [])
            
        else:
            # GET request - use session data
            blocks = request.session.get('report_blocks', [])
        
        if format == "pdf":
            return generate_comprehensive_pdf(blocks)
        elif format == "pptx":
            return generate_comprehensive_pptx(blocks)
        elif format in ["jpg", "png"]:
            return generate_report_image(blocks, format)
            
    except Exception as e:
        return JsonResponse({'error': f'Report generation failed: {str(e)}'}, status=500)
    
    return HttpResponse("Invalid format", status=400)


def generate_comprehensive_pdf(blocks):
    """Generate a comprehensive PDF with chat history, figures, and styling"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        import tempfile
        import requests
    except ImportError as e:
        # Fallback to simple PDF generation if reportlab is not available
        print(f"ReportLab not available: {e}")
        return generate_simple_pdf(blocks)
    
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=50, leftMargin=50, 
                              topMargin=50, bottomMargin=50)
        
        # Create styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2E86AB'),
            alignment=1  # Center alignment
        )
        
        user_style = ParagraphStyle(
            'UserMessage',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=10,
            leftIndent=20,
            textColor=colors.HexColor('#1E3A8A'),
            backColor=colors.HexColor('#EBF8FF')
        )
        
        ai_style = ParagraphStyle(
            'AIMessage',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=10,
            leftIndent=20,
            textColor=colors.HexColor('#059669'),
            backColor=colors.HexColor('#ECFDF5')
        )
        
        code_style = ParagraphStyle(
            'CodeBlock',
            parent=styles['Code'],
            fontSize=10,
            leftIndent=30,
            backColor=colors.HexColor('#F3F4F6'),
            textColor=colors.HexColor('#374151')
        )
        
        story = []
        
        # Add title
        story.append(Paragraph("Data Analysis Report", title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))
        story.append(Spacer(1, 30))
        
        # Process blocks
        for i, block in enumerate(blocks):
            block_type = block.get('type', '')
            
            if block_type == 'chat_message':
                sender = block.get('sender', 'User')
                content = block.get('content', '')
                
                if sender.lower() == 'user':
                    story.append(Paragraph(f"<b>User Question:</b>", user_style))
                    story.append(Paragraph(content, user_style))
                else:
                    story.append(Paragraph(f"<b>AI Response:</b>", ai_style))
                    story.append(Paragraph(content, ai_style))
                
                story.append(Spacer(1, 15))
                
            elif block_type == 'query':
                user_input = block.get('user_input', '')
                sql_query = block.get('sql_query', '')
                
                story.append(Paragraph(f"<b>Query Request:</b>", user_style))
                story.append(Paragraph(user_input, user_style))
                story.append(Spacer(1, 10))
                
                story.append(Paragraph(f"<b>Generated SQL:</b>", code_style))
                story.append(Paragraph(f"<font name='Courier'>{sql_query}</font>", code_style))
                story.append(Spacer(1, 15))
                
            elif block_type == 'visualization':
                chart_title = block.get('chart_title', 'Chart')
                image_url = block.get('image_url', '')
                explanation = block.get('explanation', '')
                
                story.append(Paragraph(f"<b>Visualization: {chart_title}</b>", styles['Heading3']))
                
                # Handle base64 images
                if image_url and image_url.startswith('data:'):
                    try:
                        header, encoded = image_url.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                            tmp_file.write(image_data)
                            tmp_file_path = tmp_file.name
                        
                        img = Image(tmp_file_path, width=5*inch, height=3*inch)
                        story.append(img)
                        
                        # Clean up temp file
                        import os
                        os.unlink(tmp_file_path)
                    except Exception as e:
                        story.append(Paragraph(f"[Image could not be loaded: {str(e)}]", styles['Normal']))
                
                if explanation:
                    story.append(Spacer(1, 10))
                    story.append(Paragraph(explanation, styles['Normal']))
                
                story.append(Spacer(1, 20))
                
            elif block_type == 'text':
                content = block.get('content', '')
                story.append(Paragraph(content, styles['Normal']))
                story.append(Spacer(1, 15))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=data_analysis_report.pdf'
        return response
        
    except Exception as e:
        print(f"Advanced PDF generation failed: {e}")
        return generate_simple_pdf(blocks)


def generate_simple_pdf(blocks):
    """Simple PDF generation fallback when reportlab is not available"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        # Final fallback - return HTML
        return generate_html_fallback(blocks)
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    y_position = height - 50
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y_position, "Data Analysis Report")
    y_position -= 30
    
    p.setFont("Helvetica", 10)
    p.drawString(50, y_position, f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    y_position -= 40
    
    p.setFont("Helvetica", 10)
    
    for block in blocks:
        if y_position < 100:  # Start new page
            p.showPage()
            y_position = height - 50
        
        block_type = block.get('type', '')
        
        if block_type == 'chat_message':
            sender = block.get('sender', 'User')
            content = block.get('content', '')[:100]  # Truncate for simple PDF
            
            p.setFont("Helvetica-Bold", 10)
            p.drawString(50, y_position, f"{sender}:")
            y_position -= 15
            
            p.setFont("Helvetica", 9)
            p.drawString(70, y_position, content)
            y_position -= 25
            
        elif block_type == 'visualization':
            chart_title = block.get('chart_title', 'Chart')
            explanation = block.get('explanation', '')[:80]  # Truncate
            
            p.setFont("Helvetica-Bold", 10)
            p.drawString(50, y_position, f"Chart: {chart_title}")
            y_position -= 15
            
            if explanation:
                p.setFont("Helvetica", 9)
                p.drawString(70, y_position, explanation)
                y_position -= 25
    
    p.save()
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=simple_report.pdf'
    return response


def generate_html_fallback(blocks):
    """HTML fallback when PDF generation is not possible"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Data Analysis Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; }}
            .user-message {{ background: #e3f2fd; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .ai-message {{ background: #e8f5e8; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .chart {{ text-align: center; margin: 20px 0; }}
            .chart img {{ max-width: 100%; }}
            h1 {{ color: #333; text-align: center; }}
        </style>
    </head>
    <body>
        <h1>Data Analysis Report</h1>
        <p><strong>Generated on:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    """
    
    for block in blocks:
        block_type = block.get('type', '')
        
        if block_type == 'chat_message':
            sender = block.get('sender', 'User')
            content = block.get('content', '')
            css_class = 'user-message' if sender.lower() == 'user' else 'ai-message'
            html_content += f'<div class="{css_class}"><strong>{sender}:</strong> {content}</div>'
            
        elif block_type == 'visualization':
            chart_title = block.get('chart_title', 'Chart')
            image_url = block.get('image_url', '')
            explanation = block.get('explanation', '')
            
            html_content += f'<div class="chart"><h3>{chart_title}</h3>'
            if image_url:
                html_content += f'<img src="{image_url}" alt="{chart_title}">'
            if explanation:
                html_content += f'<p>{explanation}</p>'
            html_content += '</div>'
    
    html_content += """
    </body>
    </html>
    """
    
    response = HttpResponse(html_content, content_type='text/html')
    response['Content-Disposition'] = 'attachment; filename=report.html'
    return response
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    import tempfile
    import requests
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=50, leftMargin=50, 
                          topMargin=50, bottomMargin=50)
    
    # Create styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#2E86AB'),
        alignment=1  # Center alignment
    )
    
    user_style = ParagraphStyle(
        'UserMessage',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        leftIndent=20,
        textColor=colors.HexColor('#1E3A8A'),
        backColor=colors.HexColor('#EBF8FF')
    )
    
    ai_style = ParagraphStyle(
        'AIMessage',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        leftIndent=20,
        textColor=colors.HexColor('#059669'),
        backColor=colors.HexColor('#ECFDF5')
    )
    
    code_style = ParagraphStyle(
        'CodeBlock',
        parent=styles['Code'],
        fontSize=10,
        leftIndent=30,
        backColor=colors.HexColor('#F3F4F6'),
        textColor=colors.HexColor('#374151')
    )
    
    story = []
    
    # Add title
    story.append(Paragraph("Data Analysis Report", title_style))
    story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))
    story.append(Spacer(1, 30))
    
    # Process blocks
    for i, block in enumerate(blocks):
        block_type = block.get('type', '')
        
        if block_type == 'chat_message':
            sender = block.get('sender', 'User')
            content = block.get('content', '')
            
            if sender.lower() == 'user':
                story.append(Paragraph(f"<b>User Question:</b>", user_style))
                story.append(Paragraph(content, user_style))
            else:
                story.append(Paragraph(f"<b>AI Response:</b>", ai_style))
                story.append(Paragraph(content, ai_style))
            
            story.append(Spacer(1, 15))
            
        elif block_type == 'query':
            user_input = block.get('user_input', '')
            sql_query = block.get('sql_query', '')
            
            story.append(Paragraph(f"<b>Query Request:</b>", user_style))
            story.append(Paragraph(user_input, user_style))
            story.append(Spacer(1, 10))
            
            story.append(Paragraph(f"<b>Generated SQL:</b>", code_style))
            story.append(Paragraph(f"<font name='Courier'>{sql_query}</font>", code_style))
            story.append(Spacer(1, 15))
            
        elif block_type == 'visualization':
            chart_title = block.get('chart_title', 'Chart')
            image_url = block.get('image_url', '')
            explanation = block.get('explanation', '')
            
            story.append(Paragraph(f"<b>Visualization: {chart_title}</b>", styles['Heading3']))
            
            # Download and add image
            if image_url and (image_url.startswith('http') or image_url.startswith('data:')):
                try:
                    if image_url.startswith('data:'):
                        # Handle base64 images
                        header, encoded = image_url.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                            tmp_file.write(image_data)
                            tmp_file_path = tmp_file.name
                        
                        img = Image(tmp_file_path, width=5*inch, height=3*inch)
                        story.append(img)
                        
                        # Clean up temp file
                        import os
                        os.unlink(tmp_file_path)
                    else:
                        # Handle URL images
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                                tmp_file.write(response.content)
                                tmp_file_path = tmp_file.name
                            
                            img = Image(tmp_file_path, width=5*inch, height=3*inch)
                            story.append(img)
                            
                            # Clean up temp file
                            import os
                            os.unlink(tmp_file_path)
                except Exception as e:
                    story.append(Paragraph(f"[Image could not be loaded: {str(e)}]", styles['Normal']))
            
            if explanation:
                story.append(Spacer(1, 10))
                story.append(Paragraph(explanation, styles['Normal']))
            
            story.append(Spacer(1, 20))
            
        elif block_type == 'text':
            content = block.get('content', '')
            story.append(Paragraph(content, styles['Normal']))
            story.append(Spacer(1, 15))
            
        elif block_type == 'table':
            # Handle table data if present
            table_data = block.get('data', [])
            if table_data:
                # Convert to reportlab table
                table = Table(table_data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                story.append(table)
                story.append(Spacer(1, 20))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=data_analysis_report.pdf'
    return response


def generate_comprehensive_pptx(blocks):
    """Generate comprehensive PowerPoint with chat history and figures"""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE
    import tempfile
    import requests
    
    prs = Presentation()
    
    # Title slide
    slide_layout = prs.slide_layouts[0]  # Title slide
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]
    
    title.text = "Data Analysis Report"
    subtitle.text = f"Generated on {datetime.now().strftime('%B %d, %Y')}"
    
    current_slide = None
    slide_content = []
    
    for block in blocks:
        block_type = block.get('type', '')
        
        if block_type == 'visualization':
            # Create new slide for each visualization
            slide_layout = prs.slide_layouts[5]  # Blank slide
            slide = prs.slides.add_slide(slide_layout)
            
            # Add title
            title_shape = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
            title_frame = title_shape.text_frame
            title_frame.text = block.get('chart_title', 'Visualization')
            title_frame.paragraphs[0].font.size = Pt(24)
            title_frame.paragraphs[0].font.bold = True
            
            # Add image
            image_url = block.get('image_url', '')
            if image_url:
                try:
                    if image_url.startswith('data:'):
                        # Handle base64 images
                        header, encoded = image_url.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                            tmp_file.write(image_data)
                            tmp_file_path = tmp_file.name
                        
                        slide.shapes.add_picture(tmp_file_path, Inches(1), Inches(2), Inches(8), Inches(5))
                        
                        # Clean up
                        import os
                        os.unlink(tmp_file_path)
                    else:
                        # Handle URL images
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                                tmp_file.write(response.content)
                                tmp_file_path = tmp_file.name
                            
                            slide.shapes.add_picture(tmp_file_path, Inches(1), Inches(2), Inches(8), Inches(5))
                            
                            # Clean up
                            import os
                            os.unlink(tmp_file_path)
                except Exception as e:
                    # Add error text
                    error_shape = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(2))
                    error_frame = error_shape.text_frame
                    error_frame.text = f"Image could not be loaded: {str(e)}"
            
            # Add explanation
            explanation = block.get('explanation', '')
            if explanation:
                exp_shape = slide.shapes.add_textbox(Inches(0.5), Inches(7.5), Inches(9), Inches(1))
                exp_frame = exp_shape.text_frame
                exp_frame.text = explanation
        
        elif block_type in ['chat_message', 'query', 'text']:
            # Accumulate text content for text slides
            if block_type == 'chat_message':
                sender = block.get('sender', 'User')
                content = block.get('content', '')
                slide_content.append(f"{sender}: {content}")
            elif block_type == 'query':
                user_input = block.get('user_input', '')
                sql_query = block.get('sql_query', '')
                slide_content.append(f"Query: {user_input}")
                slide_content.append(f"SQL: {sql_query}")
            elif block_type == 'text':
                content = block.get('content', '')
                slide_content.append(content)
    
    # Add accumulated text content to a summary slide
    if slide_content:
        slide_layout = prs.slide_layouts[1]  # Title and content
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        content_placeholder = slide.placeholders[1]
        
        title.text = "Analysis Summary"
        content_text = '\n\n'.join(slide_content[:10])  # Limit content
        content_placeholder.text = content_text
    
    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), 
                          content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    response["Content-Disposition"] = "attachment; filename=data_analysis_report.pptx"
    return response


def clear_session_data_endpoint(request):
    """Endpoint to manually clear session data"""
    if request.method == 'POST':
        clear_session_data(request)
        return JsonResponse({'status': 'success', 'message': 'Session data cleared'})
    return JsonResponse({'status': 'error', 'message': 'POST request required'})


def get_available_charts(request):
    """Get all available charts/visualizations from session"""
    try:
        visualizations = request.session.get('visualizations', [])
        charts = []
        
        for i, viz in enumerate(visualizations):
            charts.append({
                'id': i,
                'title': viz.get('chart_title', f'Chart {i+1}'),
                'image_url': viz.get('image_url', ''),
                'explanation': viz.get('explanation', ''),
                'timestamp': viz.get('timestamp', '')
            })
        
        return JsonResponse({'status': 'success', 'charts': charts})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


def generate_report_image(blocks, format_type):
    """Generate report as image using HTML to image conversion"""
    # This is a simplified version - you might want to use libraries like wkhtmltopdf or playwright
    html_content = "<html><head><style>body{font-family:Arial;padding:20px;}</style></head><body>"
    
    for block in blocks:
        block_type = block.get('type', '')
        
        if block_type == 'chat_message':
            sender = block.get('sender', 'User')
            content = block.get('content', '')
            html_content += f"<div style='margin:10px 0;'><b>{sender}:</b> {content}</div>"
        elif block_type == 'visualization':
            title = block.get('chart_title', '')
            image_url = block.get('image_url', '')
            html_content += f"<div style='margin:20px 0;'><h3>{title}</h3>"
            if image_url:
                html_content += f"<img src='{image_url}' style='max-width:100%;'/>"
            html_content += "</div>"
        elif block_type == 'text':
            content = block.get('content', '')
            html_content += f"<div style='margin:10px 0;'>{content}</div>"
    
    html_content += "</body></html>"
    
    # For now, return as HTML - you can implement proper image conversion
    response = HttpResponse(html_content, content_type='text/html')
    return response


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
    """Enhanced report builder with complete chat history and editing capabilities"""
    # Get all session data
    chat_history = request.session.get("chat_history", [])
    visualizations = request.session.get("visualizations", [])
    tables = request.session.get("tables", [])
    
    # Check if user has custom report blocks, otherwise build from session data
    report_blocks = request.session.get('report_blocks', [])
    
    if not report_blocks:
        # Build initial report blocks from session data
        blocks = []
        
        # Combine and sort all blocks by timestamp if available
        all_items = []
        
        # Add chat messages
        for item in chat_history:
            if 'timestamp' in item:
                all_items.append(item)
            else:
                item['timestamp'] = datetime.utcnow().isoformat()
                all_items.append(item)
        
        # Add visualizations  
        for item in visualizations:
            if 'timestamp' in item:
                all_items.append(item)
            else:
                item['timestamp'] = datetime.utcnow().isoformat()
                all_items.append(item)
        
        # Add tables
        for item in tables:
            if 'timestamp' in item:
                all_items.append(item)
            else:
                item['timestamp'] = datetime.utcnow().isoformat()
                all_items.append(item)
        
        # Sort by timestamp
        try:
            all_items.sort(key=lambda x: x.get('timestamp', ''))
        except:
            pass  # If timestamp sorting fails, keep original order
        
        # Save to session
        request.session['report_blocks'] = all_items
        blocks = all_items
    else:
        blocks = report_blocks
    
    # Get dataset info for context
    dataset_display_name = request.session.get("dataset_display_name", "Dataset")
    
    return render(request, "enhanced_report_builder.html", {
        "blocks": blocks,
        "dataset_name": dataset_display_name,
        "total_blocks": len(blocks),
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


def generate_plotly_config(df, chart_type, x_axis, y_axis):
    """
    Generate Plotly.js configuration as a JSON object based on selected axes and chart type.
    """
    # Handle multiple X and Y axes
    x_col = x_axis[0] if isinstance(x_axis, list) else x_axis
    y_cols = y_axis if isinstance(y_axis, list) else [y_axis]

    fig = go.Figure()

    if chart_type == 'bar':
        # Group data for bar chart if x-axis is categorical
        if df[x_col].dtype == 'object':
            grouped_df = df.groupby(x_col)[y_cols].mean().reset_index()
            for y_col in y_cols:
                fig.add_trace(go.Bar(x=grouped_df[x_col], y=grouped_df[y_col], name=y_col))
        else:
            for y_col in y_cols:
                fig.add_trace(go.Bar(x=df[x_col], y=df[y_col], name=y_col))
        
        fig.update_layout(title=f'Bar Chart: {", ".join(y_cols)} vs {x_col}', xaxis_title=x_col, yaxis_title=", ".join(y_cols))
        
    elif chart_type == 'line':
        for y_col in y_cols:
            fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='lines+markers', name=y_col))
        
        fig.update_layout(title=f'Line Chart: {", ".join(y_cols)} vs {x_col}', xaxis_title=x_col, yaxis_title=", ".join(y_cols))
        
    elif chart_type == 'scatter':
        for y_col in y_cols:
            fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='markers', name=y_col))
        
        fig.update_layout(title=f'Scatter Plot: {", ".join(y_cols)} vs {x_col}', xaxis_title=x_col, yaxis_title=", ".join(y_cols))
        
    elif chart_type == 'pie':
        # Plotly.py supports pie charts natively
        if df[x_col].dtype == 'object':
            grouped = df.groupby(x_col)[y_cols[0]].sum().reset_index()
            fig = px.pie(grouped, values=y_cols[0], names=x_col, title=f'Pie Chart: {y_cols[0]} by {x_col}')
        else:
            # For numeric x-axis, create bins and then plot
            df[f'{x_col}_binned'] = pd.cut(df[x_col], bins=5, precision=0)
            grouped = df.groupby(f'{x_col}_binned')[y_cols[0]].sum().reset_index()
            grouped[f'{x_col}_binned'] = grouped[f'{x_col}_binned'].astype(str)
            fig = px.pie(grouped, values=y_cols[0], names=f'{x_col}_binned', title=f'Pie Chart: {y_cols[0]} by {x_col}')

    elif chart_type == 'heatmap':
        # Heatmaps require a Z-axis, usually derived from a pivot table
        # We'll assume y_cols has the row and column names, and a value column
        if len(y_cols) < 2:
            return {'error': 'Heatmap requires at least two Y-axis columns and a value column.'}
        
        # We need three columns: x, y, and z (value)
        z_col = y_cols[0]
        y_col_heatmap = y_cols[1]
        
        fig = go.Figure(data=go.Heatmap(
                z=df[z_col],
                x=df[x_col],
                y=df[y_col_heatmap],
                colorscale='Viridis'))
        
        fig.update_layout(
            title=f'Heatmap: {z_col} vs {x_col} and {y_col_heatmap}',
            xaxis_title=x_col,
            yaxis_title=y_col_heatmap)
            
    elif chart_type == 'bubble':
        # Bubble charts require a size parameter, which we'll assume is the second y-column
        if len(y_cols) < 2:
            return {'error': 'Bubble chart requires at least two Y-axis columns for value and size.'}
        
        fig = go.Figure(data=[go.Scatter(
            x=df[x_col],
            y=df[y_cols[0]],
            mode='markers',
            marker=dict(
                size=df[y_cols[1]], # Use the second y-column for bubble size
                sizemode='area',
                sizeref=2.*max(df[y_cols[1]])/(40.**2), # Adjust sizing
                sizemin=4
            )
        )])
        
        fig.update_layout(title=f'Bubble Chart: {y_cols[0]} vs {x_col} (Size by {y_cols[1]})',
                          xaxis_title=x_col,
                          yaxis_title=y_cols[0])

    else:
        return {'error': 'Unsupported chart type'}
    
    # Convert the figure to a JSON serializable object
    return json.loads(fig.to_json())