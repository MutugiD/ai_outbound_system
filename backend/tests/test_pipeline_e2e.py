"""Manual end-to-end pipeline script (intentionally skipped in CI).

The full script lives in `backend/scripts/pipeline_e2e.py`.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Manual E2E pipeline script (not stable for CI unit tests)")
