"""Cost logger — redirects to utils/cost_logger.py for backwards compatibility."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.cost_logger import log_api_call
