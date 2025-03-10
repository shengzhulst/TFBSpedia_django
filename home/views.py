from django.shortcuts import render
from django.db import connections
from django.conf import settings
import re, traceback
from rest_framework import viewsets, status
from rest_framework.response import Response
from .serializers import TFBSSerializer

def index(request):
    context = {
        'examples': ['Example search: chr1,10000,20000', 'Example search: FOXP3'],
        'motif_info_url': '/motif-info/',
        'benchmark_url': '/benchmark-info/',
        'genome_browser_url': '/genome-browser/'
    }
    return render(request, 'pages/index.html', context)

def search_results(request):
    query = request.GET.get('query', '')
    species = request.GET.get('species', 'human')
    
    # Just prepare the context for the template,
    # actual data will be loaded via AJAX from the API
    context = {
        'query': query,
        'species': species,
        'columns': [
            {'name': 'Chromosome', 'key': 'seqnames'},
            {'name': 'Start', 'key': 'start'},
            {'name': 'End', 'key': 'end'},
            # {'name': 'TF Name', 'key': 'tf_name'},
            # {'name': 'Score', 'key': 'score'}
        ]
    }
    return render(request, 'pages/search_results.html', context)

class TFBSViewSet(viewsets.ViewSet):
    def list(self, request):
        query = request.query_params.get('query', '')
        species = request.query_params.get('species', 'human')
        draw = int(request.query_params.get('draw', 1))
        
        # Early return if no query provided
        if not query:
            return Response({
                'draw': draw,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': []
            })
        
        db_alias = 'human' if species == 'human' else 'mouse'
        
        try:
            # Determine search method and execute query
            if is_genomic_location(query):
                chrom, start, end = parse_genomic_location(query)
                results, total_count = search_by_location(db_alias, chrom, start, end, request)
            else:
                results, total_count = search_by_tf_name(db_alias, query, request)
            
            # Add action links to each result (if results aren't empty)
            for result in results:
                result['actions'] = f"/tfbs-details/{result.get('id', 0)}/"
            
            # Format response for DataTables
            return Response({
                'draw': draw,
                'recordsTotal': total_count,
                'recordsFiltered': total_count,
                'data': results
            })
            
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error in TFBSViewSet: {str(e)}")
            print(f"Traceback: {error_details}")
            
            return Response({
                'draw': draw,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': [],
                'error': str(e),
                'details': error_details if settings.DEBUG else "See server logs for details"
            }, status=status.HTTP_200_OK)  # Return 200 so DataTables can display the error

# Helper functions
def is_genomic_location(query):
    pattern = r'^chr\d+,\d+,\d+$'
    return bool(re.match(pattern, query))

def parse_genomic_location(query):
    parts = query.split(',')
    chromosome = parts[0]
    start = int(parts[1])
    end = int(parts[2])
    return chromosome, start, end

def search_by_location(db_alias, chromosome, start, end, request):
    try:
        with connections[db_alias].cursor() as cursor:
            # First get a count of total matching records
            cursor.execute("""
                SELECT COUNT(*) 
                FROM binding_sites 
                WHERE chromosome = %s AND position_start >= %s AND position_end <= %s
            """, [chromosome, start, end])
            
            count = cursor.fetchone()[0]
            
            # Handle pagination
            offset = int(request.query_params.get('start', 0))
            limit = int(request.query_params.get('length', 25))
            
            # Get paginated results
            cursor.execute("""
                SELECT id, chromosome as seqnames, position_start as start, position_end as end, 
                       tf_name, score 
                FROM binding_sites 
                WHERE chromosome = %s AND position_start >= %s AND position_end <= %s
                ORDER BY position_start
                OFFSET %s LIMIT %s
            """, [chromosome, start, end, offset, limit])
            
            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            return results, count
    except Exception as e:
        print(f"Database error in search_by_location: {str(e)}")
        # Re-raise to be caught by the main try/except block
        raise

def search_by_tf_name(db_alias, tf_name, request):
    try:
        with connections[db_alias].cursor() as cursor:
            # First get a count of total matching records
            cursor.execute("""
                SELECT COUNT(*)
                FROM "TFBS_name"
                JOIN "TFBS_position"
                ON "TFBS_name"."ID" = "TFBS_position"."ID"
                WHERE "TFBS_name"."TFBS" = %s OR "TFBS_name"."predicted_TFBS" = %s
            """, [f'%{tf_name}%', f'%{tf_name}%'])
            
            count = cursor.fetchone()[0]
            
            # Handle pagination
            offset = int(request.query_params.get('start', 0))
            limit = int(request.query_params.get('length', 25))
            
            # Get paginated results
            cursor.execute("""                
                SELECT DISTINCT
                    "TFBS_position"."ID",
                    "TFBS_position"."seqnames",
                    "TFBS_position"."start",
                    "TFBS_position"."end"
                FROM "TFBS_name"
                JOIN "TFBS_position"
                ON "TFBS_name"."ID" = "TFBS_position"."ID"
                WHERE "TFBS_name"."TFBS" = %s OR "TFBS_name"."predicted_TFBS" = %s
            """, [tf_name, tf_name])
            
            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            return results, count
    except Exception as e:
        print(f"Database error in search_by_tf_name: {str(e)}")
        # Re-raise to be caught by the main try/except block
        raise