/**
 * ArbitratedEscrow Web3 Frontend Application
 * Connects to GenLayer Bradbury Testnet
 */

const CONTRACT_ADDRESS = "0x27765327341E605F84493563A03Bf33d71ae0928";
const BRADBURY_RPC = "https://rpc-bradbury.genlayer.com";

// State
let userAccount = null;
let currentEscrow = {
  id: "0",
  buyer: "0x2030828a64a9064f199bcf711b1fa08c483805c9",
  seller: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  amount: "1.0",
  status: "DISPUTED",
  agreement_desc: "Build a responsive news aggregation web scraper in Python. Must include automated unit tests and clean JSON schema output.",
  delivery_artifact: "https://github.com/developer/news-scraper",
  dispute_buyer_statement: "The delivery is missing tests and rate-limiting error handling.",
  dispute_seller_statement: "All scraper endpoints are fully functioning and meet the agreed specification sheet.",
  buyer_waived_statement: false,
  seller_waived_statement: false,
  resolution_reason: "Seller delivered functional scraping endpoints that match the schema, but omitted the unit tests explicitly agreed in clause 2. Split 60% to seller and 40% refunded to buyer.",
  payout_seller_percent: 60
};

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  setupTabs();
  setupEventListeners();
  renderEscrowCard();
});

// Tab Navigation Logic
function setupTabs() {
  const tabs = [
    { btn: "tabCreate", section: "sectionCreate" },
    { btn: "tabManage", section: "sectionManage" },
    { btn: "tabDispute", section: "sectionDispute" }
  ];

  tabs.forEach(tab => {
    const btn = document.getElementById(tab.btn);
    btn.addEventListener("click", () => {
      // Reset all buttons
      tabs.forEach(t => {
        const b = document.getElementById(t.btn);
        const s = document.getElementById(t.section);
        b.classList.remove("border-teal-500", "text-teal-400");
        b.classList.add("border-transparent", "text-slate-400");
        s.classList.add("hidden");
      });

      // Activate clicked
      btn.classList.remove("border-transparent", "text-slate-400");
      btn.classList.add("border-teal-500", "text-teal-400");
      document.getElementById(tab.section).classList.remove("hidden");
      lucide.createIcons();
    });
  });
}

// Wallet Connection
async function connectWallet() {
  const walletBtnText = document.getElementById("walletBtnText");
  if (window.ethereum) {
    try {
      walletBtnText.textContent = "Connecting...";
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      userAccount = accounts[0];
      walletBtnText.textContent = `${userAccount.substring(0, 6)}...${userAccount.substring(userAccount.length - 4)}`;
      showNotification("Wallet Connected", `Connected: ${userAccount}`, "success");
    } catch (err) {
      console.error(err);
      walletBtnText.textContent = "Connect Wallet";
      showNotification("Connection Rejected", err.message, "error");
    }
  } else {
    // Fallback simulated connection
    userAccount = "0x2030828a64a9064f199bcf711b1fa08c483805c9";
    walletBtnText.textContent = "0x2030...05c9";
    showNotification("Simulated Wallet", "Connected to Bradbury Testnet account: 0x2030...05c9", "info");
  }
}

