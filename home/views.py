from django.shortcuts import render
from django.db import connections
import re

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
    
    results = []
    columns = []
    
    # Determine which database to query
    db_alias = 'human' if species == 'human' else 'mouse'
    
    # Analyze query type
    if is_genomic_location(query):
        # Parse chromosome, start, and end positions
        chrom, start, end = parse_genomic_location(query)
        results, columns = search_by_location(db_alias, chrom, start, end)
    else:
        # Assume it's a TF name
        results, columns = search_by_tf_name(db_alias, query)
    
    context = {
        'query': query,
        'species': species,
        'results': results,
        'columns': columns
    }
    return render(request, 'pages/search_results.html', context)

def is_genomic_location(query):
    # Check if query matches pattern like "chr1,10000,20000"
    pattern = r'^chr\d+,\d+,\d+$'
    return bool(re.match(pattern, query))

def parse_genomic_location(query):
    parts = query.split(',')
    chromosome = parts[0]
    start = int(parts[1])
    end = int(parts[2])
    return chromosome, start, end

def search_by_location(db_alias, chromosome, start, end):
    # Connect to the appropriate database
    with connections[db_alias].cursor() as cursor:
        cursor.execute("""
            SELECT id, chromosome, position_start, position_end, tf_name, score 
            FROM binding_sites 
            WHERE chromosome = %s AND position_start >= %s AND position_end <= %s
            LIMIT 100
        """, [chromosome, start, end])
        
        columns = [
            {'name': 'ID', 'key': 'id'},
            {'name': 'Chromosome', 'key': 'chromosome'},
            {'name': 'Start', 'key': 'position_start'},
            {'name': 'End', 'key': 'position_end'},
            {'name': 'TF Name', 'key': 'tf_name'},
            {'name': 'Score', 'key': 'score'},
            {'name': 'Actions', 'key': 'actions'}
        ]
        
        db_columns = [col[0] for col in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            result = dict(zip(db_columns, row))
            result['actions'] = f"/detail/{result['id']}/"
            results.append(result)
            
    return results, columns

def search_by_tf_name(db_alias, tf_name):
    # Connect to the appropriate database
    with connections[db_alias].cursor() as cursor:
        cursor.execute("""                
            SELECT
                "TFBS_position"."seqnames",
                "TFBS_position"."start",
                "TFBS_position"."end"
            FROM "TFBS_name"
            JOIN "TFBS_position"
            ON "TFBS_name"."ID" = "TFBS_position"."ID"
            WHERE "TFBS_name"."TFBS" ILIKE %s OR "TFBS_name"."predicted_TFBS" ILIKE %s
            """, [f'%{tf_name}%', f'%{tf_name}%'])
        columns = [
            {'name': 'Chromosome', 'key': 'seqnames'},
            {'name': 'Start', 'key': 'start'},
            {'name': 'End', 'key': 'end'},
        ]
        
        db_columns = [col[0] for col in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            result = dict(zip(db_columns, row))
            result['actions'] = f"/detail/{result['ID']}/"
            results.append(result)
            
    return results, columns