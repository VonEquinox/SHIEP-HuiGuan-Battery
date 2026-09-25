from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_datasets():
    """
    获取数据集列表
    """
    return {"message": "获取数据集列表"}


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: int):
    """
    获取指定数据集
    """
    return {"message": f"获取数据集 {dataset_id}"}


@router.post("/")
async def create_dataset():
    """
    创建数据集
    """
    return {"message": "创建数据集"}


@router.put("/{dataset_id}")
async def update_dataset(dataset_id: int):
    """
    更新数据集
    """
    return {"message": f"更新数据集 {dataset_id}"}


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: int):
    """
    删除数据集
    """
    return {"message": f"删除数据集 {dataset_id}"}