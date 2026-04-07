import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    # RPC — FREE-TIER MAX ROTATION
    "rpc_primary": os.getenv("RPC_PRIMARY", "https://base.drpc.org"),
    "rpc_ws_primary": os.getenv("RPC_WS_PRIMARY", "wss://base.drpc.org"),
    "rpc_fallbacks": [
        "https://base-mainnet.g.alchemy.com/v2/" + os.getenv("ALCHEMY_KEY", ""),
        "https://rpc.ankr.com/base",
        "https://1rpc.io/base",
    ],
    "rpc_ws_fallbacks": [
        "wss://base-mainnet.g.alchemy.com/v2/" + os.getenv("ALCHEMY_KEY", ""),
    ],
    "rpc_max_calls_sec": 20,          # dRPC safe limit
    "multicall_batch": 80,            # REDUCED for free-tier safety
    "scan_poll_interval_sec": 30,     # fallback if WS drops

    # Scanner thresholds (tightened for free tier)
    "min_profit_usd": 0.50,
    "min_pool_tvl_usd": 10000,        # higher filter to reduce load
    "max_price_impact": 0.02,
    "max_borrow_pct": 0.30,
    "gas_safety_buffer": 1.25,
    "max_hops": 3,                    # start with 3 to reduce compute

    # Addresses (exact)
    "multicall3": "0xcA11bde05977b3631167028862bE2a173976CA11",
    "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "aave_v3_pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",

    # Free-tier flags
    "free_tier_mode": True,
    "use_mempool_filter": False,

    # Alerts
    "telegram_alert_threshold_usd": 1.00,
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
}

# Convenience constants (used throughout the codebase)
MIN_PROFIT_USD = CONFIG["min_profit_usd"]
MIN_POOL_TVL_USD = CONFIG["min_pool_tvl_usd"]
MAX_PRICE_IMPACT = CONFIG["max_price_impact"]
MAX_BORROW_PCT = CONFIG["max_borrow_pct"]
GAS_SAFETY_BUFFER = CONFIG["gas_safety_buffer"]
MAX_HOPS = CONFIG["max_hops"]
MULTICALL_BATCH = CONFIG["multicall_batch"]
RPC_MAX_CALLS_SEC = CONFIG["rpc_max_calls_sec"]
SCAN_POLL_INTERVAL_SEC = CONFIG["scan_poll_interval_sec"]

# Core token addresses on Base
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDT = "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"

MAJOR_TOKENS = {WETH.lower(), USDC.lower(), USDT.lower()}

# DEX factory addresses on Base
UNISWAP_V3_FACTORY = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
SUSHISWAP_V3_FACTORY = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
AERODROME_FACTORY = "0x5C3F18F06CC09CA1910767A34a20F771039E37C0"
PANCAKESWAP_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
CURVE_REGISTRY_BASE = "0x5ffe7FB82894076ECB99A30D6A32e969e6e35E98"
BALANCER_VAULT = CONFIG["balancer_vault"]

# Flash-loan sources (priority order: Balancer first, then Aave V3)
FL_SOURCES = [
    {"name": "balancer", "address": BALANCER_VAULT, "fee_rate": 0.00},
    {"name": "aave_v3", "address": CONFIG["aave_v3_pool"], "fee_rate": 0.0005},
]

# BUG 1 FIX: Module-level constant for AAVE_V3_POOL
AAVE_V3_POOL = CONFIG["aave_v3_pool"]

# Gas estimates on Base (from masterplan SECTION 9)
GAS_ESTIMATES = {
    "2_hop_arb"       : 200_000,
    "3_hop_arb"       : 325_000,
    "4_hop_arb"       : 450_000,
    "fl_balancer"     : 50_000,
    "fl_aave_v3"      : 70_000,
}

# Discovery interval (seconds)
DISCOVERY_INTERVAL_SEC = 300  # 5 minutes

# Health check interval (seconds)
HEALTH_CHECK_INTERVAL_SEC = 15  # free-tier: every 15 seconds

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "scanner.db")

# CSV export path
CSV_EXPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "opportunities.csv")

# Pre-seeded known high-TVL pools for immediate scanner availability
SEED_POOLS = [
    {
        "address": "0xd0b53D9277642d899DF5C87A3966A349A798F224",
        "token0": WETH,
        "token1": USDC,
        "fee": 500,
        "dex": "uniswap_v3",
        "type": "v3",
        "tvl_usd": 50_000_000,
    },
    {
        "address": "0x4C36388bE6F416A29C8d8Eee81C771cE6bE14B18",
        "token0": WETH,
        "token1": USDC,
        "fee": 3000,
        "dex": "uniswap_v3",
        "type": "v3",
        "tvl_usd": 10_000_000,
    },
]
