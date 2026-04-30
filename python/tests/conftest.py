from pathlib import Path


def pytest_configure(config):
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent.parent
    repo = here.parent
    for p in (here / ".env", repo / ".env"):
        if p.exists():
            load_dotenv(p, override=False)
