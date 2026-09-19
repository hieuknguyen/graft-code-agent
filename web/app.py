import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import load_config, save_config, AppConfig
from core.agent import GraftAgent

app = FastAPI(title="Graft Code Agent UI", version="1.0.0")

ROOT_DIR = os.environ.get("GRAFT_ROOT_DIR") or os.getcwd()
config = load_config()
agent = GraftAgent(config, ROOT_DIR)
agent.scan()

class GraftRequest(BaseModel):
    task: str
    target_file: Optional[str] = None
    images: Optional[List[str]] = None

class ApplyRequest(BaseModel):
    action: Dict[str, Any]

class ConfigUpdateRequest(BaseModel):
    gateway_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    evaluator_model: Optional[str] = None
    dual_ai_mode: Optional[bool] = None
    auto_apply: Optional[bool] = None
    thinking: Optional[bool] = None
    web_search: Optional[bool] = None

@app.get("/", response_class=HTMLResponse)
def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Template index.html not found")
    return template_path.read_text(encoding="utf-8")

@app.get("/api/status")
def get_status():
    symbols_count = sum(len(fast.symbols) for fast in agent.graph.files.values())
    return {
        "root_dir": str(agent.root_dir),
        "gateway_url": agent.config.gateway_url,
        "model": agent.config.model,
        "evaluator_model": agent.config.evaluator_model,
        "dual_ai_mode": agent.config.dual_ai_mode,
        "thinking": agent.config.thinking,
        "files_count": len(agent.graph.files),
        "symbols_count": symbols_count,
        "has_undo": len(agent.history_backups) > 0,
        "backups_count": len(agent.history_backups)
    }

@app.get("/api/tree")
def get_tree():
    tree = []
    for fpath, fast in sorted(agent.graph.files.items()):
        symbols = []
        for s in fast.symbols:
            symbols.append({
                "name": s.name,
                "type": s.symbol_type,
                "line": s.start_line,
                "end_line": s.end_line,
                "parent": s.parent,
                "args": s.args,
                "doc": s.docstring
            })
        tree.append({
            "path": fpath,
            "lines": fast.total_lines,
            "symbols": symbols
        })
    return {"files": tree}

@app.get("/api/file")
def get_file_content(path: str = Query(..., description="Đường dẫn tương đối của file")):
    fpath = agent.root_dir / path
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại")
    try:
        content = fpath.read_text(encoding="utf-8-sig", errors="replace")
        return {
            "path": path,
            "content": content,
            "size": fpath.stat().st_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan")
def rescan():
    agent.scan()
    return get_status()

@app.post("/api/graft")
def plan_and_graft(req: GraftRequest):
    task = req.task.strip()
    if not task and not req.images:
        raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu lập trình hoặc đính kèm hình ảnh")
    if not task and req.images:
        task = "Hãy phân tích hình ảnh đính kèm trên và thực hiện yêu cầu hoặc giải thích các vấn đề trong ảnh."
    res = agent.plan_and_graft(task, target_file=req.target_file, images=req.images)
    return res

@app.post("/api/apply")
def apply_action(req: ApplyRequest):
    act = req.action
    succ = agent.apply_action(act)
    if not succ:
        raise HTTPException(status_code=400, detail="Không thể áp dụng cấy ghép vào file")
    return {"success": True, "file": act.get("file")}

@app.post("/api/undo")
def undo_last():
    succ, msg = agent.undo()
    return {"success": succ, "msg": msg}

@app.get("/api/config")
def get_config():
    return {
        "gateway_url": agent.config.gateway_url,
        "api_key": agent.config.api_key,
        "model": agent.config.model,
        "evaluator_model": agent.config.evaluator_model,
        "dual_ai_mode": agent.config.dual_ai_mode,
        "auto_apply": agent.config.auto_apply,
        "thinking": agent.config.thinking,
        "web_search": agent.config.web_search,
    }

@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    cfg = agent.config
    if req.gateway_url is not None: cfg.gateway_url = req.gateway_url
    if req.api_key is not None: cfg.api_key = req.api_key
    if req.model is not None: cfg.model = req.model
    if req.evaluator_model is not None: cfg.evaluator_model = req.evaluator_model
    if req.dual_ai_mode is not None: cfg.dual_ai_mode = req.dual_ai_mode
    if req.auto_apply is not None: cfg.auto_apply = req.auto_apply
    if req.thinking is not None: cfg.thinking = req.thinking
    if req.web_search is not None: cfg.web_search = req.web_search

    save_config(cfg)
    return {"success": True, "config": get_config()}
