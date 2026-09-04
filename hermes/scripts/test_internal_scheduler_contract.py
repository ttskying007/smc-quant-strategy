#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile

MOD = pathlib.Path('/root/.hermes/scripts/smc_unified.py')


def load_module(tmpdir):
    spec = importlib.util.spec_from_file_location('smc_unified_sched_test', MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    root = pathlib.Path(tmpdir)
    m._SCHEDULER_STATE = root / 'scheduler_state.json'
    m._SCHEDULER_LOG = root / 'scheduler.log'
    return m


def test_scheduler_runs_once_per_day_and_manual_force_reruns():
    with tempfile.TemporaryDirectory() as td:
        m = load_module(td)
        job = {'cmd': ['python3', '-c', 'print("ok")'], 'timeout': 10, 'time': '00:00', 'desc': 'test'}
        m._scheduler_run_job('unit', job, '20260615')
        m._scheduler_run_job('unit', job, '20260615')
        state = json.loads(m._SCHEDULER_STATE.read_text())
        assert state['jobs']['unit']['last_success_date'] == '20260615'
        assert state['jobs']['unit']['last_returncode'] == 0
        log = m._SCHEDULER_LOG.read_text()
        assert log.count('START unit') == 1
        assert log.count('END unit') == 1
        m._scheduler_run_job('unit', job, '20260615', force=True, trigger='manual')
        state = json.loads(m._SCHEDULER_STATE.read_text())
        assert state['jobs']['unit']['trigger'] == 'manual'
        assert state['jobs']['unit']['manual_force'] is True
        log = m._SCHEDULER_LOG.read_text()
        assert log.count('START unit') == 2
        assert log.count('END unit') == 2


if __name__ == '__main__':
    test_scheduler_runs_once_per_day_and_manual_force_reruns()
    print('internal scheduler contract PASS')
