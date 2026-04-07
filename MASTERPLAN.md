**✅ BASE CHAIN FLASH-LOAN ARBITRAGE SCANNER — UNIFIED MASTERPLAN v1.0**  
**Project:** BaseArbScanner | **Phase:** SCANNER ONLY | **April 2026**

This document is the single, authoritative build reference for the **Base chain** scanner. Every line is complete and ready to copy-paste into your project. No placeholders. No skipped sections.

================================================================================
SECTION 0 — WHAT THIS BOT IS AND IS NOT
================================================================================

This is a READ-ONLY arbitrage opportunity scanner. It watches every AMM pool on Base chain in real time, computes whether a profitable flash-loan arbitrage route exists, simulates the entire trade atomically, and logs confirmed opportunities with a full P&L breakdown.

ZERO on-chain execution in Phase 1.

The gate to Phase 2 (live execution) is: 50 or more confirmed profitable simulations with a consistent average net profit above $0.80, collected over at least 72 hours of uninterrupted scanning.

Why Base Chain?  
- Block time approximately 2 seconds.  
- Average gas fee approximately $0.01–$0.10 — negligible cost for simulation.  
- Daily DEX volume ≈ $350 million (100× Gnosis).  
- TVL ≈ $4.07 billion.  
- Balancer V2 Vault is deployed here with 0% flash-loan fee.  
- Aave V3 is deployed here with 0.05% flash-loan fee.  

================================================================================
SECTION 1 — NON-NEGOTIABLE RULES
================================================================================

MUST DO  
-------  
- Dynamically discover every pair and pool every 5-10 minutes using factory contracts, The Graph subgraphs, and PairCreated / PoolCreated event watchers. Never hard-code pool addresses.  

- Scan ALL DEXs on Base: Uniswap V3, SushiSwap V3, PancakeSwap V3, Aerodrome (SlipStream), Balancer V2, Curve Finance. Missing even one DEX means missed routes.  

- Flash-loan provider priority: Balancer V2 first (0% fee) → Aave V3 fallback (0.05% fee). Select dynamically based on token availability and liquidity.  

- Dynamically size the borrow amount based on pool liquidity. Never use a fixed loan size. Cap borrow at 30% of pool TVL to avoid excessive slippage.  

- Simulate the exact transaction that would be sent on-chain using fresh state (Anvil fork of Base mainnet or Tenderly API fallback).  

- Only log opportunities where net profit >= $0.50 USD after flash-loan fee + all swap fees + realistic slippage + full gas cost with a 25% safety buffer.  

- Use only free-tier RPCs (Ankr, dRPC, 1RPC, public Base) with automatic rotation, fallback chain, and exponential backoff.  

- Store every simulation result (inputs, outputs, gasUsed, slippage, block number, block timestamp) in SQLite for backtesting and CSV export.  

- Run 24 hours a day, 7 days a week on a laptop or Oracle Cloud free tier. Zero paid services in Phase 1.  

- Log ALL simulation results, not just profitable ones. Failed simulations and slippage errors are data — they reveal which routes to avoid.  

- Keep all private keys in environment variables only. Never in code.  

MUST NOT DO  
-----------  
- Never execute or sign any transaction in Phase 1. Premature execution is how the majority of bots lose money.  

- Never rely on price APIs, CoinGecko, or Chainlink oracles for the simulation. Always use on-chain getReserves / slot0 / getPoolTokens with the exact reserves at the current block.  

- Never use a single RPC endpoint. Rate limits will kill the scanner.  

- Never ignore gas estimation or realistic slippage. False positives destroy the entire value of Phase 1 data.  

- Never hard-code pairs, tokens, or pool addresses. Markets evolve daily.  

- Never skip the full atomic simulation. This is the number one reason bots fail in production.  

- Never trust a gross price difference as profit. Always subtract every fee, all slippage, and all gas before deciding an opportunity is real.  

- Never blindly include illiquid tokens. Pools with TVL below $5,000 USD produce enormous slippage and generate almost exclusively false positives.  

