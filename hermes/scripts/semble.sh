#!/bin/bash
# Hermes → semble wrapper: sets HF proxy env then runs semble
export https_proxy=http://127.0.0.1:7890
export HF_ENDPOINT=https://huggingface.co
exec semble "$@"
