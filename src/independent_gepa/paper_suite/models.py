"""Two explicit native DSPy LMs; no changes to the author's proposal/search code."""
from __future__ import annotations

from .contract import draft
from .control import OperationalHalt, request_role


def role_route(role: str) -> dict:
    models = draft()["models"]
    if role == "solver":
        return {"model": models["solver"], "key_env": models["api_key_env"],
                "base_env": models["base_url_env"], "provider": models["provider_profile"]}
    if role == "reflection":
        return {"model": models["reflection"], "key_env": models["reflection_api_key_env"],
                "base_env": models["reflection_base_url_env"], "provider": models["reflection_provider_profile"]}
    raise OperationalHalt("UNKNOWN_MODEL_ROLE")


def create_role_lms(dspy, roles, environment):
    """Called only after grant validation; cache keys contain the actual role model.

    Keys are resolved at the physical boundary, never stored in program state.
    The author's default teacher_lm=None selects settings.lm for reflection,
    while explicit predictor LMs take precedence for every Solver call.
    """
    lms = {}
    for role in roles:
        route = role_route(role)
        if not environment.get(route["key_env"]) or not environment.get(route["base_env"]):
            raise ValueError("ROLE_CREDENTIALS_UNAVAILABLE:" + role)
        lms[role] = dspy.LM(route["model"], api_key="env:" + route["key_env"],
                            api_base=environment[route["base_env"]], temperature=1.0,
                            max_tokens=16384, timeout=120, num_retries=0)
    dspy.configure(lm=lms.get("reflection", lms["solver"]), adapter=dspy.ChatAdapter())
    return lms


def physical_guard(completion, roles, environment, check_time):
    """Reject cross-role/model/deployment drift before a physical attempt."""
    def guarded(*args, **kwargs):
        check_time()
        role = request_role(kwargs.get("messages"))
        if role not in roles:
            raise OperationalHalt("MODEL_ROLE_NOT_AUTHORIZED_FOR_PHASE")
        route = role_route(role)
        if (kwargs.get("model") != route["model"] or kwargs.get("temperature") != 1.0
                or kwargs.get("max_tokens") != 16384):
            raise OperationalHalt("AUTHOR_MODEL_DECODING_DRIFT")
        if kwargs.get("api_base") != environment[route["base_env"]] or kwargs.get("base_url") is not None:
            raise OperationalHalt("ROLE_DEPLOYMENT_DRIFT")
        kwargs["api_key"] = environment[route["key_env"]]
        return completion(*args, **kwargs)
    return guarded
