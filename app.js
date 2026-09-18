/**
 * ArbitratedEscrow Web3 Frontend Application
 * Real On-Chain GenLayer JSON-RPC Integration (No Local Mock Simulations)
 */

const CONTRACT_ADDRESS = "0x27765327341E605F84493563A03Bf33d71ae0928";
const BRADBURY_RPC = "https://rpc-bradbury.genlayer.com";

// Global GenLayer Client State
let client = null;
let activeAccount = null;
let currentEscrowId = 0;

// Initialize when DOM and SDK are ready
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) lucide.createIcons();
  setupTabs();
  await initGenLayerClient();
  setupEventListeners();
  // Query escrow #0 on load
  await queryEscrowOnChain(0);
});

// Initialize real GenLayer SDK Client
async function initGenLayerClient() {
  try {
    if (!window.GenLayerSDK) {
      console.error("GenLayer SDK bundle not loaded yet.");
      return;
    }

    const { createClient, createAccount, testnetBradbury } = window.GenLayerSDK;

    // Check localStorage for persisted session account or generate new
    let savedKey = localStorage.getItem("genlayer_private_key");
    if (savedKey) {
      activeAccount = createAccount(savedKey);
    } else {
      activeAccount = createAccount();
      localStorage.setItem("genlayer_private_key", activeAccount.privateKey);
    }

    client = createClient({
      chain: testnetBradbury,
      account: activeAccount
    });

    document.getElementById("lblActiveAccount").textContent = activeAccount.address;
    document.getElementById("walletBtnText").textContent = `${activeAccount.address.substring(0, 6)}...${activeAccount.address.substring(activeAccount.address.length - 4)}`;

    await updateAccountBalance();
    console.log("✅ GenLayer Client Connected to Bradbury Testnet:", activeAccount.address);
  } catch (err) {
    console.error("Failed to initialize GenLayer client:", err);
    showNotification("RPC Connection Notice", err.message, "error");
  }
}

// Update balance via live RPC
async function updateAccountBalance() {
  if (!client || !activeAccount) return;
  try {
    const bal = await client.getBalance({ address: activeAccount.address });
    document.getElementById("lblActiveBalance").textContent = `${bal.toString()} WEI`;
  } catch (err) {
    document.getElementById("lblActiveBalance").textContent = "Connected (Bradbury)";
  }
}

// Tab Navigation Logic
function setupTabs() {
  const tabs = [
    { btn: "tabCreate", section: "sectionCreate" },
    { btn: "tabManage", section: "sectionManage" },
    { btn: "tabDispute", section: "sectionDispute" }
  ];

  tabs.forEach(tab => {
    const btn = document.getElementById(tab.btn);
    if (!btn) return;
    btn.addEventListener("click", () => {
      tabs.forEach(t => {
        const b = document.getElementById(t.btn);
        const s = document.getElementById(t.section);
        b.classList.remove("border-teal-500", "text-teal-400");
        b.classList.add("border-transparent", "text-slate-400");
        s.classList.add("hidden");
      });

      btn.classList.remove("border-transparent", "text-slate-400");
      btn.classList.add("border-teal-500", "text-teal-400");
      document.getElementById(tab.section).classList.remove("hidden");
      if (window.lucide) lucide.createIcons();
    });
  });
}

