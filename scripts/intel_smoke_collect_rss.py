#!/usr/bin/env python3
"""
Intel RSS Collector Smoke Test
Creates test source and collects RSS items, verifies they are saved to DB.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource, IntelRawItem
from apps.intel.services.collectors.rss_collector import RSSCollector

# Test RSS feed (Steam RSS)
TEST_RSS_URL = "https://store.steampowered.com/feeds/news.xml"


def main():
    """Run smoke test"""
    db = SessionLocal()
    
    try:
        # Get or create test source
        source = db.query(IntelSource).filter(
            IntelSource.name == "Steam RSS test"
        ).first()
        
        if not source:
            source = IntelSource(
                type="rss",
                name="Steam RSS test",
                url=TEST_RSS_URL,
                is_enabled=True
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            print(f"Created test source: {source.id}")
        else:
            print(f"Using existing source: {source.id}")
        
        # Get initial count
        initial_count = db.query(IntelRawItem).count()
        print(f"Initial intel_raw_items count: {initial_count}")
        
        # Create collector and collect
        collector = RSSCollector(db=db)
        saved_count = collector.collect_source(source)
        
        # Get final count
        final_count = db.query(IntelRawItem).count()
        new_items = final_count - initial_count
        
        print(f"COLLECTED: {saved_count} new items")
        print(f"TOTAL: {final_count} items in database")
        print(f"NEW: {new_items} items added")
        
        # Verify
        if saved_count > 0:
            print("✅ SUCCESS: Items were collected and saved")
            return 0
        elif new_items == 0 and initial_count > 0:
            print("✅ SUCCESS: Idempotency check passed (no duplicates added)")
            return 0
        else:
            print("❌ FAILED: No items were collected")
            return 1
            
    except Exception as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
