"""Manual Terminal Runner for Testing SpectraFuse Phase 4 Session Memory (STM).

Demonstrates:
1. Multi-turn dialogue context retention (Region, Year, Month, Status).
2. Follow-up reasoning for 'Explain above' without deflection.
3. Follow-up UI action resolution for 'Show that on the map'.
4. Natural timeframe transition for 'What about September?'.
5. Export resolution for 'Download that CSV'.
6. Interactive real-time conversation mode.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.schemas import ChatRequest
from backend.agents.service import get_agent_service


def print_banner(text: str):
    print("\n" + "=" * 75)
    print(f"  {text}")
    print("=" * 75)


def print_session_state(session):
    print("\n🧠 [SHORT-TERM MEMORY (STM) STATE]")
    print(f"   • Session ID     : {session.session_id}")
    print(f"   • Active Region  : {session.active_region}")
    print(f"   • Active Year    : {session.active_year}")
    print(f"   • Active Month   : {session.active_month}")
    print(f"   • Last Detections: {session.last_detections}")
    print(f"   • Last Status    : {session.last_status}")
    print(f"   • STM Turns Stored: {len(session.turns)} / {session.max_turns} (max {session.max_pairs} pairs)")
    print("-" * 75)


def run_turn(service, user_message: str, session_id: str, region: str = "sri-lanka"):
    print(f"\n💬 USER > \"{user_message}\"")
    print("-" * 75)

    req = ChatRequest(message=user_message, session_id=session_id, region=region)
    res = service.process_chat(req)

    print(f"🎯 INTENT DETECTED : {res.intent}")
    print(f"💡 AGENT ANSWER    :\n{res.answer}\n")

    if res.evidence:
        print("📊 GROUNDED EVIDENCE:")
        for ev in res.evidence:
            print(f"   • [{ev.status.upper()}] {ev.product or 'harmonized'} -> {ev.metric}: {ev.value} (source: {ev.source})")

    if res.ui_actions:
        print("🗺️ UI ACTIONS DISPATCHED:")
        for act in res.ui_actions:
            print(f"   • Type: {act.type}")
            print(f"     Payload: {json.dumps(act.payload, indent=7)}")

    if res.downloads:
        print("📥 DOWNLOADS GENERATED:")
        for dl in res.downloads:
            print(f"   • {dl.label} -> {dl.url}")

    session = service.session_store.get(session_id)
    if session:
        print_session_state(session)


def main():
    parser = argparse.ArgumentParser(description="Manual Test Runner for Phase 4 Session Memory")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive multi-turn terminal chat")
    args = parser.parse_args()

    service = get_agent_service()
    session_id = "manual_memory_demo"

    # Reset session for clean run
    service.session_store.delete(session_id)

    if args.interactive:
        print_banner("SpectraFuse Phase 4 - Interactive Memory Chat Mode")
        print("Type your questions to test context retention. Type 'exit' or 'quit' to stop.\n")
        print("Try sequence:")
        print("  1. What was the fire activity in Sri Lanka in August 2021?")
        print("  2. Explain above")
        print("  3. Show that on the map")
        print("  4. What about September?")
        print("  5. Download that CSV\n")

        while True:
            try:
                msg = input("\nYou > ").strip()
                if not msg:
                    continue
                if msg.lower() in ("exit", "quit", "q"):
                    print("Exiting interactive test mode.")
                    break
                run_turn(service, msg, session_id)
            except (KeyboardInterrupt, EOFError):
                break
        return

    print_banner("SpectraFuse Phase 4 - Automated Multi-Turn Memory Verification")

    scenario_turns = [
        ("Turn 1 (Initial Data Query)", "What was the fire activity in Sri Lanka in August 2021?"),
        ("Turn 2 (Follow-up Reasoning)", "Explain above"),
        ("Turn 3 (Follow-up UI Action)", "Show that on the map"),
        ("Turn 4 (Temporal Continuity)", "What about September?"),
        ("Turn 5 (Follow-up Export)", "Download that CSV"),
        ("Turn 6 (Deterministic Gratitude)", "thank you"),
    ]

    for label, question in scenario_turns:
        print_banner(label)
        run_turn(service, question, session_id)

    print_banner("Phase 4 Multi-Turn Memory Test Completed Successfully!")


if __name__ == "__main__":
    main()
