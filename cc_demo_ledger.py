"""Closed paper trades for the Capital Connect Binance demo."""

class PaperLedger:
    def __init__(self, database_url):
        from psycopg import connect
        from psycopg.types.json import Jsonb

        self.database_url = database_url
        self.connect = connect
        self.jsonb = Jsonb

    def restore(self):
        with self.connect(self.database_url, connect_timeout=3) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS cc_binance_demo_v2_closed_trades (
                    sequence bigint GENERATED ALWAYS AS IDENTITY,
                    trade_id uuid PRIMARY KEY,
                    trade jsonb NOT NULL,
                    realized_pnl double precision NOT NULL
                )
            """)
            rows = db.execute("""
                SELECT trade, realized_pnl
                FROM cc_binance_demo_v2_closed_trades
                ORDER BY sequence
            """).fetchall()
        return [trade for trade, _ in rows], sum(pnl for _, pnl in rows)

    def record(self, trade_id, trade, realized_pnl):
        with self.connect(self.database_url, connect_timeout=3) as db:
            # Keep the same close if a previous attempt committed before disconnecting.
            db.execute("""
                INSERT INTO cc_binance_demo_v2_closed_trades (trade_id, trade, realized_pnl)
                VALUES (%s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            """, (trade_id, self.jsonb(trade), realized_pnl))