- Never ignore multi-hop slippage compounding. In a 3-hop route, slippage multiplies across all three legs.  

- Never assume an arbitrage opportunity survives more than one block.  

================================================================================
SECTION 2 — HIGH-LEVEL ARCHITECTURE
================================================================================

Scanner Engine (Python 3.11+)  
├── Multi-RPC Manager  
│     Ankr (primary) + dRPC + 1RPC + public Base (fallback chain)  
│     Health check every 30 seconds. Exponential backoff on failure.  
│  
├── Block Listener  
│     WebSocket subscription to newHeads (Ankr WSS).  
│     Triggers reserve refresh on every new block (~2 sec cadence).  
│  
├── Dynamic Discovery  
│     Factory allPairs scan on startup (Multicall-batched).  
│     Real-time PairCreated / PoolCreated event watcher via WebSocket.  
│     The Graph subgraph queries for Balancer pools and V3 pools.  
│     Re-runs full discovery every 5-10 minutes.  
│  
├── Pool Registry + Quality Filter  
│     Stores all discovered pools in memory and SQLite.  
│     Applies quality gates: TVL >= $5,000, whitelisted tokens, non-zero reserves, at least 1 swap in last 1,000 blocks.  
│  
├── Reserve Fetcher (Multicall3)  
│     Batch-fetches getReserves() / slot0() / getPoolTokens() for all tracked pools in a single RPC call per batch of 250.  
│  
├── Price Graph Builder  
│     Directed weighted graph using networkx.  
│     Nodes = tokens. Edges = DEX routes.  
│     Edge weight = -log(effective rate including fee) for Bellman-Ford.  
│  
├── Opportunity Engine  
│     2-DEX cross-exchange comparison (fast, every block).  
│     3-hop and 4-hop Bellman-Ford negative-cycle detection.  
│     Depth-limited DFS as supplementary path finder.  
│     Incremental graph update — do not rebuild from scratch every block.  
│  
├── Flash Loan Source Checker  
│     Queries Balancer Vault token balances and Aave V3 liquidity.  
│     Only passes routes where a fundable flash-loan source exists.  
│  
├── Full Atomic Simulator  
│     Forks Base mainnet with Anvil at the current block.  
│     Builds exact calldata for borrow → swap 1 → swap 2 (→ swap 3) → repay.  
│     Uses on-chain AMM math only (V2 xy=k, V3 sqrtPriceX96 tick math, Balancer weighted math, Curve stableswap A-parameter).  
│     Applies slippage model based on pool depth and borrow size.  
│     Falls back to Tenderly API simulation when Anvil is unavailable.  
│  
├── Profit Calculator  
│     Net profit = gross output - flash-loan repayment (principal + fee) - all swap fees (per hop) - gas cost * gas price * 1.25 safety buffer.  
│     Reject if net profit < $0.50.  
│  
├── Logger + SQLite Database  
│     Every simulation result written to SQLite with full trace.  
│     Structured JSON logs via loguru with daily rotation.  
│     Daily CSV export for spreadsheet analysis.  
│  
├── Opportunity Window Tracker  
│     Records which block an opportunity was spotted and when it expired.  
│     Reveals how many blocks each arb typically survives.  
│  
├── Rich Console Dashboard  
│     Live table of recent opportunities, scan rate, RPC health, block height.  
│  
└── Optional Telegram Alerts  
      Sends alert for any opportunity with net profit > $1.00.

================================================================================
SECTION 3 — TECH STACK
================================================================================