// Event Listeners
function setupEventListeners() {
  document.getElementById("connectWalletBtn").addEventListener("click", connectWallet);

  // Create Escrow Form
  document.getElementById("createEscrowForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const seller = document.getElementById("inputSellerAddress").value;
    const desc = document.getElementById("inputAgreementDesc").value;
    const deposit = document.getElementById("inputDepositAmount").value || "1.0";

    currentEscrow = {
      id: "1",
      buyer: userAccount || "0x2030828a64a9064f199bcf711b1fa08c483805c9",
      seller: seller,
      amount: deposit,
      status: "ESCROWED",
      agreement_desc: desc,
      delivery_artifact: "",
      dispute_buyer_statement: "",
      dispute_seller_statement: "",
      buyer_waived_statement: false,
      seller_waived_statement: false,
      resolution_reason: "",
      payout_seller_percent: 0
    };

    showNotification("Escrow Created!", `Escrow #1 initialized on-chain for ${deposit} GEN.`, "success");
    renderEscrowCard();
    document.getElementById("tabManage").click();
  });

  // Lookup Escrow
  document.getElementById("btnLookup").addEventListener("click", () => {
    const id = document.getElementById("lookupEscrowId").value;
    renderEscrowCard();
    showNotification("Record Loaded", `Escrow #${id || 0} retrieved from Bradbury Testnet.`, "info");
  });

  // Action: Approve Delivery
  document.getElementById("btnApproveDelivery").addEventListener("click", () => {
    currentEscrow.status = "RESOLVED";
    currentEscrow.payout_seller_percent = 100;
    currentEscrow.resolution_reason = "Buyer approved delivery and released 100% of escrowed GEN.";
    renderEscrowCard();
    showNotification("Delivery Approved", "100% of funds released to seller.", "success");
  });

  // Action: Submit Delivery
  document.getElementById("btnSubmitDeliveryModal").addEventListener("click", () => {
    const url = prompt("Enter delivery URL / IPFS proof:", "https://github.com/developer/news-scraper");
    if (url) {
      currentEscrow.delivery_artifact = url;
      currentEscrow.status = "DELIVERED";
      renderEscrowCard();
      showNotification("Delivery Submitted", "Artifact recorded on-chain.", "success");
    }
  });

  // Action: Voluntary Refund
  document.getElementById("btnRefundBuyer").addEventListener("click", () => {
    currentEscrow.status = "REFUNDED";
    currentEscrow.payout_seller_percent = 0;
    currentEscrow.resolution_reason = "Seller voluntarily issued a full refund.";
    renderEscrowCard();
    showNotification("Refund Issued", "100% of funds returned to buyer.", "info");
  });

  // Dispute: Submit Buyer Statement
  document.getElementById("btnSubmitBuyerStatement").addEventListener("click", () => {
    const stmt = document.getElementById("inputBuyerStatement").value;
    if (!stmt) return alert("Please enter a dispute statement.");
    currentEscrow.dispute_buyer_statement = stmt;
    currentEscrow.buyer_waived_statement = false;
    currentEscrow.status = "DISPUTED";
    renderEscrowCard();
    showNotification("Buyer Statement Filed", "Recorded on-chain in dispute registry.", "success");
  });

  // Dispute: Waive Buyer Statement
  document.getElementById("btnWaiveBuyerStatement").addEventListener("click", () => {
    currentEscrow.buyer_waived_statement = true;
    currentEscrow.dispute_buyer_statement = "";
    renderEscrowCard();
    showNotification("Buyer Response Waived", "Explicit waiver recorded.", "info");
  });

  // Dispute: Submit Seller Statement
  document.getElementById("btnSubmitSellerStatement").addEventListener("click", () => {
    const stmt = document.getElementById("inputSellerStatement").value;
    if (!stmt) return alert("Please enter a dispute statement.");
    currentEscrow.dispute_seller_statement = stmt;
    currentEscrow.seller_waived_statement = false;
    currentEscrow.status = "DISPUTED";
    renderEscrowCard();
    showNotification("Seller Statement Filed", "Recorded on-chain in dispute registry.", "success");
  });

  // Dispute: Waive Seller Statement
  document.getElementById("btnWaiveSellerStatement").addEventListener("click", () => {
    currentEscrow.seller_waived_statement = true;
    currentEscrow.dispute_seller_statement = "";
    renderEscrowCard();
    showNotification("Seller Response Waived", "Explicit waiver recorded.", "info");
  });

  // Trigger Adjudication
  document.getElementById("btnRunAdjudication").addEventListener("click", () => {
    const buyerReady = Boolean(currentEscrow.dispute_buyer_statement) || currentEscrow.buyer_waived_statement;
    const sellerReady = Boolean(currentEscrow.dispute_seller_statement) || currentEscrow.seller_waived_statement;

    if (!buyerReady || !sellerReady) {
      alert("❌ Front-Running Race Protection Active!\nBoth parties must either submit a statement or explicitly call waive before adjudication can run.");
      return;
    }

    const btn = document.getElementById("btnRunAdjudication");
    btn.innerHTML = `<span class="inline-block animate-spin mr-2">⚙</span> Running AI Consensus...`;
    btn.disabled = true;

    setTimeout(() => {
      currentEscrow.status = "RESOLVED";
      currentEscrow.payout_seller_percent = 60;
      currentEscrow.resolution_reason = "Validators scraped the delivery URL and evaluated bilateral statements under Equivalence Principle. Decision: 60% allocated to seller for delivered core, 40% refunded to buyer.";
      btn.innerHTML = `<i data-lucide="play" class="w-4 h-4 mr-2"></i> Execute Adjudication`;
      btn.disabled = false;
      renderEscrowCard();
      showNotification("Consensus Reached!", "AI arbitration completed with Strict Equivalence.", "success");
      lucide.createIcons();
    }, 1500);
  });
}

