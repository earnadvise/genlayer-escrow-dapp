import json
import pytest
from genlayer import *


def test_bounty_pool_creation_and_funding(direct_deploy, direct_vm):
    """
    Tests pool creation, reward structure validation, and initial funding requirements.
    """
    oracle = direct_deploy("contracts/AutonomousBountyOracle.py", min_stake=u256(100))
    sponsor = Address("0x0000000000000000000000000000000000000010")

    direct_vm.sender = sponsor
    direct_vm.value = u256(10000)

    pool_id = oracle.create_bounty_pool(
        "GenLayer Core Protocol",
        "https://github.com/genlayer/genlayer-core",
        "In-scope: GenVM, Consensus engine, and State storage. Out of scope: Docs and UI typos.",
        u256(5000),  # Critical
        u256(2500),  # High
        u256(1000),  # Medium
        u256(250),   # Low
    )
    assert pool_id == u256(0)

    pool = oracle.get_pool(pool_id)
    assert pool.sponsor == sponsor
    assert pool.project_name == "GenLayer Core Protocol"
    assert pool.total_funded == u256(10000)
    assert pool.total_paid == u256(0)
    assert pool.active is True


def test_valid_critical_vulnerability_triage_and_payout(direct_deploy, direct_vm):
    """
    Tests valid Critical report triage:
    - Researcher submits report with anti-spam stake.
    - AI consensus validates PoC and assigns CRITICAL severity.
    - Contract releases 5,000 WEI bounty + 100 WEI stake refund to researcher.
    """
    oracle = direct_deploy("contracts/AutonomousBountyOracle.py", min_stake=u256(100))
    sponsor = Address("0x0000000000000000000000000000000000000010")
    whitehat = Address("0x0000000000000000000000000000000000000099")

    # 1. Sponsor creates pool with 10,000 WEI
    direct_vm.sender = sponsor
    direct_vm.value = u256(10000)
    pool_id = oracle.create_bounty_pool(
        "DeFi Vault",
        "https://github.com/example/vault",
        "Reentrancy, unauthorized withdrawals, and state corruption.",
        u256(5000),
        u256(2000),
        u256(500),
        u256(100)
    )
    direct_vm.value = u256(0)

    # 2. Whitehat submits vulnerability with 100 WEI stake
    direct_vm.sender = whitehat
    direct_vm.value = u256(100)
    report_id = oracle.submit_vulnerability(
        pool_id,
        "Zero-day Reentrancy in Flash Loan Callback",
        "https://gist.github.com/whitehat/poc-reentrancy",
        "CRITICAL"
    )
    assert report_id == u256(0)
    direct_vm.value = u256(0)

    report = oracle.get_report(report_id)
    assert report.status == "SUBMITTED"
    assert report.stake_amount == u256(100)

    # 3. Mock AI consensus response
    direct_vm.mock_web(r".*poc-reentrancy", {"status": 200, "body": "PoC: Exploit script drains vault via reentrancy callback."})
    direct_vm.mock_web(r".*vault", {"status": 200, "body": "Vault Contract: deposit, withdraw, flashLoan."})

    decision = json.dumps({
        "verdict": "VALID",
        "verified_severity": "CRITICAL",
        "reasoning": "Reproducible zero-day draining funds via non-reentrant missing guard."
    })
    direct_vm.mock_llm(r".*Triage Validator.*", decision)

    # 4. Triage and settle
    oracle.triage_and_settle(report_id)

    # 5. Verify results
    updated_report = oracle.get_report(report_id)
    assert updated_report.status == "PAID"
    assert updated_report.awarded_severity == "CRITICAL"
    assert updated_report.awarded_amount == u256(5000)

    updated_pool = oracle.get_pool(pool_id)
    assert updated_pool.total_paid == u256(5000)


