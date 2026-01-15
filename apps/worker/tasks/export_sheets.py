from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.export.sheets import export_to_google_sheets
from apps.worker.export.csv_export import export_trends_csv, export_pitches_csv
from datetime import date
import logging
import os

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.export_sheets.export_sheets_task")
def export_sheets_task():
    """Export data to Google Sheets or CSV - runs daily"""
    logger.info("Starting export task")
    
    db = get_db_session()
    today = date.today()
    
    try:
        # Check if Google Sheets is enabled
        sheets_enabled = os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
        
        if sheets_enabled:
            spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
            
            if not spreadsheet_id:
                logger.error("GOOGLE_SHEETS_SPREADSHEET_ID not set")
                return {"status": "error", "error": "missing_spreadsheet_id"}
            
            logger.info(f"Exporting to Google Sheets: {spreadsheet_id}")
            success = export_to_google_sheets(db, spreadsheet_id)
            
            if success:
                return {"status": "success", "method": "google_sheets", "date": str(today)}
            else:
                # Fallback to CSV
                logger.warning("Google Sheets export failed, falling back to CSV")
                sheets_enabled = False
        
        if not sheets_enabled:
            # Export to CSV
            export_dir = os.getenv("EXPORT_CSV_DIR", "/data/exports")
            logger.info(f"Exporting to CSV: {export_dir}")
            
            trends_file = export_trends_csv(db, export_dir, today)
            pitches_file = export_pitches_csv(db, export_dir, today)
            
            return {
                "status": "success",
                "method": "csv",
                "files": {
                    "trends": trends_file,
                    "pitches": pitches_file
                },
                "date": str(today)
            }
    
    except Exception as e:
        logger.error(f"Export task failed: {e}")
        return {"status": "error", "error": str(e)}
    
    finally:
        db.close()