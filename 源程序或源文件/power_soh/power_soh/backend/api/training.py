from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
import os
import sys
import torch
import numpy as np
from pathlib import Path

from db.database import get_db
from db.models import Model, TrainingRecord, User, BatteryInfo
from utils.security import get_current_user

router = APIRouter()

# 全局字典，用于跟踪正在运行的训练任务的停止状态
# key: task_id, value: {"should_stop": bool}
running_tasks = {}

# 添加项目根目录到Python路径，以便导入functions模块
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@router.get("/")
async def get_training_tasks(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取训练任务列表
    """
    training_records = db.query(TrainingRecord).filter(
        TrainingRecord.user_id == current_user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(TrainingRecord).filter(
        TrainingRecord.user_id == current_user.id
    ).count()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [
            {
                "id": record.id,
                "model_id": record.model_id,
                "model_name": record.model.name if record.model else None,
                "algorithm_type": record.model.algorithm_type if record.model else None,
                "status": record.status,
                "dataset_path": record.dataset_path,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
            for record in training_records
        ]
    }


@router.get("/{task_id}")
async def get_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取指定训练任务详情
    """
    try:
        # 尝试将task_id转换为整数（如果是字符串）
        task_id_int = int(task_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的任务ID: {task_id}"
        )
    
    training_record = db.query(TrainingRecord).filter(
        TrainingRecord.id == task_id_int,
        TrainingRecord.user_id == current_user.id
    ).first()
    
    if not training_record:
        # 检查是否是ID不存在还是用户ID不匹配
        all_records = db.query(TrainingRecord).filter(TrainingRecord.id == task_id_int).all()
        if not all_records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"训练任务不存在 (ID: {task_id_int})"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问该训练任务"
            )
    
    # 如果找到了训练记录，继续处理
    training_config = {}
    if training_record.training_config:
        try:
            training_config = json.loads(training_record.training_config)
        except:
            pass
        
        # 解析训练指标
        train_metrics = {}
        validation_metrics = {}
        test_metrics = {}
        if training_record.train_metrics:
            try:
                train_metrics = json.loads(training_record.train_metrics)
            except:
                pass
        if training_record.validation_metrics:
            try:
                validation_metrics = json.loads(training_record.validation_metrics)
            except:
                pass
        if training_record.test_metrics:
            try:
                test_metrics = json.loads(training_record.test_metrics)
            except:
                pass
        
        return {
            "id": training_record.id,
            "model_id": training_record.model_id,
            "model_name": training_record.model.name if training_record.model else None,
            "status": training_record.status,
            "dataset_path": training_record.dataset_path,
            "training_config": training_config,
            "training_logs": training_record.logs or "",
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            "created_at": training_record.created_at.isoformat() if training_record.created_at else None,
            "start_time": training_record.start_time.isoformat() if training_record.start_time else None,
            "end_time": training_record.end_time.isoformat() if training_record.end_time else None,
            "duration": training_record.duration,
            "final_loss": training_record.final_loss,
            "best_val_loss": training_record.best_val_loss,
        }


