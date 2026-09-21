import json
import pytest
from genlayer import *


def test_multi_milestone_phased_flow(direct_deploy, direct_vm):
    """
    Tests the complete multi-milestone phased workflow:
    1. Create escrow with 2 distinct milestones (Phase 1: 2000 WEI, Phase 2: 3000 WEI).
    2. Buyer deposits 5000 WEI.
    3. Seller delivers Milestone #0, Buyer approves Milestone #0 (2000 WEI released to Seller).
    4. Seller delivers Milestone #1, a dispute is raised, AI arbitrator resolves 70/30 split.
    5. Escrow transitions to COMPLETED.
    """
    contract = direct_deploy("contracts/MilestoneEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    titles = json.dumps(["Phase 1: Wireframes & Spec", "Phase 2: Full Implementation"])
    amounts = json.dumps([2000, 3000])

    # 1. Create multi-milestone escrow
    direct_vm.sender = alice
    escrow_id = contract.create_escrow(
        bob.as_hex,
        "Decentralized Oracle Integration",
        "Build multi-source price feed oracle",
        titles,
        amounts,
    )
    assert escrow_id == u256(0)

    escrow = contract.get_escrow(escrow_id)
    assert escrow.total_amount == u256(5000)
    assert escrow.released_amount == u256(0)
    assert escrow.milestone_count == u256(2)
    assert escrow.status == "AWAITING_DEPOSIT"

    # 2. Deposit 5000 WEI
    direct_vm.value = u256(5000)
    contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    escrow = contract.get_escrow(escrow_id)
    assert escrow.status == "ACTIVE"

    # 3. Phase 1: Delivery and manual approval
    direct_vm.sender = bob
    contract.submit_milestone_delivery(
        escrow_id, u256(0), "https://example.com/spec.pdf"
    )

    m0 = contract.get_milestone_item(escrow_id, u256(0))
    assert m0.status == "DELIVERED"

    direct_vm.sender = alice
    contract.approve_milestone(escrow_id, u256(0))

    m0_approved = contract.get_milestone_item(escrow_id, u256(0))
    assert m0_approved.status == "APPROVED"
    assert m0_approved.payout_seller_percent == u256(100)

    escrow = contract.get_escrow(escrow_id)
    assert escrow.released_amount == u256(2000)
    assert escrow.status == "ACTIVE"

    # 4. Phase 2: Delivery & AI Dispute Arbitration
    direct_vm.sender = bob
    contract.submit_milestone_delivery(
        escrow_id, u256(1), "https://example.com/repo-v1"
    )

    # Buyer disputes Phase 2
    direct_vm.sender = alice
    contract.dispute_milestone(
        escrow_id, u256(1), "Missing unit tests for error boundaries."
    )

    # Seller responds
    direct_vm.sender = bob
    contract.dispute_milestone(
        escrow_id, u256(1), "Core price aggregation is functional."
    )

    # Mock web & LLM decision (70% to seller, 30% to buyer)
    direct_vm.mock_web(
        r".*repo-v1", {"status": 200, "body": "<code>Oracle Code</code>"}
    )
    decision = '{"payment_to_seller_percentage": 70, "reasoning": "Core feeds work, test coverage partial."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision)

    # Adjudicate Phase 2
    direct_vm.sender = alice
    contract.adjudicate_milestone(escrow_id, u256(1))

    m1_resolved = contract.get_milestone_item(escrow_id, u256(1))
    assert m1_resolved.status == "RESOLVED"
    assert m1_resolved.payout_seller_percent == u256(70)

    # Entire escrow completed
    escrow_final = contract.get_escrow(escrow_id)
    assert escrow_final.released_amount == u256(5000)
    assert escrow_final.status == "COMPLETED"


def test_multi_milestone_waiver_flow(direct_deploy, direct_vm):
    """
    Tests that a party can waive their counter-statement so arbitration is not blocked.
    """
    contract = direct_deploy("contracts/MilestoneEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    titles = json.dumps(["Single Phase Delivery"])
    amounts = json.dumps([1000])

    direct_vm.sender = alice
    escrow_id = contract.create_escrow(
        bob.as_hex,
        "Documentation",
        "Write complete API documentation",
        titles,
        amounts,
    )
    direct_vm.value = u256(1000)
    contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Bob delivers
    direct_vm.sender = bob
    contract.submit_milestone_delivery(escrow_id, u256(0), "https://example.com/docs")

    # Alice disputes
    direct_vm.sender = alice
    contract.dispute_milestone(escrow_id, u256(0), "Docs are missing installation section.")

    # Bob waives counter-statement
    direct_vm.sender = bob
    contract.waive_milestone_dispute(escrow_id, u256(0))

    # Adjudication proceeds immediately
    direct_vm.mock_web(r".*docs", {"status": 200, "body": "API Docs"})
    decision = '{"payment_to_seller_percentage": 50, "reasoning": "Missing install guide."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision)

    contract.adjudicate_milestone(escrow_id, u256(0))
    item = contract.get_milestone_item(escrow_id, u256(0))
    assert item.status == "RESOLVED"
    assert item.payout_seller_percent == u256(50)


def test_multi_milestone_validation_errors(direct_deploy, direct_vm):
    """
    Tests security boundaries and error handling.
    """
    contract = direct_deploy("contracts/MilestoneEscrow.py")
    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")
    charlie = Address("0x0000000000000000000000000000000000000003")

    # Mismatched titles and amounts
    with pytest.raises(Exception):
        contract.create_escrow(
            bob.as_hex, "Title", "Spec", json.dumps(["A", "B"]), json.dumps([100])
        )

    # Valid creation
    direct_vm.sender = alice
    escrow_id = contract.create_escrow(
        bob.as_hex, "Security Task", "Audit", json.dumps(["Audit Report"]), json.dumps([500])
    )

    # Unauthorized deposit (Charlie tries to fund)
    direct_vm.sender = charlie
    direct_vm.value = u256(500)
    with pytest.raises(Exception):
        contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Underfunded deposit
    direct_vm.sender = alice
    direct_vm.value = u256(200)
    with pytest.raises(Exception):
        contract.deposit(escrow_id)
    direct_vm.value = u256(0)

