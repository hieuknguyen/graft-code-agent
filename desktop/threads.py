from typing import Optional, Dict, Any, List
from PySide6.QtCore import QThread, Signal
from core.agent import GraftAgent

class ScanWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, agent: GraftAgent):
        super().__init__()
        self.agent = agent

    def run(self):
        try:
            self.agent.scan()
            symbols_count = sum(len(f.symbols) for f in self.agent.graph.files.values())
            self.finished.emit({
                "files_count": len(self.agent.graph.files),
                "symbols_count": symbols_count
            })
        except Exception as e:
            self.error.emit(str(e))

class GraftWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, agent: GraftAgent, task: str, target_file: Optional[str] = None, images: Optional[List[str]] = None):
        super().__init__()
        self.agent = agent
        self.task = task
        self.target_file = target_file
        self.images = images or []

    def run(self):
        try:
            res = self.agent.plan_and_graft(self.task, target_file=self.target_file, images=self.images)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class ApplyWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, agent: GraftAgent, action: Dict[str, Any]):
        super().__init__()
        self.agent = agent
        self.action = action

    def run(self):
        try:
            succ, msg = self.agent.apply_action(self.action)
            self.finished.emit(succ, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

class UndoWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, agent: GraftAgent):
        super().__init__()
        self.agent = agent

    def run(self):
        try:
            succ, msg = self.agent.undo_last()
            self.finished.emit(succ, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

class AgentFeedbackWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, agent: GraftAgent, goal: str, last_cmd: str, exit_code: int, log_text: str):
        super().__init__()
        self.agent = agent
        self.goal = goal
        self.last_cmd = last_cmd
        self.exit_code = exit_code
        self.log_text = log_text

    def run(self):
        try:
            res = self.agent.analyze_log_and_plan_next(
                self.goal, self.last_cmd, self.exit_code, self.log_text
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class DoctorWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, agent: GraftAgent):
        super().__init__()
        self.agent = agent

    def run(self):
        try:
            res = self.agent.doctor()
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))



class ServerHealthProbeWorker(QThread):
    finished = Signal(dict)

    def __init__(self, server_url: str, delay_ms: int = 1000):
        super().__init__()
        self.server_url = server_url
        self.delay_ms = delay_ms

    def run(self):
        import time
        import urllib.request
        import urllib.error

        time.sleep(self.delay_ms / 1000.0)
        req_url = self.server_url if self.server_url.endswith("/") else (self.server_url + "/")
        result = {
            "url": req_url,
            "status_code": None,
            "is_healthy": False,
            "error": None,
            "snippet": ""
        }
        try:
            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "GraftCodeAgent-Probe/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                code = resp.getcode()
                content = resp.read(2048).decode("utf-8", errors="replace")
                result["status_code"] = code
                result["snippet"] = content[:500]
                result["is_healthy"] = (200 <= code < 400)
        except urllib.error.HTTPError as e:
            result["status_code"] = e.code
            try:
                content = e.read(2048).decode("utf-8", errors="replace")
                result["snippet"] = content[:500]
            except Exception:
                pass
            result["is_healthy"] = False
            result["error"] = f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            result["status_code"] = None
            result["is_healthy"] = False
            result["error"] = str(e)

        self.finished.emit(result)
