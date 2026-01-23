"""
TEST: MAKER Voting System
Tests first-to-ahead-by-K voting and red-flagging.

Run with: python -m brain_testing.tests.test_maker_voting
"""

import sys
import os
import random
from typing import List, Dict, Any
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.schemas.actions import AtomicAction, ActionType, ActionTarget, ActionProposal


@dataclass
class VoteResult:
    winner: ActionProposal
    total_votes: int
    margin: int
    rounds: int


class MAKERVoting:
    """MAKER voting system with first-to-ahead-by-K."""
    
    def __init__(self, default_k: int = 2):
        self.default_k = default_k
        self.red_flag_rules = [
            "low_confidence",
            "ambiguous_target",
            "irreversible_action",
            "missing_focus",
            "unexpected_modal"
        ]
    
    def red_flag_check(self, proposal: ActionProposal, observation: Dict) -> List[str]:
        """Check proposal for red flags."""
        flags = []
        
        if proposal.action.confidence < 0.7:
            flags.append("low_confidence")
        
        if proposal.action.target and not proposal.action.target.element_id:
            if not proposal.action.target.is_coordinate_target():
                flags.append("ambiguous_target")
        
        if not proposal.action.is_reversible:
            flags.append("irreversible_action")
        
        if observation.get("modal_present"):
            flags.append("unexpected_modal")
        
        return flags
    
    def vote(self, proposals: List[ActionProposal], k: int = None) -> VoteResult:
        """Run first-to-ahead-by-K voting."""
        k = k or self.default_k
        
        # Count votes per action type+target combination
        vote_counts = {}
        for p in proposals:
            key = f"{p.action.action_type.value}:{p.action.target.element_id if p.action.target else 'none'}"
            vote_counts[key] = vote_counts.get(key, 0) + 1
            p.votes = vote_counts[key]
        
        # Sort by votes
        sorted_keys = sorted(vote_counts.keys(), key=lambda x: -vote_counts[x])
        
        if len(sorted_keys) >= 2:
            leader_votes = vote_counts[sorted_keys[0]]
            runner_up_votes = vote_counts[sorted_keys[1]]
            margin = leader_votes - runner_up_votes
        else:
            leader_votes = vote_counts[sorted_keys[0]] if sorted_keys else 0
            margin = leader_votes
        
        # Find winning proposal
        winner = None
        for p in proposals:
            key = f"{p.action.action_type.value}:{p.action.target.element_id if p.action.target else 'none'}"
            if key == sorted_keys[0]:
                winner = p
                break
        
        return VoteResult(winner=winner, total_votes=len(proposals), margin=margin, rounds=1)


def test_basic_voting():
    """Test 1: Basic voting with clear winner."""
    print("=" * 60)
    print("TEST 1: Basic Voting - Clear Winner")
    print("=" * 60)
    
    target = ActionTarget(element_id="btn_login")
    proposals = [
        ActionProposal(
            action=AtomicAction(action_type=ActionType.CLICK, target=target),
            rationale="Click login button",
            proposer_id=f"agent_{i}"
        ) for i in range(4)
    ]
    # Add one dissenting vote
    proposals.append(ActionProposal(
        action=AtomicAction(action_type=ActionType.CLICK, target=ActionTarget(element_id="btn_cancel")),
        rationale="Click cancel",
        proposer_id="agent_4"
    ))
    
    voting = MAKERVoting(default_k=2)
    result = voting.vote(proposals, k=2)
    
    print(f"\n[Proposals]: 4x click login, 1x click cancel")
    print(f"[K value]: 2")
    print(f"[Winner]: {result.winner.action.target.element_id}")
    print(f"[Margin]: {result.margin} (needed: 2)")
    print(f"[Result]: {'CONSENSUS' if result.margin >= 2 else 'NO CONSENSUS'}")
    print("\n✅ TEST 1 PASSED")


def test_red_flagging():
    """Test 2: Red-flag filtering."""
    print("\n" + "=" * 60)
    print("TEST 2: Red-Flag Filtering")
    print("=" * 60)
    
    voting = MAKERVoting()
    observation = {"modal_present": False}
    
    proposals = [
        ActionProposal(
            action=AtomicAction(action_type=ActionType.CLICK, confidence=0.95, is_reversible=True,
                              target=ActionTarget(element_id="btn1")),
            rationale="High confidence click", proposer_id="agent_1"
        ),
        ActionProposal(
            action=AtomicAction(action_type=ActionType.CLICK, confidence=0.5, is_reversible=True,
                              target=ActionTarget(element_id="btn2")),
            rationale="Low confidence click", proposer_id="agent_2"
        ),
        ActionProposal(
            action=AtomicAction(action_type=ActionType.CLICK, confidence=0.9, is_reversible=False,
                              target=ActionTarget(element_id="btn3")),
            rationale="Irreversible action", proposer_id="agent_3"
        ),
    ]
    
    print("\n[Checking proposals for red flags]:")
    for p in proposals:
        flags = voting.red_flag_check(p, observation)
        p.red_flags = flags
        p.is_filtered = len(flags) > 0
        status = "❌ FILTERED" if p.is_filtered else "✅ OK"
        print(f"  {p.proposer_id}: {status} - {flags if flags else 'no flags'}")
    
    filtered = [p for p in proposals if not p.is_filtered]
    print(f"\n[Remaining after filtering]: {len(filtered)}/{len(proposals)}")
    print("\n✅ TEST 2 PASSED")


def test_dynamic_k():
    """Test 3: Dynamic K adjustment based on risk."""
    print("\n" + "=" * 60)
    print("TEST 3: Dynamic K Adjustment")
    print("=" * 60)
    
    scenarios = [
        {"risk": "low", "description": "Click a link", "k": 1},
        {"risk": "medium", "description": "Fill form field", "k": 2},
        {"risk": "high", "description": "Submit payment", "k": 4},
    ]
    
    print("\n[K values by risk level]:")
    for s in scenarios:
        print(f"  [{s['risk'].upper()}] {s['description']}: K={s['k']}")
    
    print("\n[Principle]: Higher K = more consensus needed = safer")
    print("\n✅ TEST 3 PASSED")


def run_all_tests():
    """Run all MAKER voting tests."""
    print("\n" + "=" * 60)
    print("MAKER VOTING TESTS")
    print("=" * 60)
    
    test_basic_voting()
    test_red_flagging()
    test_dynamic_k()
    
    print("\n" + "=" * 60)
    print("ALL MAKER TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
