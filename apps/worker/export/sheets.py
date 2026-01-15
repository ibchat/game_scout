import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.orm import Session
from sqlalchemy import select
from apps.db.models import TrendsDaily, Pitch, PitchScore
from datetime import date
import logging
import json
import base64
import os

logger = logging.getLogger(__name__)


def get_google_sheets_client():
    """Get authenticated Google Sheets client"""
    # Decode service account JSON from base64 env var
    service_account_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
    if not service_account_b64:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 not set")
    
    service_account_json = base64.b64decode(service_account_b64).decode('utf-8')
    service_account_info = json.loads(service_account_json)
    
    # Create credentials
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
    )
    
    client = gspread.authorize(credentials)
    return client


def export_trends_sheet(db: Session, spreadsheet_id: str, target_date: date = None):
    """Export trends to Google Sheets"""
    if target_date is None:
        target_date = date.today()
    
    # Query trends
    stmt = select(TrendsDaily).where(
        TrendsDaily.date == target_date
    ).order_by(TrendsDaily.velocity.desc())
    
    trends = db.execute(stmt).scalars().all()
    
    if not trends:
        logger.warning(f"No trends found for {target_date}")
        return
    
    # Prepare data
    headers = ["Date", "Signal", "Type", "Count", "Avg 7D", "Delta 7D", "Velocity"]
    rows = [headers]
    
    for trend in trends:
        rows.append([
            str(trend.date),
            trend.signal,
            trend.signal_type.value,
            trend.count,
            float(trend.avg_7d),
            float(trend.delta_7d),
            float(trend.velocity)
        ])
    
    # Write to sheet
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    
    try:
        worksheet = spreadsheet.worksheet("Trends")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Trends", rows=1000, cols=10)
    
    # Clear and update
    worksheet.clear()
    worksheet.update('A1', rows)
    
    logger.info(f"Exported {len(trends)} trends to Google Sheets")


def export_pitches_sheet(db: Session, spreadsheet_id: str):
    """Export pitches to Google Sheets"""
    # Query pitches with scores
    stmt = select(Pitch).join(
        PitchScore, Pitch.id == PitchScore.pitch_id, isouter=True
    ).order_by(Pitch.created_at.desc())
    
    pitches = db.execute(stmt).scalars().all()
    
    if not pitches:
        logger.warning("No pitches found")
        return
    
    # Prepare data
    headers = [
        "Created", "Dev Name", "Email", "Team Size", "Released Before",
        "Timeline (months)", "Score", "Verdict", "Top Trends",
        "Top Comparables", "Why Yes", "Why No", "Next Step", "Links"
    ]
    rows = [headers]
    
    for pitch in pitches:
        # Get top trend matches (from tags)
        top_trends = ", ".join(pitch.tags[:3]) if pitch.tags else ""
        
        # Format links
        links = []
        if pitch.video_link:
            links.append(f"Video: {pitch.video_link}")
        if pitch.build_link:
            links.append(f"Build: {pitch.build_link}")
        links_str = " | ".join(links)
        
        row = [
            str(pitch.created_at),
            pitch.dev_name,
            pitch.email,
            pitch.team_size,
            "Yes" if pitch.released_before else "No",
            pitch.timeline_months,
        ]
        
        if pitch.score:
            row.extend([
                pitch.score.score_total,
                pitch.score.verdict.value,
                top_trends,
                ", ".join([c["name"] for c in pitch.score.comparables[:3]]),
                " | ".join(pitch.score.why_yes),
                " | ".join(pitch.score.why_no),
                pitch.score.next_step or "",
                links_str
            ])
        else:
            row.extend(["", "", top_trends, "", "", "", "", links_str])
        
        rows.append(row)
    
    # Write to sheet
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    
    try:
        worksheet = spreadsheet.worksheet("Pitches")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Pitches", rows=1000, cols=20)
    
    # Clear and update
    worksheet.clear()
    worksheet.update('A1', rows)
    
    logger.info(f"Exported {len(pitches)} pitches to Google Sheets")


def export_to_google_sheets(db: Session, spreadsheet_id: str):
    """Export both trends and pitches to Google Sheets"""
    try:
        export_trends_sheet(db, spreadsheet_id)
        export_pitches_sheet(db, spreadsheet_id)
        return True
    except Exception as e:
        logger.error(f"Failed to export to Google Sheets: {e}")
        return False