# core/nurse_scheduling/serve.py
"""
最終完整版 FastAPI + SSE 即時日誌 + BackgroundTasks
已修復所有問題：日誌即時推送、BackgroundTasks 正常、CORS、flush
"""

import logging
from datetime import datetime
from io import BytesIO
import io
import uuid
import asyncio

from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from fastapi.responses import JSONResponse

from . import scheduler, exporter

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

app = FastAPI(title="Nurse Scheduling API (SSE 即時日誌版)", version="1.0-final")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://kaichen0712.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Schedule-Score", "X-Schedule-Status"],
)

# 任務儲存區
tasks: dict[str, dict] = {}


@app.post("/start-optimization")
async def start_optimization(
    yaml_content: str = Form(..., description="YAML 內容字串"),
    prettify: Optional[bool] = Form(True),
    timeout: Optional[int] = Form(300),
    background: BackgroundTasks = None,
):
    task_id = str(uuid.uuid4())
    queue = asyncio.Queue(maxsize=5000)

    tasks[task_id] = {
        "status": "running",
        "queue": queue,
        "created_at": datetime.utcnow(),
        "prettify": prettify,
        "timeout": timeout,
        "score": None,
        "status_text": None,
        "filename": None,
        "xlsx_bytes": None,
    }

    background.add_task(run_optimization_task, task_id, yaml_content)

    log.info(f"新任務啟動 → {task_id[:8]}")
    return {"task_id": task_id}


def run_optimization_task(task_id: str, yaml_content: str):
    """BackgroundTasks 只能跑普通函數"""
    task = tasks[task_id]
    queue: asyncio.Queue = task["queue"]
    prettify = task["prettify"]
    timeout = task["timeout"]

    def push(line: str):
        """統一由 SSE 負責換行，這裡不加換行"""
        try:
            queue.put_nowait(line.rstrip("\r\n"))
        except asyncio.QueueFull:
            pass
        
    push(f"任務開始 {task_id[:8]} | {datetime.now():%H:%M:%S}")
    push(f"設定 → Prettify: {prettify} | Timeout: {timeout}s\n")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        df, solution, score, status, cell_export_info = loop.run_until_complete(
            asyncio.to_thread(
                scheduler.schedule_with_logger,
                file_content=yaml_content.encode("utf-8"),
                prettify=prettify,
                timeout=timeout,
                logger=push,
            )
        )
        loop.close()

        if df is None:
            push("❌ 沒有找到可行解")
            task["status"] = "failed"
            queue.put_nowait("DONE")
            return

        buffer = BytesIO()
        exporter.export_to_excel(df, buffer, cell_export_info)
        xlsx_bytes = buffer.getvalue()
        filename = f"nurse-scheduling-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"

        task.update({
            "status": "completed",
            "score": score,
            "status_text": status,
            "filename": filename,
            "xlsx_bytes": xlsx_bytes,
        })

        push(f"✅ 優化完成！Score = {score} | Status = {status}")
        push(f"檔案產生：{filename}")
        queue.put_nowait("DONE\n")

    except Exception as e:
        log.exception(f"任務 {task_id} 失敗")
        push(f"💥 優化失敗：{str(e)}")
        task["status"] = "failed"
        queue.put_nowait("DONE\n")


@app.get("/task/{task_id}/logs")
async def stream_logs(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "任務不存在")

    async def event_generator():
        queue = tasks[task_id]["queue"]
        while True:
            try:
                # 等待新 log
                line = await asyncio.wait_for(queue.get(), timeout=0.5)

                # 完成訊號
                if line == "DONE":
                    yield "data: DONE\n\n"
                    break

                # 一般 log
                yield f"data: {line}\n\n"

            except asyncio.TimeoutError:
                # 任務已結束，但 queue 裡已無資料
                if tasks[task_id]["status"] in ("completed", "failed"):
                    yield "data: DONE\n\n"
                    break

                # SSE keep-alive
                yield ": ping\n\n"
                continue

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/task/{task_id}/download")
async def download_result(task_id: str):
      # 任務不存在或未完成 → 回傳 JSON，而不是 404
    if task_id not in tasks:
        return JSONResponse(
            status_code=200,
            content={
                "ready": False,
                "message": "找不到任務"
            }
        )

    task = tasks[task_id]

    # 如果尚未完成傳JSON，不要丟404，避免前端跳白頁
    if task["status"] != "completed":
        return JSONResponse(
            status_code=200,
            content={
                "ready": False,
                "message": "檔案尚未產生或任務失敗"
            }
        )

    # 完成後回傳XLSX
    return StreamingResponse(
        io.BytesIO(task["xlsx_bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{task["filename"]}"',
            "X-Schedule-Score": str(task["score"]),
            "X-Schedule-Status": task["status_text"],
        },
    )


@app.get("/task/{task_id}/status")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404)
    t = tasks[task_id]
    return {
        "status": t["status"],
        "score": t.get("score"),
        "filename": t.get("filename"),
    }