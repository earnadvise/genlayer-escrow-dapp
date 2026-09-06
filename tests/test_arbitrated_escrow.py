import pytest
from genlayer import *


def test_escrow_happy_path(direct_deploy, direct_vm):
    """
    Tests the basic flow: escrow creation, fund deposit, delivery submission, and manual buyer approval.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # 1. Create escrow
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(
        bob.as_hex, "Complete news web scraper project in Python."
    )

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.buyer == alice
    assert escrow.seller == bob
    assert escrow.status == "AWAITING_DEPOSIT"
    assert escrow.amount == u256(0)

    # 2. Deposit funds (1000 wei)
    direct_vm.value = u256(1000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.amount == u256(1000)
    assert escrow.status == "ESCROWED"

    # 3. Seller submits delivery artifact
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://github.com/bob/news-scraper")

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.delivery_artifact == "https://github.com/bob/news-scraper"
    assert escrow.status == "DELIVERED"

    # 4. Buyer approves delivery (manual release)
    direct_vm.sender = alice
    escrow_contract.approve_delivery(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(100)
    assert escrow.amount == u256(0)
    assert escrow.resolution_reason == "Buyer approved delivery"


def test_escrow_voluntary_refund(direct_deploy, direct_vm):
    """
    Tests the case where a seller voluntarily refunds a buyer.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Consultation session")
    direct_vm.value = u256(500)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller triggers voluntary refund
    direct_vm.sender = bob
    escrow_contract.refund_buyer(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "REFUNDED"
    assert escrow.payout_seller_percent == u256(0)
    assert escrow.amount == u256(0)
    assert escrow.resolution_reason == "Seller voluntarily refunded the buyer"


def test_dispute_race_condition_prevented_and_resolved(direct_deploy, direct_vm):
    """
    Tests that a dispute CANNOT be adjudicated when only one party has filed a statement
    (preventing front-running/race condition), and only succeeds once the counterparty responds.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Design vector logo files.")
    direct_vm.value = u256(5000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller submits delivery URL
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://example.com/logo-draft.svg")

    # Buyer files dispute with statement
    direct_vm.sender = alice
    escrow_contract.dispute_escrow(
        escrow_id, "The design is incomplete and lines are jagged."
    )

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "DISPUTED"
    assert escrow.dispute_buyer_statement == "The design is incomplete and lines are jagged."
    assert escrow.dispute_seller_statement == ""

    # ATTEMPT RACE: Trying to adjudicate before seller responds MUST fail
    with pytest.raises(Exception):
        escrow_contract.adjudicate_escrow(escrow_id)

    # Seller files response statement
    direct_vm.sender = bob
    escrow_contract.dispute_escrow(
        escrow_id, "I followed the specification sheet exactly."
    )

    # Mock non-deterministic web page rendering for the delivery URL
    direct_vm.mock_web(
        r".*logo-draft\.svg", {"status": 200, "body": "<svg>Mock SVG data</svg>"}
    )

    # Mock LLM decision: Split 60% to Seller, 40% to Buyer
    decision_json = '{"payment_to_seller_percentage": 60, "reasoning": "Seller completed primary shapes but did not apply vector smoothing."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision_json)

    # Now adjudication succeeds because both parties submitted their statements
    direct_vm.sender = alice
    escrow_contract.adjudicate_escrow(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(60)
    assert (
        escrow.resolution_reason
        == "Seller completed primary shapes but did not apply vector smoothing."
    )
    assert escrow.amount == u256(0)


def test_dispute_explicit_waiver_path(direct_deploy, direct_vm):
    """
    Tests that if a counterparty explicitly waives their response statement,
    adjudication is unblocked and resolves fairly.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")

    # Create & deposit
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Front-end refactor.")
    direct_vm.value = u256(3000)
    escrow_contract.deposit(escrow_id)
    direct_vm.value = u256(0)

    # Seller submits delivery
    direct_vm.sender = bob
    escrow_contract.submit_delivery(escrow_id, "https://github.com/bob/repo")

    # Buyer files dispute
    direct_vm.sender = alice
    escrow_contract.dispute_escrow(escrow_id, "Build failed on test suite.")

    # Seller explicitly waives right to submit a dispute counter-statement
    direct_vm.sender = bob
    escrow_contract.waive_dispute_statement(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.seller_waived_statement is True

    # Mock LLM decision: 10% to seller, 90% refund to buyer
    decision_json = '{"payment_to_seller_percentage": 10, "reasoning": "Seller provided boilerplate but failed test requirements."}'
    direct_vm.mock_llm(r".*arbitrator.*", decision_json)

    # Adjudication proceeds successfully
    direct_vm.sender = alice
    escrow_contract.adjudicate_escrow(escrow_id)

    escrow = escrow_contract.get_escrow(escrow_id)
    assert escrow.status == "RESOLVED"
    assert escrow.payout_seller_percent == u256(10)
    assert escrow.amount == u256(0)


def test_escrow_reverts(direct_deploy, direct_vm):
    """
    Verifies state checks and unauthorized caller failure conditions.
    """
    escrow_contract = direct_deploy("contracts/ArbitratedEscrow.py")

    alice = Address("0x0000000000000000000000000000000000000001")
    bob = Address("0x0000000000000000000000000000000000000002")
    charlie = Address("0x0000000000000000000000000000000000000003")

    # Create
    direct_vm.sender = alice
    escrow_id = escrow_contract.create_escrow(bob.as_hex, "Write blog post.")

    # 1. Non-buyer trying to deposit
    direct_vm.sender = charlie
    direct_vm.value = u256(100)
    with pytest.raises(Exception):
        escrow_contract.deposit(escrow_id)

    # 2. Deposit with 0 value
    direct_vm.sender = alice
    direct_vm.value = u256(0)
    with pytest.raises(Exception):
        escrow_contract.deposit(escrow_id)

    # 3. Buyer trying to approve delivery before it's deposited
    with pytest.raises(Exception):
        escrow_contract.approve_delivery(escrow_id)

    # 4. Unauthorized user trying to waive statement
    direct_vm.sender = charlie
    with pytest.raises(Exception):
        escrow_contract.waive_dispute_statement(escrow_id)
