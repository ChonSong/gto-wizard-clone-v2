"""
gRPC client for the GTO Solver service.
Direct connection to the gRPC solver server (bypasses Celery).
"""
import os
import logging
import grpc
from typing import Optional

logger = logging.getLogger(__name__)

SOLVER_GRPC_HOST = os.environ.get("SOLVER_GRPC_HOST", "localhost")
SOLVER_GRPC_PORT = int(os.environ.get("SOLVER_GRPC_PORT", "50051"))

# Add proto directory to path at module level
import sys
_proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "..", "apps", "solver", "proto")
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

import solver_pb2_grpc
import solver_pb2

# Lazy import to avoid circular deps
_client = None

def get_solver_client():
    """Get or create a gRPC channel to the solver server."""
    global _client
    if _client is None:
        try:
            import sys
            _proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                       *['..', '..', '..', 'apps', 'solver', 'proto'])
            if _proto_dir not in sys.path:
                sys.path.insert(0, _proto_dir)
            import solver_pb2_grpc
            import solver_pb2

            target = f"{SOLVER_GRPC_HOST}:{SOLVER_GRPC_PORT}"
            channel = grpc.insecure_channel(target, options=[
                ('grpc.connect_timeout_ms', 5000),
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ])
            _client = solver_pb2_grpc.SolverServiceStub(channel)
            logger.info(f"Solver gRPC client connected to {target}")
        except Exception as e:
            logger.error(f"Failed to create solver gRPC client: {e}")
            return None
    return _client


def submit_solve(
    game_type: str = "nlh",
    players: int = 2,
    board: Optional[str] = None,
    pot_size: int = 100,
    stack_depth: int = 100,
    bet_sizes: Optional[list] = None,
    iterations: int = 1000,
    street: str = "river",
    position: str = "BTN",
) -> dict:
    """Submit a solve job to the gRPC solver server."""
    import solver_pb2 as pb2
    client = get_solver_client()
    if client is None:
        return {
            "status": "error",
            "progress": 0,
            "strategy": [],
            "error": "gRPC solver client not available"
        }

    try:
        req = pb2.SolveRequest(
            game_type=game_type,
            players=players,
            board=board or "",
            pot_size=pot_size,
            stack_depth=stack_depth,
            bet_sizes=bet_sizes or [],
            iterations=iterations,
            street=street,
            position=position,
        )
        resp = client.SubmitSolve(req, timeout=30)
        job_id = resp.job_id

        # Poll until complete (sync solve runs in background thread)
        import time
        max_wait = 30  # seconds
        poll_interval = 0.5
        waited = 0
        status_resp = resp
        while waited < max_wait:
            if status_resp.status == "complete":
                break
            time.sleep(poll_interval)
            waited += poll_interval
            try:
                status_req = pb2.SolveRequest(job_id=job_id)
                status_resp = client.GetSolveStatus(status_req, timeout=10)
            except Exception:
                pass

        return {
            "job_id": resp.job_id,
            "status": resp.status,
            "progress": resp.progress,
            "strategy": [
                {
                    "action": a.action,
                    "frequency": a.frequency,
                    "ev": a.ev,
                }
                for a in resp.strategy
            ],
            "strategy_key": resp.strategy_key,
            "error": resp.error or None,
        }
    except Exception as e:
        logger.error(f"Solver gRPC call failed: {e}")
        return {
            "status": "error",
            "progress": 0,
            "strategy": [],
            "error": str(e),
        }


def check_health() -> dict:
    """Check solver server health."""
    try:
        import solver_pb2 as pb2
        client = get_solver_client()
        if client is None:
            return {"status": "unavailable", "detail": "gRPC client not created"}
        req = pb2.HealthRequest()
        resp = client.HealthCheck(req, timeout=5)
        return {"status": resp.status, "detail": getattr(resp, 'detail', '')}
    except Exception as e:
        return {"status": "unreachable", "detail": str(e)}