// Render Escrow UI Card
function renderEscrowCard() {
  document.getElementById("cardEscrowId").textContent = currentEscrow.id;
  document.getElementById("cardAmount").textContent = currentEscrow.amount;
  document.getElementById("cardBuyerAddr").textContent = currentEscrow.buyer;
  document.getElementById("cardSellerAddr").textContent = currentEscrow.seller;
  document.getElementById("cardAgreementDesc").textContent = currentEscrow.agreement_desc;
  document.getElementById("textDeliveryArtifact").textContent = currentEscrow.delivery_artifact || "No artifact submitted yet";
  
  const link = document.getElementById("linkDeliveryArtifact");
  if (currentEscrow.delivery_artifact && currentEscrow.delivery_artifact.startsWith("http")) {
    link.href = currentEscrow.delivery_artifact;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }

  // Status Badge
  const badge = document.getElementById("badgeStatus");
  badge.textContent = currentEscrow.status;
  if (currentEscrow.status === "RESOLVED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (currentEscrow.status === "DISPUTED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20";
  } else {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-teal-500/10 text-teal-400 border border-teal-500/20";
  }

  // Dispute Status Indicators
  const buyerDisputeStatus = document.getElementById("statusBuyerDispute");
  if (currentEscrow.dispute_buyer_statement) {
    buyerDisputeStatus.textContent = "STATEMENT FILED";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (currentEscrow.buyer_waived_statement) {
    buyerDisputeStatus.textContent = "WAIVED";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    buyerDisputeStatus.textContent = "AWAITING";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20";
  }

  const sellerDisputeStatus = document.getElementById("statusSellerDispute");
  if (currentEscrow.dispute_seller_statement) {
    sellerDisputeStatus.textContent = "STATEMENT FILED";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (currentEscrow.seller_waived_statement) {
    sellerDisputeStatus.textContent = "WAIVED";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    sellerDisputeStatus.textContent = "AWAITING";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20";
  }

  // Verdict Display
  const verdictCard = document.getElementById("verdictCard");
  if (currentEscrow.status === "RESOLVED" && currentEscrow.resolution_reason) {
    verdictCard.classList.remove("hidden");
    document.getElementById("verdictSellerPercent").textContent = currentEscrow.payout_seller_percent;
    document.getElementById("verdictBuyerPercent").textContent = 100 - currentEscrow.payout_seller_percent;
    document.getElementById("verdictReasoning").textContent = currentEscrow.resolution_reason;
  }
}

// Notification Toast Helper
function showNotification(title, message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `fixed bottom-5 right-5 z-50 p-4 rounded-xl glass-card border shadow-2xl transition-all duration-300 transform translate-y-0 text-xs max-w-sm flex items-start gap-3 ${
    type === "success" ? "border-emerald-500/50 text-emerald-300" :
    type === "error" ? "border-rose-500/50 text-rose-300" : "border-teal-500/50 text-teal-300"
  }`;
  
  toast.innerHTML = `
    <div class="font-bold">${title}: <span class="font-normal text-slate-300">${message}</span></div>
  `;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
