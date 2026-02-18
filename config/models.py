"""
DiscoverLatest 洞察運算 - Gemini 模型設定
所有 AI 呼叫只允許使用此處定義的模型名稱
"""

# 固定模型名稱（禁止散落在各處）
MODEL_GROUNDING = "gemini-2.5-flash"
MODEL_FINAL = "gemini-3-flash-preview"
MODEL_DEXTER = "gemini-2.5-flash"


def get_model_list():
    """取得所有允許使用的模型清單"""
    return [MODEL_GROUNDING, MODEL_FINAL, MODEL_DEXTER]


async def validate_models_on_startup(genai_client):
    """
    啟動時驗證模型可用性
    不存在則回傳錯誤訊息，供 Admin Console 顯示
    
    Args:
        genai_client: Google Generative AI client
        
    Returns:
        dict: {"valid": bool, "errors": list[str]}
    """
    errors = []
    
    try:
        # 取得可用模型清單
        available_models = []
        for model in genai_client.list_models():
            available_models.append(model.name)
        
        # 驗證必要模型是否存在
        for required_model in get_model_list():
            model_full_name = f"models/{required_model}"
            if model_full_name not in available_models:
                errors.append(f"模型不可用: {required_model}")
                
    except Exception as e:
        errors.append(f"無法驗證模型: {str(e)}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
