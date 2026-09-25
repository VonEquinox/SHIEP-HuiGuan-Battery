#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试登录API脚本
"""

import requests
import json

def test_login():
    """测试登录API"""
    url = "http://localhost:5000/api/auth/login"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "username": "admin",
        "password": "admin123"
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            print("登录成功！")
        else:
            print("登录失败！")
    except Exception as e:
        print(f"测试登录时出错: {e}")

if __name__ == "__main__":
    test_login()
