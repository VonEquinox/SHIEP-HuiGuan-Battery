import requests

print("="*60)
print("测试Flask API接口")
print("="*60)

# 1. 健康检查
print("\n1. 健康检查:")
r = requests.get('http://localhost:5000/api/health')
print(f"  状态: {r.json()['success']}")
print(f"  消息: {r.json()['message']}")

# 2. 获取电池统计
print("\n2. 电池统计:")
r = requests.get('http://localhost:5000/api/batteries/statistics')
data = r.json()['data']
print(f"  总电池数: {data['overview']['total_batteries']}")
print(f"  总数据条数: {data['lifecycle_records']:,}")
print(f"  平均SOH: {float(data['overview']['avg_soh']):.2f}%")
print(f"  平均RUL: {float(data['overview']['avg_rul']):.2f}")

# 3. 获取电池列表
print("\n3. 电池列表（前5个）:")
r = requests.get('http://localhost:5000/api/batteries')
batteries = r.json()['data'][:5]
for b in batteries:
    print(f"  #{b['battery_id']}: {b['battery_name']} - "
          f"{b['dataset_type']} - {b['total_cycles']}循环")

# 4. 获取单个电池详情
print("\n4. 电池#100详情:")
r = requests.get('http://localhost:5000/api/batteries/100')
detail = r.json()['data']
print(f"  编号: {detail['info']['battery_id']}")
print(f"  名称: {detail['info']['battery_name']}")
print(f"  类型: {detail['info']['dataset_type']}")
print(f"  总循环: {detail['info']['total_cycles']}")
if detail['statistics']:
    stats = detail['statistics']
    print(f"  电压均值: {float(stats['voltage_mean']):.4f}V")
    print(f"  温度均值: {float(stats['temperature_mean']):.2f}°C")
    print(f"  SOH均值: {float(stats['soh_mean']):.2f}%")

# 5. 获取电池生命周期数据
print("\n5. 电池#100生命周期数据（前3条）:")
r = requests.get('http://localhost:5000/api/batteries/100/lifecycle',
                 params={'page': 1, 'page_size': 3})
result = r.json()
print(f"  总数据: {result['pagination']['total']}条")
for d in result['data']:
    print(f"  循环{d['cycle_count']}: "
          f"电压={float(d['voltage']):.4f}V, "
          f"温度={float(d['temperature']):.2f}°C, "
          f"SOH={float(d['soh']):.2f}%, "
          f"RUL={d['rul']}")

print("\n" + "="*60)
print("✓ API测试完成！")
print("="*60)
