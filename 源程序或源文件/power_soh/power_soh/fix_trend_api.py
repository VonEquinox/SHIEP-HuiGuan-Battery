#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复后端API趋势分析函数的路由
"""

def fix_trend_api():
    # 读取原始文件
    with open('backend/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找趋势分析函数的位置
    target_text = "\ndef get_trend_analysis(battery_id):"
    replacement_text = "\n@app.route('/api/analysis/trend/<int:battery_id>', methods=['GET'])\ndef get_trend_analysis(battery_id):"
    
    # 替换文本
    new_content = content.replace(target_text, replacement_text)
    
    # 写回文件
    with open('backend/app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ 趋势分析API路由已修复")

if __name__ == "__main__":
    fix_trend_api()