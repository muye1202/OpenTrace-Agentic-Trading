import threading
import time


def test_llm_inflight_slot_serializes():
    from tradingagents.agents.utils.llm_concurrency import llm_inflight_slot

    key = "llm:glm:https://open.bigmodel.cn/api/paas/v4:glm-4.7-flash"
    entered = []
    lock = threading.Lock()

    def worker(tag: str):
        with llm_inflight_slot(key, 1):
            with lock:
                entered.append(tag)
            time.sleep(0.2)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))

    start = time.time()
    t1.start()
    time.sleep(0.02)  # encourage overlap attempt
    t2.start()
    t1.join()
    t2.join()
    elapsed = time.time() - start

    assert entered == ["a", "b"]
    assert elapsed >= 0.35