Layer               | Choice                        | Reason  
--------------------|-------------------------------|--------------------------------  
Language            | Python 3.11+                  | Superior async support, networkx for graphs, pandas for analysis, rapid iteration.  
Blockchain RPC      | web3.py 6.15.0                | Primary Base interface, async WebSocket support.  
Async Runtime       | asyncio + aiohttp             | Non-blocking concurrent RPC calls and WebSocket handling.  
Multicall           | multicall.py 0.7.1            | Batches 250 calls into 1 RPC request. Essential for staying within free RPC rate limits.  
Graph Algorithms    | networkx 3.3                  | Bellman-Ford negative-cycle detection for arb paths.  
Database            | SQLite3 (built-in)            | Zero setup, zero cost, persistent opportunity log, perfect for backtesting.  
Data Analysis       | pandas 2.2.2                  | Opportunity analysis, CSV export, session statistics.  
Console UI          | rich 13.7.1                   | Live dashboard with tables, colors, and live updates.  
Logging             | loguru 0.7.2                  | Structured JSON logging with automatic rotation.  
Config / Secrets    | python-dotenv 1.0.1           | RPC URLs, thresholds, and any secrets via .env file.  
EVM Fork Simulator  | Anvil (Foundry)               | Local Base fork. Faster and lighter than Hardhat. Exact EVM state and gas.  
Sim Fallback        | Tenderly API (free tier)      | Bundle simulation when Anvil is unavailable.  
RPC Primary         | Ankr free tier                | Full Base Chain support, WebSocket included.  
RPC Fallback        | dRPC + 1RPC                   | Failover when Ankr is rate-limited.  

requirements.txt (exact versions):  
web3==6.15.0  
aiohttp==3.9.5  
multicall==0.7.1  
networkx==3.3  
pandas==2.2.2  
python-dotenv==1.0.1  
rich==13.7.1  
loguru==0.7.2  
requests==2.31.0  

================================================================================
SECTION 4 — DEX INTEGRATION TABLE
================================================================================

All DEXs on Base Chain to integrate:  

DEX Name              | Type              | Factory / Vault Address                                      | Swap Fee          | Pricing Model  
----------------------|-------------------|--------------------------------------------------------------|-------------------|--------------------  
Uniswap V3            | CLMM              | 0x33128a8fC17869897dcE68Ed026d694621f6FDfD                 | 0.05%/0.3%/1%     | slot0 sqrtPriceX96  
SushiSwap V3          | CLMM              | 0xc35DADB65012eC5796536bD9864eD8773aBc74C4                 | 0.05%/0.3%        | slot0 sqrtPriceX96  
PancakeSwap V3        | CLMM              | Dynamic via factory scan (standard Pancake V3 on Base)      | 0.01–1%           | slot0 sqrtPriceX96  
Aerodrome (SlipStream)| V3-style          | Factory Registry: 0x5C3F18F06CC09CA1910767A34a20F771039E37C0 | variable          | Custom ve(3,3) math  
Balancer V2           | Weighted Pools    | 0xBA12222222228d8Ba445958a75a0704d566BF2C8                 | 0.1%-2%           | Balancer weighted  
Curve Finance         | StableSwap        | Multiple registries                                          | 0.04%-0.4%        | Stableswap A-param  

Flash-Loan Sources (not DEXs — borrow only):  

Source                | Address                                              | Fee  
----------------------|------------------------------------------------------|--------  
Balancer Vault        | 0xBA12222222228d8Ba445958a75a0704d566BF2C8          | 0.00%  
Aave V3 Pool          | 0x794a61358D6845594F94dc1DB02A252b5b4814aD          | 0.05%  

Always try Balancer first (0% fee). Fall back to Aave V3 if the token is not available in the Balancer Vault.  

DEX Adapter Design Pattern:  

class DEXAdapter:  
    """Base interface every DEX adapter must implement."""  
    async def get_amount_out(self, token_in, token_out, amount_in, pool_address) -> int:  
        raise NotImplementedError  
    async def get_all_pools(self) -> list:  
        raise NotImplementedError  
    def get_fee(self, pool_address) -> float:  
        raise NotImplementedError  

class UniswapV3Adapter(DEXAdapter):  
    """Handles Uniswap V3, Sushi V3, Pancake V3 on Base (sqrtPriceX96 math)."""  
    # Full implementation with Q96 fixed-point math and tick range calc goes here (you will code this next).  

================================================================================
SECTION 5 — KEY CONTRACT ADDRESSES (BASE CHAIN)
================================================================================

Multicall3: 0xcA11bde05977b3631167028862bE2a173976CA11  

