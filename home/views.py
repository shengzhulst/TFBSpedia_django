from django.shortcuts import render, redirect
from django.db import connections
from django.conf import settings
import re, traceback, io
from rest_framework import viewsets, status
from rest_framework.response import Response
from .serializers import TFBSSerializer
import csv
from django.http import HttpResponse
from django.contrib import messages
from django.urls import reverse

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
                print("Setting actions for ID:", result.get('ID'))  # Debug
                result['actions'] = f"/tfbs-details/{result['ID']}/?species={species}"
            
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

def download_results(request):
    query = request.GET.get('query', '')
    species = request.GET.get('species', 'human')
    chromosome = request.GET.get('chromosome', '')

    db_alias = 'human' if species == 'human' else 'mouse'

    # Use your existing search logic, but fetch ALL results (no pagination)
    if is_genomic_location(query):
        chrom, start, end = parse_genomic_location(query)
        results, _ = search_by_location(db_alias, chrom, start, end, request, no_pagination=True)
    else:
        results, _ = search_by_tf_name(db_alias, query, request, no_pagination=True)

    # Optionally filter by chromosome
    if chromosome:
        results = [r for r in results if r.get('seqnames') == chromosome or r.get('chromosome') == chromosome]

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="search_results.csv"'
    writer = csv.writer(response)
    if results:
        writer.writerow(results[0].keys())  # header
        for row in results:
            writer.writerow(row.values())
    return response

def gather_tfbs_names(pk, species='human'):
    """
    Fetch TFBS and predicted_TFBS for a given TFBS region (by pk) from the TFBS_name table.
    Returns a dictionary with comma-separated strings of TFBS and predicted_TFBS values.
    """
    db_alias = 'human' if species == 'human' else 'mouse'
    from django.db import connections
    with connections[db_alias].cursor() as cursor:
        cursor.execute('''
            SELECT "TFBS", "predicted_TFBS"
            FROM "TFBS_name"
            WHERE "ID" = %s
        ''', [pk])
        rows = cursor.fetchall()
        
# Initialize lists to store non-None values
        tfbs_values = []
        predicted_tfbs_values = []
        
        # Process each row
        for row in rows:
            tfbs, predicted_tfbs = row
            if tfbs is not None:
                tfbs_values.append(tfbs)
            if predicted_tfbs is not None:
                predicted_tfbs_values.append(predicted_tfbs)
        
        # Convert lists to comma-separated strings, or None if empty
        return {
            'tfbs': ', '.join(tfbs_values) if tfbs_values else None,
            'predicted_tfbs': ', '.join(predicted_tfbs_values) if predicted_tfbs_values else None
        }

def gather_source_info(pk, species='human'):
    """
    Fetch cell/tissue information for a given TFBS region (by pk) from the TFBS_source table.
    Returns a dictionary with cell/tissue information from the single cell_tissue column.
    """
    db_alias = 'human' if species == 'human' else 'mouse'
    from django.db import connections
    with connections[db_alias].cursor() as cursor:
        cursor.execute('''
            SELECT "cell_tissue"
        FROM "TFBS_cell_or_tissue"
            WHERE "ID" = %s
        ''', [pk])
        rows = cursor.fetchall()
        
        # Initialize set to store unique values
        cell_tissue_values = set()
        
        # Process each row
        for row in rows:
            cell_tissue = row[0]
            if cell_tissue is not None:
                cell_tissue_values.add(cell_tissue)
        
        # Join all unique values with commas
        return {
            'cell_tissue_info': ', '.join(sorted(cell_tissue_values)) if cell_tissue_values else None
        }

def gather_scores(pk, species='human'):
    """
    Fetch confident and important scores for a given TFBS region (by pk) from their respective tables.
    Returns a dictionary with both scores.
    """
    db_alias = 'human' if species == 'human' else 'mouse'
    from django.db import connections
    with connections[db_alias].cursor() as cursor:
        # Get confident score
        cursor.execute('''
            SELECT "confident_score"
            FROM "tfbs_confident_score"
            WHERE "id" = %s
        ''', [pk])
        confident_score = cursor.fetchall()
        
        # Get important score
        cursor.execute('''
            SELECT "importance_score"
            FROM "tfbs_importance_score"
            WHERE "id" = %s
        ''', [pk])
        important_score = cursor.fetchall()
        print(important_score)
        return {
            'confident_score': confident_score if confident_score and confident_score[0] is not None else None,
            'important_score': important_score if important_score and important_score[0] is not None else None
        }

