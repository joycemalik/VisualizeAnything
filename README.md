# VisualizeAnything 🚀

A comprehensive Django-based data analysis and visualization platform that combines AI-powered natural language processing with advanced data visualization capabilities. Upload datasets, query them with natural language, create interactive visualizations, and generate professional reports—all in one integrated platform.

## ✨ Key Features

### 📊 Data Management
- **Multi-Dataset Support**: Upload and manage multiple datasets simultaneously (CSV, XLSX, JSON)
- **Dataset Merging**: Combine multiple datasets with flexible join operations (inner, outer, left, right)
- **Cloud Storage**: Secure file storage with Supabase integration
- **Online Dataset Search**: AI-powered search engine to find and import public datasets from GitHub and data repositories
- **Smart Session Management**: Automatic cleanup of temporary files and session data

### 🤖 AI-Powered Analysis
- **Natural Language Queries**: Convert plain English questions to SQL using Groq AI (Llama 3.1)
- **Voice Transcription**: Speak your queries using Groq Whisper API for audio-to-text conversion
- **Multi-Dataset Queries**: Query across multiple datasets using natural language
- **Intelligent Data Analysis**: AI generates insights, trends, and recommendations from your data

### 📈 Advanced Visualizations
- **Auto-Visualization**: AI automatically generates relevant charts based on data characteristics
- **Interactive Chart Builder**: Create custom visualizations with:
  - Line charts, Bar charts, Pie charts, Scatter plots
  - Heatmaps, Box plots, Violin plots
  - 3D Surface plots, Contour plots
  - Radar charts, Waterfall charts, Sunburst diagrams
  - And many more chart types powered by Plotly
- **Advanced Visualization Builder**: Comprehensive chart creation with filtering, grouping, and aggregations
- **Real-time Preview**: See chart updates instantly as you configure options

### 📑 Report Generation
- **Enhanced Report Builder**: Create professional reports with drag-and-drop interface
- **Rich Text Editor**: Add formatted text blocks with Quill.js
- **Visual Report Elements**: Combine charts, tables, insights, and custom text
- **Export Formats**: Generate reports in multiple formats:
  - PDF (high-quality professional reports)
  - PowerPoint (PPTX presentations)
  - Excel (XLSX with data tables)
  - JSON (structured data export)
- **Sortable Blocks**: Rearrange report elements with intuitive drag-and-drop

### 🎨 User Experience
- **Modern Dark Theme**: Professional UI with smooth animations
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **Interactive Data Preview**: Explore full datasets with sorting and pagination
- **Chat History**: Track all your queries and AI responses
- **Session Persistence**: Maintain work across browser sessions

## 🛠️ Tech Stack

### Backend
- **Framework**: Django 5.2.5
- **AI & ML**: 
  - Groq API (Llama 3.1 for NLP, Whisper for speech)
  - Natural Language to SQL conversion
- **Data Processing**: 
  - Pandas 2.3.1 (data manipulation)
  - NumPy 2.3.2 (numerical computing)
  - DuckDB 1.3.2 (SQL queries on DataFrames)
- **Visualization**: 
  - Plotly 6.3.0 (interactive charts)
  - Matplotlib 3.10.6 (static visualizations)
  - Seaborn 0.13.0 (statistical graphics)

### Storage & Database
- **Cloud Storage**: Supabase (file storage and management)
- **Database**: SQLite (development), PostgreSQL (production-ready)
- **Session Management**: Django sessions with custom cleanup

### Document Generation
- **PDF**: ReportLab 4.4.3, xhtml2pdf 0.2.17, pdfkit
- **PowerPoint**: python-pptx 1.0.2
- **Excel**: XlsxWriter 3.2.5

### Frontend
- **UI Framework**: Bootstrap 5.3.2
- **Rich Text**: Quill.js editor
- **Icons**: Font Awesome 6.4.0
- **Drag & Drop**: SortableJS 1.15.0
- **Charts**: Chart.js, Plotly.js

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Git
- Groq API account (free tier available)
- Supabase account (free tier available)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/VisualizeAnything.git
   cd VisualizeAnything
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   # Django Configuration
   SECRET_KEY=your-django-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   
   # Groq AI Configuration
   GROQ_API_KEY=your-groq-api-key-here
   
   # Supabase Configuration
   SUPABASE_URL=your-supabase-project-url
   SUPABASE_KEY=your-supabase-anon-key
   SUPABASE_SERVICE_KEY=your-supabase-service-role-key
   SUPABASE_BUCKET=datasets
   ```
   
   **Get your API keys:**
   - Groq API: [console.groq.com](https://console.groq.com/) (Free tier: 30 requests/minute)
   - Supabase: [supabase.com/dashboard](https://supabase.com/dashboard) (Create a new project)

5. **Create Supabase storage bucket**
   
   In your Supabase dashboard:
   - Go to Storage
   - Create a new bucket named `datasets`
   - Set it to private (authenticated access)

6. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

7. **Create a superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

8. **Start the development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   
   Open your browser and navigate to: `http://127.0.0.1:8000/`