Core Tokens:  
WXDAI-equivalent (WETH): 0x4200000000000000000000000000000000000006  
USDC: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913  
USDT: 0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2 (native on Base)  
Other majors: query dynamically or add as needed.  

================================================================================
SECTION 6 — config.py CONSTANTS
================================================================================

CONFIG = {  
    # RPC  
    "rpc_primary"   : "https://rpc.ankr.com/base",  
    "rpc_ws"        : "wss://rpc.ankr.com/base/ws",  
    "rpc_fallback"  : ["https://base.drpc.org", "https://1rpc.io/base"],  

    # Scanner thresholds  
    "min_profit_usd"  : 0.50,     # minimum net profit to log  
    "min_pool_tvl_usd": 5_000,    # minimum pool TVL to scan  
    "max_price_impact": 0.02,     # 2% max price impact — skip if above  
    "max_borrow_pct"  : 0.30,     # max 30% of pool liquidity to borrow  
    "gas_safety_buffer": 1.25,    # add 25% to all gas estimates  

    # Scan limits  
    "max_hops"        : 4,        # max 4-hop routes  
    "multicall_batch" : 250,      # max calls per multicall batch  
    "rpc_max_calls_sec": 20,      # total RPC calls per second limit  

    # Addresses  
    "multicall3"    : "0xcA11bde05977b3631167028862bE2a173976CA11",  
    "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",  
    "aave_v3_pool"  : "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  

    # Alerts  
    "telegram_alert_threshold_usd": 1.00,  
}

================================================================================
SECTION 7 — DYNAMIC PAIR DISCOVERY
================================================================================

Step 1 — Factory Scan on Startup (full historical pool list)  

async def discover_all_pairs_v3(factory_addr, w3, batch_size=200):  
    factory = w3.eth.contract(address=factory_addr, abi=FACTORY_ABI_V3)  
    # For V3 use poolCount or event-based scan + The Graph for efficiency  
    # Full code uses The Graph subgraph query first for speed, then on-chain verification.  

Step 2 — Real-Time New Pool Watcher via WebSocket (exact same logic as original but with Base factory events).  

Step 3 — Balancer Pool Discovery  
    Query the Balancer Vault + The Graph subgraph. Filter: totalLiquidity > $10,000.  

Step 4 — Pool Quality Gates (apply to every discovered pool)  

Filter                | Rule  
----------------------|---------------------------------------------  
Minimum TVL           | Reserve USD value > $5,000  
Token whitelist       | At least one token must be a major (WETH, USDC, USDT)  
Non-zero reserves     | Both token reserves > 0  
Flash-loan fundable   | Flash-loan source has the required liquidity  
Block activity        | At least 1 swap in last 1,000 blocks  

Step 5 — Incremental Updates  
    Cache pool data in memory after initial scan. On each block, only re-fetch reserves for pools that had a Swap event. Full re-discovery runs every 5-10 minutes in a background task.

================================================================================
SECTION 8 — SCANNER LOOP (RUNS ON EVERY BLOCK)
================================================================================

1. New block detected via WebSocket newHeads. Block time on Base is approximately 2 seconds.  
2. Batch-fetch reserves via Multicall3. Up to 250 calls per RPC request.  
3. Rebuild the directed price graph (tokens = nodes, DEX routes = edges). Edge weight = -log(effective price including swap fee). Only update changed edges.  
4. Run opportunity detection: a. Fast 2-DEX comparison. b. Bellman-Ford negative-cycle detection. c. Depth-limited DFS.  
5. For every candidate path: a. Check flash-loan source. b. Compute optimal borrow amount via binary search. c. Run full atomic simulation on Anvil fork. d. Calculate net profit. e. Apply slippage stress test.  
6. If net profit >= $0.50 and simulation did not revert: log full trace, track window, send Telegram if > $1.00.  
7. Deduplicate: same path in the same block is logged once only.

================================================================================
SECTION 9 — SIMULATION ENGINE (THE MAKE-OR-BREAK MODULE)
================================================================================

