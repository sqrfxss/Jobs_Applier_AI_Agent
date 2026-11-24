"""Verify configuration without printing keys or performing network requests."""
import os,importlib.util,json
from pathlib import Path
def status():
 token=os.environ.get("AIHAWK_GOOGLE_TOKEN_FILE")
 google_client=os.environ.get("AIHAWK_GOOGLE_CLIENT_FILE")
 google_lib=all(importlib.util.find_spec(x) is not None for x in ("google_auth_oauthlib","googleapiclient"))
 return {
 "openai":{"library_installed":importlib.util.find_spec("openai") is not None,"key_configured":bool(os.environ.get("OPENAI_API_KEY")),"model_configured":bool(os.environ.get("OPENAI_MODEL")),"live_connection_verified":False},
 "google":{"sync_mode":"chatgpt_connected_handoff","local_oauth_required":False,"libraries_installed":google_lib,"oauth_client_configured":bool(google_client and Path(google_client).is_file()),"token_configured":bool(token and Path(token).is_file()),"live_connection_verified":False},
 "tinyfish":{"api_key_configured":bool(os.environ.get("TINYFISH_API_KEY")),"live_connection_verified":False},
 "mode":"chatgpt_assisted_sync"
 }
if __name__=="__main__":print(json.dumps(status(),indent=2))
