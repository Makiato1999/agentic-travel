---
name: event-collection
description: Use this skill when the user provides travel details like origin, destination, dates, purpose, or when planning a trip. It extracts structured event information for itinerary planning.
---

# Event Collection Skill

用于从用户输入中提取**本次行程**的结构化信息，供 `itinerary_planning` 等后续 agent 使用。

通常由 `IntentionAgent` 自动调度，配合 `plan-trip` 技能使用。

## 核心原则

1. 只提取**当前这一次行程**的信息，不要把用户历史偏好、家庭住址、常住地当作本次行程事实
2. 如果用户输入里明确出现了出发地、目的地、日期、时长，必须以**当前输入中的显式信息**为准，优先级高于背景信息
3. 只有当用户当前输入**没有明确说出发地**时，才允许根据背景信息中的 `home_location` 推断 `origin`
4. 用户说“常住苏州”“我家在杭州”这类信息，默认属于背景信息/偏好，不等于本次出发地，除非用户明确说“从苏州出发”
5. 如果用户当前输入中明确说“从南京去成都”，则 `origin` 必须是南京，不能被家庭住址或历史偏好覆盖

## 提取字段

请尽可能提取以下结构化字段：

1. `origin` - 出发地
2. `destination` - 目的地
3. `start_date` - 出发日期（`YYYY-MM-DD`）
4. `end_date` - 返程日期（`YYYY-MM-DD`）
5. `duration_days` - 行程天数
6. `return_location` - 返程地
7. `trip_purpose` - 行程目的
8. `missing_info` - 缺失字段列表
9. `extracted_count` - 成功提取字段数量
10. `summary` - 一句简要摘要

## 日期处理规则

- 当前时间由调用方提供
- 用户说“2月27日”“2.27”等相对日期时，需要根据当前时间推断完整年月日
- 用户说“明天”“后天”“下周”等相对时间时，需要换算成具体日期
- 所有日期必须输出为完整的 `YYYY-MM-DD`
- 如果用户给了 `duration_days = N` 且给了 `start_date`，但没有明确 `end_date`，则按**包含起始日**计算：
  - 1天 -> `end_date = start_date`
  - 2天 -> `end_date = start_date + 1天`
  - 4天 -> `end_date = start_date + 3天`
  - 一般规则：`end_date = start_date + (duration_days - 1)`

## 特殊处理

- 对于“北京一日游”这类：`origin` 和 `destination` 都设为北京
- 对于“一日游”：`duration_days = 1`
- 如果用户没明确说 `return_location`，默认 `return_location = origin`
- “常住地 / 家在某地 / 喜欢某类酒店 / 饮食习惯”不属于 `trip_purpose`，不要混入 `origin/destination/trip_purpose`

## 输出格式

严格输出 JSON：

```json
{
  "origin": "北京",
  "destination": "上海",
  "start_date": "2026-04-13",
  "end_date": "2026-04-16",
  "duration_days": 4,
  "return_location": "北京",
  "trip_purpose": "商务出行",
  "missing_info": [],
  "extracted_count": 7,
  "summary": "2026年4月13日至16日从北京到上海的4天商务出行"
}
```

缺失的信息在 `missing_info` 中列出，对应字段设为 `null`。
