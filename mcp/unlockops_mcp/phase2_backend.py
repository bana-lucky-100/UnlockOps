"""Thin v2 service adapter. IDs are validated before interpolation into URLs."""
from uuid import UUID
from pydantic import ValidationError
from unlockops.common.models import ToolFailure
from unlockops.common.phase2_tools import OUTPUTS
from .backend_client import BackendClient


class Phase2Backend(BackendClient):
    def invoke(self, name, args):
        if name in {"get_access_request_context", "assess_access_request", "execute_access_plan", "verify_access_plan"}:
            problem = str(UUID(args["problem_id"]))
            action = {"get_access_request_context": "context", "assess_access_request": "assessment",
                      "execute_access_plan": "execute", "verify_access_plan": "verify"}[name]
            payload = {k: v for k, v in args.items() if k != "problem_id"}
            data = self._request("GET" if action == "context" else "POST", f"/internal/v2/problems/{problem}/{action}", payload or None)
        else:
            action = {"get_reclaim_check_context": "context", "list_revocation_candidates": "candidates",
                      "get_reclaim_notification_history": "notification-history"}[name]
            data = self._request("POST", f"/internal/v2/reclaim/{action}", args,
                                 object_response=action != "notification-history")
            if action == "notification-history":
                data = {"items": data}
        try:
            result = OUTPUTS[name].model_validate(data).model_dump(mode="json")
        except ValidationError:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Invalid Spring v2 response") from None
        if name in {"get_access_request_context", "execute_access_plan", "verify_access_plan"}:
            actual = result["problem"]["id"] if name == "get_access_request_context" else result.get("problem_id")
            if actual is not None and actual != args["problem_id"]:
                raise ToolFailure("REQUEST_SCOPE", "Unexpected access request identity")
        if name in {"get_reclaim_check_context", "list_revocation_candidates"} and result["run_id"] != args["run_id"]:
            raise ToolFailure("RUN_SCOPE", "Unexpected reclaim run identity")
        return result
