import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "储能电池寿命预测系统"
    HOST: str = "0.0.0.0"
    PORT: int = 5000
    RELOAD: bool = True
    
    # 数据库配置
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "mysql+pymysql://root:123456@localhost/power_soh"
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "False").lower() == "true"
    
    # JWT配置
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", 
        "your-secret-key-change-in-production"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # 模型配置
    MODEL_DIR: str = os.getenv("MODEL_DIR", "./models")
    DATASET_DIR: str = os.getenv("DATASET_DIR", "./datasets")
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "./logs/app.log")

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"  # 忽略未定义的环境变量
    )


settings = Settings()