import requests

# Use evidence ID from previous response
url = "http://127.0.0.1:8000/api/reconstruct/4/"

response = requests.post(url)
print("Status:", response.status_code)
print("Response:", response.json())