import re
import time
import random
from typing import List, Tuple, Optional
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message


class MessageProcessor:
    """
    消息处理工具类 - 专为伪装成普通群员设计
    不包含明显的机器人特征，避免暴露身份
    """

    # 上次回复时间记录 (模拟自然间隔)
    _last_reply_time = {}

    # 对话状态 (模拟人类对话连贯性)
    _conversation_state = {}

    @classmethod
    def extract_text(cls, event: GroupMessageEvent) -> str:
        """提取消息文本"""
        text = ""
        for seg in event.message:
            if seg.type == "text":
                text += seg.data["text"]

        # 简单清理文本
        return text.strip()

    @classmethod
    def is_at_bot(cls, event: GroupMessageEvent, bot_qq: str) -> bool:
        """检查消息是否@机器人"""
        return any(
            seg.type == "at" and str(seg.data.get("qq", "")) == str(bot_qq)
            for seg in event.message
        )

    @classmethod
    def should_reply(cls, text: str, is_at: bool, group_id: int, user_id: int) -> bool:
        """
        决定是否回复（模拟人类行为）
        根据内容相关性、@状态、最近回复时间等判断
        """
        current_time = time.time()
        key = f"{group_id}_{user_id}"

        # 如果被@，有较高概率回复
        if is_at:
            # 但也不是100%回复，偶尔装作"没看到"
            return random.random() < 0.95

        # 检查是否是对自己上次发言的回复
        is_relevant = cls._is_relevant_to_me(text, group_id)
        if is_relevant:
            return random.random() < 0.85

        # 避免频繁回复同一用户（模拟人类注意力分散）
        last_time = cls._last_reply_time.get(key, 0)
        if current_time - last_time < 300:  # 5分钟内
            return random.random() < 0.2

        # 在保持群内存在感的同时，不对每条消息都回复
        return random.random() < 0.1

    @classmethod
    def _is_relevant_to_me(cls, text: str, group_id: int) -> bool:
        """判断消息是否与机器人上次发言相关（简单实现）"""
        last_topic = cls._conversation_state.get(f"topic_{group_id}", "")
        if not last_topic:
            return False

        # 简单关键词匹配，实际应用中可能需要更复杂的相关性分析
        return any(keyword in text for keyword in last_topic.split())

    @classmethod
    def update_conversation_state(cls, group_id: int, user_id: int, text: str):
        """更新对话状态，记录回复时间"""
        cls._last_reply_time[f"{group_id}_{user_id}"] = time.time()

        # 提取可能的主题词作为上下文（简单实现）
        words = [w for w in text.split() if len(w) > 1]
        if words:
            # 随机选择几个词作为话题记忆
            topic_words = random.sample(words, min(3, len(words)))
            cls._conversation_state[f"topic_{group_id}"] = " ".join(topic_words)

    @classmethod
    def extract_images_and_text(cls, event: GroupMessageEvent) -> Tuple[List[str], str]:
        """提取消息中的图片和文本"""
        image_urls = []
        text_parts = []

        for seg in event.message:
            if seg.type == "text":
                text_parts.append(seg.data["text"])
            elif seg.type == "image" and "url" in seg.data:
                image_urls.append(seg.data["url"])

        return image_urls, "".join(text_parts).strip()

    @classmethod
    def add_human_touch(cls, text: str) -> str:
        """
        为回复添加人类特征
        - 偶尔添加错别字
        - 添加语气词
        - 随机使用不同标点符号
        """
        # 随机决定是否添加人类特征
        if random.random() < 0.3:
            # 偶尔添加半括号
            if random.random() < 0.4:
                text += "（"

            # 偶尔添加语气词
            if random.random() < 0.3:
                fillers = ["嗯", "啊", "呢", "吧", "啦", "哈", "哦"]
                position = random.randint(0, len(text))
                text = text[:position] + random.choice(fillers) + text[position:]

            # 偶尔替换标点
            if "。" in text and random.random() < 0.5:
                text = text.replace("。", "..." if random.random() < 0.5 else "！", 1)

        return text

    @classmethod
    def calculate_typing_delay(cls, text: str) -> float:
        """
        计算模拟打字延迟（秒）
        模拟人类打字速度
        """
        # 假设平均打字速度为每分钟200字
        char_per_second = 200 / 60

        # 基础延迟
        base_delay = max(1.0, len(text) / char_per_second)

        # 添加随机波动（模拟思考和打字不均匀）
        randomness = random.uniform(0.8, 1.2)

        # 长消息额外思考时间
        thinking_time = 0
        if len(text) > 20:
            thinking_time = random.uniform(1, 3)

        return base_delay * randomness + thinking_time

    @classmethod
    def should_correct_typo(cls) -> bool:
        """决定是否要"修正错别字"（模拟人类行为）"""
        return random.random() < 0.1

    @classmethod
    def make_correction(cls, message: Message) -> Message:
        """模拟人类纠正自己的错别字"""
        # 实现简单的纠错信息
        original_text = message.extract_plain_text()
        if not original_text:
            return message

        # 随机选择一个词"打错"然后纠正
        words = [w for w in original_text.split() if len(w) > 1]
        if not words:
            return message

        target_word = random.choice(words)
        correction = Message()
        correction.append(f"*{target_word}")

        return correction