// Setup Event Handlers for Real On-Chain Transactions
function setupEventListeners() {
  // Switch / Reconnect Wallet
  document.getElementById("connectWalletBtn").addEventListener("click", async () => {
    const customKey = prompt("Enter private key to import (or leave empty to generate a fresh account):");
    if (customKey !== null) {
      if (customKey.trim()) {
        localStorage.setItem("genlayer_private_key", customKey.trim());
      } else {
        localStorage.removeItem("genlayer_private_key");
      }
      await initGenLayerClient();
      showNotification("Account Updated", `Active address: ${activeAccount.address}`, "success");
    }
  });

  document.getElementById("btnRefreshBalance").addEventListener("click", updateAccountBalance);

  // 1. Create Escrow Transaction (create_escrow)
  document.getElementById("createEscrowForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const seller = document.getElementById("inputSellerAddress").value.trim();
    const desc = document.getElementById("inputAgreementDesc").value.trim();
    const depositVal = document.getElementById("inputDepositAmount").value || "0";

    const btn = document.getElementById("btnSubmitCreate");
    const btnText = document.getElementById("btnSubmitCreateText");
    btn.disabled = true;
    btnText.textContent = "Broadcasting create_escrow on-chain...";

    try {
      showTxBanner("Broadcasting create_escrow transaction to GenLayer validators...");
      
      const txHash = await client.writeContract({
        address: CONTRACT_ADDRESS,
        functionName: "create_escrow",
        args: [seller, desc]
      });

      showTxBanner(`Transaction submitted: ${txHash.substring(0, 16)}... Waiting for GenVM finality...`, txHash);
      const receipt = await client.waitForTransactionReceipt({ hash: txHash });

      showNotification("Escrow Created On-Chain!", `Tx: ${txHash.substring(0, 10)}... Confirmed in Block.`, "success");
      
      // If user specified initial deposit, trigger deposit(escrow_id)
      if (BigInt(depositVal) > 0n) {
        btnText.textContent = "Depositing funds on-chain...";
        showTxBanner(`Depositing ${depositVal} WEI on-chain...`);
        
        // Deposit into the newly created escrow
        const depTx = await client.writeContract({
          address: CONTRACT_ADDRESS,
          functionName: "deposit",
          args: [0], // or latest escrow id
          value: BigInt(depositVal)
        });
        await client.waitForTransactionReceipt({ hash: depTx });
      }

      document.getElementById("tabManage").click();
      await queryEscrowOnChain(0);
    } catch (err) {
      console.error("create_escrow failed:", err);
      showNotification("Transaction Error", err.message || "Execution failed on GenVM", "error");
    } finally {
      btn.disabled = false;
      btnText.textContent = "Broadcast `create_escrow` Transaction";
      hideTxBanner();
    }
  });

  // 2. Query Escrow (get_escrow read call)
  document.getElementById("btnLookup").addEventListener("click", async () => {
    const id = document.getElementById("lookupEscrowId").value;
    await queryEscrowOnChain(parseInt(id, 10) || 0);
  });

  // 3. Approve Delivery (approve_delivery write call)
  document.getElementById("btnApproveDelivery").addEventListener("click", async () => {
    await executeContractWrite("approve_delivery", [currentEscrowId], "Approving delivery & releasing funds on-chain...");
  });

  // 4. Submit Delivery (submit_delivery write call)
  document.getElementById("btnSubmitDeliveryModal").addEventListener("click", async () => {
    const url = prompt("Enter real deliverable URL / IPFS hash:", "https://github.com/developer/news-scraper");
    if (url) {
      await executeContractWrite("submit_delivery", [currentEscrowId, url], "Recording delivery artifact on-chain...");
    }
  });

  // 5. Voluntary Refund (refund_buyer write call)
  document.getElementById("btnRefundBuyer").addEventListener("click", async () => {
    await executeContractWrite("refund_buyer", [currentEscrowId], "Executing voluntary refund on-chain...");
  });

  // 6. Dispute Escrow - Buyer Statement
  document.getElementById("btnSubmitBuyerStatement").addEventListener("click", async () => {
    const stmt = document.getElementById("inputBuyerStatement").value.trim();
    if (!stmt) return alert("Please enter a dispute statement.");
    await executeContractWrite("dispute_escrow", [currentEscrowId, stmt], "Recording buyer dispute statement on-chain...");
  });

  // 7. Waive Statement - Buyer
  document.getElementById("btnWaiveBuyerStatement").addEventListener("click", async () => {
    await executeContractWrite("waive_dispute_statement", [currentEscrowId], "Recording explicit buyer waiver on-chain...");
  });

  // 8. Dispute Escrow - Seller Statement
  document.getElementById("btnSubmitSellerStatement").addEventListener("click", async () => {
    const stmt = document.getElementById("inputSellerStatement").value.trim();
    if (!stmt) return alert("Please enter a dispute statement.");
    await executeContractWrite("dispute_escrow", [currentEscrowId, stmt], "Recording seller dispute statement on-chain...");
  });

  // 9. Waive Statement - Seller
  document.getElementById("btnWaiveSellerStatement").addEventListener("click", async () => {
    await executeContractWrite("waive_dispute_statement", [currentEscrowId], "Recording explicit seller waiver on-chain...");
  });

  // 10. Execute AI Adjudication (adjudicate_escrow write call)
  document.getElementById("btnRunAdjudication").addEventListener("click", async () => {
    const btn = document.getElementById("btnRunAdjudication");
    const btnText = document.getElementById("btnRunAdjudicationText");
    btn.disabled = true;
    btnText.textContent = "AI Validators Crawling & Reaching Consensus...";

    try {
      showTxBanner("Broadcasting adjudicate_escrow... GenLayer validators are scraping deliverable URL and executing LLM arbitration consensus...");

      const txHash = await client.writeContract({
        address: CONTRACT_ADDRESS,
        functionName: "adjudicate_escrow",
        args: [currentEscrowId]
      });

      showTxBanner(`Arbitration Tx: ${txHash.substring(0, 16)}... Reaching Strict Equivalence...`, txHash);
      const receipt = await client.waitForTransactionReceipt({ hash: txHash });

      showNotification("Arbitration Finalized On-Chain!", `Tx: ${txHash.substring(0, 10)}... Equivalence consensus reached.`, "success");
      await queryEscrowOnChain(currentEscrowId);
    } catch (err) {
      console.error("adjudicate_escrow failed:", err);
      // Surface real GenVM error (e.g., bilateral statement protection)
      alert(`❌ On-Chain GenVM Response:\n${err.message || "Arbitration reverted"}`);
      showNotification("Arbitration Call Reverted", err.message, "error");
    } finally {
      btn.disabled = false;
      btnText.textContent = "Execute Adjudication On-Chain";
      hideTxBanner();
    }
  });
}

