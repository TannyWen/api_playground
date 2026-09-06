"""Versioned training surface, layered on top of the original API.

Everything the workshop touches lives under /v1. The original 12 endpoints are
untouched and keep their existing behaviour, including their bare
{"detail": ...} error bodies -- the contrast between the two is itself teaching
material.
"""