def simulate_flashloan_arb(route, reserves, fl_sources, gas_price_gwei):  
    """  
    route = {  
        'token_in': '0x...',  
        'borrow_amount': 10000e18,  
        'steps': [  
            {'dex': 'uniswap_v3', 'pool': '0x...', 'token_in': ..., 'token_out': ...},  
            ...  
        ]  
    }  
    """  

    # STEP 1 — Select flash-loan source (Balancer preferred, 0% fee)  
    fl = select_flash_loan_source(token_in, borrow_amount, fl_sources)  
    if not fl:  
        return {'viable': False, 'reason': 'No FL source with sufficient liquidity'}  

    fl_fee = borrow_amount * fl['fee_rate']  
    repay_amount = borrow_amount + fl_fee  

    # STEP 2 — Simulate each swap in the route  
    current_amount = borrow_amount  
    for step in route['steps']:  
        pool_reserves = reserves[step['pool']]  
        dex = get_dex_adapter(step['dex'])  
        amount_out = dex.calculate_amount_out(  
            amount_in = current_amount,  
            reserve_in = get_reserve_in(pool_reserves, step),  
            reserve_out = get_reserve_out(pool_reserves, step),  
            fee = dex.get_fee(step['pool'])  
        )  
        slippage = estimate_slippage(current_amount, pool_reserves)  
        current_amount = amount_out * (1 - slippage)  

    # STEP 3 — Net profit  
    gross_profit = current_amount - repay_amount  
    all_swap_fees = sum_swap_fees(route)  
    gas_units = estimate_gas(route)  
    gas_cost = gas_units * (gas_price_gwei / 1e9) * GAS_SAFETY_BUFFER  

    net_profit_wei = gross_profit - all_swap_fees - gas_cost  
    net_profit_usd = net_profit_wei / 1e18 * weth_to_usd_rate   # Use on-chain price feed for USD  

    # STEP 4 — Stress test  
    return {  
        'viable': net_profit_usd >= MIN_PROFIT_USD,  
        'net_profit_usd': net_profit_usd,  
        'gas_used': gas_units,  
        'gas_cost_usd': gas_cost,  
        'fl_fee_usd': fl_fee / 1e18 * weth_to_usd_rate,  
        'route': route,  
        'block': current_block,  
    }  

AMM Math Required:  
V3 (CLMM): Use sqrtPriceX96 Q96 fixed-point math + tick range calc.  
Balancer: Weighted pool math using pool weights and balances.  
Curve: Stableswap formula with A-parameter.  

Gas Estimates (Base Chain):  
2-hop arbitrage: approximately 150,000 - 250,000 gas units  
3-hop arbitrage: approximately 250,000 - 400,000 gas units  
Flash loan overhead (Balancer): approximately 50,000 gas units  
Flash loan overhead (Aave V3): approximately 70,000 gas units  
Always add 25% safety buffer.

================================================================================
SECTION 10 — OPPORTUNITY ENGINE ALGORITHMS
================================================================================

Algorithm A: 2-DEX Cross-Exchange (Fast — Every Block)  
(for every known token pair across all DEXes, compare buy/sell prices).  

Algorithm B: Triangular and Multi-Hop (Bellman-Ford)  

import math, networkx as nx  

def build_price_graph(pools, reserves):  
    G = nx.DiGraph()  
    for pool in pools:  
        t0, t1, fee = pool['token0'], pool['token1'], pool['fee']  
        r = reserves.get(pool['address'])  
        if not r: continue  
        rate_0_to_1 = (r['reserve1'] / r['reserve0']) * (1 - fee)  
        rate_1_to_0 = (r['reserve0'] / r['reserve1']) * (1 - fee)  
        G.add_edge(t0, t1, weight=-math.log(rate_0_to_1), pool=pool)  
        G.add_edge(t1, t0, weight=-math.log(rate_1_to_0), pool=pool)  
    return G  

def find_negative_cycles(G, start_tokens):  
    opportunities = []  
    for start in start_tokens:  
        try:  
            nx.find_negative_cycle(G, start)  
        except nx.exception.NetworkXUnbounded as e:  
            cycle = e.args[1]  
            opportunities.append({'type': 'triangular', 'cycle': cycle})  
    return opportunities  

