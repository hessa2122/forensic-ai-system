import requests
r = requests.get('http://127.0.0.1:8000/api/stats/')
print('Status:', r.status_code)
print('Response:', r.text[:500])