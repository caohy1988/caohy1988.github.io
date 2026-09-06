import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import pytest

# Hermetic suite: a synthetic operator so no test reads the developer's gcloud identity (live runs set the real one).
os.environ.setdefault("OKF_OPERATOR_EMAIL", "operator@example.test")

ACME = os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail")
BUNDLE_B = os.path.join(ROOT, "fixtures", "bundle_b")


@pytest.fixture(scope="session")
def sample_root():
    if not os.path.isdir(ACME):
        pytest.skip("pinned acme_retail checkout not present")
    return ACME


@pytest.fixture(scope="session")
def bundle_b_root():
    return BUNDLE_B
