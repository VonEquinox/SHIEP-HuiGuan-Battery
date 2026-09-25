import requests

# 测试注册
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
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    print(f"Headers: {dict(response.headers)}")
except Exception as e:
    print(f"Error: {e}")