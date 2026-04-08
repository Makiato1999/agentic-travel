"""
信息查询智能体 - 真实检索版
支持：天气（WeatherAPI.com）、网络搜索（DDGS，开启 safesearch + 结果过滤）
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List, Dict, Any
import json
import logging
import re
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

logger = logging.getLogger(__name__)

from config import WEATHER_API_CONFIG

# 尝试导入 duckduckgo_search (旧包名) 或 ddgs (新包名)
try:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logger.warning("ddgs not installed. Install with: pip install ddgs")

# 疑似垃圾/低质域名：多为 SEO 或不良站，不展示给用户
_SUSPICIOUS_DOMAIN_PATTERN = re.compile(
    r"\.(cc|tk|ml|ga|cf|gq|xyz|top|work|click|link|pw|buzz)(/|$)",
    re.I
)
# 域名主体若为长随机字母（无明显词），则过滤
_RANDOM_DOMAIN_PATTERN = re.compile(r"^[a-z0-9]{10,}$", re.I)

_COMMON_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "苏州",
    "天津", "重庆", "厦门", "青岛", "大连", "宁波", "无锡", "长沙", "郑州", "济南",
    "哈尔滨", "沈阳", "昆明", "合肥", "福州", "石家庄", "南昌", "贵阳", "太原", "南宁",
]


def _is_suspicious_url(url: str) -> bool:
    """过滤疑似垃圾/不良站点（如部分 .cc/.tk 等易被滥用的域名）。"""
    if not url or not url.startswith("http"):
        return True
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or ""
        # 去掉端口
        host = host.split(":")[0].lower()
        if not host:
            return True
        # 可疑 TLD
        if _SUSPICIOUS_DOMAIN_PATTERN.search(host):
            return True
        # 主域名部分（最后一个 . 之前若还有多段则取倒数第二段之前）
        parts = host.rsplit(".", 2)
        name = parts[0] if parts else ""
        if len(name) >= 10 and _RANDOM_DOMAIN_PATTERN.match(name):
            return True
        return False
    except Exception:
        return False


class InformationQueryAgent(AgentBase):
    """
    信息查询智能体（真实检索版）

    核心功能：
    - 天气查询 - 使用 WeatherAPI.com
    - 网络搜索 - 使用 DDGS（开启 safesearch，过滤可疑来源）

    注意：
    - 差旅标准查询由独立的 RAGKnowledgeAgent 处理
    """

    def __init__(self, name: str = "InformationQueryAgent", model=None, **kwargs):
        super().__init__()
        self.name = name
        self.model = model
        from utils.skill_loader import SkillLoader
        self.skill_loader = SkillLoader()

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        if x is None:
            return Msg(name=self.name, content=json.dumps({"query_success": False}), role="assistant")

        # 解析输入
        content = x.content if not isinstance(x, list) else x[-1].content
        context = {}

        if isinstance(content, str):
            try:
                data = json.loads(content)
                context = data.get("context", {})
                user_query = context.get("rewritten_query", "") or content
            except json.JSONDecodeError:
                user_query = content
        else:
            user_query = str(content)

        # 天气类问题优先走 WeatherAPI，避免通用搜索返回低质结果
        if self._is_weather_query(user_query):
            logger.info(f"Weather query: {user_query}")
            try:
                result = await self._weather_query(user_query, context=context)
                return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")
            except Exception as e:
                logger.warning(f"Weather query failed, fallback to web search: {e}")
                result = None
        else:
            result = None

        if result is None:
            logger.info(f"Web search query: {user_query}")
            try:
                result = await self._web_search(user_query)
            except Exception as e:
                logger.error(f"Query failed: {e}")
                result = {
                    "query_type": "网络搜索",
                    "query_success": False,
                    "results": {"error": str(e)},
                }

        return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

    def _is_weather_query(self, query: str) -> bool:
        """简单判断是否为天气类问题。"""
        q = (query or "").strip()
        if not q:
            return False
        return "天气" in q or "气温" in q or "下雨" in q or "预报" in q

    async def _weather_query(self, query: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        使用 WeatherAPI.com 查询天气。
        """
        import asyncio
        try:
            import httpx
        except ImportError:
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {"message": "需要安装 httpx: pip install httpx"},
            }

        api_key = WEATHER_API_CONFIG.get("api_key", "").strip()
        if not api_key or api_key == "YOUR_WEATHERAPI_KEY":
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {
                    "message": "请先在 config.py 中配置 WeatherAPI.com 的 api_key",
                    "sources": [{"url": "https://www.weatherapi.com/", "title": "WeatherAPI.com"}],
                },
            }

        city = self._resolve_weather_city(query, context or {})
        if not city:
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {"message": "未识别到城市，请说明具体城市，如：杭州下周的天气怎么样？"},
            }

        base_url = WEATHER_API_CONFIG.get("base_url", "https://api.weatherapi.com/v1").rstrip("/")
        language = WEATHER_API_CONFIG.get("language", "zh")
        forecast_days = 7 if ("下周" in query or "一周" in query or "7天" in query) else 3
        url = f"{base_url}/forecast.json"
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: httpx.get(
                    url,
                    timeout=10.0,
                    params={
                        "key": api_key,
                        "q": city,
                        "days": forecast_days,
                        "aqi": "no",
                        "alerts": "no",
                        "lang": language,
                    },
                    headers={"User-Agent": "agentic-travel/1.0"},
                ),
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"WeatherAPI request failed for city={city}: {e}")
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {
                    "message": f"天气接口暂时不可用: {e}",
                    "sources": [{"url": "https://www.weatherapi.com/", "title": "WeatherAPI.com"}],
                },
            }

        if not isinstance(data, dict):
            logger.warning(f"WeatherAPI returned unexpected payload for city={city}: {type(data)}")
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {
                    "message": "天气接口返回格式异常",
                    "sources": [{"url": "https://www.weatherapi.com/", "title": "WeatherAPI.com"}],
                },
            }

        try:
            current = data.get("current", {}) or {}
            forecast = ((data.get("forecast") or {}).get("forecastday") or [])
            condition = current.get("condition") or {}
            temp_c = current.get("temp_c", "?")
            desc = condition.get("text", "—")
            humidity = current.get("humidity", "?")
            weather_text = f"{city}当前天气：{desc}，气温 {temp_c}°C，湿度 {humidity}%。"
            forecasts = []
            for day in forecast[:forecast_days]:
                date = day.get("date", "")
                day_info = day.get("day") or {}
                maxtemp = day_info.get("maxtemp_c", "?")
                mintemp = day_info.get("mintemp_c", "?")
                daily_desc = ((day_info.get("condition") or {}).get("text")) or "—"
                forecasts.append(f"{date}: {daily_desc}，{mintemp}~{maxtemp}°C")
            if forecasts:
                weather_text += " 未来几日：" + "；".join(forecasts[:3])
            return {
                "query_type": "天气查询",
                "query_success": True,
                "results": {
                    "summary": weather_text,
                    "sources": [{"url": "https://www.weatherapi.com/", "title": "WeatherAPI.com"}],
                },
            }
        except Exception as e:
            logger.warning(f"Parse WeatherAPI response failed for city={city}: {type(e).__name__}: {e}")
            return {
                "query_type": "天气查询",
                "query_success": False,
                "results": {
                    "message": "天气数据解析失败",
                    "sources": [{"url": "https://www.weatherapi.com/", "title": "WeatherAPI.com"}],
                },
            }

    def _extract_city_from_query(self, query: str) -> str:
        """从问题中提取城市名（简单实现：常见城市列表匹配）。"""
        q = (query or "").strip()
        for city in _COMMON_CITIES:
            if city in q:
                return city
        # 否则取前 2～6 个连续中文字作为可能城市名
        m = re.search(r"[\u4e00-\u9fa5]{2,6}", q)
        return m.group(0).strip() if m else ""

    def _resolve_weather_city(self, query: str, context: Dict[str, Any]) -> str:
        """
        为天气查询选择最合适的城市：
        1. 优先使用 intention/context 中的 destination
        2. 其次尝试提取“天气/预报”附近的城市
        3. 最后回退到全句第一个命中的城市
        """
        key_entities = context.get("key_entities", {}) if isinstance(context, dict) else {}
        destination = key_entities.get("destination")
        if isinstance(destination, str) and destination.strip():
            return destination.strip()

        q = (query or "").strip()

        weather_keywords = ["天气", "气温", "预报", "下雨"]
        keyword_positions = [q.find(k) for k in weather_keywords if q.find(k) != -1]
        if keyword_positions:
            anchor = min(keyword_positions)
            window_start = max(0, anchor - 12)
            window_end = min(len(q), anchor + 12)
            window_text = q[window_start:window_end]
            for city in _COMMON_CITIES:
                if city in window_text:
                    return city

        return self._extract_city_from_query(q)

    async def _web_search(self, query: str) -> Dict[str, Any]:
        """
        网络搜索 - 使用 DDGS（Dux Distributed Global Search），开启 safesearch，过滤可疑来源。

        Args:
            query: 用户查询

        Returns:
            搜索结果
        """
        if not DDGS_AVAILABLE:
            return {
                "query_type": "网络搜索",
                "query_success": False,
                "results": {
                    "message": "搜索库未安装",
                    "note": "请运行：pip install ddgs",
                },
            }

        try:
            ddgs = DDGS()
            # 开启安全搜索，优先 bing 后端（质量更稳定），多取几条再过滤
            search_results = []
            for backend in ("bing", "duckduckgo", "auto"):
                try:
                    raw = ddgs.text(
                        query,
                        max_results=10,
                        safesearch="on",
                        region="cn-zh",
                        backend=backend,
                    )
                    search_results = list(raw)
                    if search_results:
                        break
                except Exception as e:
                    logger.debug(f"DDGS backend {backend} failed: {e}")
                    continue

            results = []
            for result in search_results:
                href = result.get("href", "")
                if _is_suspicious_url(href):
                    continue
                results.append({
                    "title": result.get("title", ""),
                    "snippet": result.get("body", ""),
                    "url": href,
                })
                if len(results) >= 5:
                    break

            if not results:
                return {
                    "query_type": "网络搜索",
                    "query_success": False,
                    "results": {"message": "未找到相关结果"},
                }

            # 使用 LLM 总结搜索结果
            summary = await self._summarize_search_results(query, results)

            return {
                "query_type": "网络搜索",
                "query_success": True,
                "results": {
                    "summary": summary,
                    "sources": results,
                },
            }
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {
                "query_type": "网络搜索",
                "query_success": False,
                "results": {"error": f"搜索失败: {str(e)}"},
            }

    async def _summarize_search_results(self, query: str, results: List[Dict]) -> str:
        """
        使用 LLM 总结搜索结果

        Args:
            query: 用户查询
            results: 搜索结果列表

        Returns:
            总结文本
        """
        if not results:
            return "未找到相关信息"

        # 构建搜索结果文本
        results_text = ""
        for i, result in enumerate(results, 1):
            results_text += f"\n{i}. {result['title']}\n{result['snippet']}\n"

        # 获取当前时间
        from datetime import datetime
        current_date = datetime.now().strftime("%Y年%m月%d日")
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][datetime.now().weekday()]

        # 动态读取 Prompt 指令 (Progressive Disclosure)
        skill_instruction = self.skill_loader.get_skill_content("query-info")
        if not skill_instruction:
            skill_instruction = "请直接回答用户的问题，保持简洁。"

        prompt = f"""根据以下搜索结果，简洁地回答用户的问题。

【当前时间】
{current_date} {weekday}
（用户查询中的相对时间请基于此日期理解，如"明天"、"2月28日"等）

【用户问题】
{query}

【搜索结果】
{results_text}

【任务说明】
{skill_instruction}
"""

        try:
            response = await self.model([{"role": "user", "content": prompt}])

            # 获取响应文本 - 处理异步生成器
            text = ""
            if hasattr(response, '__aiter__'):
                # 异步生成器，需要迭代获取内容
                async for chunk in response:
                    if isinstance(chunk, str):
                        text = chunk
                    elif hasattr(chunk, 'content'):
                        if isinstance(chunk.content, str):
                            text = chunk.content
                        elif isinstance(chunk.content, list):
                            for item in chunk.content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text = item.get('text', '')
            elif hasattr(response, 'text'):
                text = response.text
            elif hasattr(response, 'content'):
                text = response.content
            elif isinstance(response, dict) and 'content' in response:
                text = response['content']
            else:
                text = str(response) if response else ""

            return text.strip() if text else "无法生成摘要"
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return "搜索成功，但摘要生成失败"
