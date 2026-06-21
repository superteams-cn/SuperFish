"""模拟子路由：Agent 访谈（同步/流式/批量/全量/历史）接口。

拆分自 routers/simulation.py。共享件见 _shared.py。
"""

import json
import os
import traceback

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...core.deps import get_current_user
from ...core.errors import error_response as _error
from ...core.settings import settings
from ...schemas.simulation import (
    InterviewAgentRequest,
    InterviewAllRequest,
    InterviewBatchRequest,
    InterviewHistoryRequest,
)
from ...services.simulation_runner import SimulationRunner
from ...utils.locale import t
from ._shared import _owned_simulation, logger, optimize_interview_prompt

router = APIRouter()


@router.post("/interview")
def interview_agent(req: InterviewAgentRequest, current=Depends(get_current_user)):
    """
    采访单个 Agent

    注意：此功能需要模拟环境处于运行状态（完成模拟循环后进入等待命令模式）

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，模拟ID
            "agent_id": 0,                     // 必填，Agent ID
            "prompt": "你对这件事有什么看法？",  // 必填，采访问题
            "platform": "twitter",             // 可选，指定平台（twitter/reddit）
            "timeout": 60                      // 可选，超时时间（秒），默认 60
        }
    """
    try:
        simulation_id = req.simulation_id
        agent_id = req.agent_id
        prompt = req.prompt
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        if agent_id is None:
            return _error(t("api.requireAgentId"), 400)

        if not prompt:
            return _error(t("api.requirePrompt"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化 prompt，添加前缀避免 Agent 调用工具
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.interviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/interview/batch")
def interview_agents_batch(req: InterviewBatchRequest, current=Depends(get_current_user)):
    """
    批量采访多个 Agent

    注意：此功能需要模拟环境处于运行状态
    """
    try:
        simulation_id = req.simulation_id
        interviews = req.interviews
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        if not interviews or not isinstance(interviews, list):
            return _error(t("api.requireInterviews"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 验证每个采访项
        for i, interview in enumerate(interviews):
            if "agent_id" not in interview:
                return _error(t("api.interviewListMissingAgentId", index=i + 1), 400)
            if "prompt" not in interview:
                return _error(t("api.interviewListMissingPrompt", index=i + 1), 400)
            # 验证每项的 platform（如果有）
            item_platform = interview.get("platform")
            if item_platform and item_platform not in ("twitter", "reddit"):
                return _error(t("api.interviewListInvalidPlatform", index=i + 1), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化每个采访项的 prompt，添加前缀避免 Agent 调用工具
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview["prompt"] = optimize_interview_prompt(interview.get("prompt", ""))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.batchInterviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"批量Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _interview_stream_response(simulation_id: str, poster) -> StreamingResponse:
    """采访流式 SSE 通用管道：订阅 Redis 频道 → 投递命令 → 逐块下发，直到 done/error/超时。

    poster: 回调 (ipc, command_id) -> None，负责投递对应的（单/批量）流式采访命令。
    子进程把 token 逐条发布到 interview:stream:{command_id}，本端点订阅并转成 text/event-stream。
    """
    import asyncio
    import uuid

    import redis.asyncio as aioredis

    from ...services.simulation_ipc import SimulationIPCClient

    async def event_gen():
        # 存活性以 Redis 心跳为准（不依赖本机 sim_dir）：模拟可能跑在另一台 worker 上，
        # 处理本 SSE 的 API 副本本地未必有该模拟目录。IPC 客户端仅据 simulation_id 收发。
        sim_dir = os.path.join(SimulationRunner.RUN_STATE_DIR, simulation_id)
        ipc = SimulationIPCClient(sim_dir)
        if not ipc.check_env_alive():
            # 环境已回收：前端应先调 ensure-env 唤醒后再发起；这里直接报错让其走兜底
            yield _sse_event({"type": "error", "error": "env-not-alive"})
            return

        command_id = str(uuid.uuid4())
        channel = f"interview:stream:{command_id}"
        r = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            # 先订阅再投递命令，避免漏掉首批 token
            poster(ipc, command_id)
            loop = asyncio.get_event_loop()
            overall_deadline = loop.time() + 200.0  # 整体上限
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20.0)
                if msg is None:
                    # 无消息：首 token 前可能在唤醒/排队，发心跳保活并检查总超时
                    if loop.time() > overall_deadline:
                        yield _sse_event({"type": "error", "error": "timeout"})
                        break
                    yield ": keep-alive\n\n"
                    continue
                try:
                    payload = json.loads(msg["data"])
                except (ValueError, TypeError):
                    continue
                yield _sse_event(payload)
                if payload.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                await r.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用反向代理缓冲，确保逐块下发
        },
    )


@router.post("/interview/stream")
def interview_stream(req: InterviewAgentRequest, current=Depends(get_current_user)):
    """单 Agent 流式采访（SSE）。事件：`data:{"type":"chunk"|"done"|"error",...}`。"""
    if not req.simulation_id or req.agent_id is None or not req.prompt:
        return _error(t("api.requireSimulationId"), 400)
    if _owned_simulation(req.simulation_id, current) is None:
        return _error(t("api.simulationNotFound", id=req.simulation_id), 404)
    agent_id = int(req.agent_id)
    prompt = req.prompt
    platform = req.platform
    return _interview_stream_response(
        req.simulation_id,
        lambda ipc, cid: ipc.post_stream_interview(agent_id, prompt, platform, command_id=cid),
    )


@router.post("/interview/stream-batch")
def interview_stream_batch(req: InterviewBatchRequest, current=Depends(get_current_user)):
    """多 Agent 并发流式群访（SSE）。

    事件：chunk/agent_done/agent_error 均带 agent_id，全部完成发 done；前端按 agent_id 分别填充。
    """
    if not req.simulation_id or not req.interviews:
        return _error(t("api.requireSimulationId"), 400)
    if _owned_simulation(req.simulation_id, current) is None:
        return _error(t("api.simulationNotFound", id=req.simulation_id), 404)
    interviews = req.interviews
    platform = req.platform
    return _interview_stream_response(
        req.simulation_id,
        lambda ipc, cid: ipc.post_stream_batch_interview(interviews, platform, command_id=cid),
    )


@router.post("/interview/all")
def interview_all_agents(req: InterviewAllRequest, current=Depends(get_current_user)):
    """
    全局采访 - 使用相同问题采访所有 Agent

    注意：此功能需要模拟环境处于运行状态
    """
    try:
        simulation_id = req.simulation_id
        prompt = req.prompt
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        if not prompt:
            return _error(t("api.requirePrompt"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化 prompt，添加前缀避免 Agent 调用工具
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.globalInterviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"全局Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/interview/history")
def get_interview_history(req: InterviewHistoryRequest, current=Depends(get_current_user)):
    """
    获取 Interview 历史记录

    从模拟数据库中读取所有 Interview 记录
    """
    try:
        simulation_id = req.simulation_id
        platform = req.platform  # 不指定则返回两个平台的历史
        agent_id = req.agent_id
        limit = req.limit

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit,
        )

        return {"success": True, "data": {"count": len(history), "history": history}}

    except Exception as e:
        logger.error(f"获取Interview历史失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())
