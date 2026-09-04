#!/usr/bin/env bash
# Isolate monitor dependencies from Hermes' managed Python runtime.
exec /root/.hermes/venvs/smc-source-monitor/bin/python /root/.hermes/scripts/v25/v536_multitf_source_monitor.py