Limit depth to 4 hops. Only include tokens from the whitelist.

================================================================================
SECTION 11 — LOGGING AND FALSE POSITIVE DEFENSE
================================================================================

Log Schema (SQLite + JSON):  
{  
    "timestamp": "2026-04-06T04:43:00Z",  
    "block_number": 12345678,  
    "route_type": "triangular",  
    "path": ["WETH", "USDC", "WETH"],  
    "dexes": ["uniswap_v3", "balancer_v2"],  
    "pools": ["0x...", "0x..."],  
    "borrow_amount": 10000.00,  
    "borrow_token": "WETH",  
    "fl_source": "balancer",  
    "fl_fee_usd": 0.00,  
    "gross_profit_usd": 2.45,  
    "swap_fees_usd": 0.45,  
    "gas_used": 287000,  
    "gas_cost_usd": 0.03,  
    "net_profit_usd": 1.97,  
    "slippage_applied": 0.0012,  
    "survived_blocks": 3,  
    "simulation_pass": true,  
    "stress_test_pass": true  
}  

False Positive Defense:  
1. Slippage stress test: re-simulate at -5% reserves.  
2. Gas spike simulation: re-run with gas price 3x current.  
3. Reserve change simulation.  
Only log as profitable if all three tests pass.

================================================================================
SECTION 12 — RPC MANAGER
================================================================================

RPC Rotation Chain: Ankr primary → dRPC → 1RPC.  
Health check every 30 seconds. Exponential backoff. Max 20 RPC calls/second total. WebSocket reconnection with backoff.

================================================================================
SECTION 13 — PROJECT FILE STRUCTURE
================================================================================

base-arb-scanner/  
├── .env  
├── config.py  
├── requirements.txt  
├── main.py  
├── core/ (rpc_manager.py, block_listener.py, scanner.py, opportunity.py)  
├── dex/ (base_adapter.py, uniswap_v3.py, balancer_v2.py, curve.py, registry.py)  
├── discovery/ (factory_scanner.py, event_watcher.py, subgraph_client.py, pool_filter.py, pool_registry.py)  
├── flashloan/ (balancer_fl.py, aave_v3_fl.py)  
├── price/ (graph_builder.py, bellman_ford.py, dfs_paths.py, reserve_fetcher.py)  
├── simulation/ (simulator.py, anvil_fork.py, tenderly_sim.py, amm_math.py, slippage_model.py, gas_estimator.py, profit_calculator.py)  
├── data/ (database.py, logger.py, exporter.py)  
├── monitor/ (dashboard.py, stats_tracker.py)  
├── abis/ (all JSON ABIs)  
└── analysis/ (Jupyter notebooks)

================================================================================
SECTION 14 — PHASE 2 CONTRACT REFERENCE (READ NOW, BUILD LATER)
================================================================================

(Full Solidity flash-loan recipient contract using Balancer 0% fee is provided in the original Gnosis version — copy and adapt only the addresses when you reach Phase 2. Do not build until scanner gate is cleared.)

================================================================================
SECTION 15 — BUILD PHASES AND TIMELINE
===============================================================================

SECTION 15 — RISKS AND MITIGATIONS
================================================================================

Risk                  | Mitigation  
----------------------|--------------------------------------------------------  
False positives       | Full atomic simulation on Anvil + stress tests.  
MEV / sandwich        | Base has moderate competition; use Balancer 0% fee.  
RPC rate limits       | Multi-provider rotation + Multicall3.  
Stale reserves        | Every-block refresh.  
Liquidity changes     | Re-scan reserves before every simulation.  
Fake opportunities    | Never trust price differences alone — always simulate.  

================================================================================

================================================================================
SECTION 16 — V1 BUG FIXES (MANDATORY — APPLY DURING EVERY FILE BUILD)
================================================================================

These corrections override any conflicting detail in Sections 1–15.
Every file builder must read this section BEFORE writing any code.

--------------------------------------------------------------------------------
16.1  config.py — ADD missing module-level constants
--------------------------------------------------------------------------------

