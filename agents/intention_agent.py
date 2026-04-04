from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List
import json
import logging
from utils.skill_loader import SkillLoader

logger = logging.getLogger(__name__)

class IntentionAgent(AgentBase):
    """意图识别智能体（IntentionRecognitionAgent）"""