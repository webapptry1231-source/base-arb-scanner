import os
import json
import sqlite3
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from config import DB_PATH, CSV_EXPORT_PATH

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for logging all simulation results."""

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def initialize(self):
        """Initialize the database and create tables if they don't exist."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._loop = asyncio.get_event_loop()
        await self._create_tables()
        logger.info(f"Database initialized at {self._db_path}")

    async def _create_tables(self):
        """Create all required tables."""
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                rpc_provider TEXT NOT NULL DEFAULT '',
                rpc_latency_ms REAL NOT NULL DEFAULT 0,
                estimated_cu_used REAL NOT NULL DEFAULT 0,
                route_type TEXT NOT NULL,
                path TEXT NOT NULL,
                dexes TEXT NOT NULL,
                pools TEXT NOT NULL,
                borrow_amount REAL NOT NULL,
                borrow_token TEXT NOT NULL,
                fl_source TEXT NOT NULL,
                fl_fee_usd REAL NOT NULL,
                gross_profit_usd REAL NOT NULL,
                swap_fees_usd REAL NOT NULL,
                gas_used INTEGER NOT NULL,
                gas_cost_usd REAL NOT NULL,
                net_profit_usd REAL NOT NULL,
                net_after_25pct_buffer REAL NOT NULL DEFAULT 0,
                slippage_applied REAL NOT NULL,
                survived_blocks INTEGER DEFAULT 0,
                simulation_pass INTEGER DEFAULT 0,
                stress_test_pass INTEGER DEFAULT 0,
                false_positive_flags TEXT DEFAULT '[]',
                free_tier_throttled INTEGER DEFAULT 0,
                log_uuid TEXT DEFAULT '',
                raw_json TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                route_type TEXT,
                path TEXT,
                dexes TEXT,
                borrow_amount REAL,
                borrow_token TEXT,
                net_profit_usd REAL,
                viable INTEGER DEFAULT 0,
                raw_json TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_block
            ON opportunities(block_number)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_simulations_block
            ON simulations(block_number)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_profit
            ON opportunities(net_profit_usd)
        """)

        self._conn.commit()

    async def log_opportunity(self, result: Dict[str, Any]):
        """Log a confirmed profitable opportunity."""
        if not self._conn:
            await self.initialize()

        candidate = result.get("candidate", {})
        path = candidate.get("path", result.get("path", []))
        dexes = candidate.get("dexes", result.get("dexes", []))
        pools = candidate.get("pools", result.get("pools", []))
        fl_source = result.get("fl_source", {})

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "block_number": result.get("block_number", 0),
            "rpc_provider": result.get("rpc_provider", "unknown"),
            "rpc_latency_ms": result.get("rpc_latency_ms", 0),
            "estimated_cu_used": result.get("estimated_cu_used", 0),
            "route_type": candidate.get("type", "unknown"),
            "path": json.dumps(path),
            "dexes": json.dumps(dexes),
            "pools": json.dumps(pools),
            "borrow_amount": result.get("borrow_amount", 0),
            "borrow_token": candidate.get("token_in", ""),
            "fl_source": fl_source.get("name", "unknown"),
            "fl_fee_usd": result.get("fl_fee_usd", 0),
            "gross_profit_usd": result.get("gross_profit_usd", 0),
            "swap_fees_usd": result.get("swap_fees_usd", 0),
            "gas_used": result.get("gas_used", 0),
            "gas_cost_usd": result.get("gas_cost_usd", 0),
            "net_profit_usd": result.get("net_profit_usd", 0),
            "net_after_25pct_buffer": result.get("net_after_25pct_buffer", 0),
            "slippage_applied": result.get("slippage_applied", 0),
            "survived_blocks": result.get("survived_blocks", 0),
            "simulation_pass": 1 if result.get("simulation_pass") else 0,
            "stress_test_pass": 1 if result.get("stress_test_pass") else 0,
            "false_positive_flags": json.dumps(result.get("false_positive_flags", [])),
            "free_tier_throttled": 1 if result.get("free_tier_throttled") else 0,
            "log_uuid": result.get("log_uuid", ""),
            "raw_json": json.dumps(result),
        }

        def _insert():
            self._conn.execute("""
                INSERT INTO opportunities (
                    timestamp, block_number, rpc_provider, rpc_latency_ms, estimated_cu_used,
                    route_type, path, dexes, pools,
                    borrow_amount, borrow_token, fl_source, fl_fee_usd,
                    gross_profit_usd, swap_fees_usd, gas_used, gas_cost_usd,
                    net_profit_usd, net_after_25pct_buffer, slippage_applied, survived_blocks,
                    simulation_pass, stress_test_pass, false_positive_flags,
                    free_tier_throttled, log_uuid, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["timestamp"], row["block_number"], row["rpc_provider"],
                row["rpc_latency_ms"], row["estimated_cu_used"],
                row["route_type"], row["path"], row["dexes"], row["pools"],
                row["borrow_amount"], row["borrow_token"], row["fl_source"],
                row["fl_fee_usd"], row["gross_profit_usd"], row["swap_fees_usd"],
                row["gas_used"], row["gas_cost_usd"], row["net_profit_usd"],
                row["net_after_25pct_buffer"], row["slippage_applied"], row["survived_blocks"],
                row["simulation_pass"], row["stress_test_pass"], row["false_positive_flags"],
                row["free_tier_throttled"], row["log_uuid"], row["raw_json"],
            ))
            self._conn.commit()

        await self._loop.run_in_executor(None, _insert)

    async def log_simulation(self, result: Dict[str, Any]):
        """Log any simulation result (profitable or not)."""
        if not self._conn:
            await self.initialize()

        candidate = result.get("candidate", {})

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "block_number": result.get("block_number", 0),
            "route_type": candidate.get("type", "unknown"),
            "path": json.dumps(candidate.get("path", [])),
            "dexes": json.dumps(candidate.get("dexes", [])),
            "borrow_amount": result.get("borrow_amount", 0),
            "borrow_token": candidate.get("token_in", ""),
            "net_profit_usd": result.get("net_profit_usd", 0),
            "viable": 1 if result.get("viable") else 0,
            "raw_json": json.dumps(result),
        }

        def _insert():
            self._conn.execute("""
                INSERT INTO simulations (
                    timestamp, block_number, route_type, path, dexes,
                    borrow_amount, borrow_token, net_profit_usd, viable, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["timestamp"], row["block_number"], row["route_type"],
                row["path"], row["dexes"], row["borrow_amount"],
                row["borrow_token"], row["net_profit_usd"], row["viable"],
                row["raw_json"],
            ))
            self._conn.commit()

        await self._loop.run_in_executor(None, _insert)

    async def get_opportunities(
        self,
        limit: int = 100,
        min_profit: float = 0,
    ) -> List[Dict[str, Any]]:
        """Query logged opportunities."""
        if not self._conn:
            await self.initialize()

        def _query():
            cursor = self._conn.execute(
                "SELECT * FROM opportunities WHERE net_profit_usd >= ? ORDER BY block_number DESC LIMIT ?",
                (min_profit, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

        return await self._loop.run_in_executor(None, _query)

    async def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if not self._conn:
            await self.initialize()

        def _query():
            cursor = self._conn.execute("""
                SELECT
                    COUNT(*) as total_simulations,
                    SUM(CASE WHEN viable = 1 THEN 1 ELSE 0 END) as viable_count,
                    AVG(net_profit_usd) as avg_profit,
                    MAX(net_profit_usd) as max_profit,
                    MIN(net_profit_usd) as min_profit
                FROM simulations
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}

        return await self._loop.run_in_executor(None, _query)

    async def export_csv(self, path: str = CSV_EXPORT_PATH):
        """Export all opportunities to CSV."""
        import pandas as pd

        if not self._conn:
            await self.initialize()

        def _query():
            df = pd.read_sql_query("SELECT * FROM opportunities", self._conn)
            return df

        df = await self._loop.run_in_executor(None, _query)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path, index=False)
        logger.info(f"Exported {len(df)} opportunities to {path}")

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            logger.info("Database connection closed")
