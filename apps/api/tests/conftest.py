"""
Test configuration for API tests.

Ensures the project root is in sys.path so that imports like
`apps.api...` and `apps.worker...` resolve correctly.
"""

import sys
from pathlib import Path

# Add project root to path (3 levels up from apps/api/tests/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
