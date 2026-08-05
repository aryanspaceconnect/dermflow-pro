"""
DermFlow Pro - Vercel Serverless Entry Point
Exposes the Flask WSGI app for Vercel Python runtime.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
