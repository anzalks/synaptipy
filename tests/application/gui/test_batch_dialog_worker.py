"""Regression tests for the batch-dialog worker lifecycle."""

import pandas as pd

from synaptipy.application.gui.batch_dialog import BatchWorker


class _CancelledEngine:
    def cancel(self):
        pass

    def run_batch(self, **_kwargs):
        return pd.DataFrame([{"file_name": "partial.abf", "metric": 1.0}])


def test_cancelled_worker_still_emits_finished(qtbot):
    """Cancellation must release the dialog by emitting its completion signal."""
    worker = BatchWorker(_CancelledEngine(), [], [])
    worker.cancel()

    with qtbot.waitSignal(worker.signals.finished, timeout=1000) as blocker:
        worker.start()

    worker.wait(1000)
    assert len(blocker.args[0]) == 1
