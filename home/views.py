from django.shortcuts import render
from django.db import connections
import re
from rest_framework import viewsets
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
    
    # DataTables will handle data fetching via AJAX
    context = {
        'query': query,
        'species': species,
    }
    return render(request, 'pages/search_results.html', context)

class TFBSViewSet(viewsets.ViewSet):
    def list(self, request):
        query = request.query_params.get('query', '')
        species = request.query_params.get('species', 'human')
        
        results = []
        db_alias = 'human' if species == 'human' else 'mouse'
        
        if self.is_genomic_location(query):
            chrom, start, end = self.parse_genomic_location(query)
            results = self.search_by_location(db_alias, chrom, start, end)
        else:
            results = self.search_by_tf_name(db_alias, query)
        
        serializer = TFBSSerializer(results, many=True)
        return Response(serializer.data)
    
    def is_genomic_location(self, query):
        pattern = r'^chr\d+,\d+,\d+$'
        return bool(re.match(pattern, query))
    
    def parse_genomic_location(self, query):
        parts = query.split(',')
        chromosome = parts[0]
        start = int(parts[1])
        end = int(parts[2])
        return chromosome, start, end
    
    def search_by_location(self, db_alias, chromosome, start, end):
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT id, chromosome as seqnames, position_start as start, position_end as end, 
                       tf_name, score 
                FROM binding_sites 
                WHERE chromosome = %s AND position_start >= %s AND position_end <= %s
                LIMIT 1000
            """, [chromosome, start, end])
            
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def search_by_tf_name(self, db_alias, tf_name):
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""                
                SELECT
                    "TFBS_position"."ID" as id,
                    "TFBS_position"."seqnames",
                    "TFBS_position"."start",
                    "TFBS_position"."end",
                    "TFBS_name"."TFBS" as tf_name
                FROM "TFBS_name"
                JOIN "TFBS_position"
                ON "TFBS_name"."ID" = "TFBS_position"."ID"
                WHERE "TFBS_name"."TFBS" ILIKE %s OR "TFBS_name"."predicted_TFBS" ILIKE %s
                LIMIT 1000
                """, [f'%{tf_name}%', f'%{tf_name}%'])
            
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]