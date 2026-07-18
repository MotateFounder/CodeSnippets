import threading
from datetime import datetime


LLM_PRIORITY_CHAT = 0
LLM_PRIORITY_BACKGROUND = 50


class LLMTaskInterrupted(Exception):
    pass


class LLMQueueRequest:
    def __init__(self, record, cancel_event):
        self.record = record
        self._cancel_event = cancel_event

    def __getitem__(self, key):
        return self.record[key]

    def get(self, key, default=None):
        return self.record.get(key, default)

    def __contains__(self, key):
        return key in self.record

    @property
    def id(self):
        return self.record["id"]

    @property
    def priority(self):
        return self.record.get("priority", LLM_PRIORITY_BACKGROUND)

    @property
    def request_type(self):
        return self.record["request_type"]

    @property
    def model_key(self):
        return self.record["model_key"]

    def interrupted(self):
        return self._cancel_event.is_set()

    def raise_if_interrupted(self):
        if self.interrupted():
            raise LLMTaskInterrupted("LLM request was cancelled.")


class LLMRequestQueue:
    def __init__(self, on_state_change=None):
        self._condition = threading.Condition()
        self._requests = {}
        self._queue = []
        self._sequence = 0
        self._running_id = ""
        self._closed = False
        self._on_state_change = on_state_change
        self._local = threading.local()
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()

    def submit(
        self,
        query,
        target_id,
        worker,
        on_done=None,
        priority=LLM_PRIORITY_BACKGROUND,
        request_type="background",
        model_key="default",
        restartable=True,
    ):
        record = self._record(
            query=query,
            target_id=target_id,
            worker=worker,
            on_done=on_done,
            priority=priority,
            request_type=request_type,
            model_key=model_key,
            restartable=restartable,
        )
        with self._condition:
            self._requests[record["id"]] = record
            self._queue.append(record["id"])
            self._condition.notify_all()
        self._emit(record)
        return record["id"]

    def call_sync(
        self,
        query,
        target_id,
        worker,
        priority=LLM_PRIORITY_BACKGROUND,
        request_type="background",
        model_key="default",
        restartable=True,
    ):
        done = threading.Event()
        outcome = {"result": None, "error": None}

        def on_done(result, error):
            outcome["result"] = result
            outcome["error"] = error
            done.set()

        self.submit(
            query=query,
            target_id=target_id,
            worker=worker,
            on_done=on_done,
            priority=priority,
            request_type=request_type,
            model_key=model_key,
            restartable=restartable,
        )
        done.wait()
        if outcome["error"]:
            raise outcome["error"]
        return outcome["result"]

    def snapshot(self):
        with self._condition:
            return [
                self._public_record(record)
                for record in sorted(self._requests.values(), key=lambda item: item["created_sequence"])
            ]

    def close(self):
        with self._condition:
            self._closed = True
            if self._running_id and self._running_id in self._requests:
                self._requests[self._running_id]["cancel_event"].set()
            for request_id in self._queue:
                record = self._requests.get(request_id)
                if record and record["status"] == "queued":
                    record["status"] = "cancelled"
                    record["finished_at"] = self._timestamp()
                    self._emit(record)
            self._queue = []
            self._condition.notify_all()

    def is_worker_thread(self):
        return bool(getattr(self._local, "in_worker", False))

    def _record(self, query, target_id, worker, on_done, priority, request_type, model_key, restartable):
        request_id = self._unique_request_id(str(target_id))
        with self._condition:
            self._sequence += 1
            sequence = self._sequence
        return {
            "id": request_id,
            "target_id": str(target_id),
            "query": query,
            "worker": worker,
            "on_done": on_done,
            "priority": int(priority),
            "request_type": str(request_type or "background"),
            "model_key": str(model_key or "default"),
            "restartable": bool(restartable),
            "status": "queued",
            "created_at": self._timestamp(),
            "started_at": "",
            "finished_at": "",
            "error": "",
            "attempts": 0,
            "created_sequence": sequence,
            "cancel_event": threading.Event(),
        }

    def _unique_request_id(self, base_id):
        with self._condition:
            if base_id not in self._requests or self._requests[base_id].get("status") in {"completed", "failed", "cancelled"}:
                return base_id
            suffix = 2
            while True:
                candidate = "{0}:{1}".format(base_id, suffix)
                if candidate not in self._requests:
                    return candidate
                suffix += 1

    def _run_loop(self):
        self._local.in_worker = True
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                request_id = self._queue.pop(0)
                record = self._requests.get(request_id)
                if not record or record["status"] != "queued":
                    continue
                record["status"] = "running"
                record["started_at"] = self._timestamp()
                record["attempts"] += 1
                self._running_id = record["id"]
            self._emit(record)

            result = None
            error = None
            try:
                request = LLMQueueRequest(record, record["cancel_event"])
                request.raise_if_interrupted()
                result = record["worker"](request)
                request.raise_if_interrupted()
            except Exception as exc:
                error = exc
                self._finish(record, "cancelled" if isinstance(exc, LLMTaskInterrupted) else "failed", error=error)
            else:
                self._finish(record, "completed", result=result)

            on_done = record.get("on_done")
            if on_done:
                try:
                    on_done(result, error)
                except Exception:
                    pass

    def _finish(self, record, status, result=None, error=None):
        with self._condition:
            if self._running_id == record["id"]:
                self._running_id = ""
            record["status"] = status
            record["finished_at"] = self._timestamp()
            if error:
                record["error"] = str(error)
            self._condition.notify_all()
        self._emit(record)

    def _emit(self, record):
        if not self._on_state_change:
            return
        try:
            self._on_state_change(self._public_record(record))
        except Exception:
            pass

    def _public_record(self, record):
        return {
            "id": record.get("id", ""),
            "target_id": record.get("target_id", ""),
            "query": record.get("query", ""),
            "priority": record.get("priority", LLM_PRIORITY_BACKGROUND),
            "request_type": record.get("request_type", "background"),
            "model_key": record.get("model_key", "default"),
            "restartable": record.get("restartable", True),
            "status": record.get("status", "queued"),
            "created_at": record.get("created_at", ""),
            "started_at": record.get("started_at", ""),
            "finished_at": record.get("finished_at", ""),
            "error": record.get("error", ""),
            "attempts": record.get("attempts", 0),
        }

    def _timestamp(self):
        return datetime.now().isoformat(timespec="seconds")
