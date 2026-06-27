import sys

import requests


def main():
    evidence_id = sys.argv[1] if len(sys.argv) > 1 else "4"
    url = f"http://127.0.0.1:8000/api/reconstruct/{evidence_id}/"
    response = requests.post(url, timeout=30)
    print("Status:", response.status_code)
    try:
        print("Response:", response.json())
    except ValueError:
        print(response.text[:500])
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