def test_out_of_scope_report_stake_refund(direct_deploy, direct_vm):
    """
    Tests that out-of-scope reports receive no payout, but have their anti-spam stake safely returned.
    """
    oracle = direct_deploy("contracts/AutonomousBountyOracle.py", min_stake=u256(100))
    sponsor = Address("0x0000000000000000000000000000000000000010")
    whitehat = Address("0x0000000000000000000000000000000000000099")

    direct_vm.sender = sponsor
    direct_vm.value = u256(6000)
    pool_id = oracle.create_bounty_pool(
        "Protocol", "https://example.com", "Core smart contracts only.",
        u256(4000), u256(2000), u256(500), u256(100)
    )

    direct_vm.sender = whitehat
    direct_vm.value = u256(100)
    report_id = oracle.submit_vulnerability(
        pool_id, "Missing Favicon in Landing Page", "https://example.com/ui-bug", "LOW"
    )

    direct_vm.mock_web(r".*ui-bug", {"status": 200, "body": "404 favicon"})
    decision = json.dumps({
        "verdict": "OUT_OF_SCOPE",
        "verified_severity": "NONE",
        "reasoning": "UI asset is outside core smart contracts scope."
    })
    direct_vm.mock_llm(r".*Triage Validator.*", decision)

    oracle.triage_and_settle(report_id)

    report = oracle.get_report(report_id)
    assert report.status == "REJECTED_OUT_OF_SCOPE"
    assert report.awarded_amount == u256(0)


def test_spam_report_stake_slashed(direct_deploy, direct_vm):
    """
    Tests that malicious or spam reports have their stake slashed and sent to the sponsor.
    """
    oracle = direct_deploy("contracts/AutonomousBountyOracle.py", min_stake=u256(100))
    sponsor = Address("0x0000000000000000000000000000000000000010")
    spammer = Address("0x0000000000000000000000000000000000000066")

    direct_vm.sender = sponsor
    direct_vm.value = u256(5000)
    pool_id = oracle.create_bounty_pool(
        "Bridge", "https://example.com", "Bridge contracts.",
        u256(3000), u256(1500), u256(400), u256(100)
    )

    direct_vm.sender = spammer
    direct_vm.value = u256(100)
    report_id = oracle.submit_vulnerability(
        pool_id, "Gibberish spam text", "https://example.com/nonsense", "CRITICAL"
    )

    direct_vm.mock_web(r".*nonsense", {"status": 404, "body": "Not found"})
    decision = json.dumps({
        "verdict": "SPAM",
        "verified_severity": "NONE",
        "reasoning": "Fake report with broken link and non-existent exploit."
    })
    direct_vm.mock_llm(r".*Triage Validator.*", decision)

    oracle.triage_and_settle(report_id)

    report = oracle.get_report(report_id)
    assert report.status == "REJECTED_SPAM"
    assert "Slashed" in report.triage_reasoning


def test_pool_top_up_and_closure(direct_deploy, direct_vm):
    """
    Tests pool top-ups and sponsor withdrawal upon pool closure.
    """
    oracle = direct_deploy("contracts/AutonomousBountyOracle.py", min_stake=u256(100))
    sponsor = Address("0x0000000000000000000000000000000000000010")
    other = Address("0x0000000000000000000000000000000000000077")

    direct_vm.sender = sponsor
    direct_vm.value = u256(5000)
    pool_id = oracle.create_bounty_pool(
        "AMM", "https://example.com", "Swap math.",
        u256(4000), u256(2000), u256(500), u256(100)
    )

    # Top up pool with additional 2000 WEI
    direct_vm.sender = other
    direct_vm.value = u256(2000)
    oracle.top_up_pool(pool_id)

    pool = oracle.get_pool(pool_id)
    assert pool.total_funded == u256(7000)

    # Sponsor closes pool
    direct_vm.sender = sponsor
    oracle.close_bounty_pool(pool_id)

    closed_pool = oracle.get_pool(pool_id)
    assert closed_pool.active is False

    # Attempting to submit report on closed pool should fail
    direct_vm.sender = other
    direct_vm.value = u256(100)
    with pytest.raises(Exception):
        oracle.submit_vulnerability(pool_id, "Bug", "https://example.com/p", "LOW")
