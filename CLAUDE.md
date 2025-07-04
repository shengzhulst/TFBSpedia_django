# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TFBSpedia is a Django-based bioinformatics web application that provides a database interface for transcription factor binding site (TFBS) data. The project includes search functionality, detailed TFBS information views, and data export capabilities for both human and mouse genomic data.

## Development Commands

### Environment Setup
```bash
# Create virtual environment
pip install virtualenv
virtualenv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Database Operations
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input
```

### Development Server
```bash
# Run development server
python manage.py runserver
# Access at http://127.0.0.1:8000/
```

### Production Build
```bash
# Use the build script for production deployment
./build.sh
```

## Architecture

### Database Configuration
- Uses PostgreSQL with multiple database connections (`default`, `human`, `mouse`)
- Database routing allows species-specific queries to different PostgreSQL databases
- Configured via environment variables (DB_NAME, DB_USERNAME, DB_PASS, DB_HOST, DB_PORT)

### Core Components

#### Models (`home/models.py`)
- `UserProfile`: Basic user profile extension
- Database models are primarily accessed via raw SQL queries to PostgreSQL

#### Views (`home/views.py`)
- `index`: Homepage with search interface
- `search_results`: Search results page with DataTables integration
- `TFBSViewSet`: REST API viewset for TFBS data with pagination
- `tfbs_details`: Detailed view for individual TFBS regions
- `download_results`: CSV export functionality

#### Key Search Functions
- `search_by_location()`: Genomic coordinate-based search (chr1,10000,20000)
- `search_by_tf_name()`: Transcription factor name search
- `is_genomic_location()`: Query type detection using regex patterns

#### Data Gathering Functions
- `gather_tfbs_names()`: Retrieves TFBS and predicted TFBS names
- `gather_source_info()`: Gets cell/tissue information
- `gather_scores()`: Fetches confidence and importance scores
- `get_overlap_annotations()`: Retrieves overlapping genomic annotations

### Database Tables Structure
The application works with multiple PostgreSQL tables:
- `TFBS_position`: Genomic coordinates
- `TFBS_name`: TF names and predictions
- `TFBS_cell_or_tissue`: Cell/tissue context
- `tfbs_confident_score`, `tfbs_importance_score`: Scoring data
- Multiple annotation tables: `Enhancer_GB`, `Promoter`, `histone`, `cCREs`, `rE2G`, `TE`, `GWAS`, `eQTL`, `blacklist`, etc.

### Frontend
- Bootstrap-based responsive design
- jQuery DataTables for search results with server-side processing
- AJAX-based search functionality
- Custom template tags in `home/templatetags/`

### Static Files
- CSS: Bootstrap, DataTables styling
- JavaScript: jQuery, DataTables, Bootstrap components
- Images: Logos and assets

### API Endpoints
- `/api/tfbs/`: REST API for TFBS data (supports pagination)
- `/api/tfbs/download/`: CSV download endpoint
- `/tfbs-details/<id>/`: Individual TFBS detail pages

## Species Support
The application supports both human and mouse data through database routing. Species selection affects which PostgreSQL database connection is used for queries.

## Environment Variables
- `SECRET_KEY`: Django secret key
- `DEBUG`: Debug mode setting
- `APP_DOMAIN`: Application domain
- `DB_NAME`, `HUMAN_DB_NAME`, `MOUSE_DB_NAME`: Database names
- `DB_USERNAME`, `DB_PASS`, `DB_HOST`, `DB_PORT`: Database credentials

## Deployment
- Configured for Render.com deployment (`render.yaml`)
- Gunicorn WSGI server configuration (`gunicorn-cfg.py`)
- WhiteNoise for static file serving
- Nginx configuration available (`nginx/appseed-app.conf`)