# backend/generate_model.py
import torch
import torch.nn as nn
import os

# 1. 这里的网络结构【必须】和 main.py 里写的一模一样
class BiLSTM_SOH_Model(nn.Module):
    def __init__(self, input_size=4, hidden_size=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, bidirectional=True)
        # 输出层：分别预测 SOH (0~1) 和 RUL (剩余循环次数)
        self.fc_soh = nn.Linear(hidden_size * 2, 1)
        self.fc_rul = nn.Linear(hidden_size * 2, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :] # 取序列的最后一个时间步
        soh = self.fc_soh(out)
        rul = self.fc_rul(out)
        return soh, rul

if __name__ == "__main__":
    print("正在初始化 BiLSTM 模型...")
    # 2. 实例化这个模型（此刻它的大脑里是随机初始化的数学参数）
    model = BiLSTM_SOH_Model()

    # 3. 在 backend 目录下建一个 models 文件夹来存放
    os.makedirs("models", exist_ok=True)

    # 4. 将这些参数保存为 .pth 文件
    save_path = "models/best_bilstm_model.pth"
    torch.save(model.state_dict(), save_path)

    print(f"✅ 太棒了！测试用的模型权重已生成并保存在: {save_path}")
    print("👉 现在您可以去 main.py 中取消注释加载模型的代码了！")