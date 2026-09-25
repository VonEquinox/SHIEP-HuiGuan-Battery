import requests
import traceback

try:
    response = requests.post(
        'http://localhost:5000/api/auth/register',
        json={
            'username': 'testuser',
            'email': 'test@test.com',
            'password': 'Test123456'
        },
        timeout=10
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    print(f"Response Headers: {dict(response.headers)}")
except requests.exceptions.ConnectionError:
    print("Connection Error: Could not connect to the server")
except Exception as e:
    print(f"Request Error: {e}")
    traceback.print_exc()