def get_overlap_annotations(tfbs_id, species='human'):
    """
    Fetch all overlap annotation information for a given TFBS region (by pk) from various annotation tables.
    Returns a list of dictionaries containing annotation information.
    """
    db_alias = 'human' if species == 'human' else 'mouse'
    from django.db import connections
    overlap_annotations = []
    print(db_alias)
    with connections[db_alias].cursor() as cursor:
        # 1. Get Enhancer information
        cursor.execute('''
            SELECT e."seqnames", e."start", e."end"
            FROM "TFBS_to_enhancer" te
            JOIN "Enhancer_GB" e ON te."enhancer_ID" = e."enhancer_ID"
            WHERE te."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Enhancer',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })

        # 2. Get Promoter information
        cursor.execute('''
            SELECT p."seqnames", p."start", p."end"
            FROM "TFBS_to_promoter" tp
            JOIN "Promoter" p ON tp."promoter_ID" = p."promoter_ID"
            WHERE tp."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Promoter',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })

        # 3. Get Histone information
        cursor.execute('''
            SELECT h."seqnames", h."start", h."end", h."histone"
            FROM "TFBS_to_histone" th
            JOIN "histone" h ON th."histone_ID" = h."histone_ID"
            WHERE th."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Histone',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })

        # 4. Get cCREs information
        cursor.execute('''
            SELECT c."seqnames", c."start", c."end"
            FROM "TFBS_to_cCREs" tc
            JOIN "cCREs" c ON tc."cCREs_ID" = c."cCREs_ID"
            WHERE tc."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'cCREs',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })

        # 5. Get rE2G information
        cursor.execute('''
            SELECT r."seqnames", r."start", r."end", r."gene"
            FROM "TFBS_to_rE2G" tr
            JOIN "rE2G" r ON tr."rE2G_ID" = r."rE2G_ID"
            WHERE tr."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'rE2G',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })

        # 6. Get TE information
        cursor.execute('''
            SELECT t."seqnames", t."start", t."end"
            FROM "TFBS_to_TE" tt
            JOIN "TE" t ON tt."TE_ID" = t."TE_ID"
            WHERE tt."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'TE',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })

        # 7. Get GWAS information
        cursor.execute('''
            SELECT g."seqnames", g."start", g."end", g."rs_ID"
            FROM "TFBS_to_GWAS" tg
            JOIN "GWAS" g ON tg."GWAS_ID" = g."GWAS_ID"
            WHERE tg."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'GWAS',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })

        # 8. Get eQTL information
        cursor.execute('''
            SELECT e."seqnames", e."start", e."end", e."tissue"
            FROM "TFBS_to_eQTL" te
            JOIN "eQTL" e ON te."eQTL_ID" = e."eQTL_ID"
            WHERE te."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            extra_info = []
            if row[3]: extra_info.append(f"tissue: {row[3]}")
            overlap_annotations.append({
                'type': 'eQTL',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ', '.join(extra_info)
            })

        # 9. Get Blacklist information
        cursor.execute('''
            SELECT b."seqnames", b."start", b."end"
            FROM "TFBS_to_blacklist" tb
            JOIN "blacklist" b ON tb."blacklist_ID" = b."blacklist_ID"
            WHERE tb."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Blacklist',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })

        # 10. Get Cookbook_ChIP information
        cursor.execute('''
            SELECT c."seqnames", c."start", c."end", c."TF_name"
            FROM "TFBS_to_Cookbook_ChIP" tc
            JOIN "Cookbook_ChIP" c ON tc."Cookbook_ChIP_ID" = c."Cookbook_ChIP_ID"
            WHERE tc."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Cookbook_ChIP',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })

        # 11. Get Cookbook_GHT_SELEX information
        cursor.execute('''
            SELECT c."seqnames", c."start", c."end", c."TF_name"
            FROM "TFBS_to_Cookbook_GHT_SELEX" tc
            JOIN "Cookbook_GHT_SELEX" c ON tc."Cookbook_GHT_SELEX_ID" = c."Cookbook_GHT_SELEX_ID"
            WHERE tc."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'Cookbook_GHT_SELEX',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': row[3] if row[3] else ''
            })

        # 12. Get variable_CpG information
        cursor.execute('''
            SELECT v."seqnames", v."start", v."end"
            FROM "TFBS_to_variable_CpG" tv
            JOIN "variable_CpG" v ON tv."variable_CpG_ID" = v."variable_CpG_ID"
            WHERE tv."ID" = %s
        ''', [tfbs_id])
        for row in cursor.fetchall():
            overlap_annotations.append({
                'type': 'variable_CpG',
                'chr': row[0],
                'start': row[1],
                'end': row[2],
                'extra': ''
            })
        print(overlap_annotations)
    return overlap_annotations

def tfbs_details(request, pk):
    species = request.GET.get('species', 'human')
    region_info = gather_information_chr_start_end(pk, species)
    tfbs_info = gather_tfbs_names(pk, species)
    source_info = gather_source_info(pk, species)
    scores_info = gather_scores(pk, species)
    overlap_annotations = get_overlap_annotations(pk, species)
    context = {**region_info, **tfbs_info, **source_info, **scores_info, 'overlap_annotations': overlap_annotations}
    return render(request, 'pages/tfbs_details.html', context)

def gather_information_chr_start_end(pk, species='human'):
    """
    Fetch Chr, Start, and End for a given TFBS region (by pk) from the TFBS_position table.
    Returns a dictionary: {'chr': ..., 'start': ..., 'end': ...}
    """
    db_alias = 'human' if species == 'human' else 'mouse'
    from django.db import connections
    with connections[db_alias].cursor() as cursor:
        cursor.execute('''
            SELECT "seqnames", "start", "end"
            FROM "TFBS_position"
            WHERE "ID" = %s
        ''', [pk])
        row = cursor.fetchone()
        if row:
            return {'chr': row[0], 'start': row[1], 'end': row[2]}
        else:
            return {'chr': None, 'start': None, 'end': None}

# Helper functions
def is_genomic_location(query):
    # Check for full genomic location (chrN,start,end)
    pattern = r'^chr\d+,\d+,\d+$'
    if bool(re.match(pattern, query)):
        return True
    # Check for chromosome-only query (chrN)
    pattern_chr = r'^chr\d+$'
    return bool(re.match(pattern_chr, query))

def parse_genomic_location(query):
    if ',' in query:
        parts = query.split(',')
        chromosome = parts[0]
        start = int(parts[1])
        end = int(parts[2])
        return chromosome, start, end
    else:
        # For chromosome-only queries
        return query, None, None

def search_by_location(db_alias, chromosome, start, end, request, no_pagination=False):
    try:
        with connections[db_alias].cursor() as cursor:
            if not no_pagination:
                # Use DRF or Django request for pagination
                offset = int(getattr(request, 'query_params', request.GET).get('start', 0))
                limit = int(getattr(request, 'query_params', request.GET).get('length', 25))
            # Chromosome-only search
            if start is None or end is None:
                # COUNT
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM "TFBS_position"
                    WHERE "seqnames" = %s
                """, [chromosome])
                count = cursor.fetchone()[0]
                # DATA
                if no_pagination:
                    cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s
                        ORDER BY "start"
                    """, [chromosome])
                else:
                    cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s
                        ORDER BY "start"
                        OFFSET %s LIMIT %s
                    """, [chromosome, offset, limit])
            else:
                # Genomic region search
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM "TFBS_position"
                    WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                """, [chromosome, start, end])
                count = cursor.fetchone()[0]
                if no_pagination:
                    cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                        ORDER BY "start"
                    """, [chromosome, start, end])
                else:
                        cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                        ORDER BY "start"
                        OFFSET %s LIMIT %s
                    """, [chromosome, start, end, offset, limit])
            columns = [col[0] for col in cursor.description]
            raw_results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            seen = set()
            results = []
            for row in raw_results:
                key = (row['seqnames'], row['start'], row['end'])
                if key not in seen:
                    seen.add(key)
                    results.append(row)
            return results, count
    except Exception as e:
        print(f"Database error in search_by_location: {str(e)}")
        raise

def search_by_tf_name(db_alias, tf_name, request, no_pagination=False):
    try:
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT all_count, tfbs_count, predicted_tfbs_count
                FROM tfbs_name_counts
                WHERE tfbs = %s
            """, [tf_name])
            count_info = cursor.fetchone()
            all_count = count_info[0] if count_info else 0
            if no_pagination:
                cursor.execute("""
                    SELECT DISTINCT
                        p."ID",
                        p."seqnames",
                        p."start",
                        p."end"
                    FROM "TFBS_position" p
                    WHERE EXISTS (
                        SELECT 1 
                        FROM "TFBS_name" n 
                        WHERE n."ID" = p."ID" 
                        AND (n."TFBS" = %s OR n."predicted_TFBS" = %s)
                    )
                """, [tf_name, tf_name])
            else:
                offset = int(request.query_params.get('start', 0))
                limit = int(request.query_params.get('length', 25))
                cursor.execute("""
                    SELECT DISTINCT
                        p."ID",
                        p."seqnames",
                        p."start",
                        p."end"
                    FROM "TFBS_position" p
                    WHERE EXISTS (
                        SELECT 1 
                        FROM "TFBS_name" n 
                        WHERE n."ID" = p."ID" 
                        AND (n."TFBS" = %s OR n."predicted_TFBS" = %s)
                    )
                    OFFSET %s LIMIT %s
                """, [tf_name, tf_name, offset, limit])
            columns = [col[0] for col in cursor.description]
            raw_results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            seen = set()
            results = []
            for row in raw_results:
                key = (row['seqnames'], row['start'], row['end'])
                if key not in seen:
                    seen.add(key)
                    results.append(row)
            return results, all_count
    except Exception as e:
        print(f"Database error in search_by_tf_name: {str(e)}")
        raise

def batch_search_by_tf_name(db_alias, tf_names, request=None, no_pagination=False):
    """
    Batch search for multiple TF names using the same pattern as search_by_tf_name.
    """
    if not tf_names:
        return [], 0
    print(tf_names)
    try:
        with connections[db_alias].cursor() as cursor:
            # Create placeholders for the IN clause
            placeholders = ','.join(['%s'] * len(tf_names))
            # Get total count for all TF names
            cursor.execute(f"""
                SELECT all_count, tfbs_count, predicted_tfbs_count
                FROM tfbs_name_counts
                WHERE tfbs IN ({placeholders})
            """, tf_names)
            total_count = cursor.fetchone()
            total_count=sum(total_count)
            if no_pagination:
                # Get all results (limited to prevent explosion)
                cursor.execute(f"""
                    SELECT DISTINCT
                        p."ID",
                        p."seqnames",
                        p."start",
                        p."end"
                    FROM "TFBS_position" p
                    WHERE EXISTS (
                        SELECT 1 
                        FROM "TFBS_name" n 
                        WHERE n."ID" = p."ID" 
                        AND (n."TFBS" IN ({placeholders}) OR n."predicted_TFBS" IN ({placeholders}))
                    )
                """, tf_names + tf_names)
            else:
                # Get paginated results
                print('test start')
                offset = int(getattr(request, 'query_params', request.GET).get('start', 0))
                limit = int(getattr(request, 'query_params', request.GET).get('length', 25))
                cursor.execute(f"""
                    SELECT DISTINCT
                        p."ID",
                        p."seqnames",
                        p."start",
                        p."end"
                    FROM "TFBS_position" p
                    WHERE EXISTS (
                        SELECT 1 
                        FROM "TFBS_name" n 
                        WHERE n."ID" = p."ID" 
                        AND (n."TFBS" IN ({placeholders}) OR n."predicted_TFBS" IN ({placeholders}))
                )
                OFFSET %s LIMIT %s
            """, tf_names + tf_names + [offset, limit])
                print('test end')
            
            columns = [col[0] for col in cursor.description]
            raw_results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            seen = set()
            results = []
            for row in raw_results:
                key = (row['seqnames'], row['start'], row['end'])
                if key not in seen:
                    seen.add(key)
                    results.append(row)
            return results, total_count
            
    except Exception as e:
        print(f"Database error in batch_search_by_tf_name: {str(e)}")
        raise

def batch_search_by_location(db_alias, locations, request=None, no_pagination=False):
    """
    Batch search for multiple genomic locations using the same pattern as search_by_location.
    locations: list of tuples [(chromosome, start, end), ...]
    """
    if not locations:
        return [], 0
    
    print(locations)
    try:
        with connections[db_alias].cursor() as cursor:
            # Get pagination parameters if not no_pagination
            if not no_pagination and request:
                offset = int(getattr(request, 'query_params', request.GET).get('start', 0))
                limit = int(getattr(request, 'query_params', request.GET).get('length', 25))
            else:
                offset = 0
                limit = 25
            
            # Separate chromosome-only and region searches
            chr_only_searches = []
            region_searches = []
            
            for chromosome, start, end in locations:
                if start is None or end is None:
                    chr_only_searches.append(chromosome)
                else:
                    region_searches.append((chromosome, start, end))
            
            # Get total count
            total_count = 0
            
            # Count chromosome-only searches
            if chr_only_searches:
                chr_placeholders = ','.join(['%s'] * len(chr_only_searches))
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM "TFBS_position"
                    WHERE "seqnames" IN ({chr_placeholders})
                """, chr_only_searches)
                chr_count = cursor.fetchone()[0]
                total_count += chr_count
            
            # Count region searches
            for chromosome, start, end in region_searches:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM "TFBS_position"
                    WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                """, [chromosome, start, end])
                region_count = cursor.fetchone()[0]
                total_count += region_count
            
            # Get results
            all_results = []
            
            # Handle chromosome-only searches
            if chr_only_searches:
                chr_placeholders = ','.join(['%s'] * len(chr_only_searches))
                if no_pagination:
                    cursor.execute(f"""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" IN ({chr_placeholders})
                        ORDER BY "seqnames", "start"
                    """, chr_only_searches)
                else:
                    cursor.execute(f"""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" IN ({chr_placeholders})
                        ORDER BY "seqnames", "start"
                        OFFSET %s LIMIT %s
                    """, chr_only_searches + [offset, limit])
                
                columns = [col[0] for col in cursor.description]
                chr_results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                all_results.extend(chr_results)
            
            # Handle region searches
            for chromosome, start, end in region_searches:
                if no_pagination:
                    cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                        ORDER BY "start"
                    """, [chromosome, start, end])
                else:
                    cursor.execute("""
                        SELECT "ID", "seqnames", "start", "end"
                        FROM "TFBS_position"
                        WHERE "seqnames" = %s AND "start" >= %s AND "end" <= %s
                        ORDER BY "start"
                        OFFSET %s LIMIT %s
                    """, [chromosome, start, end, offset, limit])
                
                columns = [col[0] for col in cursor.description]
                region_results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                all_results.extend(region_results)
            
            # Remove duplicates from combined results
            seen = set()
            results = []
            for row in all_results:
                key = (row['seqnames'], row['start'], row['end'])
                if key not in seen:
                    seen.add(key)
                    results.append(row)
            
            return results, total_count
            
    except Exception as e:
        print(f"Database error in batch_search_by_location: {str(e)}")
        raise

def evaluation_metrics(request):
    """
    View function for the evaluation metrics explanation page.
    """
    return render(request, 'pages/evaluation_metrics.html')

def batch_search(request):
    """
    Handle file upload and batch search for multiple TF names and regions.
    """
    if request.method == 'POST':
        if 'search_file' not in request.FILES:
            messages.error(request, 'No file uploaded. Please select a file.')
            return redirect('index')
        
        file = request.FILES['search_file']
        species = request.POST.get('species', 'human')
        
        if file.size > 10 * 1024 * 1024:  # 10MB limit
            messages.error(request, 'File size too large. Please keep files under 10MB.')
            return redirect('index')
        
        try:
            # Read file content
            file_content = file.read().decode('utf-8')
            queries = parse_batch_file(file_content)
            
            if not queries:
                messages.error(request, 'No valid search terms found in the file.')
                return redirect('index')
            
            if len(queries) > 1000:  # Limit number of queries
                messages.error(request, 'Too many search terms. Please limit to 1000 queries per file.')
                return redirect('index')
            
            # Store file content in session for batch processing
            request.session['batch_file_content'] = file_content
            
            # Process batch search and redirect to results
            return redirect(f"{reverse('batch_results')}?species={species}&query_count={len(queries)}")
            
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
            return redirect('index')
    
    return redirect('index')

def batch_results(request):
    """
    Display batch search results page.
    """
    species = request.GET.get('species', 'human')
    query_count = request.GET.get('query_count', 0)
    
    context = {
        'species': species,
        'query_count': query_count,
        'is_batch_search': True,
        'columns': [
            {'name': 'Chromosome', 'key': 'seqnames'},
            {'name': 'Start', 'key': 'start'},
            {'name': 'End', 'key': 'end'},
        ]
    }
    return render(request, 'pages/batch_results.html', context)

class BatchTFBSViewSet(viewsets.ViewSet):
    """
    API endpoint for batch search processing.
    """
    def list(self, request):
        file_content = request.session.get('batch_file_content', '')
        species = request.query_params.get('species', 'human')
        draw = int(request.query_params.get('draw', 1))
        
        # Early return if no file content provided
        if not file_content:
            return Response({
                'draw': draw,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': []
            })
        
        db_alias = 'human' if species == 'human' else 'mouse'
        
        try:
            # Parse queries and execute batch search
            queries = parse_batch_file(file_content)
            
            # Separate TF names and genomic locations
            tf_names = []
            locations = []
            
            for query in queries:
                if is_genomic_location(query):
                    chrom, start, end = parse_genomic_location(query)
                    locations.append((chrom, start, end))
                else:
                    tf_names.append(query)
            
            # Execute batch searches (no pagination to get all results)
            all_results = []
            total_count = 0
            
            # Process TF names in batch
            if tf_names:
                tf_results, tf_total_count = batch_search_by_tf_name(db_alias, tf_names, request, no_pagination=False)
                total_count += tf_total_count
                for result in tf_results:
                    result['actions'] = f"/tfbs-details/{result['ID']}/?species={species}"
                    all_results.append(result)
            
            # Process genomic locations in batch
            if locations:
                location_results, location_total_count = batch_search_by_location(db_alias, locations, request, no_pagination=False)
                total_count += location_total_count
                for result in location_results:
                    result['actions'] = f"/tfbs-details/{result['ID']}/?species={species}"
                    all_results.append(result)
            
            # Format response for DataTables
            return Response({
                'draw': draw,
                'recordsTotal': total_count,
                'recordsFiltered': total_count,
                'data': all_results
            })
            
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Error in BatchTFBSViewSet: {str(e)}")
            print(f"Traceback: {error_details}")
            
            return Response({
                'draw': draw,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': [],
                'error': str(e),
                'details': error_details if settings.DEBUG else "See server logs for details"
            }, status=status.HTTP_200_OK)  # Return 200 so DataTables can display the error

def parse_batch_file(file_content):
    """
    Parse uploaded file content to extract search queries.
    Supports both CSV and plain text formats.
    """
    queries = []
    
    # Remove UTF-8 BOM if present
    if file_content.startswith('\ufeff'):
        file_content = file_content[1:]
    
    lines = file_content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):  # Skip empty lines and comments
            continue
        
        # Clean up the line (remove any remaining BOM or special characters)
        if line:
            # Remove any leading/trailing whitespace and special characters
            clean_line = line.strip()
            # Remove any remaining BOM characters
            if clean_line.startswith('\ufeff'):
                clean_line = clean_line[1:].strip()
            
            # Remove trailing commas
            clean_line = clean_line.rstrip(',')
            
            if clean_line:  # Only process non-empty lines
                # Check if this is a genomic location first (after cleaning)
                if is_genomic_location(clean_line):
                    # It's a genomic location, use as-is
                    queries.append(clean_line)
                elif ',' in clean_line:
                    # It's CSV format, take first column
                    parts = clean_line.split(',')
                    csv_query = parts[0].strip()
                    if csv_query:
                        queries.append(csv_query)
                else:
                    # It's a plain text query
                    queries.append(clean_line)
    
    print(queries)
    return queries

def download_batch_results(request):
    """
    Download batch search results as CSV.
    """
    file_content = request.session.get('batch_file_content', '')
    species = request.GET.get('species', 'human')
    
    if not file_content:
        return HttpResponse("No batch search data available", status=400)
    
    db_alias = 'human' if species == 'human' else 'mouse'
    
    try:
        # Parse queries and execute batch search (no pagination for downloads)
        queries = parse_batch_file(file_content)
        
        # Separate TF names and genomic locations
        tf_names = []
        locations = []
        
        for query in queries:
            if is_genomic_location(query):
                chrom, start, end = parse_genomic_location(query)
                locations.append((chrom, start, end))
            else:
                tf_names.append(query)
        
        # Execute batch searches (no pagination)
        all_results = []
        
        # Process TF names in batch
        if tf_names:
            tf_results, _ = batch_search_by_tf_name(db_alias, tf_names, request, no_pagination=True)
            all_results.extend(tf_results)
        
        # Process genomic locations in batch
        if locations:
            location_results, _ = batch_search_by_location(db_alias, locations, request, no_pagination=True)
            all_results.extend(location_results)
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="batch_search_results.csv"'
        writer = csv.writer(response)
        
        if all_results:
            writer.writerow(['Chromosome', 'Start', 'End', 'ID'])
            for row in all_results:
                writer.writerow([
                    row.get('seqnames', ''),
                    row.get('start', ''),
                    row.get('end', ''),
                    row.get('ID', '')
                ])
        
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating CSV: {str(e)}", status=500)