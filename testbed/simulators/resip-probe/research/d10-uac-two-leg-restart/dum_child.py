#!/usr/bin/env python3
import argparse
import json
import os
import sys
import threading
from pathlib import Path

import _as_resip_two_leg


ROOT = Path(__file__).resolve().parent
LOGICAL_TOKEN = "as-call-two-leg-restart-2026-10-01"
LEG_NAMES = ("leg-a", "leg-b")


def write_json_atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def phase_a_specs(peer_a_port, peer_b_port):
    specs = []
    for name, port in (("leg-a", peer_a_port), ("leg-b", peer_b_port)):
        specs.append(
            {
                "name": name,
                "target_uri": f"sip:uas-{name}@127.0.0.1:{port};transport=udp",
                "route_set": [
                    f"sip:127.0.0.1:{port};lr;transport=udp",
                ],
            }
        )
    return specs


def phase_b_specs(snapshot):
    if snapshot.get("schema_version") != 1:
        raise ValueError("unsupported app snapshot schema")
    if snapshot.get("logical_call_token") != LOGICAL_TOKEN:
        raise ValueError("snapshot logical call token mismatch")
    legs = snapshot.get("legs")
    if not isinstance(legs, list) or len(legs) != 2:
        raise ValueError("snapshot must contain exactly two legs")
    by_name = {leg.get("name"): leg for leg in legs}
    if set(by_name) != set(LEG_NAMES):
        raise ValueError("snapshot leg names differ from the expected pair")

    restored = []
    for name in LEG_NAMES:
        leg = by_name[name]
        if leg.get("business_context_key") != LOGICAL_TOKEN:
            raise ValueError(f"snapshot business key mismatch for {name}")
        dialog_set_id = leg.get("dialog_set_id")
        if not isinstance(dialog_set_id, dict):
            raise ValueError(f"snapshot DialogSetId is missing for {name}")
        restored.append(
            {
                "name": name,
                "call_id": dialog_set_id["call_id"],
                "local_tag": dialog_set_id["local_tag"],
                "remote_to_tag": leg["remote_to_tag"],
                "remote_target_contact": leg["remote_target_contact"],
                "route_set": leg["route_set"],
                "last_cseq": leg["last_cseq"],
            }
        )
    return restored


def run(args):
    callback_records = []
    expected_call_ids = {}
    if args.phase == "phase-a":
        legs = phase_a_specs(args.peer_a_port, args.peer_b_port)
    else:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        legs = phase_b_specs(snapshot)
        expected_call_ids = {
            leg["name"]: leg["call_id"] for leg in legs
        }

    def policy_callback(event, logical_token, leg_name, call_id, status, callback_tid):
        values = (event, logical_token, leg_name, call_id, status, callback_tid)
        all_strings = all(type(value) is str for value in values)
        same_thread = callback_tid == str(threading.get_native_id())
        identity_ok = (
            logical_token == LOGICAL_TOKEN
            and leg_name in LEG_NAMES
            and bool(call_id)
            and status == "200"
        )
        if args.phase == "phase-b":
            identity_ok = identity_ok and expected_call_ids.get(leg_name) == call_id
        prior_call_ids = {
            record["call_id"]
            for record in callback_records
            if record["leg"] != leg_name
        }
        identity_ok = identity_ok and call_id not in prior_call_ids
        accepted = all_strings and same_thread and identity_ok and event in {
            "answer",
            "connected",
        }
        record = {
            "event": event,
            "logical_call_token": logical_token,
            "leg": leg_name,
            "call_id": call_id,
            "status": status,
            "callback_tid": callback_tid,
            "all_inputs_are_strings": all_strings,
            "same_event_loop_thread": same_thread,
            "accepted": accepted,
        }
        callback_records.append(record)
        print("CPYTHON_POLICY_CALLBACK " + json.dumps(record, sort_keys=True), flush=True)
        return bool(accepted)

    print(
        f"CHILD_START phase={args.phase} pid={os.getpid()} "
        f"python_thread_id={threading.get_native_id()} snapshot={args.snapshot}",
        flush=True,
    )
    result = _as_resip_two_leg.run_phase(
        args.phase,
        args.client_port,
        LOGICAL_TOKEN,
        legs,
        policy_callback,
    )
    if result["pid"] != os.getpid():
        raise RuntimeError("native DUM PID differs from child process PID")
    if result["loop_thread_id"] != threading.get_native_id():
        raise RuntimeError("DUM event loop did not run on the child Python thread")
    if result["answer_count"] != 2 or result["connected_count"] != 2:
        raise RuntimeError("native DUM did not complete both client sessions")
    if len(callback_records) != 4 or not all(
        record["accepted"] for record in callback_records
    ):
        raise RuntimeError("scalar CPython policy callback evidence is incomplete")

    if args.phase == "phase-a":
        snapshot_legs = []
        for leg in result["legs"]:
            if leg["business_context_key"] != LOGICAL_TOKEN:
                raise RuntimeError("phase-A app context token was not attached")
            snapshot_legs.append(
                {
                    "name": leg["name"],
                    "dialog_set_id": {
                        "call_id": leg["call_id"],
                        "local_tag": leg["local_tag"],
                    },
                    "remote_to_tag": leg["remote_to_tag"],
                    "remote_target_contact": leg["remote_target_contact"],
                    "route_set": leg["route_set"],
                    "last_cseq": leg["last_cseq"],
                    "business_context_key": LOGICAL_TOKEN,
                }
            )
        snapshot = {
            "schema_version": 1,
            "logical_call_token": LOGICAL_TOKEN,
            "created_by_pid": os.getpid(),
            "legs": snapshot_legs,
        }
        write_json_atomic(args.snapshot, snapshot)
        print(
            f"APP_SNAPSHOT_WRITTEN path={args.snapshot} "
            f"legs={len(snapshot_legs)} contains_dum_handles=false",
            flush=True,
        )
    else:
        attached = all(
            leg["handle_attached_to_logical_token"]
            and leg["business_context_key"] == LOGICAL_TOKEN
            for leg in result["legs"]
        )
        handle_ids = {leg["handle_id"] for leg in result["legs"]}
        if not attached or len(handle_ids) != 2:
            raise RuntimeError("phase-B handles did not share the restored call token")
        print(
            "PHASE_B_HANDLES_ATTACHED "
            + json.dumps(
                {
                    "legs": [
                        {
                            "name": leg["name"],
                            "handle_id": leg["handle_id"],
                            "logical_call_token": leg["business_context_key"],
                            "attached": leg["handle_attached_to_logical_token"],
                        }
                        for leg in result["legs"]
                    ],
                    "distinct_handle_count": len(handle_ids),
                    "same_logical_token": attached,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    print(
        f"CHILD_PASS phase={args.phase} pid={os.getpid()} "
        f"answers={result['answer_count']} connected={result['connected_count']} "
        f"policy_callbacks={len(callback_records)}",
        flush=True,
    )
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("phase-a", "phase-b"), required=True)
    parser.add_argument("--client-port", type=int, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--peer-a-port", type=int)
    parser.add_argument("--peer-b-port", type=int)
    args = parser.parse_args()
    if args.phase == "phase-a" and (args.peer_a_port is None or args.peer_b_port is None):
        parser.error("phase-a requires both peer ports")
    try:
        return run(args)
    except Exception as error:
        print(f"CHILD_FAIL phase={args.phase} pid={os.getpid()} error={error}", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    sys.exit(main())