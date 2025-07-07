"""
Module utilitaires pour ArticSpace
"""

# Import des fonctions principales pour un accès facile
from .helpers import (
    clean_text,
    extract_keywords,
    generate_unique_filename,
    format_file_size,
    format_response,
    truncate_text,
    create_success_response,
    create_error_response
)

from .validators import (
    validate_email,
    validate_password,
    validate_username,
    validate_file_upload,
    validate_pdf_file,
    validate_question,
    validate_search_query,
    validate_article_data,
    validate_language_code
)

from .decorators import (
    require_api_key,
    rate_limit,
    cache_response,
    log_execution_time,
    validate_json,
    admin_required,
    handle_exceptions,
    api_endpoint
)

__all__ = [
    # Helpers
    'clean_text',
    'extract_keywords', 
    'generate_unique_filename',
    'format_file_size',
    'format_response',
    'truncate_text',
    'create_success_response',
    'create_error_response',
    
    # Validators
    'validate_email',
    'validate_password',
    'validate_username',
    'validate_file_upload',
    'validate_pdf_file',
    'validate_question',
    'validate_search_query',
    'validate_article_data',
    'validate_language_code',
    
    # Decorators
    'require_api_key',
    'rate_limit',
    'cache_response',
    'log_execution_time',
    'validate_json',
    'admin_required',
    'handle_exceptions',
    'api_endpoint'
]