@router.post("/")
async def create_training_task(
    training_data: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建训练任务并开始训练
    
    请求参数：
    - algorithm_type: 算法类型 (baseline, bilstm, deepphm)
    - battery_ids: 选中的电池组ID列表
    - network_params: 网络结构参数 (layers, nodes, activation)
    - hyperparams: 训练超参数 (learning_rate, batch_size, epochs, optimizer)
    - dataset_split: 数据集划分参数 (train_ratio, validation_ratio)
    """
    try:
        algorithm_type = training_data.get("algorithm_type", "baseline")
        battery_ids = training_data.get("battery_ids", [])
        network_params = training_data.get("network_params", {})
        hyperparams = training_data.get("hyperparams", {})
        dataset_split = training_data.get("dataset_split", {})
        
        if not battery_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请至少选择一个电池组"
            )
        
        # 验证电池组是否存在
        batteries = db.query(BatteryInfo).filter(
            BatteryInfo.battery_id.in_(battery_ids)
        ).all()
        
        if len(batteries) != len(battery_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="部分电池组不存在"
            )
        
        # 创建模型记录
        model_name = f"{algorithm_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        new_model = Model(
            user_id=current_user.id,
            name=model_name,
            algorithm_type=algorithm_type,
            framework="PyTorch",
            description=f"{algorithm_type.upper()}模型，训练时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            hyperparameters=json.dumps(hyperparams),
            architecture=json.dumps(network_params),
            status="training",
            is_active=True
        )
        
        db.add(new_model)
        db.commit()
        db.refresh(new_model)
        
        # 创建训练记录
        training_config = {
            "battery_ids": battery_ids,
            "network_params": network_params,
            "hyperparams": hyperparams,
            "dataset_split": dataset_split
        }
        
        training_record = TrainingRecord(
            user_id=current_user.id,
            model_id=new_model.id,
            dataset_path=json.dumps(battery_ids),
            training_config=json.dumps(training_config),
            status="training"
        )
        
        db.add(training_record)
        db.commit()
        db.refresh(training_record)
        
        # 在后台执行训练任务（不传递db session，在函数内部获取）
        background_tasks.add_task(
            execute_training,
            model_id=new_model.id,
            training_record_id=training_record.id,
            algorithm_type=algorithm_type,
            battery_ids=battery_ids,
            network_params=network_params,
            hyperparams=hyperparams,
            dataset_split=dataset_split
        )
        
        return {
            "success": True,
            "message": "训练任务已创建，正在后台执行",
            "data": {
                "model_id": new_model.id,
                "training_record_id": training_record.id,
                "model_name": model_name,
                "status": "training"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建训练任务失败: {str(e)}"
        )


def execute_training(
    model_id: int,
    training_record_id: int,
    algorithm_type: str,
    battery_ids: List[int],
    network_params: dict,
    hyperparams: dict,
    dataset_split: dict
):
    """
    执行训练任务的函数（在后台运行）
    """
    from db.database import SessionLocal
    
    # 注册训练任务
    running_tasks[training_record_id] = {"should_stop": False}
    
    # 创建新的数据库session
    db = SessionLocal()
    try:
        # 更新训练状态
        model = db.query(Model).filter(Model.id == model_id).first()
        training_record = db.query(TrainingRecord).filter(
            TrainingRecord.id == training_record_id
        ).first()
        
        if not model:
            print(f"[TRAINING ERROR] 模型不存在 - Model ID: {model_id}")
            db.close()
            return
        
        if not training_record:
            print(f"[TRAINING ERROR] 训练记录不存在 - Training Record ID: {training_record_id}")
            db.close()
            return
        
        print(f"[TRAINING] 找到模型和训练记录 - Model: {model.name}, Status: {training_record.status}")
        
        # 添加训练日志
        training_logs = [
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始训练 {algorithm_type.upper()} 模型",
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 选择的电池组: {battery_ids}",
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 网络参数: {network_params}",
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 超参数: {hyperparams}"
        ]
        
        # 导入训练函数
        try:
            import functions as func
            print(f"[TRAINING] 成功导入functions模块")
        except ImportError as e:
            error_msg = f"无法导入functions模块: {str(e)}"
            print(f"[TRAINING ERROR] {error_msg}")
            training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: {error_msg}")
            training_record.logs = "\n".join(training_logs)
            training_record.status = "failed"
            training_record.end_time = datetime.now()
            model.status = "failed"
            db.commit()
            db.close()
            return
        
        # 设置设备
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 使用设备: {device}")
        
        # 准备数据
        mat_file_path = project_root / "SeversonBattery.mat"
        print(f"[TRAINING] 检查数据文件: {mat_file_path}, 存在: {mat_file_path.exists()}")
        if not mat_file_path.exists():
            error_msg = f"数据文件不存在: {mat_file_path}"
            print(f"[TRAINING ERROR] {error_msg}")
            training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: {error_msg}")
            training_record.logs = "\n".join(training_logs)
            training_record.status = "failed"
            training_record.end_time = datetime.now()
            model.status = "failed"
            db.commit()
            db.close()
            return
        
        # 加载数据
        seq_len = 1
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在加载数据...")
        training_record.logs = "\n".join(training_logs)
        db.commit()
        
        try:
            print(f"[TRAINING] 开始加载数据文件: {mat_file_path}")
            data = func.SeversonBattery(str(mat_file_path), seq_len=seq_len)
            print(f"[TRAINING] 数据加载成功")
        except Exception as e:
            error_msg = f"数据加载失败: {str(e)}"
            print(f"[TRAINING ERROR] {error_msg}")
            import traceback
            print(traceback.format_exc())
            training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: {error_msg}")
            training_record.logs = "\n".join(training_logs)
            training_record.status = "failed"
            training_record.end_time = datetime.now()
            model.status = "failed"
            db.commit()
            db.close()
            return
        
        # 根据选择的电池组创建数据集
        # 注意：这里需要根据实际的battery_ids调整数据分割逻辑
        # 简化处理：使用默认的数据分割方式
        perc_val = dataset_split.get("validation_ratio", 0.2)
        
        # 创建数据分割（这里简化处理，实际应该根据battery_ids）
        # 由于battery_ids可能包含不同数据集的电池，需要特殊处理
        inputs_dict, targets_dict = func.create_chosen_cells(
            data,
            idx_cells_train=battery_ids,
            idx_cells_test=[],
            perc_val=perc_val
        )
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 数据加载完成")
        
        # 准备训练数据
        inputs_train = inputs_dict['train'].to(device)
        inputs_val = inputs_dict['val'].to(device) if 'val' in inputs_dict else None
        targets_train = targets_dict['train'][:, :, 0:1].to(device)  # SoH预测
        targets_val = targets_dict['val'][:, :, 0:1].to(device) if 'val' in targets_dict else None
        
        # 标准化
        inputs_train_std, mean_inputs_train, std_inputs_train = func.standardize_tensor(
            inputs_train, mode='fit'
        )
        targets_train_std, mean_targets_train, std_targets_train = func.standardize_tensor(
            targets_train, mode='fit'
        )
        # 确保归一化参数无梯度
        mean_targets_train = mean_targets_train.detach()
        std_targets_train = std_targets_train.detach()
        
        if inputs_val is not None:
            inputs_val_std, _, _ = func.standardize_tensor(
                inputs_val, mode='transform',
                mean=mean_inputs_train, std=std_inputs_train
            )
            targets_val_std, _, _ = func.standardize_tensor(
                targets_val, mode='transform',
                mean=mean_targets_train, std=std_targets_train
            )
        
        # 根据算法类型构建模型
        inputs_dim = inputs_train.shape[2]
        outputs_dim = 1
        
        if algorithm_type == "baseline":
            # Baseline模型：使用DataDrivenNN（根据SoH_CaseA_Baseline.py）
            num_layers = network_params.get("layers", 2)
            num_neurons = network_params.get("nodes", 64)
            layers = [num_neurons] * num_layers
            
            # 使用functions模块中的DataDrivenNN模型
            model_net = func.DataDrivenNN(
                seq_len=seq_len,
                inputs_dim=inputs_dim,
                outputs_dim=outputs_dim,
                layers=layers,
                scaler_inputs=(mean_inputs_train, std_inputs_train),
                scaler_targets=(mean_targets_train, std_targets_train),
            ).to(device)
            
        elif algorithm_type == "bilstm":
            # BiLSTM模型（根据SOH_CaseA_BiLSTM.py）
            hidden_dim = network_params.get("nodes", 64)
            num_layers = network_params.get("layers", 2)
            
            class BiLSTMModel(torch.nn.Module):
                def __init__(self, input_dim, hidden_dim, output_dim, num_layers):
                    super(BiLSTMModel, self).__init__()
                    self.lstm = torch.nn.LSTM(
                        input_dim, hidden_dim, num_layers=num_layers,
                        batch_first=True, bidirectional=True
                    )
                    self.fc = torch.nn.Linear(hidden_dim * 2, output_dim)
                
                def forward(self, x):
                    out, _ = self.lstm(x)
                    out = self.fc(out[:, -1, :])
                    return out.unsqueeze(1)
            
            # 禁用cuDNN以避免版本不兼容问题（如SOH_CaseA_BiLSTM.py第121行）
            torch.backends.cudnn.enabled = False
            model_net = BiLSTMModel(inputs_dim, hidden_dim, outputs_dim, num_layers).to(device)
            
        elif algorithm_type == "deepphm":
            # DeepHPM模型（根据SoH_CaseA_DeepHPM_Sum.py）
            num_layers = network_params.get("layers", 4)
            num_neurons = network_params.get("nodes", 64)
            layers = [num_neurons] * num_layers
            
            # 从 settings 加载动态输入配置
            # 根据 SoH_CaseA_DeepHPM_Sum.py 和 settings_SoH_CaseA.pth
            inputs_dynamical = 's_norm, t_norm'  # 动态模型输入变量
            inputs_dim_dynamical = 'inputs_dim'  # 动态模型输入维度
            
            # 使用functions模块中的DeepHPMNN模型
            # 禁用cuDNN以确保可重现性（如SoH_CaseA_DeepHPM_Sum.py第114行）
            torch.backends.cudnn.enabled = False
            
            model_net = func.DeepHPMNN(
                seq_len=seq_len,
                inputs_dim=inputs_dim,
                outputs_dim=outputs_dim,
                layers=layers,
                scaler_inputs=(mean_inputs_train, std_inputs_train),
                scaler_targets=(mean_targets_train, std_targets_train),
                inputs_dynamical=inputs_dynamical,
                inputs_dim_dynamical=inputs_dim_dynamical
            ).to(device)
        else:
            raise ValueError(f"不支持的算法类型: {algorithm_type}")
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 模型构建完成")
        
        # 设置优化器和损失函数（根据三个训练脚本）
        learning_rate = hyperparams.get("learning_rate", 0.001)
        optimizer_name = hyperparams.get("optimizer", "adam").lower()
        
        # 初始化不确定性参数（DeepHPM和Baseline需要，BiLSTM不需要）
        log_sigma_u = torch.zeros(()).to(device)
        log_sigma_f = torch.zeros(()).to(device)
        log_sigma_f_t = torch.zeros(()).to(device)
        
        # 根据算法类型选择损失函数
        if algorithm_type == "baseline":
            # Baseline使用My_loss，模式为'Baseline'（仅数据拟合损失）
            criterion = func.My_loss(mode='Baseline')
            params = [p for p in model_net.parameters()]
        elif algorithm_type == "bilstm":
            # BiLSTM使用MSELoss
            criterion = torch.nn.MSELoss()
            params = [p for p in model_net.parameters()]
        elif algorithm_type == "deepphm":
            # DeepHPM使用My_loss，模式为'Sum'（数据拟合+物理约束+时间导数）
            criterion = func.My_loss(mode='Sum')
            params = [p for p in model_net.parameters()]
        else:
            criterion = torch.nn.MSELoss()
            params = [p for p in model_net.parameters()]
        
        # 创建优化器
        if optimizer_name == "adam":
            optimizer = torch.optim.Adam(params, lr=learning_rate)
        elif optimizer_name == "sgd":
            optimizer = torch.optim.SGD(params, lr=learning_rate)
        else:
            optimizer = torch.optim.Adam(params, lr=learning_rate)
        
        # 创建学习率调度器（根据训练脚本）
        step_size = hyperparams.get("step_size", 30)
        gamma = hyperparams.get("gamma", 0.1)
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=step_size, gamma=gamma)
        
        # 训练循环（根据三个训练脚本）
        batch_size = hyperparams.get("batch_size", 32)
        num_epochs = hyperparams.get("epochs", 100)
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始训练，共{num_epochs}轮")
        
        # 统一算法名（历史上前端/脚本里存在 deepphm / deephpm 两种拼写）
        algorithm_type = (algorithm_type or "").lower().strip()
        is_deephpm = algorithm_type in {"deepphm", "deephpm"}

        # 创建训练数据加载器
        if algorithm_type == "baseline" or is_deephpm:
            # Baseline和DeepHPM使用TensorDataset
            train_dataset = func.TensorDataset(inputs_train_std, targets_train_std)
            train_loader = torch.utils.data.DataLoader(
                train_dataset, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True
            )
        else:
            # BiLSTM使用标准TensorDataset
            train_dataset = torch.utils.data.TensorDataset(inputs_train_std, targets_train_std)
            train_loader = torch.utils.data.DataLoader(
                train_dataset, batch_size=batch_size, shuffle=True
            )
        
        best_val_loss = float('inf')
        train_losses = []
        val_losses = []
        
        # 使用functions模块的train函数（对于Baseline和DeepHPM）
        if algorithm_type == "baseline" or is_deephpm:
            # 定义日志回调函数，用于在每个epoch结束时写入训练记录，方便前端实时显示进度
            def epoch_log_callback(epoch_idx: int, train_loss: float, val_loss: float | None):
                # 检查是否需要停止训练
                if running_tasks.get(training_record_id, {}).get("should_stop", False):
                    print(f"训练任务 {training_record_id} 被用户停止")
                    return True  # 返回true表示停止训练
                
                log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Epoch {epoch_idx + 1}/{num_epochs}, Train Loss: {train_loss:.6f}"
                if val_loss is not None:
                    log_msg += f", Val Loss: {val_loss:.6f}"
                
                # 每10轮计算一次评估指标
                if (epoch_idx + 1) % 10 == 0 and inputs_val_std is not None and targets_val_std is not None:
                    try:
                        model_net.eval()
                        # 对于Baseline和DeepHPM，前向里可能会用到 autograd.grad，因此不能使用 torch.no_grad()
                        if algorithm_type == "baseline" or is_deephpm:
                            # DeepHPMNN.forward 会对 inputs 切片为 s/t 并做 autograd.grad，
                            # 这里必须保证 inputs 是叶子张量且 requires_grad=True
                            inputs_val_grad = inputs_val_std.detach().clone().requires_grad_(True)
                            out = model_net(inputs=inputs_val_grad)
                            # Baseline/DeepHPM 在本项目里 forward 返回 (U, F, F_t)
                            val_pred_std = out[0].detach()
                        else:
                            with torch.no_grad():
                                val_pred_std = model_net(inputs_val_std)
                        
                        # 反归一化预测结果
                        val_pred = (val_pred_std * std_targets_train + mean_targets_train).detach()
                        val_actual = targets_val.detach()  # 使用原始的验证集数据（未归一化），并确保无梯度
                        
                        # 将容量损失转换为健康状态（SoH）
                        val_pred_soh = (1. - val_pred).detach()
                        val_actual_soh = (1. - val_actual).detach()
                        
                        # 计算验证集RMSPE
                        val_rmspe = torch.sqrt(torch.mean(((val_pred_soh - val_actual_soh) / (val_actual_soh + 1e-8)) ** 2)).item()
                        # 计算验证集MSE
                        val_mse = torch.mean((val_pred_soh - val_actual_soh) ** 2).item()
                        # 计算验证集MAE
                        val_mae = torch.mean(torch.abs(val_pred_soh - val_actual_soh)).item()
                        # 计算验证集R²
                        SS_res_val = torch.sum((val_pred_soh - val_actual_soh) ** 2).detach()
                        SS_tot_val = torch.sum((val_actual_soh - torch.mean(val_actual_soh)) ** 2).detach()
                        if SS_tot_val > 1e-8:  # 避免除以0
                            val_r2 = (1 - (SS_res_val / SS_tot_val)).item()
                        else:
                            val_r2 = 0.0
                        
                        # 添加评估指标到日志
                        log_msg += f", RMSPE: {val_rmspe:.6f}, MSE: {val_mse:.6f}, MAE: {val_mae:.6f}, R2: {val_r2:.6f}"
                        model_net.train()
                    except Exception as e:
                        # 如果计算失败，记录详细错误信息
                        import traceback
                        print(f"Warning: Failed to calculate metrics at epoch {epoch_idx + 1}: {e}")
                        print(f"Error details: {traceback.format_exc()}")
                        return None  # 返回None表示继续训练
                
                training_logs.append(log_msg)
                training_record.logs = "\n".join(training_logs)
                db.commit()

            # 使用functions.train函数进行训练（与训练脚本一致）
            model_net, results_epoch = func.train(
                num_epoch=num_epochs,
                batch_size=batch_size,
                train_loader=train_loader,
                num_slices_train=inputs_train_std.shape[0],
                inputs_val=inputs_val_std,
                targets_val=targets_val_std,
                model=model_net,
                optimizer=optimizer,
                scheduler=scheduler,
                criterion=criterion,
                log_sigma_u=log_sigma_u,
                log_sigma_f=log_sigma_f,
                log_sigma_f_t=log_sigma_f_t,
                log_callback=epoch_log_callback
            )
            
            # 从results_epoch提取损失值（注意键名与functions.train中保持一致）
            train_losses = []
            val_losses = []
            if results_epoch:
                if 'loss_train' in results_epoch:
                    # 转成 Python float 列表，便于日志和前端使用
                    loss_train_tensor = results_epoch['loss_train']
                    train_losses = [float(v) for v in loss_train_tensor.detach().cpu().numpy().tolist()]
                if 'loss_val' in results_epoch:
                    loss_val_tensor = results_epoch['loss_val']
                    val_losses = [float(v) for v in loss_val_tensor.detach().cpu().numpy().tolist()]
                    if len(val_losses) > 0:
                        best_val_loss = min(val_losses)
            
            # 记录训练日志（每个epoch一条，方便前端画曲线）
            for epoch in range(len(train_losses)):
                log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Epoch {epoch+1}/{num_epochs}, Train Loss: {train_losses[epoch]:.6f}"
                if epoch < len(val_losses):
                    log_msg += f", Val Loss: {val_losses[epoch]:.6f}"
                training_logs.append(log_msg)
                training_record.logs = "\n".join(training_logs)
                db.commit()
        else:
            # BiLSTM使用标准训练循环
            for epoch in range(num_epochs):
                # 检查是否需要停止训练
                if running_tasks.get(training_record_id, {}).get("should_stop", False):
                    print(f"训练任务 {training_record_id} 被用户停止")
                    training_record.status = "stopped"
                    if model:
                        model.status = "stopped"
                    db.commit()
                    break
                
                # 训练
                model_net.train()
                epoch_train_loss = 0.0
                for batch_inputs, batch_targets in train_loader:
                    optimizer.zero_grad()
                    outputs = model_net(batch_inputs)
                    loss = criterion(outputs, batch_targets)
                    loss.backward()
                    optimizer.step()
                    epoch_train_loss += loss.item()
                
                epoch_train_loss /= len(train_loader)
                train_losses.append(epoch_train_loss)
                
                # 验证
                if inputs_val_std is not None:
                    model_net.eval()
                    with torch.no_grad():
                        val_outputs = model_net(inputs_val_std)
                        val_loss = criterion(val_outputs, targets_val_std).item()
                        val_losses.append(val_loss)
                        
                        if val_loss < best_val_loss:
                            best_val_loss = val_loss
                
                # 更新学习率
                scheduler.step()
                
                # 每10轮记录一次日志
                if (epoch + 1) % 10 == 0:
                    log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Epoch {epoch+1}/{num_epochs}, Train Loss: {epoch_train_loss:.6f}"
                    if inputs_val_std is not None:
                        log_msg += f", Val Loss: {val_loss:.6f}"
                    
                    # 计算评估指标（每10轮计算一次）
                    with torch.no_grad():
                        model_net.eval()
                        val_outputs_std = model_net(inputs_val_std)
                        
                        # 反归一化预测结果
                        val_outputs = (val_outputs_std * std_targets_train + mean_targets_train).detach()
                        val_actual = targets_val.detach()  # 使用原始的验证集数据，确保无梯度
                        
                        # 将容量损失转换为健康状态（SoH）
                        val_pred_soh = (1. - val_outputs).detach()
                        val_actual_soh = (1. - val_actual).detach()
                        
                        # 计算验证集RMSPE
                        val_rmspe = torch.sqrt(torch.mean(((val_pred_soh - val_actual_soh) / (val_actual_soh + 1e-8)) ** 2)).item()
                        # 计算验证集MSE
                        val_mse = torch.mean((val_pred_soh - val_actual_soh) ** 2).item()
                        # 计算验证集MAE
                        val_mae = torch.mean(torch.abs(val_pred_soh - val_actual_soh)).item()
                        # 计算验证集R²
                        SS_res_val = torch.sum((val_pred_soh - val_actual_soh) ** 2).detach()
                        SS_tot_val = torch.sum((val_actual_soh - torch.mean(val_actual_soh)) ** 2).detach()
                        if SS_tot_val > 1e-8:  # 避免除以0
                            val_r2 = (1 - (SS_res_val / SS_tot_val)).item()
                        else:
                            val_r2 = 0.0
                        
                        # 添加评估指标到日志
                        log_msg += f", RMSPE: {val_rmspe:.6f}, MSE: {val_mse:.6f}, MAE: {val_mae:.6f}, R2: {val_r2:.6f}"
                        model_net.train()
                    
                    training_logs.append(log_msg)
                    
                    # 更新数据库中的训练日志
                    training_record.logs = "\n".join(training_logs)
                    db.commit()
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 训练完成")
        
        # 保存模型文件
        results_dir = project_root / "results"
        results_dir.mkdir(exist_ok=True)
        model_filename = f"SoH_{algorithm_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pth"
        model_path = results_dir / model_filename
        
        torch.save({
            'model_state_dict': model_net.state_dict(),
            'model_architecture': network_params,
            'hyperparameters': hyperparams,
            'mean_inputs': mean_inputs_train.cpu().numpy(),
            'std_inputs': std_inputs_train.cpu().numpy(),
            'mean_targets': mean_targets_train.cpu().numpy(),
            'std_targets': std_targets_train.cpu().numpy(),
            'train_losses': train_losses,
            'val_losses': val_losses,
        }, str(model_path))
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 模型已保存: {model_path}")
        
        # 计算最终评估指标（根据三个训练脚本）
        model_net.eval()
        
        # 对于DeepHPM模型，需要启用梯度跟踪（因为forward方法内部使用torch.autograd.grad）
        if algorithm_type == "deepphm":
            # DeepHPM需要计算物理损失，必须启用梯度
            inputs_train_std_grad = inputs_train_std.detach().requires_grad_(True)
            train_pred_std, _, _ = model_net(inputs=inputs_train_std_grad)
            train_pred_std = train_pred_std.detach()  # 评估后分离梯度
            
            # 反归一化预测结果
            train_pred = train_pred_std * std_targets_train + mean_targets_train
            train_actual = targets_train  # 使用原始的训练集数据
            
            # 将容量损失转换为健康状态（SoH）
            train_pred_soh = 1. - train_pred
            train_actual_soh = 1. - train_actual
            
            # 计算训练集RMSPE（相对均方根百分比误差）
            train_rmspe = torch.sqrt(torch.mean(((train_pred_soh - train_actual_soh) / train_actual_soh) ** 2)).item()
            # 计算训练集MSE（均方误差）
            train_mse = torch.mean((train_pred_soh - train_actual_soh) ** 2).item()
            # 计算训练集MAE（平均绝对误差）
            train_mae = torch.mean(torch.abs(train_pred_soh - train_actual_soh)).item()
            # 计算训练集R²
            SS_res_train = torch.sum((train_pred_soh - train_actual_soh) ** 2)
            SS_tot_train = torch.sum((train_actual_soh - torch.mean(train_actual_soh)) ** 2)
            train_r2 = (1 - (SS_res_train / SS_tot_train)).item()
            
            metrics_dict = {
                "train": {
                    "rmspe": float(train_rmspe),
                    "mse": float(train_mse),
                    "mae": float(train_mae),
                    "r2": float(train_r2)
                }
            }
        elif algorithm_type == "baseline":
            # Baseline模型（DataDrivenNN）的forward方法内部也使用torch.autograd.grad，需要启用梯度
            inputs_train_std_grad = inputs_train_std.detach().requires_grad_(True)
            train_pred_std, _, _ = model_net(inputs=inputs_train_std_grad)
            train_pred_std = train_pred_std.detach()  # 评估后分离梯度
            
            # 反归一化预测结果
            train_pred = train_pred_std * std_targets_train + mean_targets_train
            train_actual = targets_train.detach()  # 使用原始的训练集数据，确保无梯度
            
            # 将容量损失转换为健康状态（SoH）
            train_pred_soh = 1. - train_pred
            train_actual_soh = 1. - train_actual
            
            # 计算训练集RMSPE（相对均方根百分比误差）
            train_rmspe = torch.sqrt(torch.mean(((train_pred_soh - train_actual_soh) / train_actual_soh) ** 2)).item()
            # 计算训练集MSE（均方误差）
            train_mse = torch.mean((train_pred_soh - train_actual_soh) ** 2).item()
            # 计算训练集MAE（平均绝对误差）
            train_mae = torch.mean(torch.abs(train_pred_soh - train_actual_soh)).item()
            # 计算训练集R²
            SS_res_train = torch.sum((train_pred_soh - train_actual_soh) ** 2)
            SS_tot_train = torch.sum((train_actual_soh - torch.mean(train_actual_soh)) ** 2)
            train_r2 = (1 - (SS_res_train / SS_tot_train)).item()
            
            metrics_dict = {
                "train": {
                    "rmspe": float(train_rmspe),
                    "mse": float(train_mse),
                    "mae": float(train_mae),
                    "r2": float(train_r2)
                }
            }
        else:
            with torch.no_grad():
                # BiLSTM使用标准前向传播
                train_pred_std = model_net(inputs_train_std)
                
                # 反归一化预测结果
                train_pred = train_pred_std * std_targets_train + mean_targets_train
                train_actual = targets_train.detach()  # 使用原始的训练集数据，确保无梯度
                
                # 将容量损失转换为健康状态（SoH）
                train_pred_soh = 1. - train_pred
                train_actual_soh = 1. - train_actual
            
            # 计算训练集RMSPE（相对均方根百分比误差）
            train_rmspe = torch.sqrt(torch.mean(((train_pred_soh - train_actual_soh) / train_actual_soh) ** 2)).item()
            # 计算训练集MSE（均方误差）
            train_mse = torch.mean((train_pred_soh - train_actual_soh) ** 2).item()
            # 计算训练集MAE（平均绝对误差）
            train_mae = torch.mean(torch.abs(train_pred_soh - train_actual_soh)).item()
            # 计算训练集R²
            SS_res_train = torch.sum((train_pred_soh - train_actual_soh) ** 2)
            SS_tot_train = torch.sum((train_actual_soh - torch.mean(train_actual_soh)) ** 2)
            train_r2 = (1 - (SS_res_train / SS_tot_train)).item()
            
            metrics_dict = {
                "train": {
                    "rmspe": float(train_rmspe),
                    "mse": float(train_mse),
                    "mae": float(train_mae),
                    "r2": float(train_r2)
                }
            }
            
        # 验证集评估
        if inputs_val_std is not None:
            if algorithm_type == "deepphm":
                # DeepHPM需要梯度跟踪
                inputs_val_std_grad = inputs_val_std.detach().requires_grad_(True)
                val_pred_std, _, _ = model_net(inputs=inputs_val_std_grad)
                val_pred_std = val_pred_std.detach()
                
                # 反归一化预测结果
                val_pred = val_pred_std * std_targets_train + mean_targets_train
                val_actual = targets_val  # 使用原始的验证集数据
                
                val_pred_soh = 1. - val_pred
                val_actual_soh = 1. - val_actual
                
                # 计算验证集RMSPE
                val_rmspe = torch.sqrt(torch.mean(((val_pred_soh - val_actual_soh) / (val_actual_soh + 1e-8)) ** 2)).item()
                # 计算验证集MSE
                val_mse = torch.mean((val_pred_soh - val_actual_soh) ** 2).item()
                # 计算验证集MAE
                val_mae = torch.mean(torch.abs(val_pred_soh - val_actual_soh)).item()
                # 计算验证集R²
                SS_res_val = torch.sum((val_pred_soh - val_actual_soh) ** 2)
                SS_tot_val = torch.sum((val_actual_soh - torch.mean(val_actual_soh)) ** 2)
                val_r2 = (1 - (SS_res_val / SS_tot_val)).item()
                
                metrics_dict["validation"] = {
                    "rmspe": float(val_rmspe),
                    "mse": float(val_mse),
                    "mae": float(val_mae),
                    "r2": float(val_r2)
                }
            elif algorithm_type == "baseline":
                # Baseline模型（DataDrivenNN）的forward方法内部也使用torch.autograd.grad，需要启用梯度
                inputs_val_std_grad = inputs_val_std.detach().requires_grad_(True)
                val_pred_std, _, _ = model_net(inputs=inputs_val_std_grad)
                val_pred_std = val_pred_std.detach()  # 评估后分离梯度
                
                # 反归一化预测结果
                val_pred = val_pred_std * std_targets_train + mean_targets_train
                val_actual = targets_val.detach()  # 使用原始的验证集数据，确保无梯度
                
                val_pred_soh = 1. - val_pred
                val_actual_soh = 1. - val_actual
                
                # 计算验证集RMSPE
                val_rmspe = torch.sqrt(torch.mean(((val_pred_soh - val_actual_soh) / val_actual_soh) ** 2)).item()
                # 计算验证集MSE
                val_mse = torch.mean((val_pred_soh - val_actual_soh) ** 2).item()
                # 计算验证集MAE
                val_mae = torch.mean(torch.abs(val_pred_soh - val_actual_soh)).item()
                # 计算验证集R²
                SS_res_val = torch.sum((val_pred_soh - val_actual_soh) ** 2)
                SS_tot_val = torch.sum((val_actual_soh - torch.mean(val_actual_soh)) ** 2)
                val_r2 = (1 - (SS_res_val / SS_tot_val)).item()
                
                metrics_dict["validation"] = {
                    "rmspe": float(val_rmspe),
                    "mse": float(val_mse),
                    "mae": float(val_mae),
                    "r2": float(val_r2)
                }
            else:  # BiLSTM
                with torch.no_grad():
                    val_pred_std = model_net(inputs_val_std)
                    
                    # 反归一化预测结果
                    val_pred = val_pred_std * std_targets_train + mean_targets_train
                    val_actual = targets_val.detach()  # 使用原始的验证集数据，确保无梯度
                    
                    val_pred_soh = 1. - val_pred
                    val_actual_soh = 1. - val_actual
                
                # 计算验证集RMSPE
                val_rmspe = torch.sqrt(torch.mean(((val_pred_soh - val_actual_soh) / val_actual_soh) ** 2)).item()
                # 计算验证集MSE
                val_mse = torch.mean((val_pred_soh - val_actual_soh) ** 2).item()
                # 计算验证集MAE
                val_mae = torch.mean(torch.abs(val_pred_soh - val_actual_soh)).item()
                # 计算验证集R²
                SS_res_val = torch.sum((val_pred_soh - val_actual_soh) ** 2)
                SS_tot_val = torch.sum((val_actual_soh - torch.mean(val_actual_soh)) ** 2)
                val_r2 = (1 - (SS_res_val / SS_tot_val)).item()
                
                metrics_dict["validation"] = {
                    "rmspe": float(val_rmspe),
                    "mse": float(val_mse),
                    "mae": float(val_mae),
                    "r2": float(val_r2)
                }
        
        # 更新模型记录
        model.model_path = str(model_path.relative_to(project_root))
        model.checkpoint_path = str(model_path.relative_to(project_root))
        model.model_size = model_path.stat().st_size
        model.status = "completed"
        model.metrics = json.dumps(metrics_dict)
        model.network_params = json.dumps(network_params)
        model.input_shape = json.dumps({
            "batch_size": None,
            "sequence_length": seq_len,
            "features": inputs_dim
        })
        model.output_shape = json.dumps({
            "batch_size": None,
            "sequence_length": seq_len,
            "features": outputs_dim
        })
        model.trained_at = datetime.now()
        
        # 更新训练记录
        training_record.status = "completed"
        training_record.end_time = datetime.now()
        training_record.duration = (training_record.end_time - training_record.start_time).total_seconds() if training_record.start_time else None
        training_record.final_loss = train_losses[-1] if len(train_losses) > 0 else None
        training_record.best_val_loss = best_val_loss if best_val_loss != float('inf') else None
        training_record.train_metrics = json.dumps(metrics_dict.get("train", {}))
        training_record.validation_metrics = json.dumps(metrics_dict.get("validation", {}))
        training_record.logs = "\n".join(training_logs)
        
        db.commit()
        
        training_logs.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 模型信息已保存到数据库")
        
    except Exception as e:
        import traceback
        error_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 训练失败: {str(e)}\n{traceback.format_exc()}"
        
        try:
            # 重新查询以获取最新的训练记录和模型
            training_record = db.query(TrainingRecord).filter(
                TrainingRecord.id == training_record_id
            ).first()
            model = db.query(Model).filter(Model.id == model_id).first()
            
            if training_record:
                training_record.logs = (training_record.logs or "") + "\n" + error_msg
                training_record.status = "failed"
                training_record.end_time = datetime.now()
                db.commit()
            
            if model:
                model.status = "failed"
                db.commit()
        except Exception as db_error:
            print(f"Error updating database: {db_error}")
        
        print(f"Training failed: {error_msg}")
    finally:
        # 清理训练任务
        if training_record_id in running_tasks:
            del running_tasks[training_record_id]
            print(f"清理训练任务 {training_record_id}")
        
        # 关闭数据库session
        try:
            db.close()
        except:
            pass


@router.put("/{task_id}")
async def update_training_task(
    task_id: int,
    task_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新训练任务（例如：停止训练）
    """
    training_record = db.query(TrainingRecord).filter(
        TrainingRecord.id == task_id,
        TrainingRecord.user_id == current_user.id
    ).first()
    
    if not training_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练任务不存在"
        )
    
    # 可以在这里实现停止训练的逻辑
    if task_data.get("action") == "stop":
        # 设置停止标志
        if task_id in running_tasks:
            running_tasks[task_id]["should_stop"] = True
            print(f"设置训练任务 {task_id} 的停止标志")
        
        # 更新数据库状态
        training_record.status = "stopped"
        if training_record.model:
            training_record.model.status = "stopped"
        db.commit()
        
        return {
            "success": True,
            "message": "训练任务已停止"
        }
    
    return {"message": "更新训练任务"}


@router.delete("/{task_id}")
async def delete_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除训练任务
    """
    training_record = db.query(TrainingRecord).filter(
        TrainingRecord.id == task_id,
        TrainingRecord.user_id == current_user.id
    ).first()
    
    if not training_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练任务不存在"
        )
    
    db.delete(training_record)
    db.commit()
    
    return {
        "success": True,
        "message": "训练任务已删除"
    }