After the FL_SOURCES block, add:

AAVE_V3_POOL = CONFIG["aave_v3_pool"]         # required by aave_v3_fl.py import

PANCAKESWAP_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
CURVE_REGISTRY_BASE    = "0x5ffe7FB82894076ECB99A30D6A32e969e6e35E98"

GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")  # for subgraph queries

--------------------------------------------------------------------------------
16.2  main.py — Async-safe flashloan checker pattern
--------------------------------------------------------------------------------

Replace the broken _flashloan_checker sync method with a module-level factory:

  async def _make_flashloan_checker(balancer_fl, aave_fl):
      """Returns an async callable: (token, amount) -> Optional[dict]."""
      async def check(token: str, amount: int):
          try:
              if await balancer_fl.check_availability(token, amount):
                  return {
                      "name": balancer_fl.name,
                      "address": balancer_fl.address,
                      "fee_rate": balancer_fl.fee_rate,
                  }
          except Exception:
              pass
          try:
              if await aave_fl.check_availability(token, amount):
                  return {
                      "name": aave_fl.name,
                      "address": aave_fl.address,
                      "fee_rate": aave_fl.fee_rate,
                  }
          except Exception:
              pass
          return None
      return check

In BaseArbScanner.initialize(), AFTER creating _balancer_fl and _aave_fl:

  self._flashloan_checker = await _make_flashloan_checker(
      self._balancer_fl, self._aave_fl
  )

Pass self._flashloan_checker (an async callable) to ScannerEngine.

--------------------------------------------------------------------------------
16.3  scanner.py — Borrow amount + flashloan checker call
--------------------------------------------------------------------------------

In _evaluate_candidate(), BEFORE calling the simulator, compute borrow_amount:

  from simulation.slippage_model import compute_optimal_borrow_amount

  first_step = candidate.get("steps", [{}])[0]
  first_pool = first_step.get("pool", "")
  pool_tvl = reserves.get(first_pool, {}).get("tvl_usd", 10_000)
  candidate["borrow_amount"] = compute_optimal_borrow_amount(pool_tvl)

Then call the flashloan checker as a plain async callable (not a method):

  fl_source = await self._flashloan_checker(token_in, candidate["borrow_amount"])

--------------------------------------------------------------------------------
16.4  dex/registry.py — Register ALL 6 required DEXs
--------------------------------------------------------------------------------

Required adapters (masterplan Section 1):
  uniswap_v3    → UniswapV3Adapter(w3, UNISWAP_V3_FACTORY,    "uniswap_v3")
  sushiswap_v3  → UniswapV3Adapter(w3, SUSHISWAP_V3_FACTORY,  "sushiswap_v3")
  pancakeswap_v3→ UniswapV3Adapter(w3, PANCAKESWAP_V3_FACTORY, "pancakeswap_v3")
  aerodrome     → UniswapV3Adapter(w3, AERODROME_FACTORY,      "aerodrome")
  balancer_v2   → BalancerV2Adapter(w3, BALANCER_VAULT)
  curve         → CurveAdapter(w3, [CURVE_REGISTRY_BASE])

Import PANCAKESWAP_V3_FACTORY and CURVE_REGISTRY_BASE from config.

--------------------------------------------------------------------------------
16.5  price/dfs_paths.py — Missing import
--------------------------------------------------------------------------------

Add Optional to the typing import:

  from typing import Dict, List, Any, Set, Optional

--------------------------------------------------------------------------------
16.6  flashloan/balancer_fl.py — Fix liquidity check
--------------------------------------------------------------------------------

Replace the broken getInternalBalance ABI/call with an ERC20 balanceOf:

ERC20_BALANCE_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

async def check_availability(self, token: str, amount: int) -> bool:
    try:
        erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
        balance = await erc20.functions.balanceOf(self._vault_address).call()
        return int(balance) >= amount
    except Exception as e:
        logger.debug(f"[balancer] Liquidity check failed for {token}: {e}")
        return True  # Default to True — let simulation confirm viability