// Generic Contract Write Executor with real receipt confirmation
async function executeContractWrite(functionName, args, statusMessage) {
  if (!client) return alert("GenLayer Client not connected.");
  try {
    showTxBanner(statusMessage);
    const txHash = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: functionName,
      args: args
    });

    showTxBanner(`Submitted ${functionName}: ${txHash.substring(0, 16)}... Confirming...`, txHash);
    const receipt = await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Transaction Confirmed", `Function \`${functionName}\` executed on Bradbury Testnet.`, "success");
    await queryEscrowOnChain(currentEscrowId);
  } catch (err) {
    console.error(`${functionName} failed:`, err);
    alert(`❌ GenVM Error during \`${functionName}\`:\n${err.message}`);
    showNotification("Transaction Failed", err.message, "error");
  } finally {
    hideTxBanner();
  }
}

// Live on-chain read query (get_escrow)
async function queryEscrowOnChain(escrowId) {
  currentEscrowId = escrowId;
  const btnLookupText = document.getElementById("btnLookupText");
  if (btnLookupText) btnLookupText.textContent = "Querying...";

  try {
    if (!client) {
      console.warn("Client not ready yet.");
      return;
    }

    const data = await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: "get_escrow",
      args: [escrowId]
    });

    console.log(`✅ On-Chain Escrow #${escrowId} data:`, data);
    renderOnChainEscrow(escrowId, data);
  } catch (err) {
    console.warn(`Escrow #${escrowId} read returned:`, err.message);
    document.getElementById("cardEscrowId").textContent = escrowId;
    document.getElementById("badgeStatus").textContent = "NOT FOUND / UNINITIALIZED";
    document.getElementById("badgeStatus").className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20";
    document.getElementById("cardAgreementDesc").textContent = `No on-chain escrow record found for ID #${escrowId}. Use the 'Create Escrow' tab to initialize it on Bradbury Testnet.`;
  } finally {
    if (btnLookupText) btnLookupText.textContent = "Query Chain";
  }
}

// Render real data returned from GenVM
function renderOnChainEscrow(id, data) {
  if (!data) return;

  document.getElementById("cardEscrowId").textContent = id;
  document.getElementById("cardAmount").textContent = data.amount ? data.amount.toString() : "0";
  document.getElementById("cardBuyerAddr").textContent = data.buyer || "--";
  document.getElementById("cardSellerAddr").textContent = data.seller || "--";
  document.getElementById("cardAgreementDesc").textContent = data.agreement_desc || "No agreement text recorded.";
  document.getElementById("textDeliveryArtifact").textContent = data.delivery_artifact || "No artifact submitted yet.";

  const link = document.getElementById("linkDeliveryArtifact");
  if (data.delivery_artifact && data.delivery_artifact.startsWith("http")) {
    link.href = data.delivery_artifact;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }

  // Status Badge
  const status = data.status || "UNKNOWN";
  const badge = document.getElementById("badgeStatus");
  badge.textContent = status;
  if (status === "RESOLVED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (status === "DISPUTED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20";
  } else {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-teal-500/10 text-teal-400 border border-teal-500/20";
  }

  // Dispute statuses
  const buyerDisputeStatus = document.getElementById("statusBuyerDispute");
  if (data.dispute_buyer_statement) {
    buyerDisputeStatus.textContent = "STATEMENT FILED";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (data.buyer_waived_statement) {
    buyerDisputeStatus.textContent = "WAIVED ON-CHAIN";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    buyerDisputeStatus.textContent = "AWAITING";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700";
  }

  const sellerDisputeStatus = document.getElementById("statusSellerDispute");
  if (data.dispute_seller_statement) {
    sellerDisputeStatus.textContent = "STATEMENT FILED";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (data.seller_waived_statement) {
    sellerDisputeStatus.textContent = "WAIVED ON-CHAIN";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    sellerDisputeStatus.textContent = "AWAITING";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700";
  }

  // Verdict Display from real resolution_reason in GenVM storage
  const verdictCard = document.getElementById("verdictCard");
  if (status === "RESOLVED" && data.resolution_reason) {
    verdictCard.classList.remove("hidden");
    const sellerPct = data.payout_seller_percent ? parseInt(data.payout_seller_percent.toString(), 10) : 0;
    document.getElementById("verdictSellerPercent").textContent = sellerPct;
    document.getElementById("verdictBuyerPercent").textContent = 100 - sellerPct;
    document.getElementById("verdictReasoning").textContent = `"${data.resolution_reason}"`;
  } else {
    verdictCard.classList.add("hidden");
  }
}

// Live Tx Banner Helpers
function showTxBanner(text, hash) {
  const banner = document.getElementById("liveTxBanner");
  banner.classList.remove("hidden");
  document.getElementById("liveTxText").textContent = text;
  const link = document.getElementById("liveTxLink");
  if (hash) {
    link.href = `https://explorer-bradbury.genlayer.com/tx/${hash}`;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }
}

function hideTxBanner() {
  document.getElementById("liveTxBanner").classList.add("hidden");
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
  }, 4000);
}
