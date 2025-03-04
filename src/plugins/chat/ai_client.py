import httpx
import time
import asyncio
import os
from typing import List, Dict, Any, Optional, Union, Tuple
from nonebot.log import logger
from .lifecycle import ResourceManager
from .config import config, Config


class AIRequestError(Exception):
    """AI请求异常"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        self.response_data = response_data
        super().__init__(self.message)

    def __str__(self):
        base_message = self.message
        if self.status_code:
            base_message += f" (状态码: {self.status_code})"
        return base_message


class AIClient:
    """AI接口客户端封装"""

    def __init__(self):
        self.timeout = 30.0
        self.max_retries = 2

    async def _get_api_info(self) -> tuple:
        """异步获取API信息"""
        config = await ResourceManager.get("config")
        if not config:
            raise AIRequestError("无法获取配置")
        return config.get_current_api_info()

    async def _make_request(
        self, endpoint: str, payload: Dict[str, Any], retry_count: int = 0
    ) -> Dict[str, Any]:
        """发送请求到AI服务"""
        api_base, api_key = await self._get_api_info()
        if not api_base or not api_key:
            raise AIRequestError("API配置不完整")

        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"{api_base}/{endpoint.lstrip('/')}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            # 处理HTTP错误
            error_msg = f"API请求失败"
            status_code = e.response.status_code
            response_data = None

            try:
                response_data = e.response.json()
                if "error" in response_data:
                    error_msg = f"API错误: {response_data['error'].get('message', str(response_data))}"
            except:
                pass

            # 对于某些状态码尝试重试（如429太多请求、503服务不可用）
            if (
                status_code in (429, 500, 502, 503, 504)
                and retry_count < self.max_retries
            ):
                return await self._make_request(endpoint, payload, retry_count + 1)

            raise AIRequestError(
                error_msg,
                status_code=status_code,
                original_error=e,
                response_data=response_data,
            )

        except httpx.RequestError as e:
            # 处理请求异常（如超时、连接问题）
            if retry_count < self.max_retries:
                return await self._make_request(endpoint, payload, retry_count + 1)

            raise AIRequestError(f"请求异常: {str(e)}", original_error=e)

        except Exception as e:
            # 处理其他异常
            raise AIRequestError(f"未知错误: {str(e)}", original_error=e)

    async def get_chat_completion(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> str:
        """获取聊天回复"""
        config = await ResourceManager.get("config")
        if not config:
            return "配置未就绪，请稍后再试"

        if "model" not in kwargs or kwargs["model"] is None:
            kwargs["model"] = config.get_random_model()

        payload = {
            "model": kwargs["model"],
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
        }

        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        try:
            response = await self._make_request("chat/completions", payload)
            return response["choices"][0]["message"]["content"]
        except AIRequestError as e:
            # 如果是模型相关错误且允许重试不同模型
            if (
                kwargs.get("retry_different_model", True)
                and e.status_code in (400, 404)
                and kwargs["model"]
            ):
                # 尝试使用不同模型
                try:
                    new_model = next(
                        (
                            m
                            for m in config.response.model_probabilities.keys()
                            if m != kwargs["model"]
                        ),
                        None,
                    )
                    if new_model:
                        return await self.get_chat_completion(
                            messages,
                            model=new_model,
                            temperature=kwargs.get("temperature", 0.7),
                            max_tokens=kwargs.get("max_tokens"),
                            retry_different_model=False,
                        )
                except Exception:
                    pass  # 如果重试失败，返回原始错误

            return f"AI回复失败: {str(e)}"
        except Exception as e:
            return f"处理AI回复时出错: {str(e)}"


# 初始化AI客户端
async def initialize_ai_client():
    client = AIClient()
    ResourceManager.set("ai_client", client)


# 注册AI客户端，依赖于配置
ResourceManager.add_to_registry(
    name="ai_client", dependencies=["config"], initializer=initialize_ai_client
)


async def get_ai_client() -> Optional[AIClient]:
    """获取AI客户端实例"""
    return await ResourceManager.get("ai_client")


# 简化的API
async def get_ai_response(message: str) -> str:
    """获取AI回复"""
    client = await get_ai_client()
    if not client:
        return "AI服务未就绪，请稍后再试"
    return await client.get_chat_completion([{"role": "user", "content": message}])
