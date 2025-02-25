# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.

def index(request):
    context = {
        'examples': ['Example search: chr1,10000,20000', 'Example search: FOXP3'],
        'motif_info_url': 'https://example.com/motif',
        'benchmark_url': 'https://example.com/benchmark',
        'genome_browser_url': 'https://example.com/browser'
    }
    # Page from the theme 
    return render(request, 'pages/index.html',context)

def search_results(request):
    query = request.GET.get('query', '')
    # Process the query here
    results = []  # Replace with actual search results
    
    context = {
        'query': query,
        'results': results
    }
    return render(request, 'pages/search_results.html', context)