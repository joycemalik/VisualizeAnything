# Datanaut.ai 🚀

A Django-based data analysis platform that allows users to upload datasets and query them using natural language, powered by AI.

## Features

- 📊 Upload CSV, XLSX, and JSON datasets
- 🤖 Natural language to SQL query conversion using Groq AI
- 💾 Secure cloud storage with Supabase
- 📈 Interactive data preview and exploration
- 🎯 Real-time query execution and results

## Tech Stack

- **Backend**: Django 5.2.5
- **AI**: Groq (Llama 3.1)
- **Database**: SQLite (development), PostgreSQL (production)
- **Cloud Storage**: Supabase
- **Data Processing**: Pandas, NumPy
- **Frontend**: HTML, CSS, JavaScript

## Setup Instructions

### Prerequisites

- Python 3.8+
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/datanaut.git
   cd datanaut
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit the `.env` file with your actual credentials:
   - Get Groq API key from [Groq Console](https://console.groq.com/)
   - Get Supabase credentials from [Supabase Dashboard](https://supabase.com/dashboard)

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Start the development server**
   ```bash
   python manage.py runserver
   ```

7. **Access the application**
   Open your browser and navigate to `http://127.0.0.1:8000/`

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Groq AI Configuration
GROQ_API_KEY=your-groq-api-key-here

# Supabase Configuration
SUPABASE_URL=your-supabase-url-here
SUPABASE_KEY=your-supabase-anon-key-here
SUPABASE_SERVICE_KEY=your-supabase-service-key-here
SUPABASE_BUCKET=datasets
```

## Usage

1. **Upload a Dataset**: Click "Upload Dataset" and select your CSV, XLSX, or JSON file
2. **Preview Data**: View the first 5 rows and column information
3. **Query with Natural Language**: Ask questions like:
   - "Show me all employees aged 25"
   - "What's the average salary by department?"
   - "Find the top 10 highest paid employees"
4. **View Results**: See the generated SQL and query results in a formatted table

## Project Structure

```
datanaut/
├── core/                 # Django project settings
│   ├── settings.py      # Main settings
│   ├── urls.py          # URL routing
│   └── wsgi.py          # WSGI config
├── studio/              # Main Django app
│   ├── models.py        # Database models
│   ├── views.py         # Business logic
│   ├── forms.py         # Django forms
│   ├── urls.py          # App URLs
│   └── templates/       # HTML templates
├── static/              # Static files (CSS, JS)
├── media/               # User uploads
├── requirements.txt     # Python dependencies
├── manage.py           # Django management
└── .env.example        # Environment variables template
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.

---

Made with ❤️ by [Your Name]
