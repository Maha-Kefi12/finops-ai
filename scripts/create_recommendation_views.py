"""
Create PostgreSQL views for easier recommendation data retrieval
Provides denormalized views for common queries
"""

from src.storage.database import SessionLocal, engine
import logging

logger = logging.getLogger(__name__)

def create_views():
    """Create recommendation history and analytics views."""
    
    sql_statements = [
        # View 1: Recent recommendation snapshots with summary stats
        """
        CREATE OR REPLACE VIEW v_recommendation_history AS
        SELECT 
            id,
            architecture_id,
            architecture_name,
            status,
            source,
            card_count,
            engine_card_count,
            llm_card_count,
            total_savings_monthly,
            generation_time_ms,
            llm_model,
            created_at,
            error_message,
            ROW_NUMBER() OVER (
                PARTITION BY architecture_id 
                ORDER BY created_at DESC
            ) as rec_sequence
        FROM rec_snapshots
        WHERE status = 'completed'
        ORDER BY created_at DESC;
        """,
        
        # View 2: Architecture recommendation statistics
        """
        CREATE OR REPLACE VIEW v_architecture_rec_stats AS
        SELECT 
            architecture_id,
            COUNT(*) as total_snapshots,
            COUNT(CASE WHEN source = 'engine' THEN 1 END) as engine_only_snapshots,
            COUNT(CASE WHEN source = 'llm' THEN 1 END) as llm_only_snapshots,
            COUNT(CASE WHEN source = 'both' THEN 1 END) as both_sources_snapshots,
            SUM(card_count) as total_recommendations,
            AVG(card_count) as avg_cards_per_snapshot,
            SUM(engine_card_count) as total_engine_cards,
            SUM(llm_card_count) as total_llm_cards,
            SUM(total_savings_monthly) as total_savings_accumulated,
            AVG(total_savings_monthly) as avg_savings_per_snapshot,
            AVG(generation_time_ms) as avg_generation_time_ms,
            MIN(created_at) as first_recommendation,
            MAX(created_at) as last_recommendation
        FROM rec_snapshots
        WHERE status = 'completed'
        GROUP BY architecture_id;
        """,
        
        # View 3: Recent engine vs LLM comparison
        """
        CREATE OR REPLACE VIEW v_engine_vs_llm_comparison AS
        SELECT 
            architecture_id,
            source,
            COUNT(*) as snapshot_count,
            SUM(card_count) as total_cards,
            SUM(engine_card_count) as engine_cards,
            SUM(llm_card_count) as llm_cards,
            AVG(total_savings_monthly) as avg_savings,
            MAX(created_at) as most_recent
        FROM rec_snapshots
        WHERE status = 'completed'
        GROUP BY architecture_id, source
        ORDER BY architecture_id, source;
        """,
        
        # View 4: Top performing recommendations (by savings)
        """
        CREATE OR REPLACE VIEW v_top_recommendations AS
        SELECT 
            architecture_id,
            architecture_name,
            source,
            card_count,
            total_savings_monthly,
            creation_time_ms,
            created_at,
            RANK() OVER (
                PARTITION BY architecture_id 
                ORDER BY total_savings_monthly DESC
            ) as savings_rank
        FROM rec_snapshots
        WHERE status = 'completed'
        ORDER BY architecture_id, savings_rank;
        """,
    ]
    
    with engine.connect() as connection:
        for i, sql in enumerate(sql_statements, 1):
            try:
                connection.execute(sql)
                connection.commit()
                logger.info(f"Successfully created view {i}/4")
            except Exception as e:
                logger.error(f"Error creating view {i}/4: {e}")
                connection.rollback()
                raise

    logger.info("All recommendation views created successfully")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_views()
