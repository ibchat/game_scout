"""
Wishlist Import Task - Import verified wishlist data from CSV
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, GameSource
from apps.db.models_narrative import WishlistData, WishlistMode
from sqlalchemy import select
import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.import_wishlist.import_wishlist_csv")
def import_wishlist_csv(csv_filepath: str, source: str = "steam"):
    """
    Импорт wishlist данных из CSV файла
    
    CSV Format:
    - Steam: appid, wishlist_count, date
    - Itch.io: game_id, wishlist_count, date
    
    Args:
        csv_filepath: Path to CSV file in /mnt/user-data/uploads
        source: "steam" or "itch"
    """
    logger.info(f"📊 Importing wishlist data from {csv_filepath}")
    
    results = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0
    }
    
    try:
        db = get_db_session()
        
        try:
            csv_path = Path(csv_filepath)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_filepath}")
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        if source == "steam":
                            game_id = row.get("appid") or row.get("app_id")
                            wishlist_count = int(row.get("wishlist_count") or row.get("wishlists") or 0)
                            date_str = row.get("date") or datetime.utcnow().isoformat()
                        else:  # itch
                            game_id = row.get("game_id") or row.get("id")
                            wishlist_count = int(row.get("wishlist_count") or row.get("wishlists") or 0)
                            date_str = row.get("date") or datetime.utcnow().isoformat()
                        
                        if not game_id:
                            results["skipped"] += 1
                            continue
                        
                        # Найти игру в базе
                        stmt = select(Game).where(
                            Game.source == GameSource[source],
                            Game.source_id == str(game_id)
                        )
                        game = db.execute(stmt).scalar_one_or_none()
                        
                        if not game:
                            logger.warning(f"Game not found: {source} {game_id}")
                            results["skipped"] += 1
                            continue
                        
                        # Парсим дату
                        try:
                            import_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        except:
                            import_date = datetime.utcnow()
                        
                        # Проверяем существующую запись
                        stmt = select(WishlistData).where(
                            WishlistData.game_id == game.id,
                            WishlistData.date >= import_date.replace(hour=0, minute=0, second=0),
                            WishlistData.date < import_date.replace(hour=23, minute=59, second=59)
                        )
                        existing = db.execute(stmt).scalar_one_or_none()
                        
                        if existing:
                            # Обновляем
                            existing.wishlist_count = wishlist_count
                            existing.mode = WishlistMode.verified
                            existing.confidence = "high"
                            existing.verified_source = "csv_import"
                            existing.verified_at = datetime.utcnow()
                            results["updated"] += 1
                        else:
                            # Создаём новую запись
                            wishlist_data = WishlistData(
                                game_id=game.id,
                                date=import_date,
                                mode=WishlistMode.verified,
                                confidence="high",
                                wishlist_count=wishlist_count,
                                verified_source="csv_import",
                                verified_at=datetime.utcnow(),
                                estimation_metadata={"imported_from": csv_filepath}
                            )
                            db.add(wishlist_data)
                            results["imported"] += 1
                        
                        logger.info(f"  ✅ {game.title}: {wishlist_count:,} wishlists")
                        
                    except Exception as e:
                        logger.error(f"Failed to import row: {row}, error: {e}")
                        results["errors"] += 1
                        continue
            
            db.commit()
            
            logger.info(f"✅ Import complete! Imported: {results['imported']}, Updated: {results['updated']}")
            
            return {
                "status": "success",
                "results": results
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def generate_sample_csv(output_path: str, source: str = "steam"):
    """Генерация примера CSV файла для импорта"""
    
    if source == "steam":
        header = ["appid", "wishlist_count", "date"]
        sample_data = [
            ["1091500", "150000", "2026-01-07"],  # Cyberpunk
            ["1245620", "89000", "2026-01-07"],   # Elden Ring
            ["2379780", "45000", "2026-01-07"]    # Baldur's Gate 3
        ]
    else:  # itch
        header = ["game_id", "wishlist_count", "date"]
        sample_data = [
            ["our-life", "5000", "2026-01-07"],
            ["anxiety", "3000", "2026-01-07"],
            ["holocure", "12000", "2026-01-07"]
        ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(sample_data)
    
    logger.info(f"✅ Sample CSV created: {output_path}")
