"""All tests use demo mode and local retrieval, regardless of the developer environment."""
import os
os.environ["AGENT_MODE"] = "demo"
os.environ["EMBEDDING_BASE_URL"] = ""
os.environ["EMBEDDING_MODEL"] = ""
