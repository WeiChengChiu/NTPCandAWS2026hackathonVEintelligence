"""Central configuration. Everything is overridable by environment variable."""

import os

DEFAULT_REGION = os.getenv("VE_AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))

# Bedrock managed knowledge base holding the 建築管理 / 公共安全檢查申報 corpus.
DEFAULT_KB_ID = os.getenv("VE_KB_ID", "CMKZVQHAYB")

# Agentic retrieval defaults.
DEFAULT_FOUNDATION_MODEL_TYPE = os.getenv("VE_KB_FM_TYPE", "MANAGED")
DEFAULT_MAX_AGENT_ITERATION = int(os.getenv("VE_KB_MAX_ITERATION", "5"))