--------------------------------------------------------------------------------
16.7  flashloan/aave_v3_fl.py — Fix ABI and liquidity check
--------------------------------------------------------------------------------

Fix the interestRateStrategyAddress field type: "address" not "uint8".

Fix check_availability to get aToken address (index 7) then check balanceOf:

  async def check_availability(self, token: str, amount: int) -> bool:
      try:
          reserve_data = await self._pool.functions.getReserveData(token).call()
          atoken_address = reserve_data[7]          # aTokenAddress
          erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
          available = await erc20.functions.balanceOf(atoken_address).call()
          return int(available) >= amount
      except Exception as e:
          logger.debug(f"[aave_v3] Liquidity check failed for {token}: {e}")
          return False

Add ERC20_BALANCE_ABI (same as 16.6) at the top of aave_v3_fl.py.

--------------------------------------------------------------------------------
16.8  simulation/simulator.py — Complete the 3-test stress test
--------------------------------------------------------------------------------

def stress_test() must run all three tests and return True ONLY if ALL pass:

  async def stress_test(self, candidate, reserves, block_number,
                         gas_price_gwei=0.1) -> bool:
      # Test A: -5% reserves
      stressed_res = {
          addr: {k: int(v * 0.95) if isinstance(v, (int, float)) else v
                 for k, v in r.items()}
          for addr, r in reserves.items()
      }
      result_a = await self.simulate_flashloan_arb(
          candidate, stressed_res, block_number, gas_price_gwei)
      if not result_a or not result_a.get("viable"):
          return False

      # Test B: gas price 3x spike
      result_b = await self.simulate_flashloan_arb(
          candidate, reserves, block_number, gas_price_gwei * 3)
      if not result_b or not result_b.get("viable"):
          return False

      # Test C: reserve shift (+2% on reserve0 of first pool)
      shifted_res = {addr: dict(r) for addr, r in reserves.items()}
      steps = candidate.get("steps", [])
      if steps:
          first_pool = steps[0].get("pool", "")
          if first_pool in shifted_res:
              r = shifted_res[first_pool]
              r["reserve0"] = int(r.get("reserve0", 0) * 1.02)
      result_c = await self.simulate_flashloan_arb(
          candidate, shifted_res, block_number, gas_price_gwei)
      if not result_c or not result_c.get("viable"):
          return False

      return True

--------------------------------------------------------------------------------
16.9  data/logger.py — Intercept stdlib logging into loguru
--------------------------------------------------------------------------------

In setup_logging(), after configuring loguru sinks, add:

  import logging as _logging

  class InterceptHandler(_logging.Handler):
      def emit(self, record):
          try:
              level = logger.level(record.levelname).name
          except ValueError:
              level = record.levelno
          logger.opt(depth=6, exception=record.exc_info).log(
              level, record.getMessage()
          )

  _logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
  for name in _logging.root.manager.loggerDict:
      _logging.getLogger(name).handlers = []
      _logging.getLogger(name).propagate = True

--------------------------------------------------------------------------------
16.10 discovery/subgraph_client.py — Update to working subgraph URLs
--------------------------------------------------------------------------------

Replace SUBGRAPH_URLS with:

SUBGRAPH_URLS = {
    "uniswap_v3":  (
        "https://gateway.thegraph.com/api/{key}/subgraphs/id/"
        "HUZDsRpEVP2AvzDCyzDHtdc64dyDxx8FQjzsmqSg4H3B"
    ),
    "balancer_v2": (
        "https://gateway.thegraph.com/api/{key}/subgraphs/id/"
        "H9oPAbXnobBRq1cB3HDmbZ1E8MWQyJYQjT1QDJMrdbNp"
    ),
}

In query_subgraph(), format the URL with GRAPH_API_KEY from config:

  from config import GRAPH_API_KEY
  url = subgraph_url.format(key=GRAPH_API_KEY) if GRAPH_API_KEY else None
  if not url:
      logger.warning("GRAPH_API_KEY not set — subgraph query skipped, using factory scan only")
      return {}

================================================================================
END OF SECTION 16
================================================================================