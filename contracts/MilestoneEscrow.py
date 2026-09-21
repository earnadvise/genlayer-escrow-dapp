# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
import genlayer as gl
from genlayer import *


@allow_storage
@dataclass
class MilestoneItem:
    index: u256
    title: str
    amount: u256
    status: str  # "PENDING" | "DELIVERED" | "APPROVED" | "DISPUTED" | "RESOLVED" | "REFUNDED"
    delivery_artifact: str
    dispute_buyer_statement: str
    dispute_seller_statement: str
    buyer_waived_statement: bool
    seller_waived_statement: bool
    resolution_reason: str
    payout_seller_percent: u256


@allow_storage
@dataclass
class MultiMilestoneEscrow:
    id: u256
    buyer: Address
    seller: Address
    total_amount: u256
    released_amount: u256
    current_milestone_index: u256
    milestone_count: u256
    status: str  # "AWAITING_DEPOSIT" | "ACTIVE" | "COMPLETED" | "CANCELLED"
    project_title: str
    project_spec: str
    milestones: TreeMap[u256, MilestoneItem]


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


class MilestoneEscrow(gl.Contract):
    escrows: TreeMap[u256, MultiMilestoneEscrow]
    next_escrow_id: u256

    def __init__(self) -> None:
        self.next_escrow_id = u256(0)

    @gl.public.write
    def create_escrow(
        self,
        seller_address: str,
        project_title: str,
        project_spec: str,
        titles_json: str,
        amounts_json: str
    ) -> u256:
        """
        Creates a multi-milestone escrow agreement with phased tranches.
        titles_json: JSON list of string titles, e.g. '["Phase 1: Architecture", "Phase 2: MVP Implementation"]'
        amounts_json: JSON list of integer amounts, e.g. '[1000, 2500]'
        """
        escrow_id = self.next_escrow_id
        self.next_escrow_id = self.next_escrow_id + u256(1)

        titles = json.loads(titles_json)
        amounts = json.loads(amounts_json)

        if len(titles) != len(amounts):
            raise gl.vm.UserError("Titles and amounts array lengths must match")

        if len(titles) == 0:
            raise gl.vm.UserError("Must specify at least one milestone")

        total_escrow_amount = u256(0)
        milestones_map = TreeMap[u256, MilestoneItem]()

        for idx, (t, a) in enumerate(zip(titles, amounts)):
            amount_u256 = u256(int(a))
            total_escrow_amount = total_escrow_amount + amount_u256
            milestones_map[u256(idx)] = MilestoneItem(
                index=u256(idx),
                title=str(t),
                amount=amount_u256,
                status="PENDING",
                delivery_artifact="",
                dispute_buyer_statement="",
                dispute_seller_statement="",
                buyer_waived_statement=False,
                seller_waived_statement=False,
                resolution_reason="",
                payout_seller_percent=u256(0)
            )

        new_escrow = MultiMilestoneEscrow(
            id=escrow_id,
            buyer=gl.message.sender_address,
            seller=Address(seller_address),
            total_amount=total_escrow_amount,
            released_amount=u256(0),
            current_milestone_index=u256(0),
            milestone_count=u256(len(titles)),
            status="AWAITING_DEPOSIT",
            project_title=project_title,
            project_spec=project_spec,
            milestones=milestones_map
        )
        self.escrows[escrow_id] = new_escrow
        return escrow_id

    @gl.public.write.payable
    def deposit(self, escrow_id: u256) -> None:
        """
        Deposits total project funds into the multi-milestone contract.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.buyer != gl.message.sender_address:
            raise gl.vm.UserError("Only buyer can deposit funds")

        if escrow.status != "AWAITING_DEPOSIT":
            raise gl.vm.UserError("Escrow is not awaiting deposit")

        if gl.message.value < escrow.total_amount:
            raise gl.vm.UserError("Deposit value must meet or exceed total milestone sum")

        escrow.status = "ACTIVE"
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def submit_milestone_delivery(
        self,
        escrow_id: u256,
        milestone_index: u256,
        delivery_artifact: str
    ) -> None:
        """
        Allows seller to submit delivery for a specific milestone tranche.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.seller != gl.message.sender_address:
            raise gl.vm.UserError("Only seller can submit milestone delivery")

        if escrow.status != "ACTIVE":
            raise gl.vm.UserError("Escrow is not in active state")

        if milestone_index not in escrow.milestones:
            raise gl.vm.UserError("Milestone index not found")

        milestone = escrow.milestones[milestone_index]

        if milestone.status not in ["PENDING", "DELIVERED"]:
            raise gl.vm.UserError("Milestone cannot be delivered in current status")

        milestone.delivery_artifact = delivery_artifact
        milestone.status = "DELIVERED"
        escrow.milestones[milestone_index] = milestone
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def approve_milestone(self, escrow_id: u256, milestone_index: u256) -> None:
        """
        Allows buyer to approve a milestone tranche, releasing 100% of that milestone's funds.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if escrow.buyer != gl.message.sender_address:
            raise gl.vm.UserError("Only buyer can approve milestone")

        if escrow.status != "ACTIVE":
            raise gl.vm.UserError("Escrow is not in active state")

        if milestone_index not in escrow.milestones:
            raise gl.vm.UserError("Milestone index not found")

        milestone = escrow.milestones[milestone_index]

        if milestone.status != "DELIVERED":
            raise gl.vm.UserError("Milestone must be delivered before approval")

        payout_amount = milestone.amount
        seller_addr = escrow.seller

        # Transfer tranche to seller
        _Recipient(seller_addr).emit_transfer(value=payout_amount)

        milestone.status = "APPROVED"
        milestone.payout_seller_percent = u256(100)
        milestone.resolution_reason = "Buyer approved milestone tranche"
        escrow.milestones[milestone_index] = milestone

        escrow.released_amount = escrow.released_amount + payout_amount
        if escrow.released_amount >= escrow.total_amount:
            escrow.status = "COMPLETED"

        self.escrows[escrow_id] = escrow

    @gl.public.write
    def dispute_milestone(
        self,
        escrow_id: u256,
        milestone_index: u256,
        statement: str
    ) -> None:
        """
        Disputes a specific milestone tranche.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        if not statement or not statement.strip():
            raise gl.vm.UserError("Dispute statement cannot be empty")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only buyer or seller can dispute a milestone")

        if milestone_index not in escrow.milestones:
            raise gl.vm.UserError("Milestone index not found")

        milestone = escrow.milestones[milestone_index]

        if milestone.status not in ["PENDING", "DELIVERED", "DISPUTED"]:
            raise gl.vm.UserError("Milestone cannot be disputed in current status")

        if sender == escrow.buyer:
            milestone.dispute_buyer_statement = statement
            milestone.buyer_waived_statement = False
        else:
            milestone.dispute_seller_statement = statement
            milestone.seller_waived_statement = False

        milestone.status = "DISPUTED"
        escrow.milestones[milestone_index] = milestone
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def waive_milestone_dispute(self, escrow_id: u256, milestone_index: u256) -> None:
        """
        Explicitly waives right to submit counter-statement on a disputed milestone.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]
        sender = gl.message.sender_address

        if sender != escrow.buyer and sender != escrow.seller:
            raise gl.vm.UserError("Only buyer or seller can waive dispute statement")

        if milestone_index not in escrow.milestones:
            raise gl.vm.UserError("Milestone index not found")

        milestone = escrow.milestones[milestone_index]

        if milestone.status != "DISPUTED":
            raise gl.vm.UserError("Milestone is not in disputed state")

        if sender == escrow.buyer:
            milestone.buyer_waived_statement = True
        else:
            milestone.seller_waived_statement = True

        escrow.milestones[milestone_index] = milestone
        self.escrows[escrow_id] = escrow

    @gl.public.write
    def adjudicate_milestone(self, escrow_id: u256, milestone_index: u256) -> None:
        """
        Resolves a disputed milestone tranche using AI-Validator consensus.
        """
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")

        escrow = self.escrows[escrow_id]

        if milestone_index not in escrow.milestones:
            raise gl.vm.UserError("Milestone index not found")

        milestone = escrow.milestones[milestone_index]

        if milestone.status != "DISPUTED":
            raise gl.vm.UserError("Milestone is not in disputed status")

        buyer_ready = bool(milestone.dispute_buyer_statement.strip()) or milestone.buyer_waived_statement
        seller_ready = bool(milestone.dispute_seller_statement.strip()) or milestone.seller_waived_statement

        if not buyer_ready or not seller_ready:
            raise gl.vm.UserError("Both parties must submit statements or explicitly waive before adjudication")

        spec = escrow.project_spec
        m_title = milestone.title
        artifact = milestone.delivery_artifact
        buyer_stmt = milestone.dispute_buyer_statement or "[Buyer waived counter-statement]"
        seller_stmt = milestone.dispute_seller_statement or "[Seller waived counter-statement]"

        def resolve_milestone_ai() -> str:
            web_content = ""
            if artifact.startswith("http://") or artifact.startswith("https://"):
                try:
                    web_content = gl.nondet.web.render(artifact, mode="text")
                except Exception as e:
                    web_content = f"Error fetching artifact: {str(e)}"

            task = f"""
            You are a decentralized arbitrator. Adjudicate this specific milestone tranche dispute:
            PROJECT SPEC: {spec}
            MILESTONE TITLE: {m_title}
            DELIVERY ARTIFACT: {artifact}
            WEB CONTENT: {web_content}
            BUYER CLAIM: {buyer_stmt}
            SELLER CLAIM: {seller_stmt}

            Determine fair percentage (0 to 100) allocated to the Seller for this milestone tranche.
            Format output strictly as JSON:
            {{
                "payment_to_seller_percentage": int,
                "reasoning": str
            }}
            """
            res = gl.nondet.exec_prompt(task, response_format="json")
            return json.dumps(res, sort_keys=True)

        result_str = gl.eq_principle.strict_eq(resolve_milestone_ai)
        result_json = json.loads(result_str)

        payout_percent = int(result_json["payment_to_seller_percentage"])
        if payout_percent < 0:
            payout_percent = 0
        elif payout_percent > 100:
            payout_percent = 100

        tranche_amount = milestone.amount
        seller_share = (tranche_amount * u256(payout_percent)) // u256(100)
        buyer_share = tranche_amount - seller_share

        if seller_share > u256(0):
            _Recipient(escrow.seller).emit_transfer(value=seller_share)
        if buyer_share > u256(0):
            _Recipient(escrow.buyer).emit_transfer(value=buyer_share)

        milestone.status = "RESOLVED"
        milestone.payout_seller_percent = u256(payout_percent)
        milestone.resolution_reason = result_json.get("reasoning", "AI Arbitration completed")
        escrow.milestones[milestone_index] = milestone

        escrow.released_amount = escrow.released_amount + tranche_amount
        if escrow.released_amount >= escrow.total_amount:
            escrow.status = "COMPLETED"

        self.escrows[escrow_id] = escrow

    @gl.public.view
    def get_escrow(self, escrow_id: u256) -> MultiMilestoneEscrow:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")
        return self.escrows[escrow_id]

    @gl.public.view
    def get_milestone_item(self, escrow_id: u256, milestone_index: u256) -> MilestoneItem:
        if escrow_id not in self.escrows:
            raise gl.vm.UserError("Escrow not found")
        if milestone_index not in self.escrows[escrow_id].milestones:
            raise gl.vm.UserError("Milestone index not found")
        return self.escrows[escrow_id].milestones[milestone_index]
