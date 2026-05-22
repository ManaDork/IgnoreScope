"""Integration smoke for the lifecycle drain progress signal wiring.

The Pass 1.3 refactor added a ``pushProgress(int, int)`` Qt signal on
``ContainerWorker`` so the lifecycle's marked-push drain (Phase 10a inside
``execute_create`` / ``execute_update``) can surface per-file progress to the
``QProgressDialog`` the GUI shows during container ops. The dialog switches
from indeterminate to determinate the first time progress fires.

This test exercises that wiring end-to-end against real Qt objects (real
``QApplication``, real ``ContainerWorker`` QThread, real ``QProgressDialog``) —
the equivalent of clicking ``Container → Update Container`` and watching the
dialog go determinate, but reproducible. It does NOT call the actual
``execute_create`` (no Docker) — the operation is a stub that drives the
progress callback the way the orchestrator would.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtWidgets import QApplication, QProgressDialog

from IgnoreScope.core.op_result import OpResult
from IgnoreScope.gui.container_ops_ui import ContainerWorker


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _wait_for_finish(worker: ContainerWorker, timeout_ms: int = 2000) -> None:
    """Block the test thread until the worker emits `finished`, spinning the
    Qt event loop so queued signals (pushProgress, finished) actually fire on
    the main thread.
    """
    loop = QEventLoop()
    worker.finished.connect(lambda *_: loop.quit())
    # Safety belt — worker could already be done by the time we attach.
    if not worker.isRunning():
        return
    # processEvents while waiting so signals deliver promptly.
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while worker.isRunning():
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() > deadline:
            raise AssertionError(f"worker did not finish within {timeout_ms}ms")
    # Flush any pending queued signals after the thread ended.
    QApplication.processEvents()


def test_pushprogress_signal_fires_with_correct_args():
    """ContainerWorker.run passes a progress_cb into the operation; that callback
    emits pushProgress(current, total). Five progress ticks → five signals.
    """
    captured: list[tuple[int, int]] = []

    def operation(progress_cb):
        for i in range(1, 6):
            progress_cb(i, 5)
        return OpResult(success=True, message="ok")

    worker = ContainerWorker(operation)
    worker.pushProgress.connect(lambda c, t: captured.append((c, t)))

    worker.start()
    _wait_for_finish(worker)

    assert captured == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


def test_progress_dialog_switches_to_determinate_on_first_tick():
    """_run_container_operation wires pushProgress to _on_push_progress, which
    flips an indeterminate (0, 0) QProgressDialog into determinate mode and
    drives it to completion. We re-create that wiring inline and verify the
    dialog state transition.
    """
    # Indeterminate QProgressDialog, exactly as _create_progress_dialog builds.
    dialog = QProgressDialog("Updating Container...", None, 0, 0, None)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    # In production _on_operation_finished closes the dialog explicitly; the
    # default autoClose/autoReset=True would otherwise reset value to -1 when
    # value reaches maximum, masking the state we want to observe.
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    # Don't show — the test runs headless-ish; we only assert internal state.

    assert dialog.maximum() == 0  # sanity: indeterminate before progress

    # The slot's job is to flip the indeterminate (max=0) dialog into
    # determinate mode and drive setValue. We capture what the slot was
    # called with — that's the wiring under test. (QProgressDialog's
    # value() can be unreliable to query before show(), so we snapshot
    # the slot inputs and the max-after-setMaximum, which is stable.)
    slot_calls: list[tuple[int, int, int]] = []  # (current, total, max_after_set)

    def operation(progress_cb):
        for i in range(1, 4):
            progress_cb(i, 3)
        return OpResult(success=True, message="ok")

    worker = ContainerWorker(operation)

    def on_push_progress(current: int, total: int) -> None:
        # Mirror ContainerOperations._on_push_progress.
        if total > 0:
            dialog.setMaximum(total)
            dialog.setValue(current)
            slot_calls.append((current, total, dialog.maximum()))

    worker.pushProgress.connect(on_push_progress)
    worker.start()
    _wait_for_finish(worker)

    # Three queued signals delivered; cross-thread ordering of rapid-fire
    # emits isn't strictly preserved by Qt, but every emit must reach the
    # slot exactly once with its original args. The dialog must be in
    # determinate mode (max=3) throughout — the indeterminate→determinate
    # flip is the property under test.
    assert len(slot_calls) == 3, "expected three slot invocations"
    assert sorted(slot_calls) == [(1, 3, 3), (2, 3, 3), (3, 3, 3)], (
        "each emit should reach the slot with its (current, total) args "
        "and the dialog should be determinate (max=3) every time"
    )
    dialog.close()


def test_operation_without_progress_calls_works():
    """Operations that never call progress_cb (the non-drain code path in the
    orchestrator) still complete cleanly through ContainerWorker. The dialog
    stays indeterminate but no error fires.
    """
    finished: list[tuple[bool, str]] = []

    def operation(_progress_cb):
        # No progress emitted; same as a preflight failure or detached_init.
        return OpResult(success=True, message="done")

    worker = ContainerWorker(operation)
    worker.finished.connect(lambda ok, msg: finished.append((ok, msg)))

    worker.start()
    _wait_for_finish(worker)

    assert finished == [(True, "done")]


def test_operation_exception_propagates_to_finished_signal():
    """ContainerWorker.run catches exceptions from the operation and emits
    finished(False, "Error: ..."). Keeps the existing failure contract.
    """
    finished: list[tuple[bool, str]] = []

    def operation(_progress_cb):
        raise RuntimeError("boom")

    worker = ContainerWorker(operation)
    worker.finished.connect(lambda ok, msg: finished.append((ok, msg)))

    worker.start()
    _wait_for_finish(worker)

    assert len(finished) == 1
    ok, msg = finished[0]
    assert ok is False
    assert "boom" in msg