## 📖 Usage Guide

### Getting Started

1. **Upload Your First Dataset**
   - Click "Upload Dataset" on the home page
   - Select one or more CSV, XLSX, or JSON files
   - Or search for public datasets using the AI-powered search

2. **Explore Your Data**
   - View dataset preview with column information
   - See data types, statistics, and sample values
   - Switch between multiple datasets easily

3. **Query with Natural Language**
   
   Simply type questions like:
   ```
   "Show me the top 10 customers by revenue"
   "What's the average age by department?"
   "Find all products with price > 100"
   "Calculate monthly sales trends"
   ```
   
   Or use voice input by clicking the microphone button!

4. **Create Visualizations**
   
   - **Auto-Generate**: Click "Auto Visualize" for AI-recommended charts
   - **Chart Builder**: Manually create custom visualizations
   - **Advanced Builder**: Fine-tune with filters, grouping, and aggregations

5. **Build Reports**
   
   - Navigate to Report Builder
   - Add text blocks with rich formatting
   - Insert charts and tables from your analysis
   - Rearrange elements by dragging
   - Export as PDF, PowerPoint, or Excel

### Advanced Features

#### Multi-Dataset Operations

```
1. Upload multiple related datasets
2. Use the merge tool to combine them
3. Query across datasets: "Compare sales between dataset1 and dataset2"
```

#### Voice Queries

```
1. Click the microphone icon
2. Speak your question clearly
3. The AI transcribes and executes your query
```

#### Custom Visualizations

```
1. Select chart type (30+ options)
2. Choose X and Y axes
3. Apply filters and grouping
4. Customize colors and styling
5. Save to report or download
```
## 📂 Project Structure

```
VisualizeAnything/
├── core/                          # Django project settings
│   ├── settings.py               # Main configuration
│   ├── urls.py                   # Root URL routing
│   └── wsgi.py                   # WSGI config
│
├── studio/                        # Main application
│   ├── views.py                  # Core business logic (5000+ lines)
│   ├── models.py                 # Database models
│   ├── urls.py                   # App URL patterns
│   ├── forms.py                  # Form definitions
│   ├── middleware.py             # Custom middleware
│   ├── utils.py                  # Helper functions
│   │
│   ├── templates/                # HTML templates
│   │   ├── index.html                           # Home/upload page
│   │   ├── multi_dataset_preview.html           # Dataset explorer
│   │   ├── enhanced_report_builder.html         # Report builder
│   │   ├── advanced_visualization_builder_new.html  # Chart builder
│   │   └── session_debug.html                   # Debug utilities
│   │
│   ├── templatetags/             # Custom template filters
│   │   └── report_tags.py
│   │
│   └── migrations/               # Database migrations
│
├── manage.py                      # Django management script
├── requirements.txt               # Python dependencies
├── db.sqlite3                     # SQLite database
├── .env                           # Environment variables (create this)
├── LICENSE                        # Project license
└── README.md                      # This file
```

## 🎯 Core Capabilities

### Data Query Examples

The AI understands complex queries across various domains:

**Sales Analysis:**
```
"What are the top 5 products by revenue this quarter?"
"Show me monthly sales trends for the last year"
"Which regions have declining sales?"
```

**HR & Employee Data:**
```
"Calculate average salary by department and experience level"
"Find employees who joined in 2023 and have performance rating > 4"
"Show the distribution of employees by age group"
```

**Financial Analysis:**
```
"What's the total revenue and expenses by month?"
"Calculate profit margins for each product category"
"Identify transactions above $10,000"
```

**Customer Analytics:**
```
"Find customers who haven't purchased in 6 months"
"What's the average order value by customer segment?"
"Show the top 10 customers by lifetime value"
```

### Visualization Types

Choose from 30+ chart types including:

**Basic Charts:**
- Line, Bar, Column, Area
- Pie, Donut, Scatter
- Bubble, Histogram

**Statistical:**
- Box Plot, Violin Plot
- Heatmap, Correlation Matrix
- Distribution Plot

**Advanced:**
- 3D Surface, Contour
- Waterfall, Funnel
- Sunburst, Treemap
- Radar, Polar Charts
- Sankey Diagrams

## 🔧 Configuration

### Django Settings

Key configuration in `core/settings.py`:

```python
# Session timeout (1 hour)
SESSION_COOKIE_AGE = 3600

# File upload settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

# Allowed file types
ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.json']
```

### Supabase Setup

