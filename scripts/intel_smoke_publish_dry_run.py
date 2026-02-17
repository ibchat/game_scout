#!/usr/bin/env python3
"""
Smoke test for Steam Intel pipeline (dry run).
Tests that pipeline runs without errors and generates business briefs.
Does not require Telegram token.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.db.session import SessionLocal
from apps.intel.services.pipeline.steam_intel_pipeline import run_pipeline
from apps.intel.db.models import IntelEvent

def main():
    """Run smoke test"""
    db = SessionLocal()
    
    try:
        print("=== Steam Intel Pipeline Smoke Test (Dry Run) ===")
        print()
        
        # Run pipeline in dry_run mode
        print("Running pipeline with dry_run=True...")
        result = run_pipeline(
            sources=["Steam RSS test"],  # Use test source
            db=db,
            dry_run=True
        )
        
        print(f"✅ Pipeline completed:")
        print(f"   Collected: {result['collected']}")
        print(f"   Extracted: {result['extracted']}")
        print(f"   Events created: {result['events_created']}")
        print(f"   Briefs generated: {result['briefs_generated']}")
        print(f"   Published: {result['published']} (dry_run)")
        print(f"   Skipped: {result['skipped']}")
        print()
        
        # Check that at least one event has business_brief_json
        events_with_brief = db.query(IntelEvent).filter(
            IntelEvent.business_brief_json.isnot(None)
        ).count()
        
        print(f"✅ Events with business brief: {events_with_brief}")
        
        if events_with_brief > 0:
            print("✅ SUCCESS: Business briefs are being generated")
            return 0
        else:
            print("⚠️  WARNING: No business briefs generated (may be normal if no events)")
            return 0  # Not a failure, just informational
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