1. Create a new Supabase project
2. Navigate to Storage → Create bucket
3. Bucket name: `datasets`
4. Access: Private (authenticated users only)
5. Copy your API keys to `.env`

### Groq API Setup

1. Visit [console.groq.com](https://console.groq.com/)
2. Sign up for free account
3. Navigate to API Keys
4. Create new key and copy to `.env`
5. Free tier includes 30 requests/minute

## 🚀 Deployment

### Production Checklist

Before deploying to production:

```python
# In settings.py
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# Use PostgreSQL instead of SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'your_db_name',
        # ... other settings
    }
}

# Enable HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

### Deployment Options

**Heroku:**
```bash
# Install Heroku CLI and login
heroku create your-app-name
git push heroku main
heroku run python manage.py migrate
```

**Railway:**
```bash
# Connect GitHub repo
# Set environment variables in dashboard
# Deploy automatically on push
```

**DigitalOcean/AWS/Azure:**
- Use Gunicorn as WSGI server
- Configure Nginx as reverse proxy
- Set up PostgreSQL database
- Use WhiteNoise for static files

## 🔒 Security

- CSRF protection enabled by default
- Session-based file storage with automatic cleanup
- Supabase RLS (Row Level Security) for data isolation
- SQL injection prevention via parameterized queries
- File type validation on uploads
- API key encryption in environment variables

## 🐛 Troubleshooting

### Common Issues

**API Key Not Found:**
```
Error: GROQ_API_KEY not found
Solution: Ensure .env file exists in project root with correct key
```

**File Upload Fails:**
```
Error: File too large
Solution: Check file size < 10MB or adjust DATA_UPLOAD_MAX_MEMORY_SIZE
```

**Supabase Connection Error:**
```
Error: Invalid Supabase credentials
Solution: Verify SUPABASE_URL and keys in .env are correct
```

**No Module Named 'dotenv':**
```
Solution: pip install python-dotenv
```

### Debug Mode

Enable debug information:

1. Visit `/debug_session/` to view session data
2. Check browser console for JavaScript errors
3. Review Django logs in terminal
4. Use Django Debug Toolbar (optional):
   ```bash
   pip install django-debug-toolbar
   ```

## 📊 Performance Tips

1. **Large Datasets**: For files > 5MB, consider:
   - Sampling data for preview
   - Pagination in results
   - Database indexing

2. **API Rate Limits**:
   - Groq: 30 requests/minute (free tier)
   - Implement caching for repeated queries
   - Queue complex operations

3. **Session Management**:
   - Clear session data when done
   - Use "Clear Session" button on home page
   - Auto-cleanup runs hourly for old files

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add docstrings to functions
- Write unit tests for new features
- Update README for new capabilities

## 📝 API Endpoints

### Main Endpoints

```
GET  /                              # Home page
POST /upload/                       # Upload single dataset
POST /upload_datasets/              # Upload multiple datasets
GET  /datasets/                     # View all datasets
POST /run_multi_query/              # Execute natural language query
POST /generate_chart/               # Create visualization
GET  /report-builder/               # Report builder interface
POST /save_report/<format>/         # Export report (pdf/pptx/xlsx/json)
POST /transcribe_audio/             # Voice-to-text
GET  /advanced_viz/                 # Advanced chart builder
POST /merge_datasets/               # Merge multiple datasets
POST /auto_visualize/               # AI auto-generate charts
GET  /clear_session/                # Clear session data
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Groq**: For providing powerful AI APIs (Llama 3.1, Whisper)
- **Supabase**: For reliable cloud storage infrastructure
- **Plotly**: For interactive visualization library
- **Django Community**: For the excellent web framework
- **Bootstrap**: For responsive UI components

## 📧 Support

For questions, issues, or suggestions:

- Open an issue on GitHub
- Check this README and inline code comments
- Visit `/debug_session/` for troubleshooting

## 🗺️ Roadmap

Future enhancements planned:

- [ ] Real-time collaboration on reports
- [ ] Custom ML model training on datasets
- [ ] Scheduled report generation
- [ ] API for programmatic access
- [ ] Mobile app (iOS/Android)
- [ ] Advanced data transformations
- [ ] Integration with more data sources (Google Sheets, APIs)
- [ ] Export to more formats (Markdown, LaTeX)
- [ ] Dashboard builder with live data refresh

## 📈 Version History

### v2.0.0 (Current)
- ✨ Multi-dataset support
- ✨ Voice query transcription
- ✨ Enhanced report builder with drag-and-drop
- ✨ Advanced visualization builder
- ✨ Online dataset search
- 🔧 Improved session management
- 🔧 Better error handling

### v1.0.0 (Initial Release)
- Basic dataset upload
- Natural language queries
- Simple visualizations
- Basic report generation

---

**Built with ❤️ by Joyce & Sharik**

*Transform your data into insights with the power of natural language and visualization.*
